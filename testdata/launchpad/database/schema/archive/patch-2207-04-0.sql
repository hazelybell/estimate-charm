-- Copyright 2009 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;


-- Add a column to indicate that the attendee is physically attending
-- the sprint.
ALTER TABLE SprintAttendance
  ADD COLUMN is_physical BOOLEAN NOT NULL DEFAULT FALSE;


INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 04, 0);
