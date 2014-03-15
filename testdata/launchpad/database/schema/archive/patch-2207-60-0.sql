-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE BranchSubscription
   ADD COLUMN subscribed_by integer REFERENCES Person;

UPDATE BranchSubscription
SET subscribed_by = person;

ALTER TABLE BranchSubscription ALTER COLUMN subscribed_by SET NOT NULL;

-- Index needed for person merging.
CREATE INDEX branchsubscription__subscribed_by__idx
   ON BranchSubscription(subscribed_by);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 60, 0);
