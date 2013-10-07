SET client_min_messages = ERROR;

DROP INDEX bugtaskflat__fti__idx;
ALTER INDEX bugtaskflat__fti__idx2 RENAME TO bugtaskflat__fti__idx;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 21, 1);
