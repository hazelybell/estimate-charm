SET client_min_messages=ERROR;

-- Permit bug searches ordered by 'importance' - the default - to serve from
-- index rather than doing the full search and sorting.

CREATE INDEX bugtask_importance_idx ON BugTask (importance, id desc nulls first);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 8, 2);
