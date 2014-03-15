-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- We no longer need date_next_suggest_packaging; the portlet using it is
-- gone.
ALTER TABLE product DROP COLUMN date_next_suggest_packaging;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 34, 1);
