-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

-- Add a column that identifies the person or team that is exempt from
-- the regexp check.
ALTER TABLE NameBlacklist
    ADD COLUMN admin
        INTEGER,
    ADD CONSTRAINT nameblacklist_admin_fk FOREIGN KEY ("admin")
        REFERENCES person (id) MATCH SIMPLE
        ON UPDATE NO ACTION ON DELETE NO ACTION;


INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 36, 0);
