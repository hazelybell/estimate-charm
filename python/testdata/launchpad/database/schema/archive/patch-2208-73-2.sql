-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- For IHWSubmissionSet, which can now search by date_created.
CREATE INDEX hwsubmission__date_created__idx ON hwsubmission USING btree (date_created);

-- For IHWSubmissionSet, which can now search by date_submitted.
CREATE INDEX hwsubmission__date_submitted__idx ON hwsubmission USING btree (date_submitted);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 73, 2);
