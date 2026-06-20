{% macro drop_catalog_if_exists() %}
  {% set query %}
    DROP CATALOG IF EXISTS {{ target.catalog }} CASCADE
  {% endset %}
  {% do run_query(query) %}
  {{ log("Catalog " ~ target.catalog ~ " dropped (if it existed)", info=True) }}
{% endmacro %}
