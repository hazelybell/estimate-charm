-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE DistributionMirror
    ADD COLUMN country_dns_mirror boolean DEFAULT FALSE NOT NULL;

--- Index for country archive mirrors, one per country.
CREATE UNIQUE INDEX distributionmirror__archive__distribution__country__key
    ON DistributionMirror(distribution, country, content)
    WHERE country_dns_mirror IS TRUE AND content = 1;

--- Index for country CD image mirrors, one per country.
CREATE UNIQUE INDEX distributionmirror__releases__distribution__country__key
    ON DistributionMirror(distribution, country, content)
    WHERE country_dns_mirror IS TRUE AND content = 2;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 23, 0);
