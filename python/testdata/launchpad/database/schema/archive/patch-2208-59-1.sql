-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Poor index, superceded in -2.
DROP INDEX bugtask__product__heat__idx;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 59, 1);
