# Безопасность ServiceTitan MCP

## Оценка вариантов (ресёрч)

**Официального MCP от ServiceTitan нет.** Сторонние варианты:

| Вариант | Зрелость | Главный риск |
|---|---|---|
| [glassdoc/servicetitan-mcp](https://github.com/glassdoc/servicetitan-mcp) (Py, 60 тулов, MIT) | ~1★ | generic-тул `servicetitan_api_call` умеет POST/PATCH/PUT → запись в прод |
| [JordanDalton](https://github.com/JordanDalton/ServiceTitanMcpServer) (TS) | 5★, 1 коммит, «please test» | непроверен |
| [BusyBee3333 (108 тулов)](https://github.com/BusyBee3333/servicetitan-mcp-2026-complete) | новый | большой surface, непроверен |
| [Zapier (managed)](https://zapier.com/mcp/servicetitan) | стабилен | креды/данные проходят через третью сторону |
| **Наш read-only MCP** | — | минимальный (только GET + View-scopes) |

Общая проблема сторонних: непроверенный код получает client-credentials с доступом
ко **всему тенанту**. Поэтому выбран свой минимальный сервер; glassdoc
использован как референс покрытия эндпоинтов (его код не запускаем; клонирование
для построчного аудита заблокировано scope'ом прокси — оценка по публичному
README/метаданным).

## Модель угроз и меры

| Угроза | Мера |
|---|---|
| LLM/инъекция меняет данные (джобы, инвойсы) | **View-only scopes** в ServiceTitan (`tn.acc.invoices:r` и т.п.) → API вернёт 403 на любую запись. В MCP нет write-тулов. |
| Generic API-passthrough как у glassdoc | Не реализуем. Клиент (`servicetitan/client.py`) делает только GET; POST идёт лишь на token-endpoint. |
| SQL-инъекция / порча локальной БД через `query_analytics` | `safe_sql.ensure_select_only` (только SELECT/WITH, запрет DDL/DML, одно выражение) + DuckDB `read_only=True`. |
| Prompt-injection из текстов звонков/заметок | При View-scopes последствий записи нет; данные остаются read-only. |
| Утечка кредов | Только в env конфига MCP-клиента; `.env`/`db/`/`data/` в `.gitignore`. Токен живёт 15 мин, refresh-токена нет. |
| Превышение лимитов API | Клиент уже с retry/backoff; лимиты ST: 60 rps/app/tenant, отчёты 5/min. |

## Чек-лист перед запуском

- [ ] API-приложение в ServiceTitan создано с **только `View`**-scopes на нужные ресурсы (calls, jobs, invoices, customers, bookings).
- [ ] Проверено: попытка записи через эти креды возвращает **403** (нет `Modify`).
- [ ] `grep -RInE "\.(post|put|patch|delete)\(" mcp_server servicetitan` не находит вызовов к API (кроме token POST в `client.py`).
- [ ] `query_analytics` отвергает `DROP/UPDATE/INSERT` (юнит-тест `tests/test_safe_sql.py`).
- [ ] Креды не в гите.
