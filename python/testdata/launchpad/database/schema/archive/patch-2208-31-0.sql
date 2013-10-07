-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

ALTER TABLE Product
    ADD COLUMN enable_bugfiling_duplicate_search
        BOOLEAN NOT NULL DEFAULT True;
ALTER TABLE DistributionSourcePackage
    ADD COLUMN enable_bugfiling_duplicate_search
        BOOLEAN NOT NULL DEFAULT True;

CLUSTER DistributionSourcePackage USING
    distributionpackage__sourcepackagename__distribution__key;
CLUSTER Product USING product_name_key;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 31, 0);
