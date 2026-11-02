-- Clean user dimension: trim/upper country codes, fill missing device, drop internal accounts
select
    cast(user_id as integer)                         as user_id,
    date(signup_date)                                as signup_date,
    coalesce(nullif(trim(lower(device)), ''), 'unknown') as device,
    upper(trim(country))                             as country,
    cast(is_internal as integer)                     as is_internal
from raw_users
