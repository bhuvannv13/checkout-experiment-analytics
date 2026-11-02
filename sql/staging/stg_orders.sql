-- De-duplicate exported rows and remove zero/negative refund artefacts
with dedup as (
    select *,
           row_number() over (partition by order_id order by ordered_at) as rn
    from raw_orders
)
select
    cast(order_id as integer)     as order_id,
    cast(user_id as integer)      as user_id,
    datetime(ordered_at)          as ordered_at,
    cast(order_value as real)     as order_value,
    currency
from dedup
where rn = 1
  and cast(order_value as real) > 0
