-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

-- Create new indexes to replace those using 'variant' column on either
-- TranslationMessage or POFile tables.  Done as a separate patch so it
-- can be run on production DBs separately from actual DROP COLUMNs.

CREATE UNIQUE INDEX pofile__potemplate__language__idx
   ON pofile USING btree (potemplate, language);

CREATE UNIQUE INDEX tm__potmsgset__language__shared__current__key ON translationmessage USING btree (potmsgset, language) WHERE (((is_current IS TRUE) AND (potemplate IS NULL)));

CREATE UNIQUE INDEX tm__potmsgset__language__shared__imported__key ON translationmessage USING btree (potmsgset, language) WHERE (((is_imported IS TRUE) AND (potemplate IS NULL)));

CREATE INDEX tm__potmsgset__language__not_used__idx ON translationmessage USING btree (potmsgset, language) WHERE (NOT ((is_current IS TRUE) AND (is_imported IS TRUE)));

CREATE UNIQUE INDEX tm__potmsgset__potemplate__language__diverged__current__idx ON translationmessage USING btree (potmsgset, potemplate, language) WHERE (((is_current IS TRUE) AND (potemplate IS NOT NULL)));

CREATE UNIQUE INDEX tm__potmsgset__potemplate__language__diverged__imported__idx ON translationmessage USING btree (potmsgset, potemplate, language) WHERE (((is_imported IS TRUE) AND (potemplate IS NOT NULL)));

CREATE INDEX translationmessage__language__submitter__idx ON translationmessage USING btree (language, submitter);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 28, 1);
