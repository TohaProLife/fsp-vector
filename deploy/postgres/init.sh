#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v app_password="$PG_APP_PASSWORD" -v identity_password="$PG_IDENTITY_PASSWORD" <<'SQL'
CREATE ROLE vector LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE vector_identity LOGIN PASSWORD :'identity_password' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE DATABASE vector OWNER vector;
CREATE DATABASE vector_identity OWNER vector_identity;
SQL
