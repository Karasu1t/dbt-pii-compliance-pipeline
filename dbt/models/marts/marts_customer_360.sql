select
    c.customer_id,
    c.full_name,
    c.email,
    c.phone_number,
    c.postal_code,
    c.birth_date,
    c.gender,
    c.national_id_ref,
    c.loyalty_tier,
    c.support_notes,
    c.last_login_ip,
    count(o.order_id) as total_orders,
    sum(o.order_total) as lifetime_value,
    max(o.order_date) as last_order_date
from {{ ref('stg_customers') }} c
left join {{ ref('stg_orders') }} o on c.customer_id = o.customer_id
group by 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11
