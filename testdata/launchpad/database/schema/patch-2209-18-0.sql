-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE Packageset ADD COLUMN score INTEGER DEFAULT 0 NOT NULL;

COMMENT ON COLUMN Packageset.score IS 'Build score bonus for packages in this package set.';

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 18, 0);
