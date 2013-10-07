SET client_min_messages=ERROR;

ALTER TABLE LaunchpadDatabaseRevision
    ADD start_time timestamp without time zone,
    ADD end_time timestamp without time zone;
   
ALTER TABLE LaunchpadDatabaseRevision
    ALTER COLUMN start_time
        SET DEFAULT (transaction_timestamp() AT TIME ZONE 'UTC'),
    ALTER COLUMN end_time
        SET DEFAULT (statement_timestamp() AT TIME ZONE 'UTC');

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 01, 1);

