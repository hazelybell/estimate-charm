-- Copyright 2009 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Add bugtask heat denormalisation for sort efficiency. We will enforce non-null subsequently;

ALTER TABLE bugtask ADD COLUMN heat integer;

UPDATE bugtask SET heat=bug.heat FROM bug WHERE bug.id=bugtask.bug;

ALTER TABLE bugtask ALTER COLUMN heat SET NOT NULL;
ALTER TABLE bugtask ALTER COLUMN heat SET DEFAULT 0;

-- Primary use case is 'sort by heat in a context'; for no context we can use
-- the bug.heat column & index.

-- contexts - product, productseries, distro sourcepackage, distroseries sourcepackage, distro and distroseries.
-- product context
CREATE INDEX bugtask__product__heat__idx ON bugtask USING btree (product, heat) WHERE product IS NOT NULL;
-- productseries context
CREATE INDEX bugtask__productseries__heat__idx ON bugtask USING btree (productseries, heat) WHERE productseries IS NOT NULL;
-- distribution context (handles distribution and distribution source package queries)
CREATE INDEX bugtask__distribution_sourcepackage__heat__idx ON bugtask USING btree (distribution, sourcepackagename, heat) WHERE distribution IS NOT NULL;
-- distroseries context (handles series and series source package queries)
CREATE INDEX bugtask__distroseries_sourcepackage__heat__idx ON bugtask USING btree (distroseries, sourcepackagename, heat) WHERE distroseries IS NOT NULL;

-- may wish to drop these indices as superceded by the above; if so should
-- CLUSTER the distribution_sourcepackagename index.
-- DROP INDEX bugtask__distribution__sourcepackagename__idx
-- DROP INDEX bugtask__distroseries__sourcepackagename__idx

-- When a bug is changed we copy the heat; brand new bugs will not have their
-- heat copied until they are recalculated (but equally brand new bugs have 0
-- heat).
CREATE TRIGGER bug_to_bugtask_heat AFTER UPDATE ON bug FOR EACH ROW EXECUTE PROCEDURE bug_update_heat_copy_to_bugtask();

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 59, 0);
