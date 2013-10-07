-- Copyright 2013 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE INDEX incrementaldiff__diff__idx ON incrementaldiff(diff);
CREATE INDEX previewdiff__diff__idx ON previewdiff(diff);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 44, 4);
