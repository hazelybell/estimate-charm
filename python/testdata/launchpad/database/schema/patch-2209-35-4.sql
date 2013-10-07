-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Only the values InformationType.PUBLIC, InformationType.PROPRIETRAY
-- and InformationType.EMBARGOED make sense for products.

ALTER TABLE product ADD CONSTRAINT product__valid_information_type
    CHECK (information_type IN (1, 5, 6));

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 35, 4);
