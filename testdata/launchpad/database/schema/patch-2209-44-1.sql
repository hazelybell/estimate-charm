-- Copyright 2013 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE UNIQUE INDEX previewdiff__branch_merge_proposal__date_created__key
    ON previewdiff (branch_merge_proposal, date_created);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 44, 1);
