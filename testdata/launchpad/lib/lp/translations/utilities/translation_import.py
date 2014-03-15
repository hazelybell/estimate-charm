# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'TranslationImporter',
    'importers',
    'is_identical_translation',
    ]

import datetime
from operator import attrgetter

import posixpath
import pytz
from storm.exceptions import TimeoutError
import transaction
from zope.component import getUtility
from zope.interface import implements

from lp.registry.interfaces.person import (
    IPersonSet,
    PersonCreationRationale,
    )
from lp.registry.interfaces.sourcepackage import ISourcePackageFactory
from lp.services.config import config
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import (
    cursor,
    quote,
    )
from lp.services.identity.interfaces.emailaddress import InvalidEmailAddress
from lp.services.propertycache import (
    cachedproperty,
    get_property_cache,
    )
from lp.services.webapp import canonical_url
from lp.translations.enums import RosettaImportStatus
from lp.translations.interfaces.side import ITranslationSideTraitsSet
from lp.translations.interfaces.translationexporter import (
    ITranslationExporter,
    )
from lp.translations.interfaces.translationfileformat import (
    TranslationFileFormat,
    )
from lp.translations.interfaces.translationimporter import (
    ITranslationImporter,
    NotExportedFromLaunchpad,
    OutdatedTranslationError,
    )
from lp.translations.interfaces.translationmessage import (
    RosettaTranslationOrigin,
    TranslationConflict,
    TranslationValidationStatus,
    )
from lp.translations.interfaces.translations import TranslationConstants
from lp.translations.utilities.gettext_po_importer import GettextPOImporter
from lp.translations.utilities.kde_po_importer import KdePOImporter
from lp.translations.utilities.mozilla_xpi_importer import MozillaXpiImporter
from lp.translations.utilities.sanitize import (
    sanitize_translations_from_import,
    )
from lp.translations.utilities.translation_common_format import (
    TranslationMessageData,
    )
from lp.translations.utilities.validate import (
    GettextValidationError,
    validate_translation,
    )


importers = {
    TranslationFileFormat.KDEPO: KdePOImporter(),
    TranslationFileFormat.PO: GettextPOImporter(),
    TranslationFileFormat.XPI: MozillaXpiImporter(),
    }


def is_identical_translation(existing_msg, new_msg):
    """Is a new translation substantially the same as the existing one?

    Compares msgid and msgid_plural, and all translations.

    :param existing_msg: a `TranslationMessageData` representing a translation
        message currently kept in the database.
    :param new_msg: an alternative `TranslationMessageData` translating the
        same original message.
    :return: True if the new message is effectively identical to the
        existing one, or False if replacing existing_msg with new_msg
        would make a semantic difference.
    """
    assert new_msg.msgid_singular == existing_msg.msgid_singular, (
        "Comparing translations for different messages.")

    if (existing_msg.msgid_plural != new_msg.msgid_plural):
        return False
    if len(new_msg.translations) < len(existing_msg.translations):
        return False
    length_overlap = min(
        len(existing_msg.translations), len(new_msg.translations))
    for pluralform_index in xrange(length_overlap):
        # Plural forms that both messages have.  Translations for each
        # must match.
        existing_text = existing_msg.translations[pluralform_index]
        new_text = new_msg.translations[pluralform_index]
        if existing_text != new_text:
            return False
    for pluralform_index in xrange(length_overlap, len(new_msg.translations)):
        # Plural forms that exist in new_translations but not in
        # existing_translations.  That's okay, as long as all of them are
        # None.
        if new_msg.translations[pluralform_index] is not None:
            return False
    return True


class ExistingPOFileInDatabase:
    """All existing translations for a PO file.

    Fetches all information needed to compare messages to be imported in one
    go.  Used to speed up PO file import.
    """

    def __init__(self, pofile, simulate_timeout=False):
        self.pofile = pofile

        # Dict indexed by (msgid, context) containing current
        # TranslationMessageData: doing this for the speed.
        self.current_messages = {}
        # Messages which have been seen in the file: messages which exist
        # in the database, but not in the import, will be expired.
        self.seen = set()

        # Pre-fill self.ubuntu_messages and self.upstream_messages with data.
        self._fetchDBRows(simulate_timeout=simulate_timeout)

    def _getFlagName(self):
        """Get the name of the database is_current flag to look for."""
        return getUtility(ITranslationSideTraitsSet).getForTemplate(
            self.pofile.potemplate).flag_name

    def _fetchDBRows(self, simulate_timeout=False):
        msgstr_joins = [
            "LEFT OUTER JOIN POTranslation AS pt%d "
            "ON pt%d.id = TranslationMessage.msgstr%d" % (form, form, form)
            for form in xrange(TranslationConstants.MAX_PLURAL_FORMS)]

        translations = [
            "pt%d.translation AS translation%d" % (form, form)
            for form in xrange(TranslationConstants.MAX_PLURAL_FORMS)]

        substitutions = {
            'translation_columns': ', '.join(translations),
            'translation_joins': '\n'.join(msgstr_joins),
            'language': quote(self.pofile.language),
            'potemplate': quote(self.pofile.potemplate),
            'flag': self._getFlagName(),
        }

        sql = """
            SELECT
                POMsgId.msgid AS msgid,
                POMsgID_Plural.msgid AS msgid_plural,
                context,
                date_reviewed,
                %(translation_columns)s
            FROM POTMsgSet
            JOIN TranslationTemplateItem ON
                TranslationTemplateItem.potmsgset = POTMsgSet.id AND
                TranslationTemplateItem.potemplate = %(potemplate)s
            JOIN TranslationMessage ON
                POTMsgSet.id=TranslationMessage.potmsgset AND (
                    TranslationMessage.potemplate = %(potemplate)s OR
                    TranslationMessage.potemplate IS NULL) AND
                TranslationMessage.language = %(language)s
            %(translation_joins)s
            JOIN POMsgID ON
                POMsgID.id = POTMsgSet.msgid_singular
            LEFT OUTER JOIN POMsgID AS POMsgID_Plural ON
                POMsgID_Plural.id = POTMsgSet.msgid_plural
            WHERE
                %(flag)s IS TRUE
            ORDER BY
                TranslationTemplateItem.sequence,
                TranslationMessage.potemplate NULLS LAST
          """ % substitutions

        cur = cursor()
        try:
            # XXX JeroenVermeulen 2010-11-24 bug=680802: We set a
            # timeout to work around bug 408718, but the query is
            # simpler now.  See if we still need this.

            # We have to commit what we've got so far or we'll lose
            # it when we hit TimeoutError.
            transaction.commit()

            if simulate_timeout:
                # This is used in tests.
                timeout = '1ms'
                query = "SELECT pg_sleep(2)"
            else:
                timeout = 1000 * int(config.poimport.statement_timeout)
                query = sql
            cur.execute("SET statement_timeout to %s" % quote(timeout))
            cur.execute(query)
        except TimeoutError:
            # XXX JeroenVermeulen 2010-11-24 bug=680802: Log this so we
            # know whether it still happens.
            transaction.abort()
            return

        rows = cur.fetchall()

        assert TranslationConstants.MAX_PLURAL_FORMS == 6, (
            "Change this code to support %d plural forms"
            % TranslationConstants.MAX_PLURAL_FORMS)
        for row in rows:
            msgid, msgid_plural, context, date = row[:4]
            # The last part of the row is msgstr0 .. msgstr5. Store them
            # in a dict indexed by the number of the plural form.
            msgstrs = dict(enumerate(row[4:]))

            key = (msgid, msgid_plural, context)
            if key in self.current_messages:
                message = self.current_messages[key]
            else:
                message = TranslationMessageData()
                self.current_messages[key] = message

                message.context = context
                message.msgid_singular = msgid
                message.msgid_plural = msgid_plural

            for plural in xrange(TranslationConstants.MAX_PLURAL_FORMS):
                msgstr = msgstrs.get(plural, None)
                if (msgstr is not None and
                    ((len(message.translations) > plural and
                      message.translations[plural] is None) or
                     (len(message.translations) <= plural))):
                    message.addTranslation(plural, msgstr)

    def markMessageAsSeen(self, message):
        """Marks a message as seen in the import, to avoid expiring it."""
        self.seen.add(self._getMessageKey(message))

    def getUnseenMessages(self):
        """Return a set of messages present in the database but not seen
        in the file being imported.
        """
        return self.current_messages - self.seen

    def _getMessageKey(self, message):
        """Return tuple identifying `message`.

        Both `ubuntu_messages` and `upstream_messages` are indexed by
        this key.
        """
        return (message.msgid_singular, message.msgid_plural, message.context)

    def isAlreadyTranslatedTheSame(self, message):
        """Does `pool` have a message that's just like `message`?

        :param message: a message being processed from import.
        :param pool: a dict mapping message keys to messages; should be
            either `self.upstream_messages` or `self.ubuntu_messages`.
        """
        msg_in_db = self.current_messages.get(self._getMessageKey(message))
        if msg_in_db is None:
            return False
        else:
            return is_identical_translation(msg_in_db, message)


class TranslationImporter:
    """Handle translation resources imports."""

    implements(ITranslationImporter)

    @cachedproperty
    def supported_file_extensions(self):
        """See `ITranslationImporter`."""
        file_extensions = []

        for importer in importers.itervalues():
            file_extensions.extend(importer.file_extensions)

        return sorted(set(file_extensions))

    @cachedproperty
    def template_suffixes(self):
        """See `ITranslationImporter`."""
        # Several formats (particularly the various gettext variants) can have
        # the same template suffix.
        unique_suffixes = set(
            importer.template_suffix for importer in importers.values())
        return sorted(unique_suffixes)

    def isTemplateName(self, path):
        """See `ITranslationImporter`."""
        for importer in importers.itervalues():
            if path.endswith(importer.template_suffix):
                return True
        return False

    def isHidden(self, path):
        """See `ITranslationImporter`."""
        normalized_path = posixpath.normpath(path)
        return normalized_path.startswith('.') or '/.' in normalized_path

    def isTranslationName(self, path):
        """See `ITranslationImporter`."""
        base_name, suffix = posixpath.splitext(path)
        if suffix not in self.supported_file_extensions:
            return False
        for importer_suffix in self.template_suffixes:
            if path.endswith(importer_suffix):
                return False
        return True

    def getTranslationFileFormat(self, file_extension, file_contents):
        """See `ITranslationImporter`."""
        all_importers = importers.values()
        all_importers.sort(key=attrgetter('priority'), reverse=True)
        for importer in all_importers:
            if file_extension in importer.file_extensions:
                return importer.getFormat(file_contents)

        return None

    def getTranslationFormatImporter(self, file_format):
        """See `ITranslationImporter`."""
        return importers.get(file_format, None)

    def importFile(self, translation_import_queue_entry, logger=None):
        """See ITranslationImporter."""
        assert translation_import_queue_entry is not None, (
            "Import queue entry cannot be None.")
        assert (translation_import_queue_entry.status ==
                RosettaImportStatus.APPROVED), (
            "Import queue entry is not approved.")
        assert (translation_import_queue_entry.potemplate is not None or
                translation_import_queue_entry.pofile is not None), (
            "Import queue entry has no import target.")

        importer = self.getTranslationFormatImporter(
            translation_import_queue_entry.format)
        assert importer is not None, (
            'There is no importer available for %s files' % (
                translation_import_queue_entry.format.name))

        # Select the import file type.
        if translation_import_queue_entry.pofile is None:
            # Importing a translation template (POT file).
            file_importer = POTFileImporter(
                translation_import_queue_entry, importer, logger)
        else:
            # Importing a translation (PO file).
            file_importer = POFileImporter(
                translation_import_queue_entry, importer, logger)

        # Do the import and return the errors.
        return file_importer.importFile()


class FileImporter(object):
    """Base class for importing translations or translation templates.

    This class is meant to be subclassed for the specialised tasks of
    importing translations (PO)or translation templates (POT) respectively.
    Subclasses need to implement the importMessage method and extend
    the constructor to set self.pofile and self.potemplate correctly.
    """

    def __init__(self, translation_import_queue_entry,
                 importer, logger=None):
        """Base constructor to set up common attributes and parse the imported
        file into a member variable (self.translation_file).

        Subclasses must extend this constructor to set the default values
        according to their needs, most importantly self.pofile and
        self.potemplate.

        :param translation_import_queue_entry: The queue entry, as has been
            provided to TranslationImporter.importFile.
        :param importer: The importer to use for parsing the file.
        :param logger: An optional logger.
        """

        self.translation_import_queue_entry = translation_import_queue_entry
        self.importer = importer
        self.logger = logger

        # These two must be set correctly by the derived classes.
        self.pofile = None
        self.potemplate = None

        self._cached_format_exporter = None

        # Parse the file using the importer.
        self.translation_file = importer.parse(
            translation_import_queue_entry)

        self.is_editor = False
        self.last_translator = None
        self.lock_timestamp = None
        self.pofile_in_db = None
        self.errors = []

    def getOrCreatePOTMsgSet(self, message):
        """Get the POTMsgSet that this message belongs to or create a new
        one if none was found.

        :param message: The message.
        :return: The POTMsgSet instance, existing or new.
        """
        return self.potemplate.getOrCreateSharedPOTMsgSet(
            message.msgid_singular, plural_text=message.msgid_plural,
            context=message.context,
            initial_file_references=message.file_references,
            initial_source_comment=message.source_comment)

    @cachedproperty
    def share_with_other_side(self):
        """Returns True if translations should be shared with the other side.
        """
        from_upstream = self.translation_import_queue_entry.by_maintainer
        potemplate = self.potemplate
        policy = potemplate.getTranslationPolicy()
        return policy.sharesTranslationsWithOtherSide(
            self.translation_import_queue_entry.importer,
            self.pofile.language, sourcepackage=potemplate.sourcepackage,
            purportedly_upstream=from_upstream)

    @cachedproperty
    def is_upstream_import_on_sourcepackage(self):
        """Use TranslationMessage.acceptFromUpstreamImportOnPackage`."""
        if self.pofile is None:
            return False
        if not self.translation_import_queue_entry.by_maintainer:
            return False
        if self.translation_import_queue_entry.sourcepackagename is None:
            return False
        sourcepackage = getUtility(ISourcePackageFactory).new(
            self.translation_import_queue_entry.sourcepackagename,
            self.translation_import_queue_entry.distroseries)
        return not sourcepackage.has_sharing_translation_templates

    @cachedproperty
    def translations_are_msgids(self):
        """Are these English strings instead of translations?

        If this template uses symbolic message ids, the English POFile
        will contain the English original texts that correspond to the
        symbols."""
        return (
            self.importer.uses_source_string_msgids and
            self.pofile.language.code == 'en')

    def _storeCredits(self, potmsgset, credits):
        """Store credits but only those provided by the maintainer."""
        if not self.translation_import_queue_entry.by_maintainer:
            return None
        return potmsgset.setCurrentTranslation(
            self.pofile, self.last_translator, credits,
            RosettaTranslationOrigin.SCM, share_with_other_side=True)

    def _validateMessage(self, potmsgset, message,
                         translations, message_data):
        """Validate the message and report success or failure."""
        try:
            validate_translation(
                potmsgset.singular_text, potmsgset.plural_text,
                translations, potmsgset.flags)
        except GettextValidationError as e:
            self._addUpdateError(message_data, potmsgset, unicode(e))
            message.validation_status = (
                TranslationValidationStatus.UNKNOWNERROR)
            return False

        message.validation_status = TranslationValidationStatus.OK
        return True

    def _acceptMessage(self, potmsgset, message, message_data):
        """Try to approve the message, return None on TranslationConflict."""
        try:
            if self.is_upstream_import_on_sourcepackage:
                message.acceptFromUpstreamImportOnPackage(
                    self.pofile, self.lock_timestamp)
            else:
                message.acceptFromImport(
                    self.pofile, self.share_with_other_side,
                    self.lock_timestamp)
        except TranslationConflict:
            self._addConflictError(message_data, potmsgset)
            if self.logger is not None:
                self.logger.info(
                    "Conflicting updates on message %d." % potmsgset.id)
            # The message remains a suggestion.
            return None

        if self.translations_are_msgids:
            # Make sure singular_text picks up the new translation.
            del get_property_cache(potmsgset).singular_text

        return message

    def storeTranslationsInDatabase(self, message_data, potmsgset):
        """Try to store translations in the database.

        Perform check if a PO file is available and if the message has any
        translations that can be stored. If an exception is caught, an error
        is added to the list in self.errors but the translations are stored
        anyway, marked as having an error.

        :param message_data: The message data for which translations will be
            stored.
        :param potmsgset: The POTMsgSet that this message belongs to.

        :return: The updated translation_message entry or None, if no storing
            war done.
        """
        if self.pofile is None:
            # It's neither an IPOFile nor an IPOTemplate that needs to
            # store English strings in an IPOFile.
            return None

        no_translations = (
            message_data.translations is None or
            not any(message_data.translations))
        if no_translations:
            # We don't have anything to import.
            return None

        sanitized_translations = sanitize_translations_from_import(
            potmsgset.singular_text, message_data.translations,
            self.pofile.language.pluralforms)

        # Flush the store now because flush order rules can cause messages
        # to be flushed before the potmsgset arrives in the database.
        IStore(potmsgset).flush()

        if potmsgset.is_translation_credit:
            # Translation credits cannot be added as suggestions.
            return self._storeCredits(potmsgset, sanitized_translations)

        # The message is first stored as a suggestion and only made
        # current if it validates.
        new_message = potmsgset.submitSuggestion(
            self.pofile, self.last_translator, sanitized_translations,
            from_import=True)

        validation_ok = self._validateMessage(
            potmsgset, new_message, sanitized_translations, message_data)
        if validation_ok and self.is_editor:
            return self._acceptMessage(potmsgset, new_message, message_data)

        return new_message

    def importMessage(self, message):
        """Import a single message.

        This method must be implemented by the derived class to perform all
        necessary steps to import a single message into the database.

        :param message: The message to be imported.

        :raise NotImplementedError: if no implementation is provided.
        """
        raise NotImplementedError

    def importFile(self):
        """Import a parsed file into the database.

        Loop through all message entries in the parsed file and import them
        using the importMessage.

        :return: The errors encountered during the import.
        """
        # Collect errors here.
        self.errors = []

        for message in self.translation_file.messages:
            if message.msgid_singular:
                self.importMessage(message)

        return self.errors, self.translation_file.syntax_warnings

    @property
    def format_exporter(self):
        """Get the exporter to display a message in error messages."""
        if self._cached_format_exporter is None:
            self._cached_format_exporter = getUtility(
                  ITranslationExporter).getExporterProducingTargetFileFormat(
                        self.translation_import_queue_entry.format)
        return self._cached_format_exporter

    def _addUpdateError(self, message, potmsgset, errormsg):
        """Add an error returned by updateTranslation.

        This has been put in a method enhance clarity by removing the long
        error text from the calling method.

        :param message: The current message from the translation file.
        :param potmsgset: The current messageset for this message id.
        :param errormsg: The errormessage returned by updateTranslation.
        """
        self.errors.append({
            'potmsgset': potmsgset,
            'pofile': self.pofile,
            'pomessage': self.format_exporter.exportTranslationMessageData(
                message),
            'error-message': unicode(errormsg),
        })

    def _addConflictError(self, message, potmsgset):
        """Add an error if there was an edit conflict.

        This has been put in a method enhance clarity by removing the long
        error text from the calling method.

        :param message: The current message from the translation file.
        :param potmsgset: The current messageset for this message id.
        """
        self._addUpdateError(message, potmsgset,
            "This message was updated by someone else after you"
            " got the translation file. This translation is now"
            " stored as a suggestion, if you want to set it as"
            " the used one, go to %s/+translate and approve"
            " it." % canonical_url(self.pofile))


class POTFileImporter(FileImporter):
    """Import a translation template file."""

    def __init__(self, translation_import_queue_entry, importer, logger):
        """Construct an Importer for a translation template."""

        assert translation_import_queue_entry.pofile is None, (
            "Pofile must be None when importing a template.")

        # Call base constructor
        super(POTFileImporter, self).__init__(
             translation_import_queue_entry, importer, logger)

        self.pofile = None
        self.potemplate = translation_import_queue_entry.potemplate

        self.potemplate.source_file_format = (
            translation_import_queue_entry.format)
        self.potemplate.source_file = (
            translation_import_queue_entry.content)
        if self.importer.uses_source_string_msgids:
            # We use the special 'en' language as the way to store the
            # English strings to show instead of the msgids.
            self.pofile = self.potemplate.getPOFileByLang('en')
            if self.pofile is None:
                self.pofile = self.potemplate.newPOFile('en')

        # Expire old messages.
        self.potemplate.expireAllMessages()
        if self.translation_file.header is not None:
            # Update the header.
            self.potemplate.header = (
                self.translation_file.header.getRawContent())
        UTC = pytz.timezone('UTC')
        self.potemplate.date_last_updated = datetime.datetime.now(UTC)

        # By default translation template uploads are done only by
        # editors.
        self.is_editor = True
        self.last_translator = (
            translation_import_queue_entry.importer)

        # Messages are counted to maintain the original sequence.
        self.count = 0

    def importMessage(self, message):
        """See FileImporter."""
        self.count += 1

        if 'fuzzy' in message.flags:
            message.flags.remove('fuzzy')
            message._translations = None

        if len(message.flags) > 0:
            flags_comment = u", " + u", ".join(message.flags)
        else:
            flags_comment = u""

        potmsgset = self.getOrCreatePOTMsgSet(message)
        potmsgset.setSequence(self.potemplate, self.count)
        potmsgset.commenttext = message.comment
        potmsgset.sourcecomment = message.source_comment
        potmsgset.filereferences = message.file_references
        potmsgset.flagscomment = flags_comment

        translation_message = self.storeTranslationsInDatabase(
                                  message, potmsgset)

        # Update translation_message's comments and flags.
        if translation_message is not None:
            translation_message.comment = message.comment
            if self.translation_import_queue_entry.by_maintainer:
                translation_message.was_obsolete_in_last_import = (
                    message.is_obsolete)


class POFileImporter(FileImporter):
    """Import a translation file."""

    def __init__(self, translation_import_queue_entry, importer, logger):
        """Construct an Importer for a translation file."""

        assert translation_import_queue_entry.pofile is not None, (
            "Pofile must not be None when importing a translation.")

        # Call base constructor
        super(POFileImporter, self).__init__(
             translation_import_queue_entry, importer, logger)

        self.pofile = translation_import_queue_entry.pofile
        self.potemplate = self.pofile.potemplate

        upload_header = self.translation_file.header
        if upload_header is not None:
            # Check whether we are importing a new version.
            if self.pofile.isTranslationRevisionDateOlder(upload_header):
                if translation_import_queue_entry.by_maintainer:
                    # Files uploaded by the maintainer can be older than the
                    # last import and still be imported. They don't update
                    # header information, though, so this is deleted here.
                    self.translation_file.header = None
                else:
                    # The new imported file is older than latest one imported,
                    # we don't import it, just ignore it as it could be a
                    # mistake and it would make us lose translations.
                    pofile_timestamp = (
                        self.pofile.getHeader().translation_revision_date)
                    upload_timestamp = (
                        upload_header.translation_revision_date)
                    raise OutdatedTranslationError(
                        'The last imported version of this file was '
                        'dated %s; the timestamp in the file you uploaded '
                        'is %s.' % (pofile_timestamp, upload_timestamp))
            # Get the timestamp when this file was exported from
            # Launchpad. If it was not exported from Launchpad, it will be
            # None.
            self.lock_timestamp = (
                upload_header.launchpad_export_date)

        if (not self.translation_import_queue_entry.by_maintainer and
            self.lock_timestamp is None):
            # We got a translation file from offline translation (not from
            # the maintainer) and it misses the export time so we don't have a
            # way to figure whether someone changed the same translations
            # while the offline work was done.
            raise NotExportedFromLaunchpad

        # Update the header with the new one. If this is an old upstream
        # file, the new header has been set to None and no update will occur.
        self.pofile.updateHeader(self.translation_file.header)

        # Get last translator that touched this translation file.
        # We may not be able to guess it from the translation file, so
        # we take the importer as the last translator then.
        if upload_header is not None:
            name, email = upload_header.getLastTranslator()
            self.last_translator = self._getPersonByEmail(email, name)
        if self.last_translator is None:
            self.last_translator = (
                self.translation_import_queue_entry.importer)

        if self.translation_import_queue_entry.by_maintainer:
            # The maintainer always has edit rights.
            # For Soyuz uploads, the "importer" reflects the package upload
            # not the translations upload.
            self.is_editor = True
        else:
            # Use the importer rights to make sure the imported
            # translations are actually accepted instead of being just
            # suggestions.
            self.is_editor = (
                self.pofile.canEditTranslations(
                    self.translation_import_queue_entry.importer))

        self.pofile_in_db = ExistingPOFileInDatabase(self.pofile)

    def _getPersonByEmail(self, email, name=None):
        """Return the person for given email.

        If the person is unknown in Launchpad, the account will be created but
        it will not have a password and thus, will be disabled.

        :param email: text that contains the email address.
        :param name: name of the owner of the given email address.

        :return: A person object or None, if email is None.
        """
        if email is None:
            return None

        personset = getUtility(IPersonSet)

        # We may have to create a new person.  If we do, this is the
        # rationale.
        comment = 'when importing the %s translation of %s' % (
            self.pofile.language.displayname, self.potemplate.displayname)
        rationale = PersonCreationRationale.POFILEIMPORT

        try:
            return personset.ensurePerson(
                email, displayname=name, rationale=rationale, comment=comment)
        except InvalidEmailAddress:
            return None

    def importMessage(self, message):
        """See FileImporter."""
        # Mark this message as seen in the import
        self.pofile_in_db.markMessageAsSeen(message)
        if self.pofile_in_db.isAlreadyTranslatedTheSame(message):
            return

        potmsgset = self.getOrCreatePOTMsgSet(message)

        if 'fuzzy' in message.flags:
            message.flags.remove('fuzzy')
            message._translations = None

        translation_message = self.storeTranslationsInDatabase(
            message, potmsgset)

        # Update translation_message's comments and flags.
        if translation_message is not None:
            translation_message.comment = message.comment
            if self.translation_import_queue_entry.by_maintainer:
                translation_message.was_obsolete_in_last_import = (
                    message.is_obsolete)
