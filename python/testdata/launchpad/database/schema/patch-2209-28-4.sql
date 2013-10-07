-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

ALTER TABLE AccessArtifact ADD COLUMN specification integer REFERENCES specification DEFAULT NULL;

ALTER TABLE AccessArtifact DROP CONSTRAINT has_artifact;

ALTER TABLE AccessArtifact ADD CONSTRAINT has_artifact CHECK (
    (bug IS NOT NULL AND branch IS NULL AND specification IS NULL) OR
    (bug IS NULL AND branch IS NOT NULL AND specification IS NULL) OR
    (bug IS NULL AND branch IS NULL AND specification IS NOT NULL));

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 28, 4);
