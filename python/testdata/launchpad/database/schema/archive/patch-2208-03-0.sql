SET client_min_messages=ERROR;

ALTER TABLE SuggestivePOTemplate
    ADD CONSTRAINT suggestivepotemplate__potemplate__fk
    FOREIGN KEY (potemplate) REFERENCES POTemplate
    ON DELETE CASCADE;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 03, 0);

