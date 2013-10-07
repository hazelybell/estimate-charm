-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE INDEX specification__milestone__idx
    ON specification (milestone);
CREATE INDEX specification__distroseries__idx
    ON specification (distroseries);
CREATE INDEX specification__productseries__idx
    ON specification (productseries);
CREATE UNIQUE INDEX specification__product__name__key
    ON specification (product, name);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 23, 4);
