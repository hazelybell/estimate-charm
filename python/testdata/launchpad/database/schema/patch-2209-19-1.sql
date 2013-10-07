-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE INDEX bugsummary__distribution__idx2 ON bugsummary USING btree
    (distribution, sourcepackagename) WHERE distribution IS NOT NULL;
CREATE INDEX bugsummary__distroseries__idx2 ON bugsummary USING btree
    (distroseries, sourcepackagename) WHERE distroseries IS NOT NULL;
CREATE INDEX bugsummary__distribution_count__idx2 ON bugsummary USING btree
    (distribution, sourcepackagename, status)
    WHERE distribution IS NOT NULL AND tag IS NULL;
CREATE INDEX bugsummary__distroseries_count__idx2 ON bugsummary USING btree
    (distroseries, sourcepackagename, status)
    WHERE distroseries IS NOT NULL AND tag IS NULL;
CREATE INDEX bugsummary__distribution_tag_count__idx2 ON bugsummary USING btree
    (distribution, sourcepackagename, status)
    WHERE distribution IS NOT NULL AND tag IS NOT NULL;
CREATE INDEX bugsummary__distroseries_tag_count__idx2 ON bugsummary USING btree
    (distroseries, sourcepackagename, status)
    WHERE distroseries IS NOT NULL AND tag IS NOT NULL;
CREATE INDEX bugsummary__full__idx2 ON bugsummary USING btree
    (tag, status, product, productseries, distribution, distroseries,
     sourcepackagename, viewed_by, access_policy, milestone, importance);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 19, 1);
