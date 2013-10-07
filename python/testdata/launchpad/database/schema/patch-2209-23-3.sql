-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE INDEX binarypackagepublishinghistory__archive__das__bpn__idx
    ON binarypackagepublishinghistory
    (archive, distroarchseries, binarypackagename);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 23, 3);
