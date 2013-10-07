-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE INDEX
    sourcepackagepublishinghistory__archive__distroseries__component__spn__idx
    ON sourcepackagepublishinghistory
    USING btree (archive, distroseries, component, sourcepackagename)
    WHERE status IN (1, 2);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 16, 2);
