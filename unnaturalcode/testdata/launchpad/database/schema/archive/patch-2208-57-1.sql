-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Partial index for queue processing view : the lopsided data makes this
-- necessary (millions of rows matching the archive, 100's of rows match the
-- query).


CREATE INDEX packageupload__id_distroseries__archive__idx ON
    packageupload(id, distroseries, archive) WHERE status IN (0,1);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 57, 1);
