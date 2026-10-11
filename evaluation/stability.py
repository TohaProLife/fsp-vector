"""Locked synthetic B4 experiment, separate from programmatic correctness."""
from collections import Counter,defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics
from app.engines.assessment import create_form,public_form,grade_form
from app.engines.taxonomy import SPECIALIZATIONS,GRADES
from evaluation.responders import fixed_profiles,respond,digest

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL_ID="vector-synthetic-retest-v1"
LOCKED_SEED=2026100704
REPEATS=8


def pearson(xs,ys):
    if len(xs)!=len(ys) or len(xs)<2:return None
    mx=statistics.mean(xs);my=statistics.mean(ys)
    vx=sum((x-mx)**2 for x in xs);vy=sum((y-my)**2 for y in ys)
    if vx<=1e-15 or vy<=1e-15:return None
    return round(max(-1.,min(1.,sum((x-mx)*(y-my) for x,y in zip(xs,ys))/math.sqrt(vx*vy))),6)


def paired_metrics(pairs):
    if not pairs:return {"pairs":0,"agreement":None,"kappa":None,"mean_absolute_score_difference":None,"score_correlation":None,"confusion":{}}
    left=Counter(row[0]["category"] for row in pairs);right=Counter(row[1]["category"] for row in pairs);n=len(pairs)
    agreement=sum(a["category"]==b["category"] for a,b in pairs)/n
    expected=sum(left[key]*right[key] for key in left.keys()|right.keys())/n**2
    differences=[b["score"]-a["score"] for a,b in pairs]
    return {"pairs":n,"agreement":round(agreement,6),"expected_agreement":round(expected,6),"kappa":round((agreement-expected)/(1-expected),6) if expected<1-1e-15 else None,"mean_signed_score_difference":round(statistics.mean(differences),6),"mean_absolute_score_difference":round(statistics.mean(abs(value) for value in differences),6),"max_absolute_score_difference":round(max(abs(value) for value in differences),6),"score_correlation":pearson([a["score"] for a,b in pairs],[b["score"] for a,b in pairs]),"confusion":dict(sorted(Counter(a["category"]+" -> "+b["category"] for a,b in pairs).items()))}


def item_metrics(rows):
    # earned/rest are actual points; the target item is excluded at collection.
    values=[row["fraction"] for row in rows];rest=[row["rest"] for row in rows]
    variance=statistics.pvariance(values) if values else None
    rest_variance=statistics.pvariance(rest) if rest else None
    ordered=sorted(rows,key=lambda row:(row["rest"],row["profile"],row["repeat"]))
    count=min(len(rows)//2,max(1,math.floor(len(rows)*.27)))
    separation=statistics.mean(row["fraction"] for row in ordered[-count:])-statistics.mean(row["fraction"] for row in ordered[:count]) if count and rest_variance else None
    correlation=pearson(values,rest)
    flags=[]
    if variance is None or variance<=1e-15:flags.append("zero_item_variance")
    if rest_variance is None or rest_variance<=1e-15:flags.append("zero_rest_variance")
    if correlation is not None and correlation<0:flags.append("negative_corrected_correlation")
    if separation is not None and separation<=0:flags.append("nonpositive_upper_lower_separation")
    return {"responses":len(rows),"mean_fraction":round(statistics.mean(values),6) if values else None,"exact_correct_rate":round(statistics.mean(value>=.999999 for value in values),6) if values else None,"item_variance":round(variance,6) if variance is not None else None,"rest_variance":round(rest_variance,6) if rest_variance is not None else None,"corrected_item_rest_correlation":correlation,"upper_lower_group_count":count,"upper_lower_difference":round(separation,6) if separation is not None else None,"rest_ties":len(rest)-len(set(rest)),"flags":flags}


def _write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8",newline="\n")


def stability_evaluation():
    protocol=ROOT/"evaluation/ASSESSMENT-STABILITY-PROTOCOL.md"
    protocol_sha=hashlib.sha256(protocol.read_bytes()).hexdigest()
    attempts=[];form_hashes=[];definitions={};route_metrics={};all_pairs=[];kind_pairs=defaultdict(list);item_rows=defaultdict(list);profile_outcomes={};grade_pass_rates=defaultdict(dict)
    for spec_index,(spec,definition) in enumerate(SPECIALIZATIONS.items()):
        profiles=fixed_profiles(definition["competencies"]);definitions[spec]=profiles
        for grade_index,grade in enumerate(GRADES):
            route=spec+"/"+grade;exposure={};forms=[]
            for repeat in range(REPEATS):
                seed=LOCKED_SEED+(spec_index*4+grade_index)*100+repeat
                private=create_form(spec,grade,seed=seed,exposure=exposure);public=public_form(private)
                for item in private["items"]:
                    if item["slot"]=="short":exposure[item["family_id"]]=exposure.get(item["family_id"],0)+1
                forms.append((seed,private,public))
                form_hashes.append({"route":route,"repeat":repeat,"seed":seed,"public_form_sha256":digest(public)})
            route_pairs=[];kind_rows=defaultdict(list);unstable=[]
            for profile in profiles:
                results=[]
                for repeat,(seed,private,public) in enumerate(forms):
                    answers={item["id"]:respond(item,profile) for item in public["items"]}
                    result=grade_form(private,answers)
                    row={"route":route,"profile":profile["id"],"kind":profile["kind"],"repeat":repeat,"seed":seed,"public_answers_sha256":digest(answers),"score":result["score"],"category":result["confirmed_grade"] or "UNCONFIRMED","passed":result["passed"],"failed_floors":result["failed_floors"],"competencies":result["competencies"]}
                    attempts.append(row);results.append(row);kind_rows[profile["kind"]].append(row)
                    total=sum(feedback["earned_score"] for feedback in result["feedback"])
                    by_id={item["id"]:item for item in private["items"]}
                    for feedback in result["feedback"]:
                        item=by_id[feedback["item_id"]]
                        key=(route,item["competency"],item["slot"],item["family_id"])
                        item_rows[key].append({"fraction":feedback["earned_score"]/feedback["max_score"],"rest":total-feedback["earned_score"],"profile":profile["id"],"repeat":repeat})
                pairs=list(zip(results[::2],results[1::2]));route_pairs.extend(pairs);all_pairs.extend(pairs);kind_pairs[profile["kind"]].extend(pairs)
                categories=Counter(row["category"] for row in results)
                if len(categories)>1:unstable.append(profile["id"])
                profile_outcomes[route+"/"+profile["id"]]={"kind":profile["kind"],"categories":dict(categories),"pass_rate":sum(row["passed"] for row in results)/REPEATS,"mean_score":round(statistics.mean(row["score"] for row in results),6)}
                grade_pass_rates[(spec,profile["id"])][grade]=profile_outcomes[route+"/"+profile["id"]]["pass_rate"]
            route_metrics[route]={**paired_metrics(route_pairs),"profiles":len(profiles),"profiles_with_mixed_raw_assignments":unstable,"by_kind":{kind:{"administrations":len(rows),"pass_rate":round(statistics.mean(row["passed"] for row in rows),6),"mean_score":round(statistics.mean(row["score"] for row in rows),6)} for kind,rows in sorted(kind_rows.items())}}
    family_metrics=[{"route":key[0],"competency":key[1],"slot":key[2],"family":key[3],**item_metrics(rows)} for key,rows in sorted(item_rows.items())]
    nonmonotonic=[]
    for (spec,profile),rates in grade_pass_rates.items():
        for low,high in zip(GRADES,GRADES[1:]):
            if rates[high]>rates[low]:nonmonotonic.append({"specialization":spec,"profile":profile,"lower_grade":low,"higher_grade":high,"lower_pass_rate":rates[low],"higher_pass_rate":rates[high]})
    observation_path=ROOT/"data/evaluation/assessment-stability-observations.json"
    _write(observation_path,{"protocol_id":PROTOCOL_ID,"protocol_sha256":protocol_sha,"locked_seed":LOCKED_SEED,"origin":"PROJECT_AUTHORED_SYNTHETIC_BEHAVIOR_METHODS","human_participants":0,"profile_definitions":definitions,"forms":form_hashes,"attempts":attempts})
    flags=Counter(flag for row in family_metrics for flag in row["flags"])
    summary={"protocol_id":PROTOCOL_ID,"protocol_sha256":protocol_sha,"locked_seed":LOCKED_SEED,"distinct_forms":len(form_hashes),"profile_attempt_administrations":len(attempts),"item_responses":sum(len(rows) for rows in item_rows.values()),"fixed_profiles":sum(len(rows) for rows in definitions.values()),"repeats_per_route_profile":REPEATS,"overall":paired_metrics(all_pairs),"by_kind":{kind:paired_metrics(pairs) for kind,pairs in sorted(kind_pairs.items())},"route_profiles_with_mixed_raw_assignments":sum(len(row["profiles_with_mixed_raw_assignments"]) for row in route_metrics.values()),"item_family_groups":len(family_metrics),"item_flags":dict(flags),"undefined_item_rest_correlations":sum(row["corrected_item_rest_correlation"] is None for row in family_metrics),"nonmonotonic_grade_profile_comparisons":len(nonmonotonic),"observations_sha256":hashlib.sha256(observation_path.read_bytes()).hexdigest(),"report_path":"evaluation/reports/assessment-stability.json","observations_path":"data/evaluation/assessment-stability-observations.json","human_test_retest":"NOT_MEASURED","human_item_discrimination":"NOT_MEASURED","interpretation":"Fixed public-method profiles evaluated by ordinary grader. Behavior mixture/attention propensities are author assumptions, not learned human response probabilities; raw assignments do not use persisted prior-grade retention."}
    _write(ROOT/summary["report_path"],{"summary":summary,"routes":route_metrics,"profile_outcomes":profile_outcomes,"item_discrimination":family_metrics,"nonmonotonic_grade_flags":nonmonotonic,"limitations":["Repeated profile observations are dependent. No human-population significance or confidence claims.","Concept knowledge depends on the author review ledger; synthetic separation is not human semantic validity.","Different grade contracts may be non-monotonic under a limited method; flags are not proof of a bug.","Undefined variance is null; perfect controls are trivial correctness controls, not calibrated grade stability.","No thresholds/responders were tuned after the measured experiment."]})
    return summary


if __name__=="__main__":print(json.dumps(stability_evaluation(),ensure_ascii=False,indent=2))
