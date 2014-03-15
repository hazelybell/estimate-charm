SET client_min_messages=ERROR;

/*
Create a table to store snapshots of the pg_stat_user_tables or the
pg_stat_all_tables views.

\d pg_stat_user_tables
          View "pg_catalog.pg_stat_user_tables"
      Column      |           Type           | Modifiers 
------------------+--------------------------+-----------
 relid            | oid                      | 
 schemaname       | name                     | 
 relname          | name                     | 
 seq_scan         | bigint                   | 
 seq_tup_read     | bigint                   | 
 idx_scan         | bigint                   | 
 idx_tup_fetch    | bigint                   | 
 n_tup_ins        | bigint                   | 
 n_tup_upd        | bigint                   | 
 n_tup_del        | bigint                   | 
 n_tup_hot_upd    | bigint                   | 
 n_live_tup       | bigint                   | 
 n_dead_tup       | bigint                   | 
 last_vacuum      | timestamp with time zone | 
 last_autovacuum  | timestamp with time zone | 
 last_analyze     | timestamp with time zone | 
 last_autoanalyze | timestamp with time zone | 
*/


CREATE TABLE DatabaseTableStats AS
SELECT
    CAST(NULL AS timestamp without time zone) AS date_created,
    schemaname, relname, seq_scan, seq_tup_read, idx_scan, idx_tup_fetch,
    n_tup_ins, n_tup_upd, n_tup_del, n_tup_hot_upd, n_live_tup, n_dead_tup,
    last_vacuum, last_autovacuum, last_analyze, last_autoanalyze
FROM pg_stat_user_tables
WHERE FALSE;

ALTER TABLE DatabaseTableStats
    ADD CONSTRAINT databasetablestats_pkey
    PRIMARY KEY (date_created, schemaname, relname),
    ALTER COLUMN date_created
        SET DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    ALTER COLUMN date_created SET NOT NULL,
    ALTER COLUMN schemaname SET NOT NULL,
    ALTER COLUMN relname SET NOT NULL,
    ALTER COLUMN seq_scan SET NOT NULL,
    ALTER COLUMN seq_tup_read SET NOT NULL,
    ALTER COLUMN idx_scan SET NOT NULL,
    ALTER COLUMN idx_tup_fetch SET NOT NULL,
    ALTER COLUMN n_tup_ins SET NOT NULL,
    ALTER COLUMN n_tup_upd SET NOT NULL,
    ALTER COLUMN n_tup_del SET NOT NULL,
    ALTER COLUMN n_tup_hot_upd SET NOT NULL,
    ALTER COLUMN n_live_tup SET NOT NULL,
    ALTER COLUMN n_dead_tup SET NOT NULL;

CREATE TABLE DatabaseCpuStats (
    date_created timestamp without time zone NOT NULL
        DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    username text NOT NULL,
    cpu integer NOT NULL,
    CONSTRAINT databasecpustats_pkey PRIMARY KEY (date_created, username)
    );


INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 51, 0);

