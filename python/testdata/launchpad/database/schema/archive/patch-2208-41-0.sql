SET client_min_messages=ERROR;

alter table bugmessage alter column index set not null;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 41, 0);
