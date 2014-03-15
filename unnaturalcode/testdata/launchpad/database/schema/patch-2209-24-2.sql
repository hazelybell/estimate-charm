SET client_min_messages = ERROR;

-- ftq() moved to public. Remove the old code to avoid confusion.
DROP FUNCTION ts2.ftq(text);
DROP FUNCTION ts2._ftq(text);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 24, 2);
