-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE INDEX sourcepackagepublishinghistory__packageupload__idx ON sourcepackagepublishinghistory USING btree (id) WHERE packageupload IS NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 15, 3);
