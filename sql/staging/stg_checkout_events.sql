select distinct
    cast(user_id as integer) as user_id,
    event_name,
    datetime(event_ts)       as event_ts
from raw_checkout_events
