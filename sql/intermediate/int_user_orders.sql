-- Orders split into pre-period (covariate) and post-assignment (outcome) windows
select
    e.user_id,
    sum(case when o.ordered_at <  e.assigned_at then 1 else 0 end)              as pre_orders,
    sum(case when o.ordered_at <  e.assigned_at then o.order_value else 0 end)  as pre_revenue,
    sum(case when o.ordered_at >= e.assigned_at then 1 else 0 end)              as orders,
    sum(case when o.ordered_at >= e.assigned_at then o.order_value else 0 end)  as revenue
from int_experiment_users e
left join stg_orders o on o.user_id = e.user_id
group by e.user_id
