# Snowflake Semantic Layer Agent

**Make your Snowflake data safe for AI agents — governed metrics, no raw SQL, no hallucinated joins.**

A production-pattern implementation of a dbt MetricFlow semantic layer with Snowflake Horizon Catalog integration and a FastAPI agentic query interface.

> Built as a reference architecture for teams moving from "AI querying raw tables" to "AI querying governed, version-controlled business logic."

---

## What This Actually Does

1. **Defines your metrics once** — in dbt MetricFlow YAML. Revenue, AOV, active customers, WoW growth. Every downstream system uses the same definition.
2. **Registers them in Snowflake Horizon Catalog** — so AI agents discover and query governed Semantic Views, not raw tables.
3. **Exposes a natural language API** — POST a question, get a structured metric result with the generated SQL included for full auditability.

---

## Live Example

```bash
POST /query
{
  "question": "What was total revenue last month by region?",
  "time_grain": "month",
  "group_by": ["region"]
}
```

```json
{
  "metric_name": "total_revenue",
  "display_name": "Total Revenue (USD)",
  "time_grain": "month",
  "group_by": ["region"],
  "rows": [
    { "metric_time__month": "2024-01-01", "region": "EMEA",   "total_revenue": 48320.00 },
    { "metric_time__month": "2024-01-01", "region": "APAC",   "total_revenue": 39150.75 },
    { "metric_time__month": "2024-01-01", "region": "AMER",   "total_revenue": 55360.25 }
  ],
  "generated_sql": "SELECT ... FROM fct_orders WHERE order_status != 'cancelled' GROUP BY ...",
  "source": "dbt MetricFlow Semantic Layer",
  "governance_note": "Result resolved through governed MetricFlow definitions. Business logic is version-controlled in dbt and registered in Snowflake Horizon Catalog."
}
```

The `generated_sql` field is always returned — so every agent query is fully auditable.

---

## Why This Matters

Without a semantic layer, AI agents querying Snowflake directly will:
- Guess at joins between tables
- Apply inconsistent time grain logic
- Define "revenue" differently than your finance team does
- Return results that look correct but use different business rules each time

This architecture solves that by moving business logic out of prompts and dashboards, and into a single governed layer that every system — BI tools, ML pipelines, AI agents — reads from.

**Commercial impact:**
- Eliminates revenue metric disputes between teams (finance vs. sales vs. product)
- Reduces analyst dependency for metric queries — agents handle the long tail
- Enables safe self-serve analytics for non-technical stakeholders via natural language
- Makes AI agent outputs auditable and trustworthy enough to act on

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Agentic Systems                        │
│  (LangGraph agents · Cortex · Claude via MCP · Custom)  │
└───────────────────────┬─────────────────────────────────┘
                        │  POST /query  (natural language)
                        ▼
┌─────────────────────────────────────────────────────────┐
│              Semantic Layer Agent (FastAPI)              │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │            Intent Router (Hybrid)                │   │
│  │                                                  │   │
│  │  Rule-based triage (keyword → metric candidate)  │   │
│  │       ↓ ambiguous or multi-metric queries        │   │
│  │  LLM tool-calling layer (Claude / GPT-4o)        │   │
│  │  → selects metric + dimensions + filters         │   │
│  └─────────────────────────────────────────────────┘   │
└───────────────────────┬─────────────────────────────────┘
                        │  GraphQL / JDBC
                        ▼
┌─────────────────────────────────────────────────────────┐
│           dbt Semantic Layer (MetricFlow)                │
│  Semantic models · Metrics · Dimensions · Entities       │
│  SQL generated at query time — no precomputed cubes      │
└───────────────────────┬─────────────────────────────────┘
                        │  Generated SQL
                        ▼
┌─────────────────────────────────────────────────────────┐
│                    Snowflake                             │
│  marts.fct_orders · Horizon Catalog Semantic Views       │
│  Governance · Lineage · Access Policy · Agent Identity   │
└─────────────────────────────────────────────────────────┘
```

### Intent Routing — How It Works

The agent uses a **hybrid routing strategy**:

- **Fast path (rule-based):** keyword triage maps unambiguous questions directly to a metric. "What is revenue?" → `total_revenue`. Zero LLM latency for common queries.
- **Slow path (LLM tool-calling):** ambiguous or compound questions are passed to an LLM with the metric catalog as tools. The LLM selects the right metric(s), dimensions, and filters. This handles questions like "How are our best customers performing vs. last quarter?" where intent requires reasoning, not just keyword matching.
- **Fallback:** if neither path resolves, the API returns the full metric catalog so the calling agent can re-prompt with grounded context.

---

## Repository Structure

```
snowflake-semantic-agent/
│
├── dbt_project/
│   ├── dbt_project.yml
│   └── models/
│       ├── staging/
│       │   ├── stg_orders.sql              # Typed, renamed raw orders
│       │   └── stg_customers.sql           # Typed, renamed raw customers
│       ├── marts/
│       │   ├── fct_orders.sql              # Orders fact table — semantic anchor
│       │   └── metricflow_time_spine.sql   # Required MetricFlow time axis
│       └── semantic/
│           └── sem_orders.yml              # ★ MetricFlow semantic model + all metrics
│
├── agent/
│   └── main.py                             # FastAPI semantic layer agent
│
├── docs/
│   └── horizon_catalog_semantic_views.yml  # Horizon Catalog semantic view definitions
│
├── .env.example
└── requirements.txt
```

---

## The Semantic Model

`sem_orders.yml` is the core of the project — a MetricFlow semantic model that defines the single source of truth for all order metrics.

**Entities** (how MetricFlow traverses relationships at query time):
- `order` (primary), `customer` (foreign), `product` (foreign)

**Measures** (aggregatable facts):
- `revenue` — `SUM(order_amount_usd)`
- `order_count` — `COUNT_DISTINCT(order_id)`
- `units_sold` — `SUM(order_quantity)`
- `customers_with_orders` — `COUNT_DISTINCT(customer_id)`

**Dimensions** (slicing attributes):
- `order_date` (time), `region`, `acquisition_channel`, `order_status`, `customer_plan_type`, `customer_country`

---

## Governed Metrics

| Metric | Type | Description |
|---|---|---|
| `total_revenue` | Simple | Total confirmed order revenue (USD) |
| `order_volume` | Simple | Count of confirmed orders |
| `units_sold` | Simple | Total units shipped |
| `active_customers` | Simple | Distinct customers with confirmed orders |
| `average_order_value` | Ratio | `total_revenue / order_volume` |
| `revenue_per_customer` | Ratio | `total_revenue / active_customers` |
| `cumulative_revenue_mtd` | Cumulative | Month-to-date revenue, resets monthly |
| `cumulative_orders_mtd` | Cumulative | Month-to-date order count |
| `revenue_growth_wow` | Derived | Week-over-week revenue growth rate |

Every metric filters cancelled orders at **definition level** — not at the dashboard, not in the agent prompt. The business rule lives in one version-controlled place.

---

## Snowflake Horizon Catalog Integration

Metric definitions are registered as **Semantic Views** in Snowflake Horizon Catalog — the governance and discovery layer that makes metrics accessible to both humans and AI agents from the same trusted source.

| Semantic View | Metrics | Consumer |
|---|---|---|
| `sv_revenue_metrics` | Revenue, AOV, WoW growth, MTD | Finance, executive agents |
| `sv_customer_metrics` | Active customers, revenue/customer | CRM, churn agents |
| `sv_operational_metrics` | Order volume, units, MTD orders | Ops, supply chain agents |

Agents connect to Horizon Catalog via the **Model Context Protocol (MCP)** — a standard interface that lets any agent framework (LangGraph, Claude, Cursor, custom) query governed Semantic Views without custom integration work per system. The agent calls the Semantic View; Horizon Catalog enforces access policy, logs agent identity, and returns governed results.

See `docs/horizon_catalog_semantic_views.yml` for the full definitions.

---

## Setup

```bash
# 1. Clone and install
git clone https://github.com/HenryMorganDibie/snowflake-semantic-agent
cd snowflake-semantic-agent
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Fill in: DBT_SL_TOKEN, DBT_ENVIRONMENT_ID, Snowflake credentials

# 3. Run dbt
cd dbt_project
dbt deps && dbt build

# 4. Validate MetricFlow semantic models
mf validate-configs
mf query --metrics total_revenue --group-by metric_time__month

# 5. Start the agent
cd ..
uvicorn agent.main:app --reload
```

**Running without credentials:** the agent degrades gracefully — all endpoints respond with stub data so you can explore the API structure without a live Snowflake connection.

---

## Key Design Decisions

**Hybrid intent routing over pure LLM routing**
Pure LLM routing adds 1–3 seconds of latency to every query and fails unpredictably on well-known metric names. Rule-based triage handles the 80% of queries that are unambiguous; LLM tool-calling handles the 20% that require reasoning. This keeps p50 latency low while maintaining coverage.

**MetricFlow over warehouse-native metric definitions**
MetricFlow metric definitions travel with the dbt project, not locked to Snowflake. If the warehouse changes, the business logic doesn't.

**`generated_sql` always returned**
Agentic systems that can't be audited don't get deployed. Returning the MetricFlow-generated SQL closes the loop between the natural language question and the data that answered it.

**Cancellation filter at metric level, not dashboard level**
If the business rule lives in a dashboard filter, a different analyst builds a different dashboard with a different filter. The metric definition is the contract.

---

## Related Work

- [NaijaFinAI](https://github.com/HenryMorganDibie/NaijaFinAI) — Nigerian-context fraud intelligence agent (FastAPI + React)
- [knowledge-rag-api](https://github.com/HenryMorganDibie/knowledge-rag-api) — Hybrid RAG with pgvector, BM25, and RRF reranking
- [Deal Intelligence Agent](https://github.com/HenryMorganDibie/deal-intelligence-agent) — 8-node LangGraph pipeline for PE/credit signal detection

---

## Author

**Henry Dibie** — ML Systems Engineer & Data Scientist
[LinkedIn](https://linkedin.com/in/kinghenrymorgan) · [GitHub](https://github.com/HenryMorganDibie) · [Medium](https://medium.com/@KingHenryMorgan)
