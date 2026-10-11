"""Independent solvers for the public advanced data contracts.

No generator or private oracle imports. Numeric correctness is programmatic;
professional grade validity requires a future human panel/pilot.
"""

from fractions import Fraction


def solve(data):
    mode=data["advanced_mode"]; senior=data["difficulty_level"]==3
    if mode=="event-ledger":
        entries=sorted(data["events"],key=lambda event:(event["entity"],-event["version"]))
        conflicts=[]; grouped={}
        for entry in entries:
            key=(entry["entity"],entry["version"])
            grouped.setdefault(key,[]).append(entry)
        bad=set()
        for key,rows in grouped.items():
            first=rows[0]
            if any(row["amount"]!=first["amount"] or row["deleted"]!=first["deleted"] for row in rows[1:]):bad.add(key);conflicts.append(f"{key[0]}:{key[1]}")
        state={};quarantine=[]
        for entity in sorted({event["entity"] for event in entries}):
            versions=sorted((version for name,version in grouped if name==entity),reverse=True)
            chosen=next((version for version in versions if (entity,version) not in bad),None) if not senior else versions[0]
            if chosen is None or (entity,chosen) in bad:quarantine.append(entity);continue
            event=grouped[(entity,chosen)][0]
            if not event["deleted"]:state[entity]=event["amount"]
        return {"state":state,"conflicts":sorted(conflicts),"quarantine":quarantine,"total":sum(state.values())}
    if mode=="ui-replay":
        state={"base":data["initial"]["base"],"version":data["initial"]["version"],"request":None,"pending":{},"ignored":0}
        for event in data["timeline"]:
            kind=event["kind"]
            if kind=="start":state["request"]=event["id"]
            elif kind=="optimistic":state["pending"][event["id"]]=event["delta"]
            elif kind=="reject":
                if state["pending"].pop(event["id"],None) is None:state["ignored"]+=1
            else:
                if kind=="commit":state["pending"].pop(event["id"],None)
                admissible=(kind=="commit" or event["id"]==state["request"]) and (not senior or event["version"]>state["version"])
                if admissible:state.update(base=event["value"],version=event["version"])
                else:state["ignored"]+=1
        return {"value":state["base"]+sum(state["pending"].values()),"version":state["version"],"pending":sorted(state["pending"]),"ignored":state["ignored"]}
    if mode in ("risk-cover","rollout-capacity"):
        rows=data["tests"] if mode=="risk-cover" else data["pods"]
        best=None
        for mask in range(1,2**len(rows)):
            chosen=[row for index,row in enumerate(rows) if mask&(1<<index)]
            ids=sorted(row["id"] for row in chosen)
            if mode=="risk-cover":
                if any(not any(fault in test["kills"] for test in chosen) for fault in data["required_faults"]):continue
                cost=sum(row["cost"] for row in chosen);key=(cost,len(chosen),ids)
            else:
                if any(not row["ready"] or not(row["schema_min"]<=data["database_schema"]<=row["schema_max"]) for row in chosen):continue
                cost=sum(row["memory"] for row in chosen)
                if cost>data["capacity"] or (senior and len({row["zone"] for row in chosen})<2):continue
                key=(-len(chosen),cost,ids)
            if best is None or key<best:best=key
        if mode=="risk-cover":return {"selected":best[2],"cost":best[0],"uncovered":[]}
        return {"selected":best[2] if best else [],"memory":best[1] if best else 0,"feasible":best is not None}
    if mode=="grant-replay":
        allowed=[];denied=[];invalidated=[]
        events=data["timeline"]
        for index,event in enumerate(events):
            if event["kind"]=="revoke":invalidated.append(event["company"])
            if event["kind"]!="read":continue
            previous=[row for row in events[:index] if row["company"]==event["company"] and row["kind"]!="read"]
            grant=previous[-1] if previous else None
            ok=bool(grant and grant["kind"]=="grant" and event["time"]<grant["expires"])
            if senior and ok:ok=event["cache_version"]==grant["version"]
            (allowed if ok else denied).append(event["id"])
        return {"allowed":sorted(allowed),"denied":sorted(denied),"invalidate_companies":sorted(set(invalidated))}
    if mode=="retry-deadline":
        elapsed=0;ids=[];final="deadline"
        for index,event in enumerate(data["attempts"]):
            if index>0 and not data["idempotent"]:final="unsafe_retry";break
            if senior and index>data["retry_tokens"]:final="retry_budget";break
            end=elapsed+event["duration"]
            if end>data["deadline"]:break
            elapsed=end;ids.append(event["id"])
            if event["status"]=="200":final="success";break
            if elapsed+event["retry_after"]>=data["deadline"]:break
            elapsed+=event["retry_after"]
        return {"attempted":ids,"elapsed":elapsed,"final":final}
    if mode=="slo-windows":
        by_id={row["id"]:row for row in data["windows"]}
        burns={key:round(float(Fraction(row["failures"]*1000,row["requests"])),2) for key,row in by_id.items()}
        return {"burns":burns,"page":burns["short"]>=14 and (not senior or burns["long"]>=2),"remaining_long_budget":max(0,by_id["long"]["requests"]//1000-by_id["long"]["failures"])}
    if mode=="stratified-effect":
        groups=data["groups"]
        raw=Fraction(sum(row["b_success"] for row in groups),sum(row["b_total"] for row in groups))-Fraction(sum(row["a_success"] for row in groups),sum(row["a_total"] for row in groups))
        adj=sum(Fraction(row["weight"],100)*(Fraction(row["b_success"],row["b_total"])-Fraction(row["a_success"],row["a_total"])) for row in groups)
        return {"raw_delta_pp":round(float(raw*100),2),"adjusted_delta_pp":round(float(adj*100),2),"reversal":raw*adj<0,"causal_supported":False,"decision":"rollout" if senior and adj*100>=data["min_effect_pp"] else "hold"}
    if mode=="key-rotation":
        keys={row["kid"]:row for row in data["keys"]};accepted=[]
        for token in data["tokens"]:
            key=keys.get(token["kid"])
            rejected=key is None or key["revoked"] or data["now"]>=key["verify_until"] or token["exp"]<=data["now"] or token["iat"]>data["now"] or token["aud"]!="vector" or token["alg"]!="RS256" or not token["signature_valid"]
            if key and senior and token["iat"]<key["valid_from"]:rejected=True
            if not rejected:accepted.append(token["id"])
        return {"allowed":sorted(accepted),"rejected":sorted(set(row["id"] for row in data["tokens"])-set(accepted)),"retire_keys":sorted(key for key,row in keys.items() if row["revoked"] or row["verify_until"]<=data["now"])}
    if mode=="modal-focus":
        eligible=[row for row in data["controls"] if row["dialog"]==data["active_dialog"] and not(row["hidden"] or row["disabled"] or row["inert"])]
        eligible.sort(key=lambda row:(row["order"],row["id"]))
        opener=next(row for row in data["controls"] if row["id"]==data["opener"])
        return {"next_tab":eligible[0]["id"],"unnamed":sorted(row["id"] for row in eligible if not row["name"].strip()),"return_focus":"open" if opener["hidden"] or opener["disabled"] or opener["inert"] else opener["id"]}
    raise ValueError("No independent advanced public-contract solver")
