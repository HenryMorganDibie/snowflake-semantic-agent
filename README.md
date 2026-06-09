# Snowflake Semantic Layer Agent

**A production-pattern implementation of a governed dbt MetricFlow semantic layer with Snowflake Horizon Catalog integration and an agentic query interface.**

Built to demonstrate the architecture for making Snowflake data reliably available to agentic AI systems — without raw SQL, guessed joins, or metric drift.

---

## The Problem This Solves

When AI agents query raw Snowflake tables, they guess. They guess at joins. They guess at time grains. They guess at what "revenue" means. Each model guesses differently, producing answers that look credible but use inconsistent logic.

The solution is a **governed semantic layer**: metric definitions version-controlled in dbt, served through MetricFlow, registered in Snowflake Horizon Catalog, and consumed by agents via a structured API — so every system operates from the same trusted business logic.

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
│  Intent router → metric resolution → SL API call        │
└───────────────────────┬─────────────────────────────────┘
                        │  GraphQL / JDBC
                        ▼
┌─────────────────────────────────────────────────────────┐
│           dbt Semantic Layer (MetricFlow)                │
│  Semantic models · Metrics · Dimensions · Entities       │
│  SQL generation at query time — no precomputed cubes     │
└───────────────────────┬─────────────────────────────────┘
                        │  Generated SQL
                        ▼
┌─────────────────────────────────────────────────────────┐
│                    Snowflake                             │
│  marts.fct_orders · Horizon Catalog Semantic Views       │
│  Governance · Lineage · Access Policy · Agent Identity   │
└─────────────────────────────────────────────────────────┘
```

---

## Repository Structure

```
snowflake-semantic-agent/
│
├── dbt_project/
│   ├── dbt_project.yml
│   └── models/
│       ├── staging/
│       │   ├── stg_orders.sql          # Typed, renamed raw orders
│       │   └── stg_customers.sql       # Typed, renamed raw customers
│       ├── marts/
│       │   ├── fct_orders.sql          # Orders fact table — semantic anchor
│       │   └── metricflow_time_spine.sql  # Required MetricFlow time axis
│       └── semantic/
│           └── sem_orders.yml          # ★ MetricFlow semantic model + all metrics
│
├── agent/
│   └── main.py                         # FastAPI semantic layer agent
│
├── docs/
│   └── horizon_catalog_semantic_views.yml  # Horizon Catalog semantic view definitions
│
├── .env.example
└── requirements.txt
```

---

## The Semantic Model

The core of this project is `sem_orders.yml` — a MetricFlow semantic model that defines:

**Entities** (join keys MetricFlow uses to traverse relationships at query time):
- `order` (primary), `customer` (foreign), `product` (foreign)

**Measures** (aggregatable facts):
- `revenue` — `SUM(order_amount_usd)`
- `order_count` — `COUNT_DISTINCT(order_id)`
- `units_sold` — `SUM(order_quantity)`
- `customers_with_orders` — `COUNT_DISTINCT(customer_id)`

**Dimensions** (slicing attributes for agents and BI tools):
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

Every metric filters out cancelled orders at definition level — not at the dashboard level, not at the agent prompt level. The business rule lives in one place.

---

## Snowflake Horizon Catalog Integration

Metric definitions are registered as **Semantic Views** in Snowflake Horizon Catalog, organised into three governed views:

| Semantic View | Metrics | Consumer |
|---|---|---|
| `sv_revenue_metrics` | Revenue, AOV, WoW growth, MTD | Finance, executive agents |
| `sv_customer_metrics` | Active customers, revenue/customer | CRM, churn agents |
| `sv_operational_metrics` | Order volume, units, MTD orders | Ops, supply chain agents |

With Horizon Context, these views are:
- **Discoverable** — agents find the right semantic view automatically
- **Queryable via MCP** — expose to Claude, Cursor, or any agent framework
- **Governed** — access policies, data classification, and owner metadata attached
- **Auditable** — agent identity tracking distinguishes human vs. agent queries

See `docs/horizon_catalog_semantic_views.yml` for the full definitions.

---

## Agent Query Interface

The FastAPI agent wraps the Semantic Layer behind a natural language endpoint:

```bash
# Start the agent
uvicorn agent.main:app --reload --port 8000
```

```bash
# List all governed metrics
curl http://localhost:8000/metrics

# Query by natural language
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What was total revenue last month by region?",
    "time_grain": "month",
    "group_by": ["region"]
  }'
```

**Response:**
```json
{
  "metric_name": "total_revenue",
  "display_name": "Total Revenue (USD)",
  "time_grain": "month",
  "group_by": ["region"],
  "rows": [...],
  "generated_sql": "-- MetricFlow generated SQL shown for transparency",
  "source": "dbt MetricFlow Semantic Layer",
  "governance_note": "This result is resolved through governed MetricFlow metric definitions. Business logic is version-controlled in dbt and registered in Snowflake Horizon Catalog."
}
```

The `generated_sql` field returns the SQL MetricFlow produced — so agents and engineers can audit exactly what ran.

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

# 3. Set up dbt profile (profiles.yml in ~/.dbt/)
# See: https://docs.getdbt.com/docs/core/connect-data-platform/snowflake-setup

# 4. Run dbt
cd dbt_project
dbt deps
dbt build

# 5. Validate MetricFlow semantic models
mf validate-configs
mf query --metrics total_revenue --group-by metric_time__month

# 6. Start the agent
cd ..
uvicorn agent.main:app --reload
```

---

## Key Design Decisions

**Why MetricFlow over defining metrics in the warehouse?**
MetricFlow is query-engine-agnostic — metric definitions travel with the dbt project, not locked to Snowflake. If the warehouse changes, the business logic doesn't.

**Why Horizon Catalog for agent consumption?**
Raw table access forces agents to infer joins and business rules. Horizon Catalog exposes governed Semantic Views with rich metadata — agents get context, not just schema. The MCP interface means any agent framework can connect without custom integration.

**Why expose `generated_sql` in the API response?**
Trust. Agentic systems that can't be audited don't get deployed. Showing the SQL MetricFlow generated closes the loop between the natural language question and the data that answered it.

**Why filter cancelled orders at the metric level?**
Business rules belong in one place. If the cancellation filter lives in a dashboard, a different analyst builds a different dashboard with a different filter. The metric definition is the contract.

---

## Related Work

- [NaijaFinAI](https://github.com/HenryMorganDibie/NaijaFinAI) — Nigerian-context fraud intelligence agent (FastAPI + React)
- [knowledge-rag-api](https://github.com/HenryMorganDibie/knowledge-rag-api) — Hybrid RAG with pgvector, BM25, and RRF reranking
- [Deal Intelligence Agent](https://github.com/HenryMorganDibie/deal-intelligence-agent) — 8-node LangGraph pipeline for PE/credit signal detection

---

## Author

**Henry Dibie** — ML Systems Engineer & Data Scientist  
[LinkedIn](https://linkedin.com/in/kinghenrymorgan) · [GitHub](https://github.com/HenryMorganDibie) · [Medium](https://medium.com/@KingHenryMorgan)
