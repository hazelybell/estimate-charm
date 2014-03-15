SET client_min_messages=ERROR;

ALTER TABLE Language ALTER englishname SET NOT NULL;

ALTER TABLE LibraryFileContent ALTER filesize TYPE bigint;
-- Do later - too much downtime this cycle.
--CLUSTER LibraryFileContent USING libraryfilecontent_pkey; -- repack

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 21, 0);
