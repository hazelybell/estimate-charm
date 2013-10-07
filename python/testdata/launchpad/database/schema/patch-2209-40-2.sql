-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE INDEX packageupload__searchable_names__idx ON packageupload
    USING gin ((searchable_names::tsvector));
CREATE INDEX packageupload__searchable_versions__idx ON packageupload
    USING gin (searchable_versions);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 40, 2);
