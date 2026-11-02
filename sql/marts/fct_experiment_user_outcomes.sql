-- Analysis-ready table: one row per experiment user
select
    e.user_id,
    e.experiment_id,
    e.variant,
    e.device,
    e.country,
    coalesce(o.pre_orders, 0)   as pre_orders,
    coalesce(o.pre_revenue, 0)  as pre_revenue,
    case when exists (select 1 from stg_checkout_events c where c.user_id = e.user_id) then 1 else 0 end as started_checkout,
    case when coalesce(o.orders, 0) > 0 then 1 else 0 end as converted,
    coalesce(o.orders, 0)       as orders,
    round(coalesce(o.revenue, 0), 2) as revenue
from int_experiment_users e
left join int_user_orders o using (user_id)
