select
    variant,
    count(*)                                   as users,
    sum(started_checkout)                      as checkout_starters,
    sum(converted)                             as converters,
    round(1.0 * sum(converted) / count(*), 5)  as conversion_rate,
    round(1.0 * sum(converted) / nullif(sum(started_checkout), 0), 5) as checkout_completion_rate,
    round(sum(revenue), 2)                     as revenue,
    round(sum(revenue) / count(*), 4)          as revenue_per_user,
    round(sum(revenue) / nullif(sum(orders), 0), 2) as avg_order_value
from fct_experiment_user_outcomes
group by variant
order by variant
