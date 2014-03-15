SET client_min_messages=ERROR;

-- Per Bug #417636
CREATE UNIQUE INDEX bugtask__productseries__bug__key
ON BugTask(productseries, bug) WHERE productseries IS NOT NULL;

DROP INDEX bugtask__productseries__idx;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 0, 2);

