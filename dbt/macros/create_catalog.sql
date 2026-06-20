{% macro create_catalog_if_not_exists() %}
  {% set query %}
    CREATE CATALOG IF NOT EXISTS {{ target.catalog }}
  {% endset %}
  {% do run_query(query) %}
  {{ log("Catalog " ~ target.catalog ~ " created or already exists", info=True) }}
{% endmacro %}
