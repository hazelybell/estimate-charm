-- Copyright 2009 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Add a registrant column to distributions.
ALTER TABLE Distribution
    ADD COLUMN registrant integer REFERENCES Person;

-- Set registrant to owner for existing distros.
update Distribution
    SET registrant = owner;

-- Add NOT NULL constraint to registrant column.
ALTER TABLE Distribution ALTER COLUMN registrant SET NOT NULL;

-- Add index to registrant column.
CREATE INDEX distribution__registrant__idx ON Distribution(registrant);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 53, 0);
