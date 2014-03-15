-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE INDEX bugbranch__branch__idx ON bugbranch USING btree (branch);
CREATE INDEX scriptactivity__hostname__name__date_completed__idx
    ON scriptactivity USING btree (hostname, name, date_completed);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 0, 9);
