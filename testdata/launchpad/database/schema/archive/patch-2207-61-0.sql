-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;
ALTER TABLE SourcePackageRecipe ADD COLUMN is_stale BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE SourcePackageRecipeBuild ADD COLUMN manifest INTEGER REFERENCES SourcePackageRecipeData;

CREATE INDEX sourcepackagerecipe__is_stale__build_daily__idx
ON SourcepackageRecipe(is_stale, build_daily);

CREATE INDEX sourcepackagerecipebuild__manifest__idx ON SourcepackageRecipeBuild(manifest);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 61, 0);
