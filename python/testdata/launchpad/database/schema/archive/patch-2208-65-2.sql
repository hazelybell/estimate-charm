SET client_min_messages=ERROR;

CREATE INDEX translationmessage__potemplate__idx
ON TranslationMessage (potemplate) WHERE potemplate IS NOT NULL;

CREATE INDEX potmsgset__potemplate__idx
ON PotMsgSet (potemplate) WHERE potemplate IS NOT NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 65, 2);
