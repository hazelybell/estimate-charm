-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- And add a BugTaskFlat.latest_patch_uploaded sort index to each set.
CREATE INDEX
    bugtaskflat__distribution__latest_patch_uploaded__bugtask__idx
    ON bugtaskflat
    USING btree (distribution, latest_patch_uploaded, bugtask DESC)
    WHERE distribution IS NOT NULL;
CREATE INDEX
    bugtaskflat__distribution__spn__latest_patch_uploaded__bug__idx
    ON bugtaskflat
    USING btree (
        distribution, sourcepackagename, latest_patch_uploaded, bug DESC)
    WHERE distribution IS NOT NULL;
CREATE INDEX
    bugtaskflat__distroseries__latest_patch_uploaded__bugtask__idx
    ON bugtaskflat
    USING btree (distroseries, latest_patch_uploaded, bugtask DESC)
    WHERE distroseries IS NOT NULL;
CREATE INDEX
    bugtaskflat__distroseries__spn__latest_patch_uploaded__bug__idx
    ON bugtaskflat
    USING btree (
        distroseries, sourcepackagename, latest_patch_uploaded, bug DESC)
    WHERE distroseries IS NOT NULL;
CREATE INDEX
    bugtaskflat__product__latest_patch_uploaded__bug__idx
    ON bugtaskflat
    USING btree (product, latest_patch_uploaded, bug DESC)
    WHERE product IS NOT NULL;
CREATE INDEX
    bugtaskflat__productseries__latest_patch_uploaded__bug__idx
    ON bugtaskflat
    USING btree (productseries, latest_patch_uploaded, bug DESC)
    WHERE productseries IS NOT NULL;
CREATE INDEX
    bugtaskflat__latest_patch_uploaded__bugtask__idx
    ON bugtaskflat
    USING btree (latest_patch_uploaded, bugtask DESC);

-- Also BugTaskFlat.date_closed.
CREATE INDEX
    bugtaskflat__distribution__date_closed__bugtask__idx
    ON bugtaskflat
    USING btree (distribution, date_closed, bugtask DESC)
    WHERE distribution IS NOT NULL;
CREATE INDEX
    bugtaskflat__distribution__spn__date_closed__bug__idx
    ON bugtaskflat
    USING btree (
        distribution, sourcepackagename, date_closed, bug DESC)
    WHERE distribution IS NOT NULL;
CREATE INDEX
    bugtaskflat__distroseries__date_closed__bugtask__idx
    ON bugtaskflat
    USING btree (distroseries, date_closed, bugtask DESC)
    WHERE distroseries IS NOT NULL;
CREATE INDEX
    bugtaskflat__distroseries__spn__date_closed__bug__idx
    ON bugtaskflat
    USING btree (
        distroseries, sourcepackagename, date_closed, bug DESC)
    WHERE distroseries IS NOT NULL;
CREATE INDEX
    bugtaskflat__product__date_closed__bug__idx
    ON bugtaskflat
    USING btree (product, date_closed, bug DESC)
    WHERE product IS NOT NULL;
CREATE INDEX
    bugtaskflat__productseries__date_closed__bug__idx
    ON bugtaskflat
    USING btree (productseries, date_closed, bug DESC)
    WHERE productseries IS NOT NULL;
CREATE INDEX
    bugtaskflat__date_closed__bugtask__idx
    ON bugtaskflat
    USING btree (date_closed, bugtask DESC);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 16, 4);
