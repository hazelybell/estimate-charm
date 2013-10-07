SET client_min_messages=ERROR;

ALTER TABLE SourcePackageRecipeBuild ADD COLUMN dependencies text;
ALTER TABLE SourcePackageRecipeBuild ADD COLUMN pocket integer
    DEFAULT 0 NOT NULL;
ALTER TABLE SourcePackageRecipeBuild ADD COLUMN upload_log integer
    CONSTRAINT sourcepackagerecipebuild__upload_log__fk
    REFERENCES LibraryFileAlias;

CREATE INDEX sourcepackagerecipebuild__upload_log__idx
    ON SourcePackageRecipeBuild(upload_log) WHERE upload_log IS NOT NULL;

-- We can't drop tables in DB patches due to Slony-I limitations, so
-- we give them a magic name for database/schema/upgrade.py to deal
-- with correctly.
-- Drop the constraint right now so the person privacy checker doesn't
-- look at this table at all.
ALTER TABLE SourcePackageRecipeBuildUpload DROP CONSTRAINT sourcepackagerecipebuildupload_archive_fkey;
ALTER TABLE SourcePackageRecipeBuildUpload DROP CONSTRAINT sourcepackagerecipebuildupload_registrant_fkey;
ALTER TABLE SourcePackageRecipeBuildUpload DROP CONSTRAINT sourcepackagerecipebuildupload_sourcepackage_recipe_build_fkey;
ALTER TABLE SourcePackageRecipeBuildUpload DROP CONSTRAINT sourcepackagerecipebuildupload_upload_log_fkey;
ALTER TABLE SourcePackageRecipeBuildUpload SET SCHEMA todrop; 

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 32, 0);
