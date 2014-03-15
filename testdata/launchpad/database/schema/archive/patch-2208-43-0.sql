SET client_min_messages TO error;

CREATE TABLE DatabaseDiskUtilization (
    date_created timestamp without time zone
        DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC') NOT NULL,
    namespace text NOT NULL,
    name text NOT NULL,
    sub_namespace text,
    sub_name text,
    kind char NOT NULL,
    sort text NOT NULL,
    table_len bigint NOT NULL,
    tuple_count bigint NOT NULL,
    tuple_len bigint NOT NULL,
    tuple_percent float8 NOT NULL,
    dead_tuple_count bigint NOT NULL,
    dead_tuple_len bigint NOT NULL,
    dead_tuple_percent float8 NOT NULL,
    free_space bigint NOT NULL,
    free_percent float8 NOT NULL,
    CONSTRAINT databasediskutilization_pkey PRIMARY KEY (date_created, sort)
    ) WITH (fillfactor=100);

CREATE OR REPLACE VIEW LatestDatabaseDiskUtilization AS
SELECT * FROM DatabaseDiskUtilization
WHERE date_created = (SELECT max(date_created) FROM DatabaseDiskUtilization);


INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 43, 0);
