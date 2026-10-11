"""Bounded multi-step data exercises; no submitted program is executed.

Middle and Senior are author difficulty hypotheses. All constraints required for
an objective answer are public; these tasks do not establish market grade validity.
"""

from itertools import combinations

FAMILIES = {
    "api": "event-ledger", "reliability": "event-ledger", "data_quality": "event-ledger",
    "javascript": "ui-replay", "state": "ui-replay",
    "testing": "risk-cover", "test_design": "risk-cover",
    "authorization": "grant-replay", "web_security": "grant-replay", "incident_response": "grant-replay",
    "containers": "rollout-capacity", "networking": "retry-deadline",
    "observability": "slo-windows", "statistics": "stratified-effect", "interpretation": "stratified-effect",
    "cryptography": "key-rotation", "accessibility": "modal-focus",
}


def _item(mode, level, title, prompt, data, expected, critical=()):
    fields = ", ".join(expected)
    return {"title": title, "type": "json", "advanced": True,
            "prompt": prompt + f" Ответ — JSON-объект с полями {fields}; лишние поля не допускаются. Массивы id сортируйте по возрастанию. Каждое поле имеет равный вес. Ошибка критического поля ограничивает балл задания 40%. Критические поля: {', '.join(critical) or 'нет'}.",
            "public_cases": {"advanced_mode": mode, "difficulty_level": level, **data},
            "_family": f"advanced.{mode}.{'senior' if level == 3 else 'middle'}",
            "_oracle": {"kind": "rubric_json", "expected": expected, "critical": list(critical)}}


def advanced_practical(rng, competency, level, mutation=False):
    mode = FAMILIES[competency]
    if mode == "event-ledger":
        events = []
        for entity in ("a", "b", "c"):
            for version in (1, 2, 3):
                events.append({"entity": entity, "version": version, "amount": rng.randrange(1, 30), "deleted": version == 3 and entity == "c"})
        events.append(dict(events[1]))
        conflict = dict(events[4]); conflict["amount"] += 5; events.append(conflict)
        if level == 3:
            # A conflict at the newest version must not silently resurrect an old value.
            conflict = dict(events[2]); conflict["deleted"] = True; events.append(conflict)
        rng.shuffle(events)
        by_key = {}
        for row in events:
            by_key.setdefault((row["entity"], row["version"]), set()).add((row["amount"], row["deleted"]))
        conflicts = sorted(f"{entity}:{version}" for (entity, version), values in by_key.items() if len(values) > 1)
        state = {}; quarantined = []
        for entity in ("a", "b", "c"):
            versions = [version for name, version in by_key if name == entity]
            if level == 3:
                chosen = max(versions)
                values = by_key[(entity, chosen)]
                if len(values) > 1: quarantined.append(entity); continue
            else:
                valid = [version for version in versions if len(by_key[(entity, version)]) == 1]
                if not valid: quarantined.append(entity); continue
                values = by_key[(entity, max(valid))]
            amount, deleted = next(iter(values))
            if not deleted: state[entity] = amount
        prompt = "Сверьте события по (entity, version), одинаковые payload — повтор. Разные (amount, deleted) одного ключа — конфликт, его ключ entity:version входит в conflicts. "
        prompt += "Для каждой entity берите максимальную version из неконфликтующих ключей." if level == 2 else "Сначала найдите максимальную version entity, включая конфликтующие. Если она конфликтует — entity целиком quarantine; откат к старой version запрещён."
        prompt += " Deleted=true — tombstone: entity не входит в state и её amount не суммируется. Верните state (entity→amount), conflicts, quarantine и total по state."
        return _item(mode, level, "Версии, повторы, конфликт и tombstone", prompt, {"events": events}, {"state": state, "conflicts": conflicts, "quarantine": sorted(quarantined), "total": sum(state.values())}, ("state", "quarantine"))
    if mode == "ui-replay":
        initial = rng.randrange(20, 60)
        timeline = [{"kind": "start", "id": 1}, {"kind": "optimistic", "id": "m1", "delta": 5}, {"kind": "start", "id": 2}, {"kind": "response", "id": 2, "version": 3, "value": initial + 8}, {"kind": "response", "id": 1, "version": 5, "value": 999}, {"kind": "reject", "id": "m1"}]
        if level == 3:
            timeline.extend([{"kind": "optimistic", "id": "m2", "delta": -3}, {"kind": "response", "id": 2, "version": 2, "value": 777}, {"kind": "commit", "id": "m2", "version": 4, "value": initial + 5}, {"kind": "reject", "id": "m2"}])
        active = 0; version = 1; base = initial; pending = {}; ignored = 0
        for event in timeline:
            kind = event["kind"]
            if kind == "start": active = event["id"]
            elif kind == "optimistic": pending[event["id"]] = event["delta"]
            elif kind == "response":
                if event["id"] != active or (level == 3 and event["version"] <= version): ignored += 1
                else: base = event["value"]; version = event["version"]
            elif kind == "reject":
                if event["id"] in pending: del pending[event["id"]]
                else: ignored += 1
            elif kind == "commit":
                pending.pop(event["id"], None)
                if event["version"] > version: base = event["value"]; version = event["version"]
                else: ignored += 1
        prompt = "Обработайте timeline по порядку. start меняет active_request. optimistic записывает delta по mutation id; отображаемое value = base + сумма pending. response чужого request id игнорируется, иначе меняет base и version. reject удаляет только свой pending; если его нет — событие игнорируется."
        if level == 3: prompt += " Дополнительно response с version <= текущей игнорируется. commit удаляет свой pending и применяет base/value только при version > текущей, иначе считается игнорированным. Поздний reject уже committed mutation не откатывает base."
        return _item(mode, level, "Гонка запросов и optimistic rollback", prompt, {"initial": {"base": initial, "version": 1}, "timeline": timeline}, {"value": base + sum(pending.values()), "version": version, "pending": sorted(pending), "ignored": ignored}, ("value", "version"))
    if mode == "risk-cover":
        faults = ["boundary", "replay", "foreign_scope", "revocation"]
        if level == 3: faults += ["concurrent_accept", "stale_cache"]
        tests = [{"id": "t1", "cost": 2, "kills": ["boundary", "replay"]}, {"id": "t2", "cost": 3, "kills": ["foreign_scope", "revocation"]}, {"id": "t3", "cost": 5, "kills": faults[:4]}, {"id": "t4", "cost": rng.randrange(2, 5), "kills": ["concurrent_accept", "stale_cache"] if level == 3 else ["boundary"]}, {"id": "t5", "cost": 1, "kills": ["replay", "foreign_scope"]}, {"id": "t6", "cost": 2, "kills": ["boundary", "revocation"]}]
        for test in tests:
            test["cost"]=rng.randrange(1,8)
            test["id"]=f"t{rng.randrange(1000,9999)}"
        if len({test["id"] for test in tests})!=len(tests):
            for index,test in enumerate(tests):test["id"]=f"t{index}-{test['id']}"
        candidates = []
        for n in range(1, len(tests) + 1):
            for subset in combinations(tests, n):
                if set(faults) <= {fault for test in subset for fault in test["kills"]}:
                    candidates.append((sum(test["cost"] for test in subset), n, sorted(test["id"] for test in subset)))
        cost, _, selected = min(candidates)
        return _item(mode, level, "Риск и минимальный mutation cover", "Выберите tests, которые убивают все required_faults. Минимизируйте суммарный cost, затем число тестов, затем лексикографический отсортированный список id. Не требуются тесты для faults вне required_faults. Верните selected, cost и uncovered (пустой, если найдено покрытие). Это ограниченная модель выбора, а не полное доказательство качества тестов.", {"required_faults": faults, "tests": tests}, {"selected": selected, "cost": cost, "uncovered": []}, ("uncovered", "selected"))
    if mode == "grant-replay":
        expiry = rng.randrange(15, 25)
        timeline = [{"time": 1, "kind": "grant", "company": "c1", "version": 1, "expires": expiry}, {"time": 2, "kind": "read", "id": "r1", "company": "c1", "cache_version": 1}, {"time": 3, "kind": "read", "id": "r2", "company": "c2", "cache_version": 1}, {"time": 5, "kind": "revoke", "company": "c1", "version": 2}, {"time": 6, "kind": "read", "id": "r3", "company": "c1", "cache_version": 1}, {"time": 7, "kind": "grant", "company": "c1", "version": 3, "expires": expiry}, {"time": 8, "kind": "read", "id": "r4", "company": "c1", "cache_version": 1}, {"time": expiry, "kind": "read", "id": "r5", "company": "c1", "cache_version": 3}]
        timeline[2]["company"]=rng.choice(["c1","c2"])
        timeline[7]["cache_version"]=rng.choice([1,3])
        for index,event in enumerate(timeline):
            if event["kind"]=="read":event["id"]=f"r{index}-{rng.randrange(1000,9999)}"
        grants = {}; allowed = []; denied = []; invalidated = []
        for event in timeline:
            company = event["company"]
            if event["kind"] == "grant": grants[company] = {"active": True, "version": event["version"], "expires": event["expires"]}
            elif event["kind"] == "revoke": grants[company] = {"active": False, "version": event["version"], "expires": 0}; invalidated.append(company)
            else:
                grant = grants.get(company)
                ok = bool(grant and grant["active"] and event["time"] < grant["expires"])
                if level == 3: ok = ok and event["cache_version"] == grant["version"]
                (allowed if ok else denied).append(event["id"])
        prompt = "Обработайте timeline по порядку. grant заменяет актуальное разрешение company, revoke делает его неактивным и требует инвалидировать cache компании. read разрешён только по актуальному active grant той же company и time < expires (граница срока исключена)."
        prompt += " В Middle cache_version не входит в allow: сервер читает актуальный grant." if level == 2 else " В Senior выдача из cache допустима дополнительно лишь при cache_version == актуальная grant version; stale cache запрещён даже после нового grant."
        return _item(mode, level, "Отзыв, повторный grant и stale cache", prompt, {"timeline": timeline}, {"allowed": sorted(allowed), "denied": sorted(denied), "invalidate_companies": sorted(set(invalidated))}, ("allowed",))
    if mode == "rollout-capacity":
        rows = [{"id": f"p{i}", "ready": i != 1, "schema_min": rng.choice([1, 2, 3]), "schema_max": 3, "memory": rng.choice([200, 300, 400]), "zone": "a" if i < 3 else "b"} for i in range(6)]
        schema = 2; capacity = 900; selected = [row for row in rows if row["ready"] and row["schema_min"] <= schema <= row["schema_max"]]
        feasible = []
        for n in range(1, len(selected) + 1):
            for subset in combinations(selected, n):
                memory = sum(row["memory"] for row in subset)
                if memory <= capacity and (level == 2 or len({row["zone"] for row in subset}) >= 2): feasible.append((-n, memory, sorted(row["id"] for row in subset)))
        chosen = min(feasible) if feasible else (0, 0, [])
        return _item(mode, level, "Совместимость схемы и rollout capacity", "Отберите ready pods с schema_min <= database_schema <= schema_max. Выберите подмножество с суммарной memory <= capacity. Максимизируйте число pods, затем минимизируйте memory, затем лексикографический список id." + (" Senior: обязательны хотя бы две разные zone; если такого подмножества нет, selected=[], memory=0, feasible=false." if level == 3 else " Если нет ни одного pod, selected=[], memory=0, feasible=false.") + " Верните selected, memory, feasible.", {"pods": rows, "database_schema": schema, "capacity": capacity}, {"selected": chosen[2], "memory": chosen[1], "feasible": bool(chosen[2])}, ("selected", "feasible"))
    if mode == "retry-deadline":
        deadline = rng.randrange(180, 230)
        attempts = [{"id": "a1", "duration": 40, "status": "timeout", "retry_after": 20}, {"id": "a2", "duration": 70, "status": "503", "retry_after": 60}, {"id": "a3", "duration": 30, "status": "200", "retry_after": 0}]
        safe = level == 2 or rng.choice([True,False]); retry_tokens=rng.choice([1,2]) if level==3 else None
        elapsed = 0; used = []; final = "deadline"
        for index, row in enumerate(attempts):
            if index and not safe: final = "unsafe_retry"; break
            if level==3 and index>retry_tokens:final="retry_budget";break
            if elapsed + row["duration"] > deadline: final = "deadline"; break
            elapsed += row["duration"]; used.append(row["id"])
            if row["status"] == "200": final = "success"; break
            if elapsed + row["retry_after"] >= deadline: final = "deadline"; break
            elapsed += row["retry_after"]
        return _item(mode, level, "Retry amplification и общий deadline", "Попытки идут по порядку, без параллельности. duration должна полностью уместиться в общий deadline (равенство разрешено). После timeout/503 ждём retry_after; если ожидание доведёт elapsed до deadline или выше — прекращаем без ожидания. Повтор после первой попытки допустим лишь при idempotent=true; иначе final='unsafe_retry'." + (" Senior: каждый повтор потребляет один retry_token; после проверки idempotency, но до проверки duration, при исчерпании бюджета final='retry_budget'. Первая попытка токен не потребляет." if level==3 else " Middle: лимита retry_tokens нет.") + " Успех 200 → final='success'; нехватка времени → 'deadline'. Верните attempted id, elapsed (фактически потраченное время), final.", {"deadline": deadline, "idempotent": safe, "retry_tokens":retry_tokens,"attempts": attempts}, {"attempted": used, "elapsed": elapsed, "final": final}, ("attempted", "final"))
    if mode == "slo-windows":
        windows = [{"id": "short", "requests": 1000, "failures": rng.randrange(10, 30)}, {"id": "long", "requests": 100000, "failures": rng.randrange(50, 250)}]
        rates = {row["id"]: round(row["failures"] / row["requests"] / .001, 2) for row in windows}
        page = rates["short"] >= 14 and (rates["long"] >= 2 if level == 3 else True)
        return _item(mode, level, "Multi-window SLO burn и correlated alerts", "SLO=99.9%. Burn window = failures / requests / 0.001, округлите до 2 знаков. page=true при short burn >=14." + (" Senior: дополнительно long burn >=2; windows перекрываются, requests/failures суммировать нельзя." if level == 3 else " Middle: long burn выводится, но не участвует в page.") + " Верните burns (id→число), page и remaining_long_budget = max(0, floor(long.requests*0.001)-long.failures).", {"windows": windows, "slo": .999}, {"burns": rates, "page": page, "remaining_long_budget": max(0, 100 - windows[1]["failures"])}, ("page",))
    if mode == "stratified-effect":
        groups = [{"id": "new", "weight": 70, "a_total": 100, "a_success": rng.randrange(10, 25), "b_total": 900, "b_success": rng.randrange(180, 225)}, {"id": "returning", "weight": 30, "a_total": 900, "a_success": rng.randrange(630, 720), "b_total": 100, "b_success": rng.randrange(75, 85)}]
        a = sum(row["a_success"] for row in groups) / sum(row["a_total"] for row in groups)
        b = sum(row["b_success"] for row in groups) / sum(row["b_total"] for row in groups)
        weighted_a = sum(row["weight"] * row["a_success"] / row["a_total"] for row in groups) / 100
        weighted_b = sum(row["weight"] * row["b_success"] / row["b_total"] for row in groups) / 100
        return _item(mode, level, "Состав популяции и Simpson reversal", "Из groups вычислите raw_delta_pp = (общая B конверсия - общая A конверсия)*100. adjusted_delta_pp = сумма weight/100*(B.rate-A.rate)*100; fixed weight — заранее заданная единая популяция, не объём текущей группы. Округляйте только итоговые delta до 2 знаков. reversal=true, если знаки raw и adjusted строго противоположны. causal_supported=false: данных о рандомизации нет." + (" Senior: для deployment используйте adjusted: решение='rollout' лишь при adjusted >= min_effect_pp, иначе 'hold'; причинность всё равно не установлена." if level == 3 else " Middle: решение='hold' независимо от величины эффекта до проверки дизайна эксперимента."), {"groups": groups, "min_effect_pp": 5}, {"raw_delta_pp": round((b-a)*100, 2), "adjusted_delta_pp": round((weighted_b-weighted_a)*100, 2), "reversal": (b-a)*(weighted_b-weighted_a)<0, "causal_supported": False, "decision": "rollout" if level == 3 and (weighted_b-weighted_a)*100 >= 5 else "hold"}, ("causal_supported", "decision"))
    if mode == "key-rotation":
        now = rng.randrange(100, 200)
        keys = [{"kid": "old", "valid_from": 0, "verify_until": now+20, "revoked": False}, {"kid": "new", "valid_from": now-10, "verify_until": now+100, "revoked": False}, {"kid": "leaked", "valid_from": 0, "verify_until": now+100, "revoked": True}]
        tokens = [{"id": "t1", "kid": "old", "iat": now-30, "exp": now+10, "aud": "vector", "alg": "RS256", "signature_valid": True}, {"id": "t2", "kid": "new", "iat": now-20, "exp": now+10, "aud": "vector", "alg": "RS256", "signature_valid": True}, {"id": "t3", "kid": "leaked", "iat": now-1, "exp": now+10, "aud": "vector", "alg": "RS256", "signature_valid": True}, {"id": "t4", "kid": "new", "iat": now-1, "exp": now+10, "aud": "other", "alg": "RS256", "signature_valid": True}, {"id": "t5", "kid": "new", "iat": now-1, "exp": now, "aud": "vector", "alg": "none", "signature_valid": True}]
        tokens[1]["iat"]=now-rng.choice([5,20])
        tokens[3]["aud"]=rng.choice(["vector","other"])
        for index,token in enumerate(tokens):token["id"]=f"t{index}-{rng.randrange(1000,9999)}"
        allowed = []; rejected = []
        for token in tokens:
            key = next(row for row in keys if row["kid"] == token["kid"])
            ok = not key["revoked"] and now < key["verify_until"] and token["exp"] > now and token["iat"] <= now and token["aud"] == "vector" and token["alg"] == "RS256" and token["signature_valid"]
            if level == 3: ok = ok and token["iat"] >= key["valid_from"]
            (allowed if ok else rejected).append(token["id"])
        return _item(mode, level, "Key rotation, audience и временные границы", "По уже проверенным signature_valid (криптографические операции здесь не выполняются) допустим token только если kid существует, key не revoked, now < verify_until, exp > now, iat <= now, aud='vector', alg='RS256'." + (" Senior: iat дополнительно >= key.valid_from; новый ключ не может подписывать до его активации." if level == 3 else " Middle: valid_from предоставлено для контекста, но в этой упрощённой policy не проверяется.") + " Верните allowed, rejected и retire_keys — kid с revoked=true ИЛИ verify_until <= now.", {"now": now, "keys": keys, "tokens": tokens}, {"allowed": sorted(allowed), "rejected": sorted(rejected), "retire_keys": ["leaked"]}, ("allowed",))
    if mode == "modal-focus":
        controls = [{"id": "open", "order": 1, "disabled": False, "hidden": False, "inert": False, "name": "Открыть", "dialog": None}, {"id": "close", "order": 2, "disabled": False, "hidden": False, "inert": False, "name": "Закрыть", "dialog": "outer"}, {"id": "save", "order": 3, "disabled": False, "hidden": False, "inert": level==3, "name": "Сохранить", "dialog": "outer"}, {"id": "inner-close", "order": 4, "disabled": False, "hidden": False, "inert": False, "name": "", "dialog": "inner"}, {"id": "inner-save", "order": 5, "disabled": True, "hidden": False, "inert": False, "name": "Сохранить", "dialog": "inner"}]
        controls[2]["inert"]=level==3 and rng.choice([True,False])
        controls[4]["disabled"]=rng.choice([True,False])
        controls[3]["name"]=rng.choice(["","Закрыть вложенное окно"])
        for row in controls:row["order"]+=rng.randrange(1,20)
        active = "inner" if level == 3 else "outer"
        tabbable = sorted([row for row in controls if row["dialog"] == active and not any(row[key] for key in ("disabled", "hidden", "inert"))], key=lambda row: (row["order"],row["id"]))
        ids = [row["id"] for row in tabbable]
        violations = sorted(row["id"] for row in tabbable if not row["name"].strip())
        opener=controls[2] if level==3 else controls[0]
        return _item(mode, level, "Nested dialog и восстановление focus", "Активен только active_dialog. Tab обходится циклически по его controls в порядке order (при равенстве по id); disabled/hidden/inert исключены. current_focus — последний доступный control, next_tab — первый. unnamed — доступные controls с пустым name. Escape закрывает только активный dialog и возвращает focus к его opener, если opener доступен (не disabled/hidden/inert), иначе fallback='open'. Верните next_tab, unnamed, return_focus. Это ограниченная модель focus; полный WCAG аудит не заменяется.", {"controls": controls, "active_dialog": active, "opener": opener["id"], "current_focus": ids[-1]}, {"next_tab": ids[0], "unnamed": violations, "return_focus": "open" if opener["inert"] else opener["id"]}, ("next_tab", "return_focus"))
    raise ValueError("Unsupported advanced family")


def advanced_manifest():
    return [{"id": f"advanced.{mode}.{grade}", "title": mode, "competency": next(comp for comp, value in FAMILIES.items() if value == mode), "slot": "practice", "grades": [grade], "status": "author_initial", "human_review": "NOT_MEASURED", "empirical_calibration": "NOT_MEASURED", "automated_review": "independent_public_data_solver"} for mode in sorted(set(FAMILIES.values())) for grade in ("middle", "senior")]
