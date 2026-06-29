# ServiceTitan MCP (read-only)

Тонкий MCP-сервер поверх нашего `servicetitan/client.py` и аналитического DuckDB.
Даёт владельцу/админу задавать вопросы по данным прямо в чате с Claude, **без
права что-либо менять**. Официального MCP у ServiceTitan нет; этот — наш, чтобы не
запускать непроверенный сторонний код с доступом к кредам тенанта.

## Инструменты (все read-only)

| Тул | Что делает | Переиспользует |
|---|---|---|
| `funnel_yoy()` | YoY-воронка + LMDI-декомпозиция дельты выручки | `pipeline/build_funnel.py` |
| `revenue_trend(months)` | помесячный YoY — когда началось падение | `pipeline/revenue_trend.py` |
| `list_calls/list_jobs/list_invoices/list_bookings(start,end,limit)` | сырые записи за период | `servicetitan/*` |
| `query_analytics(sql)` | **SELECT-only** к таблицам пайплайна (`funnel`, `call_analysis`, `agg_*`, …) | DuckDB `read_only=True` |

## Установка

```bash
cd servicetitan-analytics
pip install -e ".[mcp]"     # ставит mcp SDK
```

## Подключение

**Claude Code** (из каталога `servicetitan-analytics`):
```bash
claude mcp add servicetitan -- python -m mcp_server.server
```

**Claude Desktop / `.mcp.json`** (env с кредами — только во View-scope приложении!):
```json
{
  "mcpServers": {
    "servicetitan": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/абсолютный/путь/servicetitan-analytics",
      "env": {
        "ST_CLIENT_ID": "…",
        "ST_CLIENT_SECRET": "…",
        "ST_APP_KEY": "…",
        "ST_TENANT_ID": "…"
      }
    }
  }
}
```
После — перезапустить клиент, убедиться что тулы появились, спросить
«вызови funnel_yoy».

## Безопасность

См. [`../docs/mcp_security.md`](../docs/mcp_security.md). Кратко:
1. **API-приложению в ServiceTitan выдать только `View`-scopes (`:r`)** — главная
   защита: креды физически не могут писать.
2. В этом MCP **нет write-тулов и нет generic-passthrough**; клиент шлёт к API
   только GET.
3. `query_analytics` — только SELECT (`mcp_server/safe_sql.py`) и `read_only=True`.
4. Креды — только в env конфига клиента, не в коде/гите.
