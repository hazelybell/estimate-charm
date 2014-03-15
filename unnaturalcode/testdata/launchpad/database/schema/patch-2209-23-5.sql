-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE INDEX buildfarmjob__status__id__idx ON buildfarmjob (status, id);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 23, 5);
