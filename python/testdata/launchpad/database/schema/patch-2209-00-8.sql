-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE UNIQUE INDEX archive__distribution__purpose__distro_archives__key
    ON archive USING btree (distribution, purpose) WHERE purpose IN (1, 4, 7);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 0, 8);
