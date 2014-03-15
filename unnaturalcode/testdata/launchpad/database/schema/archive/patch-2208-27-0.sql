-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;
ALTER TABLE SourcePackageRecipeDataInstruction DROP CONSTRAINT sourcepackagerecipedatainstruction__directory_not_null;
ALTER TABLE SourcePackageRecipeDataInstruction ADD CONSTRAINT sourcepackagerecipedatainstruction__directory_not_null CHECK (type = 3 OR type = 1 AND directory IS NULL OR type = 2 AND directory IS NOT NULL);
ALTER TABLE SourcePackageRecipeDataInstruction ADD COLUMN source_directory text;
ALTER TABLE SourcePackageRecipeDataInstruction ADD CONSTRAINT sourcepackagerecipedatainstruction__source_directory_null CHECK (type in (1, 2) AND source_directory IS NULL OR type = 3 AND source_directory IS NOT NULL);


INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 27, 0);
