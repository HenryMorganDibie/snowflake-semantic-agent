-- models/marts/fct_orders.sql
-- Orders fact table — primary semantic model anchor
-- Grain: one row per order
-- Downstream: MetricFlow semantic model for revenue, volume, and customer metrics

with orders as (
    select * from {{ ref('stg_orders') }}
),

customers as (
    select * from {{ ref('stg_customers') }}
),

final as (
    select
        -- keys
        o.order_id,
        o.customer_id,
        o.product_id,

        -- time
        o.order_date,
        date_trunc('week',  o.order_date)::date  as order_week,
        date_trunc('month', o.order_date)::date  as order_month,

        -- measures
        o.order_amount_usd,
        o.order_quantity,

        -- dimensions
        o.order_status,
        o.region,
        o.acquisition_channel,
        c.plan_type          as customer_plan_type,
        c.country            as customer_country,
        c.is_active          as customer_is_active,

        o.created_at
    from orders o
    left join customers c using (customer_id)
)

select * from final
