-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

CREATE UNIQUE INDEX accessartifact__specification__key
    ON AccessArtifact(specification)  WHERE specification IS NOT NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 28, 5);
