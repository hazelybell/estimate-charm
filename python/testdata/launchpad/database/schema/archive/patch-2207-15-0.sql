SET client_min_messages=ERROR;

ALTER TABLE LibraryFileAlias
 ALTER COLUMN content DROP NOT NULL;

UPDATE LibraryFileAlias SET content=NULL
FROM LibraryFileContent
WHERE LibraryFileAlias.content = LibraryFileContent.id
    AND deleted IS TRUE;

ALTER TABLE LibraryFileContent
 DROP COLUMN datemirrored,
 DROP COLUMN deleted;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 15, 0);
