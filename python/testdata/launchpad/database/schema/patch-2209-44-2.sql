-- Copyright 2013 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE branchmergeproposal DROP COLUMN merge_diff;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 44, 2);
