# ServiceTitan Revenue Analytics

Системная аналитика падения выручки для HVAC/сантехнической компании на ServiceTitan.

Принцип: **сначала ГДЕ (количественная декомпозиция воронки по данным API), потом ПОЧЕМУ
(автоматический разбор звонков: транскрибация + LLM)** — точечно по сломавшемуся этапу.

Полное описание этапов глобальной аналитики — в [`docs/methodology.md`](docs/methodology.md).

## Воронка выручки

```
Выручка ≈ Лиды × Answer rate × Booking rate × Run rate × Conversion × Средний чек
          + рекуррентка (мембершипы) + допродажи
```

Падение на 20–30% «сидит» в одном-двух звеньях. Пайплайн строит эту таблицу за два периода
(текущий месяц vs тот же месяц год назад — YoY гасит сезонность HVAC) и считает вклад каждого
звена в дельту выручки.

## Установка

```bash
cd servicetitan-analytics
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env   # заполнить ключи
```

## Конфигурация (`.env`)

| Переменная | Назначение |
|---|---|
| `ST_CLIENT_ID`, `ST_CLIENT_SECRET` | OAuth2 client credentials ServiceTitan |
| `ST_APP_KEY` | Заголовок `ST-App-Key` |
| `ST_TENANT_ID` | ID тенанта (в путях API) |
| `ST_ENV` | `production` или `integration` (по умолчанию production) |
| `DEEPGRAM_API_KEY` | Транскрибация с диаризацией (бэкенд `deepgram`) |
| `ANTHROPIC_API_KEY` | LLM-разбор звонков (Claude) |

## Запуск (MVP, по порядку)

```bash
# 1. Проверить доступ к API (короткий диапазон)
python -m pipeline.check_access

# 2. Этап 1 — YoY-воронка за 2 периода → таблица декомпозиции (ГДЕ)
python -m pipeline.build_funnel
#    + помесячный YoY-тренд → когда началось падение (ступенька vs плавно)
python -m pipeline.revenue_trend

# 3. Этап 3 — авто-разбор звонков: выгрузка → транскрибация → LLM
python -m pipeline.ingest_calls
python -m pipeline.transcribe
python -m pipeline.analyze_calls

# 4. Сводки
python -m pipeline.aggregate_calls
```

Все периоды и параметры — в `config.py` (читает из `.env`, разумные дефолты).

## Структура

```
servicetitan/   API-клиент (OAuth2+пагинация) и ресурс-модули (telecom, jpm, crm, accounting, marketing)
pipeline/       шаги: check_access, build_funnel, revenue_trend, ingest_calls, transcribe, analyze_calls, aggregate_calls
tests/          юнит-тесты чистой логики (LMDI, YoY-периоды, правило call-lead)
analysis/       hypotheses.md (backlog гипотез + фреймворк проверки), ноутбуки
db/             DuckDB + parquet (создаётся при запуске)
data/recordings аудио звонков (gitignored)
docs/           methodology.md — этапы глобальной аналитики
```

## Verification

См. раздел Verification в [`docs/methodology.md`](docs/methodology.md): сверка KPI с дашбордами
ServiceTitan, проверка диаризации на 5–10 звонках, калибровка LLM-разметки на 20–30 звонках,
сходимость суммы вкладов звеньев с фактической дельтой YoY.
