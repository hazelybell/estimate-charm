-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- denormalise message.owner for query efficiency.
ALTER TABLE bugmessage ADD COLUMN owner int;
-- And an index.
CREATE INDEX bugmessage__owner__index__idx ON bugmessage USING btree(owner, index);

-- Triggers to maintain in both directions.
CREATE TRIGGER bugmessage__owner__mirror AFTER UPDATE OR INSERT ON bugmessage FOR EACH ROW EXECUTE PROCEDURE bugmessage_copy_owner_from_message();
CREATE TRIGGER message__owner__mirror AFTER UPDATE ON message FOR EACH ROW EXECUTE PROCEDURE message_copy_owner_to_bugmessage();

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 60, 0);
