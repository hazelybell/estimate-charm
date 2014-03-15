-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

--- Index for owner and source package recipe name.
ALTER TABLE SourcePackageRecipe ADD CONSTRAINT
    sourcepackagerecipe__owner__name__key UNIQUE (owner, name);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 59, 0);
