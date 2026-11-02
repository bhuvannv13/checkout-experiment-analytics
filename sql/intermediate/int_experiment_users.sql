-- One row per (non-internal) user in the experiment, with segment attributes
select
    a.user_id,
    a.experiment_id,
    a.variant,
    a.assigned_at,
    u.device,
    u.country
from stg_assignments a
join stg_users u using (user_id)
where u.is_internal = 0
