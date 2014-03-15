-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE ONLY latestpersonsourcepackagereleasecache
    ADD CONSTRAINT creator_fkey FOREIGN KEY (creator) REFERENCES person(id)
    ON DELETE CASCADE;

ALTER TABLE ONLY latestpersonsourcepackagereleasecache
    ADD CONSTRAINT maintainer_fkey FOREIGN KEY (maintainer) REFERENCES person(id)
    ON DELETE CASCADE;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 38, 1);
