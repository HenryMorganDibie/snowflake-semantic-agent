# Migration Guide: Adopting MetricFlow on an Existing dbt Project

This guide covers how to introduce MetricFlow and Snowflake Horizon Catalog
into a dbt project that is already in production — without disrupting existing
transformations, dashboards, or downstream consumers.

---

## Guiding Principle: Additive, Not Disruptive

MetricFlow semantic models are defined alongside your existing dbt models in
YAML — they do not replace or modify any existing `.sql` files or mart tables.
Your current transformations continue to run unchanged. The semantic layer is
a new consumption interface on top of what already exists.

This means the migration can be done in phases, with zero downtime and no
changes to existing pipelines until you are ready.

---

## Phase 0 — Audit Your Existing dbt Project

Before writing any MetricFlow YAML, map what you have:

```
Checklist:
  □ Identify mart tables with clear, stable grain (one row per order, per customer, etc.)
  □ Flag metrics currently defined inconsistently across dashboards or downstream tools
  □ Identify the join relationships between mart tables (these become MetricFlow entities)
  □ Note any existing dbt metrics (legacy dbt metrics block) — these migrate to MetricFlow
  □ Review column naming conventions — MetricFlow expr fields must match actual column names
```

**Deliverable:** a mapping document: `mart table → grain → candidate measures → candidate dimensions`

This is typically a 2–3 day exercise on a medium-sized dbt project.

---

## Phase 1 — Add the MetricFlow Time Spine

MetricFlow requires a time spine model to anchor all time-based metric
calculations. If you do not already have one, add it to your marts layer:

```sql
-- models/marts/metricflow_time_spine.sql
{{ config(materialized='table') }}

with days as (
    {{ dbt_utils.date_spine(
        datepart   = "day",
        start_date = "cast('2020-01-01' as date)",
        end_date   = "cast('2030-01-01' as date)"
    ) }}
)

select cast(date_day as date) as date_day
from days
```

Add to `dbt_project.yml`:
```yaml
models:
  your_project:
    marts:
      metricflow_time_spine:
        +meta:
          metricflow_time_spine: true
```

This is a one-time, non-breaking addition.

---

## Phase 2 — Define Your First Semantic Model

Start with your highest-value, most stable mart table. Do not try to semanticise
everything at once. Pick the table that answers the most common business questions.

```yaml
# models/semantic/sem_orders.yml

semantic_models:
  - name: orders
    model: ref('fct_orders')   # ← points to your existing mart, unchanged

    entities:
      - name: order
        type: primary
        expr: order_id         # ← must match actual column name in fct_orders

    measures:
      - name: revenue
        agg: sum
        expr: order_amount_usd # ← must match actual column name

    dimensions:
      - name: order_date
        type: time
        type_params:
          time_granularity: day

      - name: region
        type: categorical
```

**Validate before proceeding:**
```bash
mf validate-configs          # validates semantic model structure
mf query --metrics revenue --group-by metric_time__month  # test a live query
```

Fix validation errors before adding more models or metrics. A broken semantic
model blocks all metrics that depend on it.

---

## Phase 3 — Layer Metrics on Top

Once the semantic model validates cleanly, define metrics:

```yaml
metrics:
  - name: total_revenue
    type: simple
    type_params:
      measure: revenue
    filter: |
      {{ Dimension('order__order_status') }} != 'cancelled'
```

**Metric migration from legacy dbt metrics:**
If you have existing metrics defined using the old dbt `metrics:` block format,
MetricFlow is a direct upgrade. The main changes are:

| Legacy dbt metrics | MetricFlow equivalent |
|---|---|
| `type: sum` | `type: simple` + measure with `agg: sum` |
| `sql:` field | `expr:` on the measure |
| `filters:` list | `filter:` Jinja on the metric |
| `dimensions:` list | Dimensions defined on semantic model |

Migrate one metric at a time. Validate each with `mf query` before committing.

---

## Phase 4 — Register in Snowflake Horizon Catalog

Once MetricFlow semantic models are validated, register them as Semantic Views
in Horizon Catalog. This is what makes metrics discoverable and queryable by
AI agents and BI tools through a governed interface.

**Prerequisites:**
- Snowflake account with Horizon Catalog enabled
- Role with `CREATE SEMANTIC VIEW` privilege on the target schema
- dbt Semantic Layer connected to dbt Cloud (required for API access)

**Semantic View registration** (see `docs/horizon_catalog_semantic_views.yml`):
```sql
-- Snowflake: create governed semantic view
CREATE OR REPLACE SEMANTIC VIEW analytics.semantic.sv_revenue_metrics
  ...
```

**Governance metadata to attach per view:**
```
  □ owner (team or individual)
  □ data_classification (internal / confidential / public)
  □ row access policy (if applicable)
  □ column masking policy (for PII dimensions)
```

Do not skip governance metadata on the first deployment. Retrofitting access
policies after agents are live is significantly harder than setting them upfront.

---

## Phase 5 — Agent Consumption Layer

With Horizon Catalog live, connect your agentic systems:

**Option A — dbt Semantic Layer GraphQL API (recommended for custom agents)**
```python
# See agent/main.py for full implementation
# Endpoint: https://semantic-layer.cloud.getdbt.com/api/graphql
# Auth: dbt Cloud service token
```

**Option B — MCP interface (for Claude, Cursor, LangGraph)**
```
Snowflake Horizon Catalog exposes an MCP server endpoint.
Connect any MCP-compatible agent framework directly —
no custom integration required per agent system.
```

**Option C — JDBC (for BI tools: Tableau, Sigma, Hex)**
```
Use the dbt Semantic Layer JDBC driver.
Configure your BI tool to point to the Semantic Layer endpoint
instead of directly to Snowflake marts.
```

---

## Org Constraint Considerations

Things that commonly block or delay semantic layer rollouts in enterprise environments:

| Constraint | Mitigation |
|---|---|
| Multiple dbt projects in one org | Define semantic models per project; MetricFlow supports cross-project metrics in dbt Cloud |
| Existing metrics defined in BI tool (LookML, Tableau calcs) | Audit for overlap; migrate high-contention metrics first; deprecate BI-layer definitions gradually |
| No dbt Cloud (OSS dbt Core only) | MetricFlow CLI works locally; Semantic Layer API requires dbt Cloud |
| Snowflake role/permission constraints | Work with Snowflake admin upfront; Horizon Catalog requires specific privileges |
| Stakeholder resistance to changing dashboard logic | Show metric parity first — prove the Semantic Layer returns the same numbers before asking teams to switch |

---

## Rollback Strategy

MetricFlow semantic models are YAML files in your dbt project — they are
version-controlled like any other code. Rollback is a git revert.

```bash
# Revert a bad semantic model change
git revert <commit-hash>
dbt build
mf validate-configs
```

Semantic Views in Horizon Catalog can be dropped and recreated independently
of the dbt project:
```sql
DROP SEMANTIC VIEW analytics.semantic.sv_revenue_metrics;
-- Recreate from docs/horizon_catalog_semantic_views.yml
```

No downstream mart tables are affected by semantic model changes. The semantic
layer is a read-only interface on top of existing data.

---

## Versioning Strategy

Treat semantic model definitions like API contracts:

- **Breaking changes** (removing a metric, renaming a dimension) require a deprecation cycle — notify consumers before removing
- **Non-breaking changes** (adding a new metric, new dimension) can be deployed immediately
- **Metric filters** (e.g. changing the cancellation filter logic) are breaking changes — they change the number every consumer sees

Use dbt's `meta:` block to track metric version and deprecation status:
```yaml
metrics:
  - name: total_revenue
    meta:
      version: 2
      deprecated_metrics: ["revenue_v1"]
      owner: data_engineering
      last_reviewed: "2024-01-15"
```

