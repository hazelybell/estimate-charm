-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- denormalise message.owner for query efficiency.
ALTER TABLE QuestionMessage ADD COLUMN owner int;
-- And an index.
CREATE INDEX questionmessage__owner__idx ON QuestionMessage(owner);

UPDATE QuestionMessage SET owner = (
    SELECT owner FROM Message WHERE Message.id=QuestionMessage.message);

ALTER TABLE QuestionMessage ALTER COLUMN owner SET NOT NULL;

-- Triggers to maintain in both directions.
CREATE TRIGGER questionmessage__owner__mirror
    AFTER UPDATE OR INSERT ON questionmessage
    FOR EACH ROW EXECUTE PROCEDURE questionmessage_copy_owner_from_message();
CREATE TRIGGER message__owner__mirror__questionmessage AFTER UPDATE ON message
    FOR EACH ROW EXECUTE PROCEDURE message_copy_owner_to_questionmessage();

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 69, 0);
