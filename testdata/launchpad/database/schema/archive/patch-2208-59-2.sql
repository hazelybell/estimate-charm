-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Better indices from qa testing.

-- product context, id needed to override bitmap index plas.
CREATE INDEX bugtask__product__heat__id__idx ON bugtask USING btree (product, heat DESC, id) WHERE product IS NOT NULL;
-- And just distribution
CREATE INDEX bugtask__distribution__heat__id__idx ON bugtask USING btree(distribution, heat DESC, id) WHERE distribution IS NOT NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 59, 2);
