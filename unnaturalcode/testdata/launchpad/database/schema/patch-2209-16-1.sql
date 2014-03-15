-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Add the usual 5 search indices for the global contextless bug listing.
CREATE INDEX bugtaskflat__date_last_updated__idx ON bugtaskflat
    USING btree (date_last_updated);
CREATE INDEX bugtaskflat__datecreated__idx ON bugtaskflat
    USING btree (datecreated);
CREATE INDEX bugtaskflat__heat__bugtask__idx ON bugtaskflat
    USING btree (heat, bugtask DESC);
CREATE INDEX bugtaskflat__importance__bugtask__idx ON bugtaskflat
    USING btree (importance, bugtask DESC);
CREATE INDEX bugtaskflat__status__bugtask__idx ON bugtaskflat
    USING btree (status, bugtask DESC);

-- And add a Bug.id sort index to each set.
CREATE INDEX
    bugtaskflat__distribution__bug__bugtask__idx
    ON bugtaskflat
    USING btree (distribution, bug, bugtask DESC)
    WHERE distribution IS NOT NULL;
CREATE INDEX
    bugtaskflat__distribution__spn__bug__idx
    ON bugtaskflat
    USING btree (distribution, sourcepackagename, bug)
    WHERE distribution IS NOT NULL;
CREATE INDEX
    bugtaskflat__distroseries__bug__bugtask__idx
    ON bugtaskflat
    USING btree (distroseries, bug, bugtask DESC)
    WHERE distroseries IS NOT NULL;
CREATE INDEX
    bugtaskflat__distroseries__spn__bug__idx
    ON bugtaskflat
    USING btree (distroseries, sourcepackagename, bug)
    WHERE distroseries IS NOT NULL;
CREATE INDEX
    bugtaskflat__product__bug__idx
    ON bugtaskflat
    USING btree (product, bug)
    WHERE product IS NOT NULL;
CREATE INDEX
    bugtaskflat__productseries__bug__idx
    ON bugtaskflat
    USING btree (productseries, bug)
    WHERE productseries IS NOT NULL;
CREATE INDEX
    bugtaskflat__bug__bugtask__idx
    ON bugtaskflat
    USING btree (bug, bugtask DESC);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 16, 1);
