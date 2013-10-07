SET client_min_messages = ERROR;

CREATE INDEX bugtaskflat__fti__idx2 ON BugTaskFlat USING GIN (fti);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 21, 0);
