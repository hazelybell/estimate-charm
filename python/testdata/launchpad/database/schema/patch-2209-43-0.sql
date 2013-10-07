-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE INDEX branch__name__trgm ON branch
    USING gin (lower(name) trgm.gin_trgm_ops);
CREATE INDEX branch__unique_name__trgm ON branch
    USING gin (lower(unique_name) trgm.gin_trgm_ops);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 43, 0);
