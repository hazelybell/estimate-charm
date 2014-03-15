-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE TABLE TranslationTemplatesBuild (
    id SERIAL PRIMARY KEY,
    build_farm_job integer NOT NULL REFERENCES BuildFarmJob(id),
    branch integer NOT NULL REFERENCES Branch(id));

CREATE INDEX translationtemplatesbuild__build_farm_job__idx ON
    TranslationTemplatesBuild(build_farm_job);

CREATE INDEX translationtemplatesbuild__branch__idx ON
    TranslationTemplatesBuild(branch);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 13, 0);
