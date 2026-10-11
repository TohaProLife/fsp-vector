"""Independent reference solvers consume only public task statements/data.

They deliberately do not import bank generators or private grading payloads.
Concept choices use an explicit reviewed-fact table; numeric/data cases are solved
from the public specification. This proves programmatic correctness, not grade validity.
"""

import json
import re
from collections import defaultdict

FACTS={
"Повторный запрос":"Вернуть сохранённый результат этой операции",
"Изменение контракта":"Отклонить конфликт и сохранить исходную операцию",
"Отсутствующая связь":"LEFT JOIN orders по идентификатору клиента",
"NULL в агрегате":"SUM(COALESCE(discount, 0))",
"Повторная доставка":"Атомарная фиксация бизнес-изменения и обработанного event_id",
"Событие после commit":"Транзакционный outbox и идемпотентная доставка",
"Конкурентное принятие":"Проверить атомарность перехода и уникальность grant",
"Независимый oracle":"Одинаковая ошибка может быть повторена в ожидаемом результате",
"Асинхронный порядок":"Microtask из Promise.then",
"Обновление массива":"Создать новый массив и новый изменённый объект",
"Гонка поиска":"Применять ответ только для текущего request_id",
"Авторизация кнопки":"Серверная проверка grant при каждом чтении контактов",
"Кнопка с иконкой":"Доступное имя через aria-label или связанный текст",
"Открытие диалога":"Фокус внутри, Escape закрывает, фокус возвращается инициатору",
"Недоверенный текст":"Вывести через экранирующий текстовый API",
"Сессия и CSRF":"Проверять CSRF token и Origin вместе с cookie policy",
"Граница диапазона":"L-1, L, U, U+1",
"Состояния договора":"После declined повторный accept не создаёт grant",
"Error budget":"Допустимая доля ошибок × число всех запросов",
"Диагностика p95":"Порог, не выше которого завершились не менее 95% измеренных запросов",
"Секреты образа":"Подать секрет при запуске из защищённого хранилища",
"Сбой миграции":"Нет, readiness сообщает неготовность до совместимой схемы",
"Повтор запроса":"Есть согласованный механизм идемпотентности операции",
"TLS проверка":"Проверку сертификата и имени узла",
"Смешение групп":"Нет, изменение состава трафика может смешивать эффект",
"Знаменатель":"Определение события успеха, популяции и знаменателя",
"Дедупликация":"Дубликаты могут завысить метрику, а конфликтующие payload требуют явной политики",
"Пропуски":"Отделить неизвестное от достоверного нуля и описать обработку",
"Синтетическая оценка":"Результат на указанном синтетическом benchmark с его ограничениями",
"Корреляция":"Связь наблюдается; причинность требует отдельного дизайна",
"Чужое приглашение":"Сервер проверяет принадлежность пользователя и scope компании",
"Отзыв разрешения":"Проверять актуальное разрешение и не отдавать старые контакты из кэша",
"Хранение пароля":"Солёный медленный password hash с согласованными параметрами",
"Случайный токен":"Непредсказуемым, одноразовым, ограниченным по времени и храниться безопасно",
"Сохранение доказательств":"Ограничить ущерб, отозвать токен, сохранить релевантный аудит и выяснить scope",
"Сигнал сканирования":"Нет; это сигнал, нуждающийся в контексте и расследовании",
}


def sql_spec(item):
    if item.get("public_cases",{}).get("sql_spec"):
        spec=item["public_cases"]["sql_spec"]
        return spec["statuses"],spec["threshold"]
    prompt=item["prompt"]
    statuses=json.loads(re.search(r"status (\[[^\]]+\])",prompt).group(1).replace("'",'"'))
    threshold=int(re.search(r"amount >= (\d+)",prompt).group(1))
    return statuses,threshold


def independent_sql_rows(item):
    statuses,threshold=sql_spec(item)
    mode=item["public_cases"].get("sql_spec",{}).get("mode","aggregate")
    if mode!="aggregate":
        tables=item["public_cases"]["tables"]
        customers={row[0]:row[1] for row in tables["customers"]["rows"]}
        orders=[row for row in tables["orders"]["rows"] if row[1] in customers and row[3] in statuses and row[2]>=threshold]
        if mode=="latest_per_customer":
            ordered=sorted(orders,key=lambda row:(row[1],-row[4],-row[0]))
            selected=[]; seen=set()
            for row in ordered:
                if row[1] not in seen: selected.append(row); seen.add(row[1])
            orders=selected
        buckets=defaultdict(list)
        for row in orders:
            amount=row[2]
            if mode=="latest_per_customer": amount-=0 if row[5] is None else row[5]
            if mode=="refund_preaggregate":
                refunds=[refund[2] for refund in tables["refunds"]["rows"] if refund[1]==row[0] and refund[3]=="settled"]
                amount-=sum(refunds)
            buckets[customers[row[1]]].append(amount)
        return [[key,sum(values)] for key,values in sorted(buckets.items())]
    buckets=defaultdict(list)
    for row in item["public_cases"]["tables"]["orders"]["rows"]:
        if row[3] in statuses and row[2]>=threshold:
            buckets[row[1]].append(row[2])
    return [[region,sum(values)] for region,values in sorted(buckets.items())]


def reference_answer(item):
    data=item.get("public_cases") or {}
    if "advanced_mode" in data:
        from evaluation.advanced_reference import solve
        return solve(data)
    if item["type"]=="single_choice":
        expected=FACTS.get(item["title"])
        if expected is None:
            # Separate author review ledger; semantic correctness of new choice
            # decisions still requires a human panel. This is structural checking.
            from pathlib import Path
            ledger=json.loads((Path(__file__).parent.parent/"assessment-bank"/"author-review-ledger.json").read_text(encoding="utf-8"))
            expected=ledger[item["title"]]
        return next(option["id"] for option in item["options"] if option["label"]==expected)
    if item["type"]=="sql":
        statuses,threshold=sql_spec(item)
        values=",".join("'"+status+"'" for status in statuses)
        mode=data.get("sql_spec",{}).get("mode","aggregate")
        if mode=="join":
            return f"SELECT c.region,SUM(o.amount) FROM orders o JOIN customers c ON c.id=o.customer_id WHERE o.status IN ({values}) AND o.amount>={threshold} GROUP BY c.region"
        if mode=="latest_per_customer":
            return f"WITH chosen AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY customer_id ORDER BY created_seq DESC,id DESC) rn FROM orders WHERE status IN ({values}) AND amount>={threshold}) SELECT c.region,SUM(o.amount-COALESCE(o.discount,0)) FROM chosen o JOIN customers c ON c.id=o.customer_id WHERE rn=1 GROUP BY c.region"
        if mode=="refund_preaggregate":
            return f"WITH refunds_sum AS (SELECT order_id,SUM(amount) total FROM refunds WHERE status='settled' GROUP BY order_id) SELECT c.region,SUM(o.amount-COALESCE(r.total,0)) FROM orders o JOIN customers c ON c.id=o.customer_id LEFT JOIN refunds_sum r ON r.order_id=o.id WHERE o.status IN ({values}) AND o.amount>={threshold} GROUP BY c.region"
        return f"SELECT region, SUM(amount) FROM orders WHERE status IN ({values}) AND amount >= {threshold} GROUP BY region"
    if "requests" in data:
        return max(0,data["requests"]*data["allowed_per_mille"]//1000-data["failures"])
    if "request_keys" in data:
        unique=[]
        for key in data["request_keys"]:
            if key not in unique: unique.append(key)
        return len(unique)
    if "start" in data:
        answer=data["start"]
        for command in data["steps"]:
            if command["operation"]=="add": answer+=command["value"]
            else: answer*=command["value"]
        return answer
    if "budget_mib" in data:
        return data["budget_mib"]-data["overhead_mib"]-sum(data["requests_mib"])
    if "uniform_random_bytes" in data:
        return data["uniform_random_bytes"]*8
    if "elements" in data:
        return [entry["id"] for entry in data["elements"] if not entry["label"].strip()]
    if "current_company" in data and "grants" in data:
        return [entry["id"] for entry in data["grants"] if entry["company"]==data["current_company"] and entry["active"] and not entry["expired"]]
    if "reads" in data:
        return [entry["id"] for entry in data["reads"] if entry["user"]==data["current_user"] and entry["company"]==data["current_company"] and entry["grant_active"] and not entry["expired"] and not entry["revoked"]]
    if "controls" in data:
        return [entry["id"] for entry in data["controls"] if not entry["disabled"] and (entry["name"]=="" or entry["keyboard"] is False)]
    if "tokens" in data:
        return [entry["id"] for entry in data["tokens"] if entry["used"] is False and entry["expires_at"]>data["now"] and entry["bytes"]>=data["min_bytes"]]
    if "nodes" in data:
        return [entry["id"] for entry in data["nodes"] if entry["ready"] and entry["memory_mib"]>=data["required_mib"] and (not data["require_tls"] or entry["tls_valid"])]
    if "responses" in data:
        applicable=[entry["result"] for entry in data["responses"] if entry["request_id"]==data["current_request_id"]]
        return {"result":applicable[0] if applicable else None}
    if "cases" in data:
        return [entry["id"] for entry in data["cases"] if data["lower"]<=entry["value"]<=data["upper"]] if data["inclusive"] else [entry["id"] for entry in data["cases"] if data["lower"]<entry["value"]<data["upper"]]
    if "lower" in data:
        return [data["upper"]+1,data["lower"],data["upper"],data["lower"]-1]
    if "events" in data:
        if "entity" in data["events"][0]:
            answer={}
            # Independent sorted replay instead of generator's online max update.
            for entry in sorted(data["events"],key=lambda row:row["version"]):
                answer[entry["entity"]]=entry["value"]
            return answer
        buckets=defaultdict(set)
        for entry in data["events"]: buckets[entry["id"]].add(entry["amount"])
        conflicts=sorted(key for key,values in buckets.items() if len(values)>1)
        return {"total":sum(next(iter(values)) for values in buckets.values() if len(values)==1),"conflicts":conflicts}
    if "rows" in data:
        rows=data["rows"]
        if "visits" in rows[0]:
            return sum(entry["conversions"] for entry in rows)/sum(entry["visits"] for entry in rows)*100
        included=[entry for entry in rows if not(data["exclude_flagged"] and entry["exclude"])]
        den=sum(entry["exposed"] for entry in included)
        return {"conversion_percent":round(sum(entry["success"] for entry in included)/den*100,2) if den else None}
    raise ValueError("No independent solver for this public task")
