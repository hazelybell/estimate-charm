-- Copyright 2009 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages TO ERROR;

DROP INDEX bug__hotness__idx;
ALTER table bug ADD COLUMN heat_last_updated timestamp without time zone;
ALTER table bug RENAME COLUMN hotness to heat;
ALTER table bugtask RENAME COLUMN hotness_rank to heat_rank;
CREATE INDEX bug__heat_last_updated__idx ON bug USING btree (heat_last_updated);
CREATE INDEX bug__heat__idx ON bug USING btree (heat);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 27, 0);
