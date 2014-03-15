-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

ALTER TABLE POTMsgSet DROP COLUMN "sequence";

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 01, 2);
