# QAI_06_DKuznetsov

QA-агент для работы с требованиями, таск-дизайном и тест-дизайном. Проект реализует пайплайн анализа требований из Confluence, создания задач в Jira и построения тестовой модели в Qase с обеспечением трассируемости между всеми этапами.

## Обзор

Проект — это агентная система на базе [OpenCode](https://opencode.ai), построенная вокруг мультиагентного пайплайна:

1. **Анализ требований** — получение и разбор требований из Confluence.
2. **Создание задач** — декомпозиция требований на задачи в Jira.
3. **Тест-дизайн** — проектирование и создание тестовой модели в Qase.

Каждый этап выполняется профильным субагентом, а результаты передаются между этапами через структурированные Artifacts. Оркестратор координирует запуск этапов, контролирует прохождение Quality Gates и обеспечивает связь «требование → задача → тест-кейс».

## Архитектура

```
QAI_06_DKuznetsov/
├── AGENTS.md                        # Роль, scope, workflow и ограничения QA-агента
├── package.json                     # Зависимости (opencode plugin)
├── .opencode/
│   ├── agents/                      # Описание агентов
│   │   ├── orchestrator.md          #   Оркестратор пайплайна
│   │   ├── requirement-reviewer.md  #   Анализ требований (subagent)
│   │   ├── task-designer.md         #   Создание задач в Jira (subagent)
│   │   └── test-designer.md         #   Тест-модель в Qase (subagent)
│   ├── skills/                      # Скиллы этапов
│   │   ├── requirement-review/      #   Skill анализа требований
│   │   ├── task-design/             #   Skill проектирования задач
│   │   └── test-design/             #   Skill тест-дизайна
│   └── plugins/
│       ├── confluence/index.ts      # Плагин: получение страницы Confluence
│       └── pii-scanner.ts           # Плагин: поиск и маскирование PII
├── artifacts/                       # Artifacts этапов (взаимосвязь результатов)
│   ├── requirement-review/          #   Анализ требований
│   ├── jira-tasks/                  #   Задачи Jira
│   ├── test-model/                  #   Тест-модель Qase
│   └── pipeline-report/             #   Итоговый отчёт пайплайна
└── evals/                           # Оценка качества агента
    ├── eval_runner.py               #   Запуск Eval Cases
    ├── evaluator.py                 #   Проверка Expected/Forbidden свойств
    ├── dataset/                     #   Eval Cases (golden_dataset.json)
    └── results/                     #   Результаты прогона
```

### Роли

| Агент | Роль | Ответственность |
| --- | --- | --- |
| `orchestrator` | primary | Запуск субагентов, контроль Quality Gates, координация пайплайна |
| `requirement-reviewer` | subagent | Анализ требований из Confluence, формирование Requirement Review Artifact |
| `task-designer` | subagent | Проектирование и создание задач в Jira, формирование Jira Tasks Artifact |
| `test-designer` | subagent | Проектирование и создание тестовой модели в Qase, формирование Test Model Artifact |

### Пайплайн

```
Confluence ──► [requirement-reviewer] ──► Requirement Review Artifact
                                                    │
                        ┌───────────────────────────┤
                        ▼                           ▼
                  [task-designer]            [test-designer]
                        │                           │
                        ▼                           ▼
                  Jira Tasks Artifact        Test Model Artifact
                        └───────────┬───────────────┘
                                    ▼
                           Pipeline Report
```

- Этапы 2 и 3 (Jira и Qase) независимы друг от друга, но оба зависят от успешного прохождения Quality Gate 1 (анализ требований).
- Результаты этапов передаются через Artifacts по фиксированным путям `/artifacts/<artifact_name>/<version>.md`, а не через историю диалога.
- Каждый этап имеет свой Quality Gate (Gate 1–3). Пайплайн считается выполненным только после прохождения всех трёх.

## Требования к окружению

- **Python 3.12+** — для запуска Eval-набора (`evals/`).
- **Node.js / npm** — для плагинов OpenCode и пакета `@opencode/plugin`.
- **OpenCode CLI** — для запуска агента (используется в `eval_runner.py`).

### Переменные окружения

| Переменная | Назначение |
| --- | --- |
| `CONFLUENCE_URL` | Базовый URL Confluence |
| `CONFLUENCE_EMAIL` | Email для Basic-авторизации в Confluence |
| `CONFLUENCE_API_TOKEN` | API-токен Confluence |
| `CONFLUENCE_TIMEOUT` | Тайм-аут запроса к Confluence (сек., по умолчанию 30) |

Также требуются учётные данные (токены/cloudId) для доступа к Jira и Qase, используемые инструментами `Jira` и `Qase`.

## Установка

```bash
# Установить зависимости npm (плагины OpenCode)
npm install

# Установить зависимости Python для evals
pip install -r requirements.txt   # при наличии
```

## Запуск Eval-набора

Eval-набор проверяет корректность работы агента по набору Eval Cases из `evals/dataset/golden_dataset.json` и формирует отчёт в `evals/results/eval_results.json`.

```bash
# Запуск всех Eval Cases датасета
python evals/eval_runner.py

# Запуск одного конкретного Eval Case
python evals/eval_runner.py EVC-003

# Запуск нескольких Eval Cases
python evals/eval_runner.py EVC-002 EVC-003
```

Ключевые параметры:

- `CASE_ID` — один или несколько идентификаторов Eval Cases (например, `EVC-003`). Если не указан, запускаются все кейсы датасета. Кейсы, относящиеся к одной странице Confluence, выполняются за один запуск агента. При указании несуществующего ID запуск останавливается со списком доступных кейсов.

### Качество прогона

Прогон завершается статусом `PASS` или `FAIL` на основе метрик:

| Метрика | Порог |
| --- | --- |
| Pass Rate (доля успешных Eval Cases) | `>= 90.0%` |
| Expected Properties Pass Rate | `>= 90.0%` |
| Forbidden Behavior Violation Rate | `<= 10.0%` |
| Технические ошибки | `0` |

Пороги настраиваются константами `MIN_PASS_RATE`, `MIN_EXPECTED_PROPERTIES_PASS_RATE`, `MAX_FORBIDDEN_BEHAVIOR_VIOLATION_RATE`, `MAX_ERRORS` в `evals/eval_runner.py`.

## Artifacts

Значимые результаты этапов сохраняются как структурированные Artifacts в каталоге `/artifacts`:

| Artifact | Producer | Consumer |
| --- | --- | --- |
| Requirement Review Artifact | `requirement-reviewer` | `task-designer`, `test-designer` |
| Jira Tasks Artifact | `task-designer` | Этап создания задач через Jira Tool |
| Test Model Artifact | `test-designer` | Этап создания тестовых сущностей через Qase Tool |

Artifacts хранятся по фиксированному пути `/artifacts/<artifact_name>/<version>.md`. При обновлении создаётся новая версия, старые версии не удаляются. Содержимое Artifact проверяется по соответствующему Quality Gate перед передачей на следующий этап.

## Правила и ограничения

- Работа ведётся только на основе доступных требований; предположения не выдаются за подтверждённые требования.
- Не создаются задачи и тест-кейсы без основания в требованиях.
- Не изменяются исходные данные в Confluence и существующие сущности в Jira/Qase.
- Сущности с тэгом `Agent` могут быть дополнены в рамках текущей задачи; изменение или удаление требует согласования с пользователем.
- При противоречии требований выполнение останавливается, конфликт фиксируется и передаётся пользователю (эскалация).
- При технической ошибке — до 3 попыток повтора действия; при частичном сбое этап помечается как «завершён с ошибками», успешные сущности сохраняются.
- Перед повторным созданием сущностей проверяется их отсутствие (по тэгу `Agent`, заголовку и ссылке на требование) — дубликаты не создаются.

## Структура проекта

- `AGENTS.md` — основная инструкция QA-агента: роль, scope, workflow, Quality Gates, обработка ошибок.
- `.opencode/agents/` — описания агентов пайплайна.
- `.opencode/skills/` — скиллы этапов: `requirement-review`, `task-design`, `test-design`.
- `.opencode/plugins/` — плагины OpenCode: интеграция с Confluence и PII-сканер.
- `artifacts/` — промежуточные результаты этапов.
- `evals/` — инфраструктура оценки качества агента.
