#!/bin/bash
#
# PostgreSQL initialization script for MCP Cooking Lab Notebook
# Sets up database with security hardening and extensions
#

set -e

# Enable required extensions
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Enable required extensions
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
    CREATE EXTENSION IF NOT EXISTS "pgcrypto";
    CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

    -- Create application-specific schemas
    CREATE SCHEMA IF NOT EXISTS cooking_mcp;
    CREATE SCHEMA IF NOT EXISTS audit;

    -- Grant permissions
    GRANT USAGE ON SCHEMA cooking_mcp TO $POSTGRES_USER;
    GRANT USAGE ON SCHEMA audit TO $POSTGRES_USER;
    GRANT CREATE ON SCHEMA cooking_mcp TO $POSTGRES_USER;
    GRANT CREATE ON SCHEMA audit TO $POSTGRES_USER;

    -- Set default search path
    ALTER USER $POSTGRES_USER SET search_path TO cooking_mcp, public;

    -- Create audit trigger function
    CREATE OR REPLACE FUNCTION audit.audit_trigger()
    RETURNS TRIGGER AS \$\$
    BEGIN
        IF TG_OP = 'INSERT' THEN
            INSERT INTO audit.audit_log (table_name, operation, new_data, changed_at, changed_by)
            VALUES (TG_TABLE_NAME, TG_OP, row_to_json(NEW), now(), current_user);
            RETURN NEW;
        ELSIF TG_OP = 'UPDATE' THEN
            INSERT INTO audit.audit_log (table_name, operation, old_data, new_data, changed_at, changed_by)
            VALUES (TG_TABLE_NAME, TG_OP, row_to_json(OLD), row_to_json(NEW), now(), current_user);
            RETURN NEW;
        ELSIF TG_OP = 'DELETE' THEN
            INSERT INTO audit.audit_log (table_name, operation, old_data, changed_at, changed_by)
            VALUES (TG_TABLE_NAME, TG_OP, row_to_json(OLD), now(), current_user);
            RETURN OLD;
        END IF;
        RETURN NULL;
    END;
    \$\$ LANGUAGE plpgsql;

    -- Create audit log table
    CREATE TABLE IF NOT EXISTS audit.audit_log (
        id SERIAL PRIMARY KEY,
        table_name TEXT NOT NULL,
        operation TEXT NOT NULL,
        old_data JSONB,
        new_data JSONB,
        changed_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
        changed_by TEXT DEFAULT current_user
    );

    -- Create index for performance
    CREATE INDEX IF NOT EXISTS idx_audit_log_table_time
    ON audit.audit_log (table_name, changed_at);

    -- Log successful initialization
    INSERT INTO audit.audit_log (table_name, operation, new_data, changed_at, changed_by)
    VALUES ('system', 'INIT', '{"message": "Database initialized successfully"}', now(), current_user);

EOSQL

echo "PostgreSQL initialization completed successfully"