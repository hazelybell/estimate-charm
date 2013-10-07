-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE sourcepackagerecipe DROP COLUMN distroseries;
ALTER TABLE sourcepackagerecipe ADD COLUMN build_daily BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE SourcePackageRecipeDistroSeries
(
    id serial NOT NULL PRIMARY KEY,
    sourcepackagerecipe integer NOT NULL REFERENCES SourcePackageRecipe(id),
    distroseries integer NOT NULL REFERENCES DistroSeries(id),
    CONSTRAINT sourcepackagerecipe_distroseries_unique UNIQUE (
      sourcepackagerecipe, distroseries)
);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 38, 0);
