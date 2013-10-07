SET client_min_messages=ERROR;

ALTER TABLE LaunchpadDatabaseRevision
    ADD branch_nick text,
    ADD revno integer,
    ADD revid text;

CREATE TABLE LaunchpadDatabaseUpdateLog (
    id serial primary key,
    start_time timestamp without time zone NOT NULL DEFAULT (
        CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    end_time timestamp without time zone,
    branch_nick text,
    revno integer,
    revid text);
   
INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 01, 3);
