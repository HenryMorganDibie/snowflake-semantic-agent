-- models/marts/metricflow_time_spine.sql
-- Required MetricFlow time spine model
-- MetricFlow uses this to anchor all time-based metric calculations

{{
    config(
        materialized = 'table',
    )
}}

with days as (
    {{
        dbt_utils.date_spine(
            datepart   = "day",
            start_date = "cast('2020-01-01' as date)",
            end_date   = "cast('2030-01-01' as date)"
        )
    }}
)

select
    cast(date_day as date) as date_day
from days
