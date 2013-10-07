-- Copyright 2009 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- There is no real reason to have limits on review_type, and it is just
-- adding an artificial constraint that just gets in the way.

-- Drop the UNIQUE indices
DROP INDEX codereviewvote__branch_merge_proposal__reviewer__key;
DROP INDEX codereviewvote__branch_merge_proposal__reviewer__review_type__k;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 17, 0);
