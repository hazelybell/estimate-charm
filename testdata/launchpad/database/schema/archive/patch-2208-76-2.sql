-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE INDEX message__datecreated__idx ON Message(datecreated);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 76, 2);
