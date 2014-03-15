-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Create a unified unique index with access_policy and without
-- fixed_upstream.
CREATE UNIQUE INDEX bugsummary__unique ON bugsummary USING btree
    ((COALESCE(product, (-1))), (COALESCE(productseries, (-1))),
     (COALESCE(distribution, (-1))), (COALESCE(distroseries, (-1))),
     (COALESCE(sourcepackagename, (-1))), status, importance, has_patch,
     (COALESCE(tag, ''::text)), (COALESCE(milestone, (-1))),
     (COALESCE(viewed_by, (-1))), (COALESCE(access_policy, (-1))));

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 19, 2);
