"""Declared synthetic behavior methods; read public conditions, never a rubric.

The fixed profile mixture is a simulation assumption, not fitted human ability.
"""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from evaluation.reference_solvers import reference_answer,sql_spec


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")).hexdigest()


def fixed_profiles(competencies):
    full={comp:"full" for comp in competencies}
    rows=[{"id":"perfect","kind":"perfect","methods":full},
          {"id":"shallow","kind":"shallow","methods":{comp:"shallow" for comp in competencies}},
          {"id":"guesser","kind":"guesser","methods":{comp:"misconception" for comp in competencies}}]
    for index,comp in enumerate(competencies):
        rows.append({"id":f"weak-{index}","kind":"weak_skill","methods":{**full,comp:"misconception"}})
        rows.append({"id":f"boundary-{index}","kind":"basic_boundary","methods":{**full,comp:"basic"}})
        methods={name:("full","basic","misconception","full")[(position-index)%4] for position,name in enumerate(competencies)}
        rows.append({"id":f"mixed-{index}","kind":"heterogeneous","methods":methods})
    for index,attention in enumerate((.70,.80,.85,.90,.95)):
        rows.append({"id":f"attention-{index}","kind":"attention_boundary","methods":full,"attention":attention,"weak_attention_competency":competencies[index%4]})
    return rows


@lru_cache(maxsize=4000)
def _known(serialized):
    return reference_answer(json.loads(serialized))


def respond(item,profile):
    # IDs/ordering/private fields cannot influence a profile's methods.
    public={key:item[key] for key in ("title","prompt","type","competency","options","public_cases","advanced") if key in item}
    behavior_input={**public,"options":sorted(option["label"] for option in item.get("options",[]))}
    method=profile["methods"][item["competency"]]
    attention=profile.get("attention",1.)
    if item["competency"]==profile.get("weak_attention_competency"):attention=max(0.,attention-.15)
    if int(digest([profile["id"],behavior_input])[:16],16)/2**64>=attention:method="misconception"
    known=method=="full" or (method=="basic" and not item.get("advanced")) or (method=="shallow" and item["type"]=="single_choice")
    if known:return deepcopy(_known(json.dumps(public,sort_keys=True,ensure_ascii=False)))
    if item["type"]=="single_choice":
        options=sorted(item["options"],key=lambda option:option["label"])
        return options[int(digest([profile["id"],behavior_input,"blind_choice"]),16)%len(options)]["id"]
    return misconception_answer(item)


def misconception_answer(item):
    """Actual flawed algorithms, whose accidental correct answers are retained."""
    d=item.get("public_cases") or {};mode=d.get("advanced_mode")
    if item["type"]=="sql":
        statuses,threshold=sql_spec(item)
        if d.get("sql_spec",{}).get("mode","aggregate")=="aggregate":
            return "SELECT region,SUM(amount) FROM orders GROUP BY region" # ignores conditions
        values=",".join("'"+value+"'" for value in statuses)
        return f"SELECT c.region,SUM(o.amount) FROM orders o JOIN customers c ON c.id=o.customer_id WHERE o.status IN ({values}) AND o.amount>={threshold} GROUP BY c.region" # ignores latest/refunds
    if mode=="event-ledger":
        state={row["entity"]:row["amount"] for row in d["events"]}
        return {"state":state,"conflicts":[],"quarantine":[],"total":sum(state.values())}
    if mode=="ui-replay":
        base=d["initial"]["base"];version=d["initial"]["version"];pending={}
        for row in d["timeline"]:
            if row["kind"]=="optimistic":pending[row["id"]]=row["delta"]
            elif row["kind"] in ("commit","response"):base=row["value"];version=row["version"]
        return {"value":base+sum(pending.values()),"version":version,"pending":sorted(pending),"ignored":0}
    if mode=="risk-cover":
        chosen=[];covered=set()
        for row in sorted(d["tests"],key=lambda row:(row["cost"],row["id"])):
            if set(d["required_faults"])<=covered:break
            chosen.append(row);covered.update(row["kills"])
        return {"selected":sorted(row["id"] for row in chosen),"cost":sum(row["cost"] for row in chosen),"uncovered":sorted(set(d["required_faults"])-covered)}
    if mode=="rollout-capacity":
        selected=[];memory=0
        for row in d["pods"]:
            if row["ready"] and memory+row["memory"]<=d["capacity"]:selected.append(row["id"]);memory+=row["memory"]
        return {"selected":sorted(selected),"memory":memory,"feasible":bool(selected)}
    if mode=="grant-replay":
        grants=set();allowed=[];denied=[]
        for row in d["timeline"]:
            if row["kind"]=="grant":grants.add(row["company"])
            elif row["kind"]=="read":(allowed if row["company"] in grants else denied).append(row["id"])
        return {"allowed":sorted(allowed),"denied":sorted(denied),"invalidate_companies":[]}
    if mode=="retry-deadline":
        elapsed=0;attempted=[];final="deadline"
        for row in d["attempts"]:
            if elapsed+row["duration"]>d["deadline"]:break
            elapsed+=row["duration"];attempted.append(row["id"])
            if row["status"]=="200":final="success";break
        return {"attempted":attempted,"elapsed":elapsed,"final":final}
    if mode=="slo-windows":
        windows={row["id"]:row for row in d["windows"]};burns={key:round(row["failures"]*1000/row["requests"],2) for key,row in windows.items()}
        return {"burns":burns,"page":burns["short"]>=14,"remaining_long_budget":windows["long"]["requests"]//1000-windows["long"]["failures"]}
    if mode=="stratified-effect":
        rows=d["groups"];raw=(sum(row["b_success"] for row in rows)/sum(row["b_total"] for row in rows)-sum(row["a_success"] for row in rows)/sum(row["a_total"] for row in rows))*100
        return {"raw_delta_pp":round(raw,2),"adjusted_delta_pp":round(raw,2),"reversal":False,"causal_supported":True,"decision":"rollout" if raw>=d["min_effect_pp"] else "hold"}
    if mode=="key-rotation":
        keys={row["kid"]:row for row in d["keys"]};allowed=sorted(row["id"] for row in d["tokens"] if row["kid"] in keys and not keys[row["kid"]]["revoked"] and row["signature_valid"])
        return {"allowed":allowed,"rejected":sorted(set(row["id"] for row in d["tokens"])-set(allowed)),"retire_keys":sorted(key for key,row in keys.items() if row["revoked"])}
    if mode=="modal-focus":
        eligible=sorted((row for row in d["controls"] if row["dialog"]==d["active_dialog"] and not row["hidden"]),key=lambda row:(row["order"],row["id"]))
        return {"next_tab":eligible[0]["id"] if eligible else None,"unnamed":sorted(row["id"] for row in eligible if not row["name"].strip()),"return_focus":d["opener"]}
    if mode:raise ValueError("Unsupported declared misconception mode")
    if "requests" in d:return d["requests"]*d["allowed_per_mille"]//1000
    if "request_keys" in d:return len(d["request_keys"])
    if "start" in d:return d["start"]+sum(row["value"] for row in d["steps"])
    if "budget_mib" in d:return d["budget_mib"]-sum(d["requests_mib"])
    if "uniform_random_bytes" in d:return d["uniform_random_bytes"]
    if "elements" in d:return [row["id"] for row in d["elements"] if row["icon_only"]]
    if "grants" in d:return [row["id"] for row in d["grants"] if row["active"]]
    if "reads" in d:return [row["id"] for row in d["reads"] if row["grant_active"]]
    if "controls" in d:return [row["id"] for row in d["controls"] if not row["name"]]
    if "tokens" in d:return [row["id"] for row in d["tokens"] if not row["used"]]
    if "nodes" in d:return [row["id"] for row in d["nodes"] if row["ready"]]
    if "responses" in d:return {"result":d["responses"][-1]["result"]}
    if "cases" in d:return [row["id"] for row in d["cases"] if d["lower"]<=row["value"]<=d["upper"]]
    if "lower" in d:return [d["lower"],d["upper"]]
    if "events" in d:
        if "entity" in d["events"][0]:return {row["entity"]:row["value"] for row in d["events"]}
        return {"total":sum(row["amount"] for row in d["events"]),"conflicts":[]}
    if "rows" in d:
        rows=d["rows"]
        if "visits" in rows[0]:return sum(row["conversions"]/row["visits"] for row in rows)/len(rows)*100
        return {"conversion_percent":round(sum(row["success"]/row["exposed"] for row in rows)/len(rows)*100,2)}
    raise ValueError("Unsupported public basic response contract")
