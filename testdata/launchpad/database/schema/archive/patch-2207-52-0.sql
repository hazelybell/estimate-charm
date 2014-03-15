-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Add a column to track when Launchpad can resume suggesting Ubuntu packages
-- that the project provides.
ALTER TABLE Product
    ADD COLUMN date_next_suggest_packaging timestamp without time zone;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 52, 0);
