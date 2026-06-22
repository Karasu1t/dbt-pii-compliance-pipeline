-- Fails if any column tagged pii_category (and not 'not_pii') on a
-- publicly-exposed model (per exposures.yml) lacks an active Unity Catalog
-- mask. This cross-checks the *actual* Unity Catalog state, not the
-- classification JSON the tagging/masking scripts were run from — tags and
-- masks could otherwise drift independently of each other.

{% set exposed_tables = [] %}
{% for exposure in graph.exposures.values() %}
  {% for dep in exposure.depends_on.nodes %}
    {% set node = graph.nodes.get(dep) %}
    {% if node %}
      {% do exposed_tables.append(node.alias) %}
    {% endif %}
  {% endfor %}
{% endfor %}

with tagged_pii as (
    select table_name, column_name, tag_value as pii_category
    from {{ target.catalog }}.information_schema.column_tags
    where tag_name = 'pii_category'
      and tag_value != 'not_pii'
      {% if exposed_tables %}
      and table_name in ({{ "'" ~ exposed_tables | join("', '") ~ "'" }})
      {% else %}
      and 1 = 0
      {% endif %}
),

-- mask_required is a separate tag (set alongside pii_category) so a
-- deliberate "tagged as risk but intentionally left unmasked" decision
-- (e.g. gender, low cardinality alone) is explicit and queryable, instead
-- of looking identical to an undetected gap.
mask_required as (
    select table_name, column_name, tag_value as required
    from {{ target.catalog }}.information_schema.column_tags
    where tag_name = 'mask_required'
),

active_masks as (
    select table_name, column_name
    from {{ target.catalog }}.information_schema.column_masks
)

select
    tp.table_name,
    tp.column_name,
    tp.pii_category
from tagged_pii tp
join mask_required mr
    on tp.table_name = mr.table_name
   and tp.column_name = mr.column_name
left join active_masks am
    on tp.table_name = am.table_name
   and tp.column_name = am.column_name
where mr.required = 'true'
  and am.column_name is null
