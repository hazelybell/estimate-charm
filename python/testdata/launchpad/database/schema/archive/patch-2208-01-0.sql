-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

CREATE INDEX milestone_dateexpected_name_sort
ON Milestone
USING btree (milestone_sort_key(dateexpected, name));

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 01, 0);
