# Production Readiness Checklist

A reference checklist for teams deploying this semantic layer pattern
into a production Snowflake + dbt Cloud environment.

Use this as a pre-launch gate before connecting agentic systems to the
Semantic Layer API or Horizon Catalog Semantic Views.

---

## 1. Semantic Model Correctness

```
  □ All semantic models pass `mf validate-configs` with zero errors
  □ Every measure references a column that exists in the anchor mart table
  □ Every dimension references a column that exists in the anchor mart table
  □ Entity expr values match actual primary/foreign key columns
  □ Time dimension grain matches the grain of the mart table
  □ Metric filters use correct Jinja syntax: {{ Dimension('model__column') }}
  □ At least one `mf query` test run per metric before promotion
```

---

## 2. Metric Parity Validation

Before deprecating any existing BI-layer metric definitions, validate that
MetricFlow returns the same numbers.

```
  □ Pick a reference date range (e.g. last full calendar month)
  □ Run each metric via MetricFlow CLI: mf query --metrics <metric_name> --group-by metric_time__month
  □ Run the equivalent query against the existing source (Looker, Tableau, raw SQL)
  □ Compare results — differences indicate either a bug in the semantic model
    or an inconsistency in the existing definition that needs a decision
  □ Document any intentional differences (e.g. MetricFlow filters cancelled orders;
    legacy dashboard did not — this is a metric contract change, not a bug)
  □ Sign off from metric owner before switching consumers to MetricFlow
```

---

## 3. Governance Configuration

```
  □ All Semantic Views in Horizon Catalog have owner metadata attached
  □ Data classification set per view (internal / confidential / public)
  □ Row access policies applied where required (e.g. region-restricted data)
  □ Column masking policies applied to any PII dimensions
  □ Agent identity logging confirmed active in Horizon Catalog audit log
  □ Access roles reviewed — agents should have read-only access to Semantic Views,
    not direct access to underlying mart tables
```

---

## 4. Semantic Layer API

```
  □ dbt Cloud service token scoped to minimum required permissions
  □ Environment ID confirmed (production environment, not development)
  □ GraphQL endpoint reachable from agent infrastructure
  □ Token stored in secrets manager — not hardcoded or in environment files
  □ API response includes generated_sql for every query (auditability)
  □ Timeout and retry logic implemented in agent layer
  □ Graceful degradation tested — what happens when the Semantic Layer API is unavailable?
```

---

## 5. Agent Safety

```
  □ Agents query via Semantic Layer API or MCP — not directly against mart tables
  □ Agent identity distinguishable in Horizon Catalog audit log (human vs. AI)
  □ No agent has write access to any Snowflake schema
  □ Rate limiting implemented on the FastAPI agent layer
  □ All agent queries logged with: metric requested, dimensions, filters, timestamp, requester
  □ Tested with intentionally bad inputs — agent handles unresolvable questions gracefully
    without falling back to raw SQL generation
```

---

## 6. Versioning and Change Management

```
  □ Semantic model YAML files committed to version control (git)
  □ Breaking vs. non-breaking change policy documented and communicated to metric consumers
  □ Metric deprecation process defined — consumers notified before removal
  □ dbt project CI pipeline runs mf validate-configs on every PR
  □ Semantic View definitions in Horizon Catalog kept in sync with dbt semantic models
    (Horizon Catalog is not auto-synced — updates require explicit re-registration)
```

---

## 7. Monitoring

```
  □ dbt model freshness alerts configured — stale mart data flows through
    to stale metric results; agents should not serve metrics from stale data
  □ Semantic Layer API latency monitored — P95 latency baseline established
  □ Horizon Catalog audit log reviewed periodically for unexpected agent queries
  □ Metric result anomaly detection in place for high-stakes metrics
    (e.g. total_revenue dropping 80% overnight is a data issue, not a business event)
```

---

## 8. Rollback Readiness

```
  □ Git revert procedure documented and tested for semantic model rollback
  □ Horizon Catalog Semantic View DROP/RECREATE procedure documented
  □ Consumers have a fallback data source during semantic layer outages
    (e.g. direct mart access for BI tools during Semantic Layer API downtime)
  □ On-call rotation aware of semantic layer architecture and rollback steps
```

---

## Sign-Off

| Area | Owner | Status |
|---|---|---|
| Semantic model correctness | Data Engineering | |
| Metric parity validation | Analytics / Finance | |
| Governance configuration | Data Governance / Security | |
| Semantic Layer API | Platform Engineering | |
| Agent safety | ML / AI Engineering | |
| Versioning and change management | Data Engineering | |
| Monitoring | Platform Engineering | |
| Rollback readiness | Platform Engineering | |

No agentic system should be connected to a production Semantic Layer until
all eight areas above are signed off. Partial deployment (e.g. BI tools only,
no agents yet) is acceptable during rollout.

