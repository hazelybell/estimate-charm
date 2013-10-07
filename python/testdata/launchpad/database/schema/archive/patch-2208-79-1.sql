-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

ALTER TABLE PackagingJob
  ADD COLUMN
    potemplate INTEGER DEFAULT NULL
      CONSTRAINT potemplate_fk REFERENCES POTemplate;

ALTER TABLE PackagingJob
  ALTER COLUMN productseries DROP NOT NULL,
  ALTER COLUMN distroseries DROP NOT NULL,
  ALTER COLUMN sourcepackagename DROP NOT NULL,
  ADD CONSTRAINT translationtemplatejob_valid_link CHECK (
    -- If there is a template, it is the template being moved.
    (potemplate IS NOT NULL AND productseries IS NULL AND
     distroseries IS NULL AND sourcepackagename IS NULL) OR
    -- If there is no template, we need all of productseries, distroseries
    -- and sourcepackagename because we are moving translations between
    -- a productseries and a source package.
    (potemplate IS NULL AND productseries IS NOT NULL AND
     distroseries IS NOT NULL AND sourcepackagename IS NOT NULL));

CREATE INDEX packagingjob__potemplate__idx ON PackagingJob (potemplate);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 79, 1);
