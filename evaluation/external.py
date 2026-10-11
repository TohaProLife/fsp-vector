"""Explicit immutable relevance labels, separate from the synthetic generator.

The loader verifies shape/identity/completeness, not the truth of a declaration
that humans independently labeled the corpus. It never invents a human pilot.
"""

import argparse
import hashlib
import json
import math
import random
import re
import statistics
import sys
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"services"/"api"))
from app.engines.matching import ALGORITHM_VERSION,admission,rank_candidates
from app.engines.taxonomy import GRADES,SPECIALIZATIONS,canonical_skill

SCHEMA_VERSION="vector-explicit-relevance-v1"
MAX_BYTES=20*1024*1024
MAX_PAIRS=20000
ID=re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}\Z")
NEED_FIELDS={"id","company_id","specialization","grade","grades","skills","required_skills","work_format","employment","salary_from","salary_to","must_have_mode","require_verified_skills","required_min_strength"}
CANDIDATE_FIELDS={"id","specialization","confirmed_grade","published","active","status","score","skills","evidence","preferences","assessment_at","blocked_companies","fsp"}
EVIDENCE_FIELDS={"skill","source","status","score","strength","scope","confirmed_at","objectively_graded","revoked"}
SCOPE_FIELDS={"specialization","grade","mode","grading","context","company_id","global_grade","blueprint_version","need_snapshot_sha256"}
PREFERENCE_FIELDS={"work_format","employment","salary_from","salary_to","strict_work_format","strict_employment","strict_salary"}
EVIDENCE_SOURCES={"ASSESSMENT_VERIFIED","PRACTICE_OBSERVED","NEED_PRACTICE_OBSERVED","SELF_DECLARED","COMPANY_REVIEWED","FSP_DEMO_CONFIRMED","FSP_REGISTRY_VERIFIED"}


def _fail(detail):
    raise ValueError("External relevance dataset: "+detail)


def _object_pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:_fail("duplicate JSON key")
        result[key]=value
    return result


def _text(value,label,maximum=100):
    if not isinstance(value,str) or len(value)>maximum or "@" in value:_fail(label+" must be a short anonymous string")


def _object(value,allowed,label,required=()):
    if not isinstance(value,dict) or set(value)-allowed or set(required)-set(value):_fail(label+" has missing/unknown fields")


def _id(value,label):
    if not isinstance(value,str) or not ID.fullmatch(value):_fail(label+" must be an opaque ID")


def _enum(value,allowed,label,nullable=False):
    if nullable and value is None:return
    if not isinstance(value,str) or value not in allowed:_fail("unsupported "+label)


def _list(value,label,maximum):
    if not isinstance(value,list) or len(value)>maximum:_fail(label+" must be a bounded list")


def _skills(value,label):
    _list(value,label,60)
    for skill in value:
        _text(skill,label,100)
        if not skill.strip():_fail(label+" contains an empty skill")


def _number(value,label,lo=0,hi=100,nullable=False):
    if nullable and value is None:return
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not lo<=value<=hi or not math.isfinite(value):_fail(label+" is outside its finite numeric range")


def _bool(value,label):
    if not isinstance(value,bool):_fail(label+" must be a boolean")


def _date(value,label):
    if value is None:return
    _text(value,label,60)
    try:datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError:_fail(label+" must be an ISO timestamp")


def _conditions(value,label):
    if "work_format" in value and value["work_format"] not in ("remote","hybrid","office","any","любой",None):_fail(label+" invalid work format")
    if "employment" in value and value["employment"] not in ("full_time","part_time","contract","any","любой",None):_fail(label+" invalid employment")
    for key in ("salary_from","salary_to"):
        if key in value:_number(value[key],label+"."+key,1,10000000,True)
    if value.get("salary_from") is not None and value.get("salary_to") is not None and value["salary_from"]>value["salary_to"]:_fail(label+" salary range is reversed")


def _fsp(value):
    _object(value,{"source","status","achievements"},"fsp")
    for key in ("source","status"):
        if value.get(key) is not None:_text(value[key],"fsp."+key)
    _list(value.get("achievements",[]),"fsp achievements",100)
    allowed={"event_id","protocol_id","title","discipline","specializations","date","place","participants","team","role","status","revoked"}
    for row in value.get("achievements",[]):
        _object(row,allowed,"fsp achievement")
        for key in ("event_id","protocol_id","title","discipline","role","status"):
            if row.get(key) is not None:_text(row[key],"achievement."+key,200)
        for key in ("place","participants"):
            if key in row:_number(row[key],"achievement."+key,1,1000000,True)
        for key in ("team","revoked"):
            if key in row:_bool(row[key],"achievement."+key)
        if "date" in row:_date(row["date"],"achievement.date")
        if "specializations" in row:
            _list(row["specializations"],"achievement.specializations",6)
            for spec in row["specializations"]:_enum(spec,SPECIALIZATIONS,"achievement specialization")


def validate_dataset(data):
    allowed={"schema_version","origin","human_labelers","corpus_origin","label_metadata","needs","candidates","queries","labels"}
    _object(data,allowed,"dataset",{"schema_version","origin","human_labelers","needs","candidates","queries","labels"})
    if data["schema_version"]!=SCHEMA_VERSION:_fail("unsupported schema_version")
    if data["origin"] not in ("external_human","external_programmatic","team_authored_explicit"):_fail("unknown label origin")
    count=data["human_labelers"]
    if isinstance(count,bool) or not isinstance(count,int) or not 0<=count<=1000:_fail("human_labelers must be an integer")
    if (data["origin"]=="external_human")!=(count>0):_fail("origin and declared human_labelers disagree")
    if "corpus_origin" in data:_text(data["corpus_origin"],"corpus_origin",200)
    if "label_metadata" in data:
        meta=data["label_metadata"]
        _object(meta,{"procedure","adjudication","blinded_to_scores","collected_at"},"label_metadata")
        for key in ("procedure","adjudication"):
            if key in meta:_text(meta[key],"label_metadata."+key,3000)
        if "blinded_to_scores" in meta:_bool(meta["blinded_to_scores"],"blinded_to_scores")
        if "collected_at" in meta:_date(meta["collected_at"],"collected_at")
    for field,maximum in (("needs",500),("candidates",5000),("queries",500),("labels",MAX_PAIRS)):_list(data[field],field,maximum)
    if not data["queries"]:_fail("at least one query is required")
    needs={};candidates={}
    for need in data["needs"]:
        _object(need,NEED_FIELDS,"need",{"id","specialization","grade","required_skills","skills"})
        _id(need["id"],"need id")
        if need["id"] in needs:_fail("duplicate need ID")
        _enum(need["specialization"],SPECIALIZATIONS,"need specialization");_enum(need["grade"],GRADES,"need grade")
        if "company_id" in need:_id(need["company_id"],"need company")
        if "grades" in need:
            _list(need["grades"],"need grades",4)
            if not need["grades"]:_fail("empty need grade list")
            for grade in need["grades"]:_enum(grade,GRADES,"need grade list")
        for key in ("skills","required_skills"):_skills(need[key],"need."+key)
        _conditions(need,"need")
        if "require_verified_skills" in need:_bool(need["require_verified_skills"],"require_verified_skills")
        if "required_min_strength" in need:_number(need["required_min_strength"],"required_min_strength",.5,1)
        if "must_have_mode" in need and need["must_have_mode"] not in ("verified","training_allowed"):_fail("unsupported must_have_mode")
        needs[need["id"]]=need
    for candidate in data["candidates"]:
        _object(candidate,CANDIDATE_FIELDS,"candidate",{"id","specialization","confirmed_grade","published"})
        _id(candidate["id"],"candidate id")
        if candidate["id"] in candidates:_fail("duplicate candidate ID")
        _enum(candidate["specialization"],SPECIALIZATIONS,"candidate specialization");_enum(candidate["confirmed_grade"],GRADES,"candidate grade",True)
        for key in ("published","active"):
            if key in candidate:_bool(candidate[key],"candidate."+key)
        if "score" in candidate:_number(candidate["score"],"candidate.score",nullable=True)
        if "status" in candidate:_text(candidate["status"],"candidate.status")
        if "skills" in candidate:_skills(candidate["skills"],"candidate.skills")
        if "assessment_at" in candidate:_date(candidate["assessment_at"],"assessment_at")
        if "blocked_companies" in candidate:
            _list(candidate["blocked_companies"],"blocked_companies",200)
            for company in candidate["blocked_companies"]:_id(company,"blocked company")
        if "preferences" in candidate:
            _object(candidate["preferences"],PREFERENCE_FIELDS,"preferences")
            _conditions(candidate["preferences"],"preferences")
            for key in ("strict_work_format","strict_employment","strict_salary"):
                if key in candidate["preferences"]:_bool(candidate["preferences"][key],key)
        if "fsp" in candidate:_fsp(candidate["fsp"])
        _list(candidate.get("evidence",[]),"evidence",100)
        for evidence in candidate.get("evidence",[]):
            _object(evidence,EVIDENCE_FIELDS,"evidence",{"skill","source"})
            _text(evidence["skill"],"evidence.skill")
            _enum(evidence["source"],EVIDENCE_SOURCES,"evidence source")
            if "score" in evidence:_number(evidence["score"],"evidence.score",nullable=True)
            if "strength" in evidence:_number(evidence["strength"],"evidence.strength",0,1,True)
            for key in ("objectively_graded","revoked"):
                if key in evidence:_bool(evidence[key],key)
            if "status" in evidence:_text(evidence["status"],"evidence.status")
            if "confirmed_at" in evidence:_date(evidence["confirmed_at"],"evidence.confirmed_at")
            if "scope" in evidence:
                scope=evidence["scope"]
                _object(scope,SCOPE_FIELDS,"evidence.scope")
                if "specialization" in scope:_enum(scope["specialization"],SPECIALIZATIONS,"evidence specialization",True)
                if "grade" in scope:_enum(scope["grade"],GRADES,"evidence grade",True)
                if "company_id" in scope:_id(scope["company_id"],"scope company")
                if "global_grade" in scope:_bool(scope["global_grade"],"global_grade")
                for key in ("mode","grading","context","blueprint_version","need_snapshot_sha256"):
                    if key in scope:_text(scope[key],"scope."+key)
        candidates[candidate["id"]]=candidate
    expected=set();query_need_ids=set()
    for query in data["queries"]:
        _object(query,{"need_id","candidate_ids"},"query",{"need_id","candidate_ids"})
        need_id=query["need_id"]
        _id(need_id,"query need")
        if need_id not in needs or need_id in query_need_ids:_fail("unknown/duplicate query need ID")
        query_need_ids.add(need_id)
        _list(query["candidate_ids"],"query candidates",200)
        for candidate_id in query["candidate_ids"]:_id(candidate_id,"query candidate")
        if len(set(query["candidate_ids"]))!=len(query["candidate_ids"]):_fail("duplicate query candidate ID")
        for candidate_id in query["candidate_ids"]:
            _id(candidate_id,"query candidate")
            if candidate_id not in candidates:_fail("unknown query candidate ID")
            expected.add((need_id,candidate_id))
        if len(expected)>MAX_PAIRS:_fail("too many query pairs")
    actual=set()
    for label in data["labels"]:
        _object(label,{"need_id","candidate_id","relevance"},"label",{"need_id","candidate_id","relevance"})
        _id(label["need_id"],"label need");_id(label["candidate_id"],"label candidate")
        relevance=label["relevance"]
        if isinstance(relevance,bool) or not isinstance(relevance,int) or not 0<=relevance<=3:_fail("relevance must be integer 0..3")
        pair=(label["need_id"],label["candidate_id"])
        if pair in actual:_fail("duplicate label pair")
        actual.add(pair)
    if actual!=expected:_fail("labels must cover exactly every query pair; missing/unknown IDs are forbidden")
    return data


def _canonical_hash(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")).hexdigest()


def load_dataset(path):
    with Path(path).open("rb") as stream:raw=stream.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:_fail("file exceeds 20 MiB")
    try:data=json.loads(raw.decode("utf-8"),object_pairs_hook=_object_pairs,parse_constant=lambda value:_fail("nonfinite JSON constant"))
    except (UnicodeDecodeError,json.JSONDecodeError,RecursionError) as error:_fail("invalid UTF-8/JSON: "+type(error).__name__)
    data=validate_dataset(data)
    labels=sorted(data["labels"],key=lambda row:(row["need_id"],row["candidate_id"]))
    return {"data":data,"input_sha256":hashlib.sha256(raw).hexdigest(),"labels_sha256":_canonical_hash(labels),"corpus_sha256":_canonical_hash({key:data[key] for key in ("needs","candidates","queries")})}


def _ndcg(order,labels,k):
    ideal=sorted(labels.values(),reverse=True)[:k]
    denominator=sum((2**value-1)/math.log2(index+2) for index,value in enumerate(ideal))
    if denominator==0:return None
    return sum((2**labels[value]-1)/math.log2(index+2) for index,value in enumerate(order[:k]))/denominator


def _aggregate(values,total):
    defined=[value for value in values if value is not None]
    return {"mean":round(statistics.mean(defined),6) if defined else None,"defined_queries":len(defined),"undefined_queries":total-len(defined),"retained_queries":total}


def evaluate_dataset(loaded,now=None):
    data=validate_dataset(loaded["data"])
    if _canonical_hash(sorted(data["labels"],key=lambda row:(row["need_id"],row["candidate_id"])))!=loaded["labels_sha256"] or _canonical_hash({key:data[key] for key in ("needs","candidates","queries")})!=loaded["corpus_sha256"]:_fail("loaded corpus/labels changed after immutable hashing")
    now=now or datetime.now(timezone.utc)
    if isinstance(now,str):now=datetime.fromisoformat(now.replace("Z","+00:00"))
    if now.tzinfo is None:now=now.replace(tzinfo=timezone.utc)
    needs={row["id"]:row for row in data["needs"]};candidates={row["id"]:row for row in data["candidates"]}
    labels={(row["need_id"],row["candidate_id"]):row["relevance"] for row in data["labels"]}
    per_query=[];gate_reasons=Counter();violations=0;rng=random.Random(71903)
    models=("full_engine","strong_category_test","random_eligible","keyword_eligible")
    metrics={model:{key:[] for key in ("precision5","ndcg10_end_to_end","ndcg10_eligible")} for model in models};recalls=[]
    for query in data["queries"]:
        need=needs[query["need_id"]]
        # Labels and metadata are never passed to admission/ranking. Candidates
        # are an allowlisted observed corpus with no latent/contact fields.
        profiles=[candidates[value] for value in query["candidate_ids"]]
        gold={value:labels[(need["id"],value)] for value in query["candidate_ids"]}
        eligible=[row for row in profiles if admission(need,row,need.get("company_id"))["eligible"]]
        eligible_ids={row["id"] for row in eligible};eligible_gold={key:value for key,value in gold.items() if key in eligible_ids}
        ranked=rank_candidates(need,profiles,now,company_id=need.get("company_id"))
        full=[row["candidate_id"] for row in ranked]
        violations+=sum(value not in eligible_ids for value in full)
        relevant={key for key,value in gold.items() if value>=2}
        recall=len(relevant&eligible_ids)/len(relevant) if relevant else None;recalls.append(recall)
        for row in profiles:
            if row["id"] in relevant and row["id"] not in eligible_ids:gate_reasons.update(admission(need,row,need.get("company_id"))["reasons"])
        random_order=sorted(eligible_ids);rng.shuffle(random_order)
        needed={canonical_skill(value) for value in need["required_skills"]+need["skills"]}
        orders={"full_engine":full,"strong_category_test":[row["id"] for row in sorted(eligible,key=lambda row:(-(row.get("score") or 0),row["id"]))],"random_eligible":random_order,"keyword_eligible":[row["id"] for row in sorted(eligible,key=lambda row:(-len(needed&{canonical_skill(value) for value in row.get("skills",[])}),row["id"]))]}
        values={}
        for model,order in orders.items():
            values[model]={"precision5":sum(gold[value]>=2 for value in order[:5])/5,"ndcg10_end_to_end":_ndcg(order,gold,10),"ndcg10_eligible":_ndcg(order,eligible_gold,10)}
            for key,value in values[model].items():metrics[model][key].append(value)
        per_query.append({"need_id":need["id"],"candidate_count":len(profiles),"eligible_count":len(eligible),"relevant_count":len(relevant),"retrieval_recall":recall,"metrics":values})
    total=len(per_query)
    return {"schema_version":SCHEMA_VERSION,"algorithm_version":ALGORITHM_VERSION,"evaluated_at":now.astimezone(timezone.utc).isoformat(),"input_sha256":loaded["input_sha256"],"labels_sha256":loaded["labels_sha256"],"corpus_sha256":loaded["corpus_sha256"],"labels_kind":"INPUT_EXPLICIT_LABELS_NOT_GENERATED_BY_SCORER","origin":data["origin"],"declared_human_labelers":data["human_labelers"],"origin_independently_verified":False,"human_pilot_claimed":False,"label_metadata":data.get("label_metadata",{}),"queries":total,"pairs":len(labels),"zero_eligible_queries":sum(row["eligible_count"]==0 for row in per_query),"no_binary_relevant_queries":sum(row["relevant_count"]==0 for row in per_query),"gate_violations":violations,"excluded_relevant_reason_counts":dict(gate_reasons),"baselines":{model:{key:_aggregate(values,total) for key,values in rows.items()} for model,rows in metrics.items()},"retrieval_recall":_aggregate(recalls,total),"per_query":per_query,"limitations":["Label origin and number of human labelers are supplied declarations, not independently verified identity/procedure.","Loader validates anonymous observed fields, complete explicit labels and immutable input hashes; it does not establish professional grade validity or real hiring outcomes.","All queries retained, including empty/zero eligible. Precision@5 always divides by5. Zero-IDCG nDCG and no-relevant recall are null with explicit defined/undefined counts.","Labels/corpus may share biases; no automatic assertion of human pilot, inter-rater agreement or IRT calibration."]}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--dataset",required=True);parser.add_argument("--output");parser.add_argument("--as-of",help="Fixed ISO time for reproducible freshness")
    args=parser.parse_args()
    try:report=evaluate_dataset(load_dataset(args.dataset),args.as_of)
    except (ValueError,OSError) as error:parser.exit(2,str(error)+"\n")
    text=json.dumps(report,ensure_ascii=False,indent=2)+"\n"
    if args.output:Path(args.output).write_text(text,encoding="utf-8",newline="\n")
    print(text,end="")


if __name__=="__main__":main()
