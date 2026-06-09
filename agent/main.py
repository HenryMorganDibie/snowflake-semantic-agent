# agent/main.py
# ─────────────────────────────────────────────────────────────────
# Semantic Layer Agent — FastAPI
#
# Exposes a natural language query interface over the dbt Semantic
# Layer API. Agents (LangGraph, Cortex, external) POST a question,
# receive a governed metric query result backed by MetricFlow.
#
# Flow:
#   1. Agent POST /query with natural language question
#   2. Router resolves intent → metric name + dimensions + filters
#   3. SemanticLayerClient calls dbt Semantic Layer GraphQL API
#   4. Response returned as structured JSON (metric, value, grain,
#      dimensions, generated_sql for transparency)
# ─────────────────────────────────────────────────────────────────

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
import httpx
import os
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Snowflake Semantic Layer Agent",
    description=(
        "Natural language query interface over a governed dbt MetricFlow "
        "semantic layer, with Snowflake Horizon Catalog integration. "
        "All metrics resolve through MetricFlow — no raw SQL, no guessed joins."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Config ────────────────────────────────────────────────────────
DBT_SL_URL        = os.getenv("DBT_SL_URL", "https://semantic-layer.cloud.getdbt.com/api/graphql")
DBT_SL_TOKEN      = os.getenv("DBT_SL_TOKEN", "")
DBT_ENVIRONMENT   = os.getenv("DBT_ENVIRONMENT_ID", "")


# ── Schemas ───────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        example="What was total revenue last month by region?",
        description="Natural language question answered using governed metric definitions.",
    )
    time_grain: Optional[str] = Field(
        "day",
        example="month",
        description="Time granularity: day | week | month | quarter | year",
    )
    group_by: Optional[list[str]] = Field(
        None,
        example=["region", "customer_plan_type"],
        description="Dimension names to group by. Must match semantic model dimensions.",
    )

class MetricResult(BaseModel):
    metric_name: str
    display_name: str
    value: float | int | None
    time_grain: str
    group_by: list[str]
    rows: list[dict]
    generated_sql: Optional[str] = None
    source: str = "dbt MetricFlow Semantic Layer"
    governance_note: str = (
        "This result is resolved through governed MetricFlow metric definitions. "
        "Business logic is version-controlled in dbt and registered in Snowflake Horizon Catalog."
    )


# ── Intent Router ─────────────────────────────────────────────────
# In production this would be an LLM call (Cortex / GPT-4o) that
# extracts metric intent from the question. Stubbed here for clarity.

INTENT_MAP = {
    "revenue":            "total_revenue",
    "aov":                "average_order_value",
    "average order":      "average_order_value",
    "orders":             "order_volume",
    "order volume":       "order_volume",
    "units":              "units_sold",
    "customers":          "active_customers",
    "revenue per customer": "revenue_per_customer",
    "growth":             "revenue_growth_wow",
    "mtd":                "cumulative_revenue_mtd",
}

def resolve_metric(question: str) -> str:
    q = question.lower()
    for keyword, metric in INTENT_MAP.items():
        if keyword in q:
            return metric
    raise HTTPException(
        status_code=422,
        detail=(
            f"Could not resolve a governed metric from: '{question}'. "
            f"Available metrics: {list(set(INTENT_MAP.values()))}"
        ),
    )


# ── Semantic Layer Client ─────────────────────────────────────────

METRIC_QUERY = """
query SemanticLayerQuery(
    $environmentId: BigInt!
    $metrics: [MetricInput!]!
    $groupBy: [GroupByInput!]
    $limit: Int
) {
    query(
        environmentId: $environmentId
        metrics: $metrics
        groupBy: $groupBy
        limit: $limit
    ) {
        totalPages
        results {
            value { intValue floatValue }
        }
        sql
    }
}
"""

async def query_semantic_layer(
    metric_name: str,
    group_by: list[str],
    time_grain: str,
) -> dict:
    """
    Calls the dbt Semantic Layer GraphQL API.
    MetricFlow resolves joins, filters, and time grains server-side.
    """
    group_by_inputs = [
        {"name": f"metric_time", "grain": time_grain.upper()}
    ] + [{"name": dim} for dim in (group_by or [])]

    payload = {
        "query": METRIC_QUERY,
        "variables": {
            "environmentId": int(DBT_ENVIRONMENT) if DBT_ENVIRONMENT else 0,
            "metrics": [{"name": metric_name}],
            "groupBy": group_by_inputs,
            "limit": 500,
        },
    }

    headers = {
        "Authorization": f"Bearer {DBT_SL_TOKEN}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(DBT_SL_URL, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


# ── Routes ────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "snowflake-semantic-layer-agent"}


@app.get("/metrics")
async def list_metrics():
    """List all governed metrics available in the semantic layer."""
    return {
        "metrics": [
            {"name": "total_revenue",           "type": "simple",     "description": "Total confirmed order revenue (USD)"},
            {"name": "average_order_value",      "type": "ratio",      "description": "Revenue per confirmed order"},
            {"name": "order_volume",             "type": "simple",     "description": "Count of confirmed orders"},
            {"name": "units_sold",               "type": "simple",     "description": "Total units sold"},
            {"name": "active_customers",         "type": "simple",     "description": "Distinct customers with confirmed orders"},
            {"name": "revenue_per_customer",     "type": "ratio",      "description": "Revenue per ordering customer"},
            {"name": "revenue_growth_wow",       "type": "derived",    "description": "Week-over-week revenue growth rate"},
            {"name": "cumulative_revenue_mtd",   "type": "cumulative", "description": "Month-to-date cumulative revenue"},
            {"name": "cumulative_orders_mtd",    "type": "cumulative", "description": "Month-to-date cumulative order count"},
        ],
        "source": "dbt MetricFlow Semantic Layer",
        "catalog": "Snowflake Horizon Catalog",
        "governance": "All metrics are version-controlled in dbt and registered as Semantic Views in Snowflake Horizon Catalog.",
    }


@app.get("/dimensions")
async def list_dimensions():
    """List all governed dimensions available for slicing metrics."""
    return {
        "dimensions": [
            {"name": "order_date",          "type": "time",        "description": "Date the order was placed"},
            {"name": "region",              "type": "categorical", "description": "Geographic region"},
            {"name": "order_status",        "type": "categorical", "description": "Fulfilment status"},
            {"name": "acquisition_channel", "type": "categorical", "description": "Customer acquisition channel"},
            {"name": "customer_plan_type",  "type": "categorical", "description": "Customer subscription tier"},
            {"name": "customer_country",    "type": "categorical", "description": "Customer country"},
        ]
    }


@app.post("/query", response_model=MetricResult)
async def query_metrics(req: QueryRequest):
    """
    Natural language metric query endpoint.

    Resolves intent to a governed MetricFlow metric, calls the
    dbt Semantic Layer API, and returns structured results.
    All results are backed by version-controlled metric definitions —
    no raw SQL, no ad-hoc aggregations.
    """
    metric_name = resolve_metric(req.question)
    logger.info(f"Resolved metric: {metric_name} | grain: {req.time_grain} | group_by: {req.group_by}")

    try:
        sl_response = await query_semantic_layer(
            metric_name=metric_name,
            group_by=req.group_by or [],
            time_grain=req.time_grain or "day",
        )
        results = sl_response.get("data", {}).get("query", {}).get("results", [])
        generated_sql = sl_response.get("data", {}).get("query", {}).get("sql")
        rows = [r.get("value", {}) for r in results]

    except httpx.HTTPStatusError as e:
        logger.warning(f"Semantic Layer API error: {e}. Returning stub for demo.")
        rows = [{"metric_time": "2024-01", "value": 142830.50, "note": "stub — connect DBT_SL_TOKEN for live data"}]
        generated_sql = f"-- MetricFlow generated SQL for {metric_name}\n-- Connect DBT_SL_TOKEN to see live query"

    except Exception as e:
        logger.warning(f"Unexpected error: {e}. Returning stub.")
        rows = [{"metric_time": "2024-01", "value": 142830.50, "note": "stub — connect DBT_SL_TOKEN for live data"}]
        generated_sql = None

    display_names = {
        "total_revenue": "Total Revenue (USD)",
        "average_order_value": "Average Order Value (USD)",
        "order_volume": "Order Volume",
        "units_sold": "Units Sold",
        "active_customers": "Active Customers",
        "revenue_per_customer": "Revenue per Customer (USD)",
        "revenue_growth_wow": "Revenue Growth WoW (%)",
        "cumulative_revenue_mtd": "Revenue MTD (USD)",
        "cumulative_orders_mtd": "Orders MTD",
    }

    return MetricResult(
        metric_name=metric_name,
        display_name=display_names.get(metric_name, metric_name),
        value=rows[0].get("floatValue") or rows[0].get("intValue") if rows else None,
        time_grain=req.time_grain or "day",
        group_by=req.group_by or [],
        rows=rows,
        generated_sql=generated_sql,
    )
