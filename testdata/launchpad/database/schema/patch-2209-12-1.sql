-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE INDEX bug__information_type__idx ON Bug(information_type);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 12, 1);
