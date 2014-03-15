SET client_min_messages=ERROR;

-- Delete index obsoleted by bugtask__date_closed__id__idx2

DROP INDEX bugtask__date_closed__id__idx;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 15, 0);
