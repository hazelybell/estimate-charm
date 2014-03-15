-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Sharing has made security contact obsolete.
ALTER TABLE product DROP COLUMN security_contact;
ALTER TABLE distribution DROP COLUMN security_contact;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 26, 4);
