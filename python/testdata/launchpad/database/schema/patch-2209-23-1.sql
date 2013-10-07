-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE INDEX binarypackagename__name__trgm ON binarypackagename
    USING gin (name trgm.gin_trgm_ops);
CREATE INDEX sourcepackagename__name__trgm ON sourcepackagename
    USING gin (name trgm.gin_trgm_ops);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 23, 1);
