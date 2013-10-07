-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

CREATE INDEX libraryfilealias__expires_content_not_null_idx
    ON libraryfilealias(expires) WHERE content IS NOT NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 88, 1);
