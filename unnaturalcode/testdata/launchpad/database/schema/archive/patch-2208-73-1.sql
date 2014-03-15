-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Use American English.

ALTER INDEX distribution_job__initialise_series__distroseries
  RENAME TO distribution_job__initialize_series__distroseries;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 73, 1);
