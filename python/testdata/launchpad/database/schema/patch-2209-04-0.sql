-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE specification
    ADD COLUMN date_last_changed timestamp without time zone,
    ADD COLUMN last_changed_by integer REFERENCES person;

ALTER TABLE specification ALTER COLUMN date_last_changed SET DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC');

CREATE INDEX specification__last_changed_by__idx ON specification USING btree (last_changed_by) WHERE (last_changed_by IS NOT NULL);
CREATE INDEX specification__date_last_changed__idx ON specification USING btree (date_last_changed);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 04, 0);


