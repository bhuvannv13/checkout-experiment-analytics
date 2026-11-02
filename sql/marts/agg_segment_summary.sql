select
    device,
    variant,
    count(*)                                  as users,
    sum(converted)                            as converters,
    round(1.0 * sum(converted) / count(*), 5) as conversion_rate,
    round(sum(revenue) / count(*), 4)         as revenue_per_user
from fct_experiment_user_outcomes
group by device, variant
order by device, variant
