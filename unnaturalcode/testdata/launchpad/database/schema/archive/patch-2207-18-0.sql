SET client_min_messages=ERROR;

-- DB patches have left this bloated. Repack.
CLUSTER LibraryFileAlias USING libraryfilealias_pkey;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 18, 0);

