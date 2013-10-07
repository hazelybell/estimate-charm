-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE Archive
   ADD COLUMN status integer DEFAULT 0 NOT NULL;
CREATE INDEX archive__status__idx ON Archive(status);


-- possible values for status are:
-- 0: ACTIVE
-- 1: DELETING

-- In the future, we'll add
-- DISABLED (instead of the disabled flag)
-- FROZEN (instead of the publish flag)

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 40, 0);
