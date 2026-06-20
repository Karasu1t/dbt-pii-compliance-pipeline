select
    order_id,
    customer_id,
    product_id,
    order_total,
    order_date,
    shipping_address
from {{ ref('raw_orders') }}
