-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Create indices for Person:+(ppa|uploaded|maintained)-packages.
CREATE INDEX latestpersonsourcepackagereleasecache__creator__purpose__date__idx
  ON latestpersonsourcepackagereleasecache (creator, archive_purpose, date_uploaded DESC);
CREATE INDEX latestpersonsourcepackagereleasecache__creator__date__non_ppa__idx
  ON latestpersonsourcepackagereleasecache (creator, date_uploaded DESC) WHERE archive_purpose <> 2;

CREATE INDEX latestpersonsourcepackagereleasecache__maintainer__purpose__date__idx
  ON latestpersonsourcepackagereleasecache (maintainer, archive_purpose, date_uploaded DESC);
CREATE INDEX latestpersonsourcepackagereleasecache__maintainer__date__non_ppa__idx
  ON latestpersonsourcepackagereleasecache (maintainer, date_uploaded DESC) WHERE archive_purpose <> 2;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 38, 3);
