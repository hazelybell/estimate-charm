-- Copyright 2013 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE processor ADD COLUMN restricted BOOLEAN;
ALTER TABLE distroarchseries
    ADD COLUMN processor INTEGER REFERENCES processor,
    ADD CONSTRAINT distroarchseries__processor__distroseries__key UNIQUE (processor, distroseries);
ALTER TABLE archivearch
    ADD COLUMN processor INTEGER REFERENCES processor,
    ADD CONSTRAINT archivearch__archive__processor__key UNIQUE (archive, processor);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 49, 0);
