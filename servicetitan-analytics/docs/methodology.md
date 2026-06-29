# Методология: этапы глобальной аналитики падения выручки

Цель — найти, **на каком этапе воронки** теряются 20–30% выручки, объяснить
**почему**, и проверять это **гипотезами**. Главный принцип:
**сначала ГДЕ (числа), потом ПОЧЕМУ (звонки)** — иначе можно прослушать тысячу
звонков, когда проблема была в рекламном бюджете или уходе техника.

## Воронка выручки

```
Выручка = L · b · r · c · t   (+ рекуррентка, + допродажи)

L = call leads          — качественный входящий спрос (звонки ≥60с или Is Lead)
b = booking rate        — bookings / call_leads
r = run/completion rate — completed_opportunity_jobs / bookings
c = conversion rate     — converted_jobs / completed_opportunity_jobs
t = average ticket      — revenue / converted_jobs
```

Падение выручки раскладывается на вклад каждого фактора **точно и аддитивно**
(LMDI-I, см. `pipeline/build_funnel.py::lmdi_decompose`). Сумма вкладов = фактическая
дельта выручки. Самый отрицательный вклад → этап для глубокого разбора.

| Звено | KPI ServiceTitan | Бенчмарк |
|---|---|---|
| Лиды | call leads по campaign/lead source | — |
| Answer rate | answered / inbound | цель >90% |
| Booking rate | Call Booking Rate | ~42% средн., 59% у 25+ техников, 24% у <5 |
| Run rate | scheduled→completed, cancellation | — |
| Conversion | converted / opportunities | зависит от индустрии |
| Средний чек | Average Ticket (по opportunity-джобам) | — |
| Рекуррентка | active memberships, renewal rate | — |

## Этап 0 — Data foundation
API-клиент (OAuth2 + `ST-App-Key`, авто-рефреш, пагинация, retry) → выгрузка за
2 периода (текущий месяц + тот же месяц год назад; YoY гасит сезонность HVAC) →
DuckDB. Сущности: calls, bookings/leads, jobs/appointments, invoices, estimates,
campaigns, memberships, timesheets. Запуск: `python -m pipeline.check_access`.

## Этап 1 — YoY-декомпозиция воронки (ГДЕ)
`python -m pipeline.build_funnel` → таблица воронки за оба периода + вклад каждого
звена в дельту выручки. Отдельно: помесячный YoY-график выручки — **когда**
началось падение. Ступенька на месяце → событие (ушёл CSR/техник, умер канал,
поменяли цены, зашёл конкурент). Плавно → структурное.

## Этап 2 — Сегментация (сужаем)
Резать воронку по business unit (HVAC vs сантехника), типу джоба
(service / install-replacement / maintenance), источнику лида, CSR, технику, гео,
времени суток/дню недели. Найти конкретные сегменты-виновники.

## Этап 3 — Разбор звонков (ПОЧЕМУ), автоматически
Точечно по сломавшемуся этапу. Пайплайн:
`ingest_calls` (выгрузка + аудио) → `transcribe` (диаризация: CSR vs клиент) →
`analyze_calls` (Claude, structured output: причина, исход, почему не booked,
чек-лист поведения CSR, тональность, missed opportunity) → `aggregate_calls`
(booking/missed-opp rate по CSR/источнику/причине, YoY). Гибридный контроль:
выборочно прослушать «проблемные» кейсы для калибровки разметки.

## Этап 4 — Гипотезы и проверка
Backlog — в [`../analysis/hypotheses.md`](../analysis/hypotheses.md). Каждая
гипотеза: метрика-индикатор → ожидаемый паттерн в данных → тест/эксперимент →
измерение эффекта и срок.

## Этап 5 — Мониторинг
Дашборд (Streamlit/Metabase поверх DuckDB) с воронкой и KPI по CSR/технику/источнику
+ еженедельный авто-разбор звонков. Чтобы просадки ловились сразу, а не через год.

## Verification
- **API:** тестовый диапазон → токен/`ST-App-Key`/пагинация; кол-во записей сходится с UI ServiceTitan.
- **Воронка:** Call Booking Rate / Conversion / Average Ticket совпадают со встроенными дашбордами ServiceTitan (±округление). Расхождение → разные определения метрик, чинить в `build_funnel.py`.
- **Транскрибация:** вручную прослушать 5–10 звонков, сверить диаризацию.
- **LLM-разметка:** на 20–30 звонках сверить поля с ручной оценкой, считать accuracy, калибровать промпт.
- **Декомпозиция:** сумма LMDI-вкладов = фактическая дельта YoY.
