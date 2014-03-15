-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

ALTER TABLE Branch DROP COLUMN merge_robot CASCADE;
ALTER TABLE Branch DROP COLUMN merge_control_status;

CREATE TABLE BranchMergeQueue (
    id serial NOT NULL PRIMARY KEY,
    registrant integer NOT NULL REFERENCES Person,
    owner integer NOT NULL REFERENCES Person,
    name TEXT NOT NULL,
    description TEXT,
    configuration TEXT,
    date_created timestamp without time zone
        DEFAULT timezone('UTC'::text, now()) NOT NULL,
    CONSTRAINT owner_name UNIQUE (owner, name),
    CONSTRAINT valid_name CHECK (valid_name(name))
);
CREATE INDEX branchmergequeue__registrant__idx ON BranchMergeQueue(registrant);

ALTER TABLE Branch ADD COLUMN merge_queue integer REFERENCES BranchMergeQueue;
ALTER TABLE Branch ADD COLUMN merge_queue_config TEXT;
CREATE INDEX branch__merge_queue__idx ON Branch(merge_queue);

ALTER TABLE BranchMergeRobot DROP CONSTRAINT "branchmergerobot_registrant_fkey";
ALTER TABLE BranchMergeRobot DROP CONSTRAINT "branchmergerobot_owner_fkey";
ALTER TABLE BranchMergeRobot SET SCHEMA todrop;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 22, 0);
