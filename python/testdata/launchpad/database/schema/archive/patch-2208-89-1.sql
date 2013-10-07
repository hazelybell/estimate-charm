-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

CREATE INDEX branch__transitively_private__idx ON Branch(transitively_private);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 89, 1);

