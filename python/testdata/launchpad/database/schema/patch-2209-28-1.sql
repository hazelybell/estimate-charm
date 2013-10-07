-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

alter table specification add column information_type integer not null default 1;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 28, 1);
