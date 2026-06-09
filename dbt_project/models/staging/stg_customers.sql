-- models/staging/stg_customers.sql
-- Staged customers from raw Snowflake source
-- Grain: one row per customer

with source as (
    select * from {{ source('raw', 'customers') }}
),

renamed as (
    select
        customer_id::varchar        as customer_id,
        first_name::varchar         as first_name,
        last_name::varchar          as last_name,
        email::varchar              as email,
        signup_date::date           as signup_date,
        plan_type::varchar          as plan_type,
        country::varchar            as country,
        is_active::boolean          as is_active,
        created_at::timestamp_ntz   as created_at
    from source
    where customer_id is not null
)

select * from renamed
