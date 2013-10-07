-- Copyright 2009 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;


-- Add a column for external archive dependencies.
ALTER TABLE Archive
  ADD COLUMN external_dependencies text DEFAULT NULL;


INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 05, 0);
