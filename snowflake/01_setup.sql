-- =====================================================================
-- Fleet Data Platform: Snowflake setup (Step 1)
-- Run as ACCOUNTADMIN in a Snowflake worksheet, top to bottom.
-- Creates: warehouses, database + schemas, roles, service users,
--          grants, and a cost guard (resource monitor).
-- =====================================================================

USE ROLE ACCOUNTADMIN;

-- ---------------------------------------------------------------------
-- 1. Warehouses (compute). One per workload so costs are visible.
-- ---------------------------------------------------------------------
CREATE WAREHOUSE IF NOT EXISTS AIRBYTE_WH
  WAREHOUSE_SIZE = XSMALL AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE
  COMMENT = 'Airbyte loads from S3';

CREATE WAREHOUSE IF NOT EXISTS DBT_WH
  WAREHOUSE_SIZE = XSMALL AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE
  COMMENT = 'dbt transformations';

CREATE WAREHOUSE IF NOT EXISTS BI_WH
  WAREHOUSE_SIZE = XSMALL AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE
  COMMENT = 'Power BI queries';

-- ---------------------------------------------------------------------
-- 2. Database and schemas (medallion layers)
--    RAW          : Airbyte lands data here exactly as in S3 (Bronze)
--    STAGING      : dbt cleaned 1:1 models (Silver)
--    INTERMEDIATE : dbt joins / sessionization
--    MARTS        : dbt facts + dimensions for Power BI (Gold)
--    SEEDS        : dbt reference CSVs (cold-chain ranges, etc.)
-- ---------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS FLEET_DB;
CREATE SCHEMA IF NOT EXISTS FLEET_DB.RAW;
CREATE SCHEMA IF NOT EXISTS FLEET_DB.STAGING;
CREATE SCHEMA IF NOT EXISTS FLEET_DB.INTERMEDIATE;
CREATE SCHEMA IF NOT EXISTS FLEET_DB.MARTS;
CREATE SCHEMA IF NOT EXISTS FLEET_DB.SEEDS;

-- ---------------------------------------------------------------------
-- 3. Roles
-- ---------------------------------------------------------------------
CREATE ROLE IF NOT EXISTS AIRBYTE_ROLE;   -- writes RAW
CREATE ROLE IF NOT EXISTS TRANSFORMER;    -- dbt: reads RAW, builds the rest
CREATE ROLE IF NOT EXISTS REPORTER;       -- Power BI: reads MARTS

GRANT ROLE AIRBYTE_ROLE TO ROLE SYSADMIN;
GRANT ROLE TRANSFORMER  TO ROLE SYSADMIN;
GRANT ROLE REPORTER     TO ROLE SYSADMIN;

-- ---------------------------------------------------------------------
-- 4. Grants: Airbyte
--    Airbyte also creates its own AIRBYTE_INTERNAL schema, so it needs
--    CREATE SCHEMA on the database.
-- ---------------------------------------------------------------------
GRANT USAGE ON WAREHOUSE AIRBYTE_WH TO ROLE AIRBYTE_ROLE;
GRANT USAGE, MONITOR, CREATE SCHEMA ON DATABASE FLEET_DB TO ROLE AIRBYTE_ROLE;
GRANT OWNERSHIP ON SCHEMA FLEET_DB.RAW TO ROLE AIRBYTE_ROLE COPY CURRENT GRANTS;

-- ---------------------------------------------------------------------
-- 5. Grants: dbt (TRANSFORMER)
-- ---------------------------------------------------------------------
GRANT USAGE ON WAREHOUSE DBT_WH TO ROLE TRANSFORMER;
GRANT USAGE, CREATE SCHEMA ON DATABASE FLEET_DB TO ROLE TRANSFORMER;

-- read RAW (current + future tables Airbyte creates)
GRANT USAGE ON SCHEMA FLEET_DB.RAW TO ROLE TRANSFORMER;
GRANT SELECT ON ALL TABLES    IN SCHEMA FLEET_DB.RAW TO ROLE TRANSFORMER;
GRANT SELECT ON FUTURE TABLES IN SCHEMA FLEET_DB.RAW TO ROLE TRANSFORMER;
GRANT SELECT ON ALL VIEWS     IN SCHEMA FLEET_DB.RAW TO ROLE TRANSFORMER;
GRANT SELECT ON FUTURE VIEWS  IN SCHEMA FLEET_DB.RAW TO ROLE TRANSFORMER;

-- own the layers dbt builds
GRANT OWNERSHIP ON SCHEMA FLEET_DB.STAGING      TO ROLE TRANSFORMER COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA FLEET_DB.INTERMEDIATE TO ROLE TRANSFORMER COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA FLEET_DB.MARTS        TO ROLE TRANSFORMER COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA FLEET_DB.SEEDS        TO ROLE TRANSFORMER COPY CURRENT GRANTS;

-- ---------------------------------------------------------------------
-- 6. Grants: Power BI (REPORTER) - MARTS only
-- ---------------------------------------------------------------------
GRANT USAGE ON WAREHOUSE BI_WH TO ROLE REPORTER;
GRANT USAGE ON DATABASE FLEET_DB TO ROLE REPORTER;
GRANT USAGE ON SCHEMA FLEET_DB.MARTS TO ROLE REPORTER;
GRANT SELECT ON ALL TABLES    IN SCHEMA FLEET_DB.MARTS TO ROLE REPORTER;
GRANT SELECT ON FUTURE TABLES IN SCHEMA FLEET_DB.MARTS TO ROLE REPORTER;
GRANT SELECT ON ALL VIEWS     IN SCHEMA FLEET_DB.MARTS TO ROLE REPORTER;
GRANT SELECT ON FUTURE VIEWS  IN SCHEMA FLEET_DB.MARTS TO ROLE REPORTER;

-- ---------------------------------------------------------------------
-- 7. Service users (key-pair auth; Snowflake is phasing out passwords
--    for service logins). Paste the PUBLIC key body from Step 1b,
--    without the BEGIN/END lines and without line breaks.
-- ---------------------------------------------------------------------
CREATE USER IF NOT EXISTS AIRBYTE_USER
  TYPE = SERVICE
  DEFAULT_ROLE = AIRBYTE_ROLE
  DEFAULT_WAREHOUSE = AIRBYTE_WH
  DEFAULT_NAMESPACE = FLEET_DB.RAW
  RSA_PUBLIC_KEY = '<PASTE_AIRBYTE_PUBLIC_KEY_HERE>';
GRANT ROLE AIRBYTE_ROLE TO USER AIRBYTE_USER;

CREATE USER IF NOT EXISTS DBT_USER
  TYPE = SERVICE
  DEFAULT_ROLE = TRANSFORMER
  DEFAULT_WAREHOUSE = DBT_WH
  DEFAULT_NAMESPACE = FLEET_DB.STAGING
  RSA_PUBLIC_KEY = '<PASTE_DBT_PUBLIC_KEY_HERE>';
GRANT ROLE TRANSFORMER TO USER DBT_USER;

-- Let your own (human) user act as every role while developing
-- Replace <YOUR_SNOWFLAKE_USERNAME>.
GRANT ROLE AIRBYTE_ROLE TO USER <YOUR_SNOWFLAKE_USERNAME>;
GRANT ROLE TRANSFORMER  TO USER <YOUR_SNOWFLAKE_USERNAME>;
GRANT ROLE REPORTER     TO USER <YOUR_SNOWFLAKE_USERNAME>;

-- ---------------------------------------------------------------------
-- 8. Cost guard: suspend warehouses after the monthly credit quota.
--    Adjust CREDIT_QUOTA to your trial/budget.
-- ---------------------------------------------------------------------
CREATE OR REPLACE RESOURCE MONITOR FLEET_MONTHLY_RM
  WITH CREDIT_QUOTA = 50
  FREQUENCY = MONTHLY
  START_TIMESTAMP = IMMEDIATELY
  TRIGGERS ON 75 PERCENT DO NOTIFY
           ON 90 PERCENT DO SUSPEND
           ON 100 PERCENT DO SUSPEND_IMMEDIATE;

ALTER WAREHOUSE AIRBYTE_WH SET RESOURCE_MONITOR = FLEET_MONTHLY_RM;
ALTER WAREHOUSE DBT_WH     SET RESOURCE_MONITOR = FLEET_MONTHLY_RM;
ALTER WAREHOUSE BI_WH      SET RESOURCE_MONITOR = FLEET_MONTHLY_RM;

-- ---------------------------------------------------------------------
-- 9. Verify
-- ---------------------------------------------------------------------
SHOW SCHEMAS IN DATABASE FLEET_DB;
SHOW GRANTS TO ROLE AIRBYTE_ROLE;
SHOW GRANTS TO ROLE TRANSFORMER;
DESC USER AIRBYTE_USER;
SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME() AS account_identifier;
