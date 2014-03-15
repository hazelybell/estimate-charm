-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

CREATE UNIQUE INDEX accesspolicy__person__key ON accesspolicy USING btree (person) WHERE (person IS NOT NULL);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 30, 2);
