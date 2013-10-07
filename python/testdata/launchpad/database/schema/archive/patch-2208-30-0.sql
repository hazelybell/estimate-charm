-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE TranslationMessage
RENAME is_current TO is_current_ubuntu;
ALTER TABLE TranslationMessage
RENAME is_imported TO is_current_upstream;

ALTER INDEX tm__potmsgset__language__shared__current__key
RENAME TO tm__potmsgset__language__shared__ubuntu__key;

ALTER INDEX tm__potmsgset__language__shared__imported__key
RENAME TO tm__potmsgset__language__shared__upstream__key;

ALTER INDEX tm__potmsgset__potemplate__language__diverged__current__idx
RENAME TO tm__potmsgset__template__language__diverged__ubuntu__key;

ALTER INDEX tm__potmsgset__potemplate__language__diverged__imported__idx
RENAME TO tm__potmsgset__template__language__diverged__upstream__key;

ALTER INDEX translationmessage__language__submitter__idx
RENAME TO tm__language__submitter__idx;

ALTER TABLE TranslationImportQueueEntry
    RENAME COLUMN is_published TO by_maintainer;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 30, 0);

