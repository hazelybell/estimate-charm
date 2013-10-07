-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE INDEX productreleasefile__productrelease__idx
    ON productreleasefile USING btree (productrelease); 
CREATE INDEX packaging__productseries__idx
    ON packaging USING btree (productseries);
CREATE INDEX milestone__distroseries__idx
    ON milestone USING btree (distroseries);
CREATE INDEX milestone__productseries__idx
    ON milestone USING btree (productseries);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 0, 6);
