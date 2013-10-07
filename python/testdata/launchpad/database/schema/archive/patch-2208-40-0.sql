SET client_min_messages=ERROR;

DROP INDEX binarypackagerelease_version_sort;
DROP INDEX sourcepackagerelease_version_sort;

ALTER TABLE SourcePackageRelease ALTER COLUMN version TYPE debversion;
ALTER TABLE BinaryPackageRelease ALTER COLUMN version TYPE debversion;

CREATE INDEX SourcePackageRelease__version__idx
    ON SourcePackageRelease(version);
CREATE INDEX BinaryPackageRelease__version__idx
    ON BinaryPackageRelease(version);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 40, 0);
