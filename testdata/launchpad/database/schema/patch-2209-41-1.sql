-- Copyright 2013 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE INDEX binarypackagebuild__log__idx
    ON binarypackagebuild (log);
CREATE INDEX binarypackagebuild__upload_log__idx
    ON binarypackagebuild (upload_log);
CREATE INDEX binarypackagebuild__build_farm_job__idx
    ON binarypackagebuild (build_farm_job);

CREATE INDEX sourcepackagerecipebuild__log__idx
    ON sourcepackagerecipebuild (log);
CREATE INDEX sourcepackagerecipebuild__upload_log__idx
    ON sourcepackagerecipebuild (upload_log);
CREATE INDEX sourcepackagerecipebuild__build_farm_job__idx
    ON sourcepackagerecipebuild (build_farm_job);

CREATE INDEX translationtemplatesbuild__log__idx
    ON translationtemplatesbuild (log);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 41, 1);
