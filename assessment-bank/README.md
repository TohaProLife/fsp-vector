# Банк ФСП Вектор

Это собственные авторские сценарии и генераторы. Внешние репозитории участников не использовались. `manifest.json` считает содержательные контракты families, а не сочетания специализации и случайного ID. Сейчас 186 families: 144 самостоятельных concept-сценария, 22 базовых data-семейства и 20 сложных контрактов Middle/Senior по десяти алгоритмическим темам. Разница Middle/Senior задаётся дополнительными условиями, а не размером массива. Предметные сценарии находятся в `services/api/app/engines/scenarios.py`; генераторы — в `bank.py` и `advanced.py`.

Каждая форма: 12 заданий, четыре компетенции × три наблюдения. Четыре коротких сценария, четыре анализа, две практические задачи и две контрольные мутации. Продолжительность 40 минут. Предварительная рубрика: общий результат ≥70, каждая competency ≥50, практика ≥60. Middle/Senior дополнительно требуют четыре сложные практические темы: средний advanced ≥60/75 соответственно и каждая advanced competency ≥50. Поля JSON имеют равный вес; ошибка указанного публично критического поля ограничивает балл задачи 40%. Поэтому даже общий91.67 не компенсирует пропущенную сложную тему. Intern/Junior остаются бинарными, Middle/Senior включают частичный балл. `STRONG_PASS` ≥85 и практика ≥75 не присваивает более высокий грейд. Рубрика хранится в попытке: старые v1 формы не получают новые ограничения задним числом.

Различия сложности — авторские гипотезы: Intern чтение базового контракта; Junior применение конкретного правила; Middle диагностика конфликтов, NULL/окна, races, ретраи; Senior ограниченные системные tradeoffs, транзакционные аномалии, изменение версии, tenant scope, эксплуатационные инциденты. По SQL практические маршруты различаются содержательно: aggregation → JOIN → latest-per-customer/window/NULL → preaggregated refunds против fanout.

Сложная практика включает version conflict/tombstone/quarantine, optimistic rollback, минимальное mutation risk cover, grant revoke и stale cache, rollout capacity/schema/zone, retry deadline/token budget, multi-window SLO, фиксированные веса популяции/Simpson reversal, key activation/revocation и nested dialog focus. Это ограниченные модели с публичными условиями и отдельными public-data reference solvers; они не доказывают production опыт. Значения порогов и 40 минут пока авторские, время/сопоставимость на людях не измерены.

`need_blueprint` связывает snapshot доступной потребности с точными измеримыми навыками. `generate_need_assessment` сохраняет общий blueprint, выставляет `scope=employer_need_practice`, SHA256 snapshot и явно показывает непроверяемые Python/React/framework требования. Результат имеет источник NEED_PRACTICE_OBSERVED, не присваивает категорию и не закрывает formal must-have. Доступ к вакансии/собственному приглашению проверяет API.

У каждой concept competency/grade два самостоятельных сценария. На старте можно передать серверный `exposure={family_id:seen_count}`; выбираются наименее показанные совместимые scenarios. Общие data-семейства параметризуются и используют контрольные условия. Важно: банк конечен; прочтение полного банка/освоение метода и удалённый помощник могут решить всё. Exposure не является гарантией защиты от утечки.

В публичных DTO есть только allowlist полей. Seed, oracle, family IDs и author review ledger сервер не отдаёт. Feedback после сдачи показывает области/баллы, без полного активного answer key. `author-review-ledger.json` — локальный тестовый артефакт исходного проекта, а не frontend asset и не отдельный API. После будущей публикации исходников он не считается секретом.

`evidence_skills` задаётся каждым реально проверенным item. Итоговое evidence рассчитывается по этим items с минимумом двух наблюдений. Выбранный Python/FastAPI/PostgreSQL/React стек не превращается в подтверждение реализации этих технологий. Возвращаются `tested_skills`, `unmeasured_requested_skills`, `route` и ограниченный scope. SQL SELECT в SQLite не подтверждает PostgreSQL-specific практику; concept PostgreSQL scenario остаётся отдельным ограниченным наблюдением.

Пользовательский Python/JavaScript/shell не выполняется. SQL работает в новой memory DB только с синтетическими таблицами задания: authorizer, query_only, whitelist функций, запрет файлов/ATTACH/PRAGMA/schema, 100000 VM steps, ≤200 input rows, ≤200 result rows и 12КБ query. JSON обрабатывается как данные с лимитами глубины/числа узлов. Для произвольного кода нужен внешний изолированный runner; основной режим честно сообщает его отсутствие.

Программный review data-oracle использует отдельные reference solvers, получающие только public prompt/data; SQL также решается независимой Python группировкой. Concept choices проверяются структурно и по авторскому ledger. Человеческая semantic review, эквивалентность форм и соответствие IT грейдам: **NOT_MEASURED**. `expert_initial` в API — технический статус начальной рубрики, не утверждение о завершённом внешнем экспертном пилоте.

По официальному QA B4 выполнена отдельная [synthetic test-retest/item discrimination procedure](../evaluation/reports/assessment-stability.md) с фиксированными public-method profiles и locked seed. Ordinary grader, raw category/UNCONFIRMED, item-rest без собственного задания и null при нулевой дисперсии. Нестабильные пограничные профили, negative correlations и non-monotonic flags сохранены; банк/пороги под результаты не изменялись. Synthetic separation не является human calibration.

Первичные материалы, использованные для проверки базовых концепций:

- [PostgreSQL transaction isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — границы изоляции и retry.
- [React useEffect](https://react.dev/reference/react/useEffect) — lifecycle и очистка эффектов.
- [OWASP authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) — проверки разрешений объекта/контекста.
- [Google SRE objectives](https://sre.google/sre-book/service-level-objectives/) — определение SLI/SLO и популяции.

Ни один материал не задаёт профессиональные grade cutoffs этого банка. Сценарии и их ограничения авторские.

Воспроизведение: `python -m evaluation.generate_data --population 3000`, `python -m evaluation.run --seeds 100`. Проверка domain invariants: `PYTHONPATH=services/api:. python -m unittest discover -s services/api/tests/engines -v` (PowerShell: `$env:PYTHONPATH='services/api;.'`).

Для опроса/старта catalog возвращает по направлению `allowed_contexts` (атомарные канонические значения), `default_contexts` и `context_aliases`. Например, REST API канонизируется в API; Java остаётся неподдерживаемым Backend контекстом. Полный catalog stack descriptor и его атомарные части одинаково принимаются. `requested_stack` сохраняет ввод пользователя, `context_stack` нормализует совместимый маршрут; ни одно из них не расширяет `tested_skills` или итоговое подтверждение.
