-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE INDEX buildfarmjob__builder__status__date_finished__id__idx ON BuildFarmJob(builder, status, date_finished DESC, id) WHERE builder IS NOT NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 27, 4);
