-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

ALTER TABLE Builder
    ADD COLUMN failure_count integer not null default 0;

ALTER TABLE BuildFarmJob
    ADD COLUMN failure_count integer not null default 0;



INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 4, 0);
