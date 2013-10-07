-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Drop the POFileTranslator.latest_message column.  Stop updating it from
-- the trigger that maintains that table (it's a cache).  Don't bother to
-- clean up or correct records that no longer apply because of a deletion or
-- an updated submitter.  Deletions normally only happen when merging
-- translations, in which case the old record will be deleted anyway; and
-- updating a message's submitter is unheard of.  Offline scrubbing should
-- take care of such unusual cases, not complexity in the inner loop.
--
-- And while we're at it, drop some other obsolete code as well.


-- These are leftovers from the pre-2007 Translations schema.  The POMsgSet
-- and POSubmission tables have long been replaced with TranslationMessage.
DROP FUNCTION IF EXISTS mv_pofiletranslator_posubmission();
DROP FUNCTION IF EXISTS mv_pofiletranslator_pomsgset();

DROP TRIGGER IF EXISTS
    mv_pofiletranslator_translationmessage ON TranslationMessage;

-- Simplify the trigger function that maintains POFileTranslator from its
-- previous hundred-line glory.
-- Along the way this fixes an apparent bug in the interaction with message
-- sharing: if the "UPDATE" part found even a single pre-existing
-- POFileTranslator record to update, it would declare victory and return.
-- But nowadays there may be a mix of sharing POFiles, some of which need
-- their existing record updated and some need new records inserted.
--
-- For the same reason, it's no longer valid to declare victory upon unique
-- violation as the trigger used to do.
CREATE OR REPLACE FUNCTION mv_pofiletranslator_translationmessage()
    RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO public
    AS $$
BEGIN
    -- Update any existing entries.
    UPDATE POFileTranslator
    SET date_last_touched = CURRENT_TIMESTAMP AT TIME ZONE 'UTC'
    FROM POFile, TranslationTemplateItem
    WHERE person = NEW.submitter AND
        TranslationTemplateItem.potmsgset = NEW.potmsgset AND
        TranslationTemplateItem.potemplate = POFile.potemplate AND
        POFile.language = NEW.language AND
        POFileTranslator.pofile = POFile.id;

    -- Insert any missing entries.
    INSERT INTO POFileTranslator (person, pofile)
    SELECT DISTINCT NEW.submitter, POFile.id
    FROM TranslationTemplateItem
    JOIN POFile ON
        POFile.language = NEW.language AND
        POFile.potemplate = TranslationTemplateItem.potemplate
    WHERE
        TranslationTemplateItem.potmsgset = NEW.potmsgset AND
        NOT EXISTS (
            SELECT *
            FROM POFileTranslator
            WHERE person = NEW.submitter AND pofile = POFile.id
        );
    RETURN NULL;
END;
$$;


-- Update the trigger definition to call the updated function.  The old
-- trigger also covered deletions; that is not needed here because the
-- function no longer deals with that case.
CREATE TRIGGER mv_pofiletranslator_translationmessage
    AFTER INSERT OR UPDATE ON TranslationMessage
    FOR EACH ROW
    EXECUTE PROCEDURE mv_pofiletranslator_translationmessage();


ALTER TABLE POFileTranslator DROP COLUMN latest_message;


INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 17, 1);
