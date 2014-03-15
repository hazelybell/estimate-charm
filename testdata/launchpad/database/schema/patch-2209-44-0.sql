-- Copyright 2013 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE previewdiff
    ADD COLUMN branch_merge_proposal integer REFERENCES branchmergeproposal,
    ADD COLUMN date_created timestamp without time zone;
ALTER TABLE previewdiff
    ALTER COLUMN date_created
        SET DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC');

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 44, 0);
