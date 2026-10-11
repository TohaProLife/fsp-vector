"""Own versioned task families. All inputs are data, never executable user code.

Difficulty labels are author-initial design hypotheses, not empirically calibrated
IT grades. The programmatic reference suite checks oracle correctness only.
"""

import random
import hashlib
from copy import deepcopy
from .taxonomy import COMPETENCY_LABELS, GRADES, SPECIALIZATIONS
from .scenarios import SCENARIOS
from .advanced import advanced_practical, advanced_manifest

BANK_VERSION = "vector-bank-2.0-advanced-data"
ITEM_LIMIT = 12

# Each option set is a complete scenario with a constrained, objectively defensible
# answer. The chosen example varies within a slot without changing its competency.
CHOICES = {
    "api": [
        ("Повторный запрос", "Клиент повторил POST с тем же Idempotency-Key после потери ответа. Первая операция уже зафиксирована. Как должен действовать сервер?", "Вернуть сохранённый результат этой операции", ["Повторно выполнить бизнес-операцию", "Всегда вернуть 500", "Очистить журнал ключей"]),
        ("Изменение контракта", "У POST /payments один и тот же ключ идемпотентности, но новый запрос содержит другую сумму. Контракт запрещает это. Что корректно?", "Отклонить конфликт и сохранить исходную операцию", ["Применить новую сумму", "Молча вернуть новый результат", "Создать второй платёж с тем же ключом"]),
    ],
    "sql": [
        ("Отсутствующая связь", "Нужно вернуть всех клиентов, включая клиентов без заказов. Какая конструкция сохраняет строки клиентов?", "LEFT JOIN orders по идентификатору клиента", ["INNER JOIN orders", "CROSS JOIN без фильтра", "WHERE orders.id IS NOT NULL после LEFT JOIN"]),
        ("NULL в агрегате", "Столбец discount допускает NULL. Требуется считать неизвестную скидку как 0. Какое выражение корректно?", "SUM(COALESCE(discount, 0))", ["SUM(discount = NULL)", "COUNT(discount)", "SUM(discount IS NULL)"]),
    ],
    "reliability": [
        ("Повторная доставка", "Система доставки гарантирует at-least-once. Какое свойство обработчика предотвращает двойное начисление?", "Атомарная фиксация бизнес-изменения и обработанного event_id", ["Удаление event_id перед обработкой", "Предположение, что брокер никогда не повторяет", "Только локальный sleep"]),
        ("Событие после commit", "Данные записаны в БД, а отправка сообщения упала. Как избежать потери события без распределённой транзакции?", "Транзакционный outbox и идемпотентная доставка", ["Отправить сначала сообщение и забыть данные", "Подавить исключение", "Держать событие только в памяти"]),
    ],
    "testing": [
        ("Конкурентное принятие", "Два запроса одновременно принимают одно приглашение. Какую проверку нужно включить для одного company-scoped разрешения контактов?", "Проверить атомарность перехода и уникальность grant", ["Только цвет кнопки после клика", "Только HTTP 200 одного запроса", "Только длину сообщения"]),
        ("Независимый oracle", "Тест ожидаемого значения повторяет точную функцию реализации. Почему такой тест слабее независимого примера?", "Одинаковая ошибка может быть повторена в ожидаемом результате", ["Тесты не должны иметь ожидаемых значений", "Любой повтор гарантирует правильность", "Случайный seed полностью решает проблему"]),
    ],
    "javascript": [
        ("Асинхронный порядок", "Обработчик уже выполнил синхронный код. В очереди Promise.then и setTimeout(..., 0). Что обычно выполняется первым в браузерном event loop?", "Microtask из Promise.then", ["Callback setTimeout всегда первый", "Они выполняются параллельно в одном JS потоке", "Порядок зависит от имени функции"]),
        ("Обновление массива", "Для React state требуется изменить один элемент массива, сохранив возможность сравнения ссылок. Что корректно?", "Создать новый массив и новый изменённый объект", ["Мутировать старый массив без setState", "Только изменить DOM вручную", "Сохранить старую ссылку и удалить ключ"]),
    ],
    "state": [
        ("Гонка поиска", "Пользователь ввёл A, затем B. Ответ A пришёл последним. Как предотвратить показ устаревшего A?", "Применять ответ только для текущего request_id", ["Всегда показывать последний по времени ответ", "Добавить любой фиксированный sleep", "Удалить loading состояние"]),
        ("Авторизация кнопки", "Кнопка контактов скрыта CSS до принятия предложения. Что обязательно для конфиденциальности?", "Серверная проверка grant при каждом чтении контактов", ["Только display:none", "Включить контакты в HTML и спрятать", "Назвать поле secret в JSON"]),
    ],
    "accessibility": [
        ("Кнопка с иконкой", "Кнопка содержит только SVG без видимого текста. Что нужно для её понятного имени скринридеру?", "Доступное имя через aria-label или связанный текст", ["Только цвет фона", "Только box-shadow", "Только hover animation"]),
        ("Открытие диалога", "Модальное окно блокирует фон. Какая схема управления клавиатурой корректна?", "Фокус внутри, Escape закрывает, фокус возвращается инициатору", ["Фокус теряется на body навсегда", "Убрать outline у всех элементов", "Потребовать мышь для закрытия"]),
    ],
    "web_security": [
        ("Недоверенный текст", "Описание вакансии содержит <script>. Требуется показать его как обычный пользовательский текст. Как безопаснее?", "Вывести через экранирующий текстовый API", ["Вставить как доверенный innerHTML", "Удалить только слово script", "Скрыть текст цветом"]),
        ("Сессия и CSRF", "Браузер автоматически отправляет cookie сессии. Как защищать изменяющие операции от межсайтовых запросов?", "Проверять CSRF token и Origin вместе с cookie policy", ["Передавать токен в публичный URL", "Проверять только наличие cookie", "Разрешить CORS всем origin с credentials"]),
    ],
    "test_design": [
        ("Граница диапазона", "Проверяется целое x из закрытого диапазона [L,U]. Какой набор покрывает обе границы и ближайшие ошибки?", "L-1, L, U, U+1", ["Только L+1", "Только середина диапазона", "Только отрицательные числа независимо от L"]),
        ("Состояния договора", "Статусы sent, accepted, declined. Отказ терминальный. Какую проверку нужно добавить?", "После declined повторный accept не создаёт grant", ["Любой accept после declined всегда успешен", "Проверить только текст sent", "Проверить один скриншот без серверного состояния"]),
    ],
    "observability": [
        ("Error budget", "SLO измеряется по доле успешных запросов. Как считать ошибочный бюджет?", "Допустимая доля ошибок × число всех запросов", ["Умножить только ошибки на SLO", "Считать только максимальную задержку", "Не учитывать неуспешные запросы"]),
        ("Диагностика p95", "Средняя задержка мала, но p95 выросла. Что отражает p95 при согласованном методе вычисления процентиля?", "Порог, не выше которого завершились не менее 95% измеренных запросов", ["Вероятность успешного найма", "Максимальную задержку каждого запроса", "Среднее только самых быстрых 95 запросов"]),
    ],
    "containers": [
        ("Секреты образа", "Контейнеру нужен пароль БД. Как избежать сохранения пароля в слоях образа?", "Подать секрет при запуске из защищённого хранилища", ["Записать пароль в Dockerfile ENV", "Включить пароль в публичный label", "Добавить пароль в Git историю"]),
        ("Сбой миграции", "Миграция схемы не завершилась. Ready endpoint должен разрешать трафик?", "Нет, readiness сообщает неготовность до совместимой схемы", ["Да, всегда 200", "Отключить аудит ошибки", "Вернуть готовность по наличию favicon"]),
    ],
    "networking": [
        ("Повтор запроса", "Можно безопасно автоматически повторять операцию с побочным эффектом, только если…", "Есть согласованный механизм идемпотентности операции", ["HTTP клиент быстро работает", "Ответ большой", "Сервер случайно выбрал тот же порт"]),
        ("TLS проверка", "Клиент подключается к сервису через HTTPS. Что нельзя отключать в рабочем режиме?", "Проверку сертификата и имени узла", ["Вывод debug логов", "Сортировку JSON ключей", "Анимацию загрузки"]),
    ],
    "statistics": [
        ("Смешение групп", "Конверсия изменена вместе с источником трафика. Достаточно общей разницы для причинного вывода?", "Нет, изменение состава трафика может смешивать эффект", ["Да, любая разница причинная", "Да, если округлить до процента", "Да, если выборка имеет красивые графики"]),
        ("Знаменатель", "Для сравнения конверсии нужно заранее зафиксировать…", "Определение события успеха, популяции и знаменателя", ["Только цвет графика", "Желаемый ответ", "Любой удобный знаменатель после анализа"]),
    ],
    "data_quality": [
        ("Дедупликация", "У данных повторяется event_id. Почему нужно определить правило перед суммированием?", "Дубликаты могут завысить метрику, а конфликтующие payload требуют явной политики", ["Дубликаты всегда полезны для точности", "Все одинаковые суммы являются дубликатами", "Можно удалить произвольную половину строк"]),
        ("Пропуски", "Поле revenue неизвестно и равно NULL. Как корректно представить это в отчёте?", "Отделить неизвестное от достоверного нуля и описать обработку", ["Всегда объявить NULL достоверным нулём", "Скрыть все пропуски без пояснения", "Заменить NULL самым большим числом"]),
    ],
    "interpretation": [
        ("Синтетическая оценка", "Алгоритм хорошо ранжирует вымышленные профили с модельными метками. Что это доказывает?", "Результат на указанном синтетическом benchmark с его ограничениями", ["Гарантию реального найма", "Рыночную точность без наблюдений", "Юридическую верификацию ФСП"]),
        ("Корреляция", "Есть положительная корреляция участия в соревнованиях и оценки теста. Какой вывод корректен?", "Связь наблюдается; причинность требует отдельного дизайна", ["Любое участие автоматически повышает грейд", "Корреляция доказывает причину", "Командная победа подтверждает все навыки каждого участника"]),
    ],
    "authorization": [
        ("Чужое приглашение", "Пользователь знает UUID приглашения другой компании. Какая проверка обязательна?", "Сервер проверяет принадлежность пользователя и scope компании", ["Достаточно непредсказуемого UUID", "Достаточно скрыть ссылку в меню", "Проверить только факт логина"]),
        ("Отзыв разрешения", "Кандидат отозвал grant контактов. Что требуется для будущих чтений?", "Проверять актуальное разрешение и не отдавать старые контакты из кэша", ["Старый экспорт навсегда разрешает любые API чтения", "Продолжать выдавать до следующего рестарта", "Удалить только кнопку в интерфейсе"]),
    ],
    "cryptography": [
        ("Хранение пароля", "Какой подход подходит для хранения пользовательского пароля?", "Солёный медленный password hash с согласованными параметрами", ["Обратимое шифрование общей константой", "Обычный SHA-256 без salt как универсальное решение", "Открытый текст с закрытой CSS кнопкой"]),
        ("Случайный токен", "Токен восстановления доступа должен быть…", "Непредсказуемым, одноразовым, ограниченным по времени и храниться безопасно", ["Датой рождения пользователя", "Последовательным номером пользователя", "Общим бессрочным словом для всех"]),
    ],
    "incident_response": [
        ("Сохранение доказательств", "Подозревается утечка токена. Какой первый план действий разумен?", "Ограничить ущерб, отозвать токен, сохранить релевантный аудит и выяснить scope", ["Удалить все логи до анализа", "Публиковать токен в отчёте", "Сделать вид, что запрос успешен"]),
        ("Сигнал сканирования", "Один запрещённый запрос на чужой ID автоматически доказывает компрометацию аккаунта?", "Нет; это сигнал, нуждающийся в контексте и расследовании", ["Да, всегда", "Да, если UUID длинный", "Нет, поэтому можно не логировать"]),
    ],
}


def _choice(rng, competency, grade, kind,exposure=None):
    pool=CHOICES[competency] if grade=="intern" else SCENARIOS[competency][grade]
    if exposure:
        counts=[max(0,int(exposure.get("concept."+hashlib.sha256(row[0].encode("utf-8")).hexdigest()[:12],0))) for row in pool]
        minimum=min(counts)
        pool=[row for row,count in zip(pool,counts) if count==minimum]
    title, prompt, answer, distractors = rng.choice(pool)
    labels = [answer, *distractors]
    rng.shuffle(labels)
    options = [{"id": f"opt-{rng.getrandbits(48):012x}", "label": label} for label in labels]
    oracle = options[labels.index(answer)]["id"]
    return {"title": title, "prompt": prompt, "type": "single_choice", "options": options, "_oracle": {"kind": "choice", "expected": oracle}, "_family": "concept."+hashlib.sha256(title.encode("utf-8")).hexdigest()[:12]}


def _analysis(rng, competency, level):
    n = 3 + level * 2
    if competency in ("sql", "statistics", "observability", "interpretation"):
        if competency == "observability":
            requests = rng.choice([10_000, 20_000, 50_000, 100_000])
            per_mille = rng.choice([1, 2, 5, 10])
            failures = rng.randrange(1, int(requests * per_mille / 1000) * 2)
            budget = requests * per_mille // 1000
            return {"title": "Остаток бюджета ошибок", "prompt": f"SLO допускает {per_mille / 10:g}% ошибочных запросов из {requests}. За период ошибок {failures}. Сколько ещё ошибок допустимо? Если бюджет исчерпан, ответьте 0. Ответ — целое число.", "type": "number", "public_cases": {"requests": requests, "allowed_per_mille": per_mille, "failures": failures}, "_oracle": {"kind": "number", "expected": max(0, budget-failures)}}
        rows = [{"group": "A" if i % 2 == 0 else "B", "visits": rng.randrange(10, 50) * 10, "conversions": rng.randrange(1, 8) * 5} for i in range(n)]
        visits = sum(row["visits"] for row in rows)
        conversions = sum(row["conversions"] for row in rows)
        prompt = "Рассчитайте общую конверсию: сумма conversions / сумма visits × 100. Ответ в процентах, допускается погрешность 0,01 п.п. Нельзя усреднять проценты строк без весов."
        return {"title": "Взвешенная конверсия", "prompt": prompt, "type": "number", "public_cases": {"rows": rows}, "_oracle": {"kind": "number", "expected": conversions / visits * 100, "tolerance": .010001}}
    if competency == "javascript":
        start = rng.randrange(1, 10)
        steps = [{"operation": rng.choice(["add", "multiply"]), "value": rng.randrange(1, 5)} for _ in range(n)]
        value = start
        for step in steps:
            value = value + step["value"] if step["operation"] == "add" else value * step["value"]
        return {"title": "Трассировка преобразований", "prompt": "Начните со start. Примените steps по порядку: add прибавляет, multiply умножает. Каково итоговое целое значение? Это задача чтения алгоритма; пользовательский код не запускается.", "type": "number", "public_cases": {"start": start, "steps": steps}, "_oracle": {"kind": "number", "expected": value}}
    if competency in ("api", "networking"):
        ids = [f"r{rng.randrange(10,99)}" for _ in range(n)]
        ids.extend(rng.sample(ids, min(2+level, len(ids))))
        rng.shuffle(ids)
        return {"title": "Идемпотентные операции", "prompt": "Каждый уникальный ключ означает ровно одну зафиксированную операцию. Повтор ключа возвращает прежний результат. Сколько бизнес-операций должно быть выполнено?", "type": "number", "public_cases": {"request_keys": ids}, "_oracle": {"kind": "number", "expected": len(set(ids))}}
    if competency in ("reliability", "data_quality", "state"):
        entities = ["a", "b", "c"][:min(2+level,3)]
        events = [{"entity": rng.choice(entities), "version": i + 1, "value": rng.randrange(10,99)} for i in range(n)]
        rng.shuffle(events)
        final = {}
        for event in events:
            if event["entity"] not in final or event["version"] > final[event["entity"]]["version"]:
                final[event["entity"]] = event
        expected = {entity: event["value"] for entity, event in final.items()}
        return {"title": "Актуальное состояние", "prompt": "События могут приходить не по порядку. Для каждой entity нужно значение с максимальной version. Ответьте JSON-объектом entity → value. Версии уникальны в этом наборе.", "type": "json", "public_cases": {"events": events}, "_oracle": {"kind": "json", "expected": expected}}
    if competency in ("testing", "test_design"):
        low = rng.randrange(1, 40)
        high = low + rng.randrange(5,50)
        return {"title": "Граничные проверки", "prompt": f"Сервис принимает целое значение в закрытом диапазоне [{low}, {high}]. Верните JSON-массив четырёх уникальных граничных значений: непосредственно снаружи каждой границы и сами границы. Порядок не важен.", "type": "json", "public_cases": {"lower": low, "upper": high}, "_oracle": {"kind": "set", "expected": [low-1,low,high,high+1]}}
    if competency == "accessibility":
        elements = [{"id": f"button-{i}", "label": "" if rng.random() < .55 else f"Действие {i}", "icon_only": True} for i in range(n)]
        expected = [element["id"] for element in elements if not element["label"].strip()]
        return {"title": "Проверка доступного имени", "prompt": "Для каждой кнопки label — её единственное доступное имя. Найдите кнопки без непустого имени. Верните JSON-массив их id, порядок не важен.", "type": "json", "public_cases": {"elements": elements}, "_oracle": {"kind": "set", "expected": expected}}
    if competency == "containers":
        limit = rng.randrange(4,10) * 128
        requests = [rng.randrange(1,5)*64 for _ in range(n)]
        return {"title": "Бюджет памяти", "prompt": "Планировщик располагает budget_mib. Резервирование requests_mib суммируется; overhead_mib обязателен. Сколько MiB останется? При превышении ответ отрицательный.", "type": "number", "public_cases": {"budget_mib": limit, "requests_mib": requests, "overhead_mib": 64}, "_oracle": {"kind": "number", "expected": limit-sum(requests)-64}}
    if competency == "cryptography":
        bytes_count = rng.choice([16,20,24,32])
        return {"title": "Энтропия токена", "prompt": f"Токен состоит из {bytes_count} независимых равномерных случайных байтов. Сколько бит энтропии в токене? Кодирование в hex не меняет энтропию.", "type": "number", "public_cases": {"uniform_random_bytes": bytes_count}, "_oracle": {"kind": "number", "expected": bytes_count*8}}
    if competency in ("authorization", "web_security", "incident_response"):
        company = f"company-{rng.randrange(1,9)}"
        records = [{"id": f"grant-{i}", "company": company if i % 2 else "other", "active": rng.choice([True,False]), "expired": rng.choice([True,False])} for i in range(n)]
        expected = [row["id"] for row in records if row["company"] == company and row["active"] and not row["expired"]]
        return {"title": "Проверка области доступа", "prompt": "Для current_company допустимы только active grants без expired. Верните JSON-массив id действующих разрешений именно этой компании; порядок не важен.", "type": "json", "public_cases": {"current_company": company, "grants": records}, "_oracle": {"kind": "set", "expected": expected}}
    raise ValueError(f"Unknown competency {competency}")


def _sql_practice(rng, level, mutation):
    if level>=1:
        return _relational_sql(rng,level,mutation)
    rows = []
    for index in range(6+level*3):
        rows.append([index+1, rng.choice(["A", "B", "C"]), rng.randrange(1,12)*10, rng.choice(["paid", "pending", "cancelled"])])
    # Force a relevant record, but keep distribution/aggregates instance-specific.
    rows[0][3] = "paid"
    dataset = {"orders": {"columns": {"id": "INTEGER", "region": "TEXT", "amount": "INTEGER", "status": "TEXT"}, "rows": rows}}
    threshold = rng.choice([20,40,60]) if level >= 2 else 0
    statuses = ["paid", "pending"] if mutation else ["paid"]
    expected = {}
    for _, region, amount, status in rows:
        if status in statuses and amount >= threshold:
            expected[region] = expected.get(region,0)+amount
    prompt = f"Таблица orders(id, region, amount, status) приведена ниже. Напишите один SELECT: region и SUM(amount), по регионам; учитывайте status {statuses} и amount >= {threshold}. Регионы без подходящих строк исключить. Имена столбцов результата и порядок строк не оцениваются. SQL работает только в отдельной ограниченной in-memory базе задания."
    return {"title": "SQL: агрегация по условиям" + (" — новые условия" if mutation else ""), "prompt": prompt, "type": "sql", "starter_code": "SELECT region, SUM(amount)\nFROM orders\nWHERE ...\nGROUP BY region;", "public_cases": {"tables": dataset,"sql_spec":{"mode":"aggregate","statuses":statuses,"threshold":threshold}}, "_oracle": {"kind": "sql", "dataset": dataset, "rows": [[key,value] for key,value in expected.items()]}}


def _relational_sql(rng,level,mutation):
    customers=[[i,rng.choice(["A","B","C"])] for i in range(1,5)]
    orders=[]
    for index in range(14):
        orders.append([index+1,rng.randrange(1,6),rng.randrange(1,12)*10,rng.choice(["paid","pending","cancelled"]),rng.randrange(1,6),None if rng.random()<.35 else rng.randrange(0,4)*5])
    orders[0][3]="paid"
    dataset={"customers":{"columns":{"id":"INTEGER","region":"TEXT"},"rows":customers},"orders":{"columns":{"id":"INTEGER","customer_id":"INTEGER","amount":"INTEGER","status":"TEXT","created_seq":"INTEGER","discount":"INTEGER"},"rows":orders}}
    statuses=["paid","pending"] if mutation else ["paid"]
    threshold=rng.choice([0,20,40])
    mode="join" if level==1 else "latest_per_customer" if level==2 else "refund_preaggregate"
    spec={"mode":mode,"statuses":statuses,"threshold":threshold}
    customer_regions=dict(customers)
    selected=[row for row in orders if row[1] in customer_regions and row[3] in statuses and row[2]>=threshold]
    prompt=f"Таблицы приведены в tables. Верните region и сумму по соответствующим customers. Orders без существующего customer исключаются. Сначала отфильтруйте orders по status {statuses} и amount >= {threshold}. "
    if level==2:
        winners={}
        for row in selected:
            if row[1] not in winners or (row[4],row[0])>(winners[row[1]][4],winners[row[1]][0]): winners[row[1]]=row
        selected=list(winners.values())
        prompt+="После фильтра выберите ровно ОДИН последний order каждого customer: максимальный created_seq, при равенстве больший id. Вклад order = amount - COALESCE(discount,0). "
    elif level==3:
        refunds=[]
        for i in range(12): refunds.append([i+1,rng.randrange(1,15),rng.randrange(1,5)*5,rng.choice(["settled","pending"])])
        # At least one order has several eligible refunds, exercising fanout.
        refunds.extend([[99,selected[0][0],5,"settled"],[100,selected[0][0],10,"settled"]] if selected else [])
        dataset["refunds"]={"columns":{"id":"INTEGER","order_id":"INTEGER","amount":"INTEGER","status":"TEXT"},"rows":refunds}
        spec["refund_status"]="settled"
        prompt+="Вклад order = amount минус сумма refunds с тем же order_id и refund.status='settled'. У order может быть несколько refunds; amount нельзя умножать при JOIN. Если refunds нет — их сумма 0. Discount в этом варианте не входит в расчёт. Допустим отрицательный вклад. "
    else:
        prompt+="Вклад каждого отфильтрованного order = amount; discount в этом варианте не входит в расчёт. "
    prompt+="Регионы без подходящих orders не выводить. Один readonly SELECT (CTE/window допустимы), порядок строк и имена result columns не оцениваются."
    expected={}
    for row in selected:
        contribution=row[2]
        if level==2: contribution-=row[5] or 0
        if level==3: contribution-=sum(refund[2] for refund in dataset["refunds"]["rows"] if refund[1]==row[0] and refund[3]=="settled")
        region=customer_regions[row[1]]
        expected[region]=expected.get(region,0)+contribution
    return {"title":{"join":"SQL: JOIN без потери условий","latest_per_customer":"SQL: window и NULL","refund_preaggregate":"SQL: предотвращение aggregate fanout"}[mode],"prompt":prompt,"type":"sql","starter_code":"WITH filtered AS (\n  SELECT * FROM orders WHERE ...\n)\nSELECT ...;","public_cases":{"tables":dataset,"sql_spec":spec},"_family":"data.sql-"+mode,"_oracle":{"kind":"sql","dataset":dataset,"rows":[[key,value] for key,value in expected.items()]}}


def _event_practice(rng, level, mutation):
    ids = [f"evt-{rng.randrange(10,999)}" for _ in range(4+level)]
    ids = list(dict.fromkeys(ids))
    events = [{"id": value, "amount": rng.randrange(1,20)*5} for value in ids]
    stream = events + deepcopy(rng.sample(events, min(2,len(events))))
    if mutation:
        conflict = deepcopy(events[0]); conflict["amount"] += 7
        stream.append(conflict)
    rng.shuffle(stream)
    accepted = {}; conflicts = set()
    for event in stream:
        if event["id"] in accepted:
            if accepted[event["id"]] != event["amount"]:
                conflicts.add(event["id"])
        else:
            accepted[event["id"]] = event["amount"]
    # Explicitly remove conflict IDs from the settlement. This makes the result
    # independent of which conflicting payload happened to arrive first.
    total = sum(value for key,value in accepted.items() if key not in conflicts)
    expected = {"total": total, "conflicts": sorted(conflicts)}
    return {"title": "Сверка повторной доставки" + (" — конфликт payload" if mutation else ""), "prompt": "Каждый id учитывается один раз. Если для id встречаются разные amount, исключите ВСЕ его записи из суммы и добавьте id в conflicts. Верните JSON {\"total\": число, \"conflicts\": [id...]} с отсортированными conflicts. Обработка идёт по данным, пользовательский код не запускается.", "type": "json", "public_cases": {"events": stream}, "_oracle": {"kind": "json", "expected": expected}}


def _practical(rng, competency, level, mutation):
    if level >= 2 and competency != "sql":
        return advanced_practical(rng,competency,level,mutation)
    if competency in ("sql", "statistics", "interpretation"):
        return _sql_practice(rng,level,mutation) if competency == "sql" else _statistics_practice(rng,level,mutation)
    if competency in ("reliability", "data_quality", "api"):
        return _event_practice(rng,level,mutation)
    if competency in ("testing", "test_design"):
        low = rng.randrange(1,20); high = low+rng.randrange(5,20)
        rows = [{"id": f"case-{i}", "value": value} for i,value in enumerate([low-1,low,low+1,high-1,high,high+1])]
        expected = [row["id"] for row in rows if (low < row["value"] < high if mutation else low <= row["value"] <= high)]
        return {"title": "Декларативный oracle диапазона", "prompt": f"Контракт принимает x в {'открытом' if mutation else 'закрытом'} диапазоне {'(' if mutation else '['}{low}, {high}{')' if mutation else ']'}. Из cases верните JSON-массив id успешных проверок, порядок не важен. {'Контрольное изменение: границы больше не включены.' if mutation else ''}", "type": "json", "public_cases": {"cases": rows, "lower": low, "upper": high, "inclusive": not mutation}, "_oracle": {"kind": "set", "expected": expected}}
    if competency in ("javascript", "state"):
        latest = rng.randrange(4,20)
        events = [{"request_id": latest-i, "result": f"value-{rng.randrange(100,999)}"} for i in range(3+level)]
        rng.shuffle(events)
        expected = [event["result"] for event in events if event["request_id"] == latest][0]
        if mutation:
            # The current search can move while responses are in flight.
            latest += 1
            expected = None
        return {"title": "Отклонение устаревших ответов", "prompt": "Ответ применим только если request_id равен current_request_id. Верните JSON {\"result\": значение применимого ответа}; если ответа текущего запроса нет, используйте null. Это декларативная проверка гонки, а не выполнение React кода.", "type": "json", "public_cases": {"current_request_id": latest, "responses": events}, "_oracle": {"kind": "json", "expected": {"result": expected}}}
    if competency == "accessibility":
        rows = [{"id": f"control-{i}", "disabled": rng.random()<.2, "name": "" if rng.random()<.4 else "Действие", "keyboard": rng.random()>.3} for i in range(5+level)]
        expected = [row["id"] for row in rows if not row["disabled"] and (not row["name"] or not row["keyboard"])]
        return {"title": "Аудит интерактивных контролов", "prompt": "Активный control нарушает данное правило, если name пустое ИЛИ keyboard=false. Disabled controls исключены из этой проверки. Верните JSON-массив id нарушений; порядок не важен. Это ограниченная рубрика, она не заменяет полный WCAG аудит.", "type": "json", "public_cases": {"controls": rows}, "_oracle": {"kind": "set", "expected": expected}}
    if competency in ("authorization", "web_security", "incident_response"):
        user = "u-current"; company = "company-current"
        rows = [{"id": f"read-{i}", "user": rng.choice([user,"u-other"]), "company": rng.choice([company,"company-other"]), "grant_active": rng.choice([True,False]), "expired": rng.choice([True,False]), "revoked": rng.choice([True,False])} for i in range(6+level)]
        expected = [row["id"] for row in rows if row["user"] == user and row["company"] == company and row["grant_active"] and not row["expired"] and not row["revoked"]]
        return {"title": "Матрица company-scoped авторизации", "prompt": "Допускается чтение только при совпадении current_user и current_company, grant_active=true, expired=false, revoked=false. Верните JSON-массив id разрешённых reads; порядок не важен. Ни UUID, ни роль employer сами по себе не дают доступ.", "type": "json", "public_cases": {"current_user": user,"current_company": company,"reads": rows}, "_oracle": {"kind": "set", "expected": expected}}
    if competency in ("containers", "networking", "observability"):
        budget = rng.randrange(5,15)*100
        nodes = [{"id": f"node-{i}", "ready": rng.choice([True,False]), "memory_mib": rng.randrange(1,8)*100, "tls_valid": rng.choice([True,False])} for i in range(5+level)]
        expected = [row["id"] for row in nodes if row["ready"] and row["memory_mib"] >= budget and (row["tls_valid"] if mutation else True)]
        return {"title": "Безопасное планирование", "prompt": "Выберите node id: ready=true и memory_mib >= required_mib." + (" Контрольное изменение: дополнительно требуется tls_valid=true." if mutation else " В этом варианте tls_valid не входит в критерий.") + " Ответ — JSON-массив id, порядок не важен.", "type": "json", "public_cases": {"required_mib": budget,"nodes": nodes,"require_tls": mutation}, "_oracle": {"kind": "set", "expected": expected}}
    if competency == "cryptography":
        now = rng.randrange(1000,5000)
        tokens = [{"id": f"token-{i}", "expires_at": now+rng.randrange(-200,200), "used": rng.choice([True,False]), "bytes": rng.choice([8,16,24,32])} for i in range(6+level)]
        min_bytes = 24 if mutation else 16
        expected = [row["id"] for row in tokens if not row["used"] and row["expires_at"] > now and row["bytes"] >= min_bytes]
        return {"title": "Проверка жизненного цикла токена", "prompt": "Токены созданы доверенным криптографическим генератором. Разрешён token, если used=false, expires_at > now, bytes >= min_bytes. Верните JSON-массив допустимых id. Эта задача проверяет policy, не доказывает криптографическую безопасность генератора.", "type": "json", "public_cases": {"now": now,"min_bytes": min_bytes,"tokens": tokens}, "_oracle": {"kind": "set", "expected": expected}}
    raise ValueError(f"Unknown practical competency {competency}")


def _statistics_practice(rng, level, mutation):
    rows = [{"segment": f"s{i}", "exposed": rng.randrange(10,60)*10, "success": rng.randrange(1,9)*5, "exclude": rng.random()<.2} for i in range(4+level)]
    selected = [row for row in rows if not row["exclude"]] if mutation else rows
    denominator = sum(row["exposed"] for row in selected)
    expected = round(sum(row["success"] for row in selected)/denominator*100,2) if denominator else None
    return {"title": "Метрика с зафиксированной популяцией", "prompt": "Верните JSON {\"conversion_percent\": значение}, округлённое до двух знаков. Формула: суммарный success / суммарный exposed × 100." + (" Контрольное изменение: строки с exclude=true исключаются из числителя И знаменателя." if mutation else " Все строки включены, exclude в этом варианте игнорируется.") + " Если знаменатель 0, значение null.", "type": "json", "public_cases": {"rows": rows,"exclude_flagged": mutation}, "_oracle": {"kind": "json", "expected": {"conversion_percent": expected}}}


def build_items(specialization, grade, rng,exposure=None):
    level = GRADES.index(grade)
    items = []
    competencies = SPECIALIZATIONS[specialization]["competencies"]
    for comp_index, competency in enumerate(competencies):
        for slot in ("short", "analysis", "practice"):
            mutation = slot == "practice" and comp_index >= 2
            if slot == "short":
                item = _choice(rng,competency,grade,slot,exposure)
            elif slot == "analysis":
                item = _analysis(rng,competency,level)
            else:
                item = _practical(rng,competency,level,mutation)
            family_id=item.get("_family") or _data_family(competency,slot)
            evidence_skills=_item_skills(competency,item)
            item.update({"id": f"item-{rng.getrandbits(80):020x}", "competency": competency, "competency_label": COMPETENCY_LABELS[competency], "slot": "mutation" if mutation else slot, "max_score": 10, "family_id": family_id, "family_version": BANK_VERSION, "difficulty_grade": grade,"evidence_skills":evidence_skills})
            if slot == "practice" and level >= 2:
                item["advanced"] = True
            if mutation:
                item["title"] = "Контрольное изменение: " + item["title"]
            items.append(item)
    # Keep mutation follow-up after its analysis while rotating competency blocks.
    blocks = [items[i:i+3] for i in range(0,len(items),3)]
    rng.shuffle(blocks)
    return [item for block in blocks for item in block]


def family_manifest():
    rows=[]
    for comp,entries in CHOICES.items():
        for title,prompt,answer,distractors in entries:
            rows.append({"id":"concept."+hashlib.sha256(title.encode("utf-8")).hexdigest()[:12],"title":title,"competency":comp,"slot":"short","grades":["intern"]})
        for grade,entries in SCENARIOS[comp].items():
            for title,prompt,answer,distractors in entries:
                rows.append({"id":"concept."+hashlib.sha256(title.encode("utf-8")).hexdigest()[:12],"title":title,"competency":comp,"slot":"short","grades":[grade]})
    known=set()
    for comp in CHOICES:
        for slot in ("analysis","practice"):
            family_id=_data_family(comp,slot)
            if family_id in known: continue
            known.add(family_id)
            supported=list(GRADES) if slot=="analysis" else ["intern"] if comp=="sql" else ["intern","junior"]
            rows.append({"id":family_id,"title":family_id.removeprefix("data."),"competency":comp,"slot":slot,"grades":supported})
    for row in rows:
        row.update({"version":BANK_VERSION,"status":"author_initial","human_review":"NOT_MEASURED","empirical_calibration":"NOT_MEASURED","automated_review":"reference_data_solver_and_structural_checks"})
    for mode,grade in (("join","junior"),("latest_per_customer","middle"),("refund_preaggregate","senior")):
        rows.append({"id":"data.sql-"+mode,"title":mode,"competency":"sql","slot":"practice","grades":[grade],"version":BANK_VERSION,"status":"author_initial","human_review":"NOT_MEASURED","empirical_calibration":"NOT_MEASURED","automated_review":"independent_python_grouping_and_SQL_solution"})
    rows.extend({**row,"version":BANK_VERSION} for row in advanced_manifest())
    return rows


def _data_family(competency,slot):
    analysis={"sql":"weighted-conversion","statistics":"weighted-conversion","interpretation":"weighted-conversion","observability":"error-budget","javascript":"operation-trace","api":"idempotency-count","networking":"idempotency-count","reliability":"versioned-state","state":"versioned-state","data_quality":"versioned-state","testing":"closed-boundaries","test_design":"closed-boundaries","accessibility":"accessible-name","containers":"memory-budget","cryptography":"token-entropy","authorization":"company-grants","web_security":"company-grants","incident_response":"company-grants"}
    practice={"sql":"sql-filter-aggregate","statistics":"population-conversion","interpretation":"population-conversion","reliability":"conflicting-event-reconciliation","data_quality":"conflicting-event-reconciliation","api":"conflicting-event-reconciliation","testing":"range-contract-mutation","test_design":"range-contract-mutation","javascript":"request-race","state":"request-race","accessibility":"control-accessibility","authorization":"authorization-matrix","web_security":"authorization-matrix","incident_response":"authorization-matrix","containers":"bounded-scheduling","networking":"bounded-scheduling","observability":"bounded-scheduling","cryptography":"token-lifecycle"}
    return "data."+(analysis if slot=="analysis" else practice)[competency]


def _item_skills(competency,item):
    # Scope is determined by the actual item, not every technology associated
    # with a role. Generic request races do not certify React implementation.
    return {"api":["API"],"sql":["SQL"],"reliability":["Идемпотентность"],"testing":["Unit testing"],"javascript":["JavaScript concepts"],"state":["UI state"],"accessibility":["Доступность"],"web_security":["Web security"],"test_design":["Test design"],"observability":["SLO"],"containers":["Container concepts"],"networking":["HTTP concepts"],"statistics":["Статистика"],"data_quality":["Data quality"],"interpretation":["Data interpretation"],"authorization":["Authorization"],"cryptography":["Cryptography concepts"],"incident_response":["Incident response"]}[competency]
