-- models/staging/stg_orders.sql
-- Staged orders from raw Snowflake source
-- Grain: one row per order

with source as (
    select * from {{ source('raw', 'orders') }}
),

renamed as (
    select
        order_id::varchar           as order_id,
        customer_id::varchar        as customer_id,
        product_id::varchar         as product_id,
        order_date::date            as order_date,
        status::varchar             as order_status,
        amount_usd::float           as order_amount_usd,
        quantity::int               as order_quantity,
        region::varchar             as region,
        channel::varchar            as acquisition_channel,
        created_at::timestamp_ntz   as created_at
    from source
    where order_id is not null
)

select * from renamed
