-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE INDEX bugsummary__milestone__idx
ON BugSummary(milestone) WHERE milestone IS NOT NULL;


CREATE INDEX bugsummary__full__idx
ON BugSummary(status, product, productseries, distribution, distroseries, sourcepackagename, viewed_by, milestone, tag);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 63, 2);
