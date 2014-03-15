CREATE OR REPLACE FUNCTION update_database_disk_utilization() RETURNS void
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO public
    AS $$
    INSERT INTO DatabaseDiskUtilization
    SELECT
        CURRENT_TIMESTAMP AT TIME ZONE 'UTC',
        namespace, name,
        sub_namespace, sub_name,
        kind,
        (namespace || '.' ||  name || COALESCE(
                '/' || sub_namespace || '.' || sub_name, '')) AS sort,
        (stat).table_len,
        (stat).tuple_count,
        (stat).tuple_len,
        (stat).tuple_percent,
        (stat).dead_tuple_count,
        (stat).dead_tuple_len,
        (stat).dead_tuple_percent,
        (stat).free_space,
        (stat).free_percent
    FROM (
        -- Tables
        SELECT
            pg_namespace.nspname AS namespace,
            pg_class.relname AS name,
            NULL AS sub_namespace,
            NULL AS sub_name,
            pg_class.relkind AS kind,
            pgstattuple(pg_class.oid) AS stat
        FROM pg_class, pg_namespace
        WHERE
            pg_class.relnamespace = pg_namespace.oid
            AND pg_class.relkind = 'r'
            AND pg_table_is_visible(pg_class.oid)

        UNION ALL
        
        -- Indexes
        SELECT
            pg_namespace_table.nspname AS namespace,
            pg_class_table.relname AS name,
            pg_namespace_index.nspname AS sub_namespace,
            pg_class_index.relname AS sub_name,
            pg_class_index.relkind AS kind,
            pgstattuple(pg_class_index.oid) AS stat
        FROM
            pg_namespace AS pg_namespace_table,
            pg_namespace AS pg_namespace_index,
            pg_class AS pg_class_table,
            pg_class AS pg_class_index,
            pg_index,
            pg_am
        WHERE
            pg_class_index.relkind = 'i'
            AND pg_am.amname <> 'gin' -- pgstattuple doesn't support GIN
            AND pg_table_is_visible(pg_class_table.oid)
            AND pg_class_index.relnamespace = pg_namespace_index.oid
            AND pg_class_table.relnamespace = pg_namespace_table.oid
            AND pg_class_index.relam = pg_am.oid
            AND pg_index.indexrelid = pg_class_index.oid
            AND pg_index.indrelid = pg_class_table.oid

        UNION ALL

        -- TOAST tables
        SELECT
            pg_namespace_table.nspname AS namespace,
            pg_class_table.relname AS name,
            pg_namespace_toast.nspname AS sub_namespace,
            pg_class_toast.relname AS sub_name,
            pg_class_toast.relkind AS kind,
            pgstattuple(pg_class_toast.oid) AS stat
        FROM
            pg_namespace AS pg_namespace_table,
            pg_namespace AS pg_namespace_toast,
            pg_class AS pg_class_table,
            pg_class AS pg_class_toast
        WHERE
            pg_class_toast.relnamespace = pg_namespace_toast.oid
            AND pg_table_is_visible(pg_class_table.oid)
            AND pg_class_table.relnamespace = pg_namespace_table.oid
            AND pg_class_toast.oid = pg_class_table.reltoastrelid

        UNION ALL

        -- TOAST indexes
        SELECT
            pg_namespace_table.nspname AS namespace,
            pg_class_table.relname AS name,
            pg_namespace_index.nspname AS sub_namespace,
            pg_class_index.relname AS sub_name,
            pg_class_index.relkind AS kind,
            pgstattuple(pg_class_index.oid) AS stat
        FROM
            pg_namespace AS pg_namespace_table,
            pg_namespace AS pg_namespace_index,
            pg_class AS pg_class_table,
            pg_class AS pg_class_index,
            pg_class AS pg_class_toast
        WHERE
            pg_class_table.relnamespace = pg_namespace_table.oid
            AND pg_table_is_visible(pg_class_table.oid)
            AND pg_class_index.relnamespace = pg_namespace_index.oid
            AND pg_class_table.reltoastrelid = pg_class_toast.oid
            AND pg_class_index.oid = pg_class_toast.reltoastidxid
        ) AS whatever;
$$;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 21, 4);
