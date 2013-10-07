-- Copyright 2009 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE TABLE sourcepackageformatselection (
  id serial PRIMARY KEY,
  distroseries integer NOT NULL
    CONSTRAINT sourceformatselection__distroseries__fk
    REFERENCES distroseries,
  format integer NOT NULL,
  CONSTRAINT sourceformatselection__distroseries__format__key
    UNIQUE (distroseries, format)
);

-- Allow all series to accept format 1.0 by default.
INSERT INTO sourcepackageformatselection (distroseries, format)
  SELECT id, 0 AS format FROM distroseries;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 08, 0);
