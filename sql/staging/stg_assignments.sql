select
    cast(user_id as integer) as user_id,
    experiment_id,
    lower(variant)           as variant,
    datetime(assigned_at)    as assigned_at
from raw_assignments
