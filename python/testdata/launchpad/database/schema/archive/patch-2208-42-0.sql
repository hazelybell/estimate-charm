SET client_min_messages=ERROR;

-- This index is getting bloated, and is mostly NULL.
ALTER TABLE Bug DROP CONSTRAINT bug_name_key;
CREATE UNIQUE INDEX bug__name__key ON Bug (name) WHERE name IS NOT NULL;

-- This table is huge and append only
ALTER TABLE BranchRevision SET (fillfactor=100);
ALTER TABLE MessageChunk SET (fillfactor=100);
ALTER TABLE Message SET (fillfactor=100);
ALTER TABLE BugActivity SET (fillfactor=100);
ALTER TABLE LibraryFileContent SET (fillfactor=100);
ALTER TABLE Karma SET (fillfactor=100);
ALTER TABLE BugWatchActivity SET (fillfactor=100);
ALTER TABLE Country SET (fillfactor=100);
ALTER TABLE Continent SET (fillfactor=100);
ALTER TABLE DatabaseCPUStats SET (fillfactor=100);
ALTER TABLE DatabaseTableStats SET (fillfactor=100);
ALTER TABLE POTranslation SET (fillfactor=100);


-- Unwanted indexes
DROP INDEX archive__commercial__idx;
DROP INDEX bugwatchactivity__date__idx;
DROP INDEX binarypackagerelease_version_idx; -- Duplicate
DROP INDEX product_bugcontact_idx; -- Duplicate
DROP INDEX hwvendorname__name__idx; -- Duplicate

-- Missing constraint we believe we rely on, and drop the duplicate
-- non-unique index.
ALTER TABLE Packaging ALTER COLUMN distroseries SET NOT NULL;
DROP INDEX packaging__distroseries__sourcepackagename__idx;

-- Should be NOT NULL per Bug #726128
ALTER TABLE FeatureFlag ALTER COLUMN value SET NOT NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 42, 0);

