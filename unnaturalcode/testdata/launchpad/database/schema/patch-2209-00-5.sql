SET client_min_messages = ERROR;

-- Compatibility code. During transition, we need code that runs with
-- both PostgreSQL 8.4 and 9.1.

-- This used to be a simple SQL function, but PG 9.1 grew an extra
-- column to pg_stat_activity. We can revert once PG 8.4
-- compatibility is not needed.
--     SELECT
--         datid, datname, procpid, usesysid, usename,
--         CASE
--             WHEN current_query LIKE '<IDLE>%'
--                 OR current_query LIKE 'autovacuum:%'
--                 THEN current_query
--             ELSE
--                 '<HIDDEN>'
--         END AS current_query,
--         waiting, xact_start, query_start,
--         backend_start, client_addr, client_port
--     FROM pg_catalog.pg_stat_activity;
--
CREATE OR REPLACE FUNCTION activity()
RETURNS SETOF pg_stat_activity
VOLATILE SECURITY DEFINER SET search_path = public
LANGUAGE plpgsql AS $$
DECLARE
    a pg_stat_activity%ROWTYPE;
BEGIN
    FOR a IN SELECT * FROM pg_stat_activity LOOP
        IF a.current_query NOT LIKE '<IDLE>%'
            AND a.current_query NOT LIKE 'autovacuum:%' THEN
            a.current_query := '<HIDDEN>';
        END IF;
        RETURN NEXT a;
    END LOOP;
END;
$$;


INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 0, 5);
