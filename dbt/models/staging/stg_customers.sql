select
    customer_id,
    full_name,
    email,
    phone_number,
    postal_code,
    birth_date,
    gender,
    national_id_ref,
    signup_date,
    loyalty_tier,
    support_notes,
    last_login_ip
from {{ ref('raw_customers') }}
