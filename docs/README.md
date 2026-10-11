# Документация ФСП Вектор

Для первого знакомства начните с [README](../README.md) или [видео работы сервиса](https://github.com/TohaProLife/fsp-vector/releases/download/v1.0.0-final/fsp-vector-demo.mp4).

## Для жюри

- [Материалы решения](submission/README.md) — презентация, видео, документация и исходники.
- [Техническое руководство](submission/technical-guide.md) · [PDF](https://github.com/TohaProLife/fsp-vector/releases/download/v1.0.0-final/fsp-vector-technical-guide.pdf) — запуск, архитектура, экзамен, подбор и интеграции.
- [Матрица требований](submission/requirements-matrix.md) — реализация и проверки каждого требования.
- [Заметки выступления](submission/pitch-notes.md) — сценарий десятиминутной защиты.

## Для разработки

- [OpenAPI](api/openapi.json), [API](../services/api/README.md) и [интерфейс](../apps/web/README.md).
- [Архитектура](02-architecture.md) и [продуктовые механики](03-product-mechanics.md).
- [Экзамен](../services/api/app/engines/assessment.py), [подбор](../services/api/app/engines/matching.py), [банк заданий](../assessment-bank/README.md).
- [Методика оценки](../evaluation/README.md), [результаты](../evaluation/reports/latest.md) и [устойчивость тестирования](../evaluation/reports/assessment-stability.md).
- [Изолированный исполнитель кода](isolated-judge.md) и [лицензии](../THIRD_PARTY_NOTICES.md).

Отчёты в `audits` сохраняют дату и область проверки. Старый результат не подтверждает автоматически новую сборку. Ранние проектные планы описывают замысел; фактическое поведение определяется исходниками, OpenAPI и выполненными проверками.

ФСП-реестр и демонстрационные профили вымышлены. Метрики получены на синтетических данных; профессиональные грейды и результаты найма на людях пока не валидированы.
