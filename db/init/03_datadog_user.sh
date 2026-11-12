#!/bin/bash
# Crea el usuario de solo lectura "datadog", que usa el Datadog Agent para vigilar PostgreSQL.
# Corre una sola vez, cuando el volumen pg-data está vacío, después de 01_schema.sql y 02_seed.sql.
# La contraseña llega en la variable DD_POSTGRES_PASSWORD (archivo .env): no se escribe en el repo.
# psql la recibe como variable (:'datadog_password') y la pone entre comillas de forma segura.
# SQL según la documentación de la integración postgres de Datadog (PostgreSQL 10 o mayor).
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     --set=datadog_password="$DD_POSTGRES_PASSWORD" <<'EOSQL'
CREATE USER datadog WITH PASSWORD :'datadog_password';
GRANT pg_monitor TO datadog;
GRANT SELECT ON pg_stat_database TO datadog;
EOSQL
