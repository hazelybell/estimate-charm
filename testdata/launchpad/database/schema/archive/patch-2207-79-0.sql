-- Copyright 2010 Canonical Ltd. This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

-- Update the flag restricted of LibraryFileAlias records which belong
-- to bug attachments of private bugs.

SET client_min_messages=ERROR;

UPDATE LibraryFileAlias SET restricted=TRUE
FROM BugAttachment, Bug
WHERE
    LibraryFileAlias.id = BugAttachment.libraryfile
    AND Bug.id = BugAttachment.bug
    AND Bug.private IS TRUE
    AND restricted=FALSE;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 79, 0);
