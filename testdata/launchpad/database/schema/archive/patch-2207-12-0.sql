SET client_min_messages=ERROR;

UPDATE SourcePackageRelease SET dsc_format='1.0' WHERE dsc_format IS NULL;
ALTER TABLE SourcePackageRelease ALTER COLUMN dsc_format SET NOT NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 12, 0);

