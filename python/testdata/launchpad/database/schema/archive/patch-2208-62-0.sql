-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

-- Make the existing primary key index think it is not the primary key.
UPDATE pg_index SET indisprimary = FALSE
WHERE pg_index.indexrelid = 'revisionnumber_pkey'::regclass;

UPDATE pg_constraint SET contype = 'u'
WHERE
    conrelid='branchrevision'::regclass
    AND conname='revisionnumber_pkey';


-- Make an existing index think it is the primary key.
UPDATE pg_index SET indisprimary = TRUE
WHERE pg_index.indexrelid = 'revision__revision__branch__key'::regclass;

UPDATE pg_constraint SET contype='p'
WHERE
    conrelid='branchrevision'::regclass
    AND conname='revision__revision__branch__key';


-- This view is no longer used - no need to recreate it.
DROP VIEW RevisionNumber;

ALTER TABLE BranchRevision
    DROP COLUMN id,
    DROP CONSTRAINT revision__branch__revision__key;

-- Rename our new primary key index to the old name to keep Slony-I happy.
ALTER INDEX revision__revision__branch__key RENAME TO revisionnumber_pkey;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 62, 0);

