# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'IPOFileSet',
    'IPOFile',
    'IPOFileAlternativeLanguage',
    ]

from lazr.restful.declarations import (
    export_as_webservice_entry,
    exported,
    )
from zope.component import getUtility
from zope.interface import (
    Attribute,
    implements,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    Field,
    Int,
    List,
    Object,
    Text,
    TextLine,
    )
from zope.schema.interfaces import IContextSourceBinder
from zope.schema.vocabulary import (
    getVocabularyRegistry,
    SimpleTerm,
    SimpleVocabulary,
    )

from lp import _
from lp.registry.interfaces.person import IPerson
from lp.services.webapp.interfaces import ILaunchBag
from lp.translations.enums import TranslationPermission
from lp.translations.interfaces.potemplate import IPOTemplate
from lp.translations.interfaces.rosettastats import IRosettaStats
from lp.translations.interfaces.translationsperson import ITranslationsPerson


class IPOFile(IRosettaStats):
    """A translation file."""

    export_as_webservice_entry(
        singular_name="translation_file",
        plural_name="translation_files")

    id = exported(Int(
        title=_('The translation file id.'), required=True, readonly=True))

    potemplate = Object(
        title=_('The translation file template.'),
        required=True, readonly=True, schema=IPOTemplate)

    language = Choice(
        title=_('Language of this PO file.'),
        vocabulary='Language', required=True)

    title = TextLine(
        title=_('The translation file title.'), required=True, readonly=True)

    description = Text(
        title=_('The translation file description.'), required=True)

    topcomment = Text(
        title=_('A comment about this translation file.'), required=True)

    header = Text(
        title=_('Header'),
        description=_(
            'The standard translation header in its native format.'),
        required=False)

    fuzzyheader = Bool(
        title=_('A flag indicating whether the header is fuzzy.'),
        required=True)

    lasttranslator = Object(
        title=_('Last person that translated a message.'), schema=IPerson)

    date_changed = Datetime(
        title=_('When this file was last changed.'), readonly=False,
        required=True)

    lastparsed = Datetime(title=_('Last time this pofile was parsed.'))

    owner = Choice(
        title=_('Translation file owner'),
        required=True,
        description=_('''
            The owner of the translation file in Launchpad can edit its
            translations and upload new versions.
            '''),
        vocabulary="ValidOwner")

    path = TextLine(
        title=_('The path to the file that was imported'),
        required=True)

    datecreated = Datetime(
        title=_('When this translation file was created.'), required=True)

    translators = List(
        title=_('Translators that have edit permissions.'),
        description=_('''
            Translators designated as having permission to edit these files
            in this language.
            '''), required=True, readonly=True)

    contributors = List(
        title=_('Translators who have made any contribution to this file.'),
        required=True, readonly=True)

    translationpermission = Choice(
        title=_('Translation permission'),
        required=True,
        description=_('''
            The permission system which is used for this translation file.
            This is inherited from the product, project and/or distro in which
            the pofile is found.
            '''),
        vocabulary=TranslationPermission)

    from_sourcepackagename = Field(
        title=_('The source package this pofile comes from.'),
        description=_('''
            The source package this pofile comes from (set it only if it\'s
            different from IPOFile.potemplate.sourcepackagename).
            '''),
        required=False)

    translation_messages = Attribute(_(
        "All `ITranslationMessage` objects related to this "
        "translation file."))

    plural_forms = Int(
        title=_('Number of plural forms for the language of this PO file.'),
        description=_('''
            Number of plural forms is a number of translations provided for
            each plural form message.  If `IPOFile.language` does not specify
            plural forms, it defaults to 2, which is the most common number
            of plural forms.
            '''),
        required=True, readonly=True)

    def getOtherSidePOFile():
        """Get the POFile for the same language on the other side.

        Follow the packaging link to find in the sharing template on the
        other side and get the POFile from there.
        Returns None if no link exists.
        """

    def translatedCount():
        """
        Returns the number of message sets which this PO file has current
        translations for.
        """

    def untranslatedCount():
        """
        Return the number of messages which this PO file has no translation
        for.
        """

    def hasPluralFormInformation():
        """Do we know the plural-forms information for this `POFile`?"""

    def getHeader():
        """Return an `ITranslationHeaderData` representing its header."""

    def findPOTMsgSetsContaining(text):
        """Get POTMsgSets where English text or translation contain `text`."""

    def getPOTMsgSetTranslated():
        """Get pot messages that are translated for this translation file."""

    def getPOTMsgSetUntranslated():
        """Get pot message sets that are untranslated for this file."""

    def getPOTMsgSetWithNewSuggestions():
        """Get pot message sets with suggestions submitted after last review.
        """

    def getPOTMsgSetDifferentTranslations():
        """Get pot message sets with different translations on both sides.
        """

    def getTranslationsFilteredBy(person):
        """Get TranslationMessages in this `IPOFile` contributed by `person`.

        Returned messages are ordered by the `POTMsgSet`, and then by
        `date_created` with newest first.
        """

    def getTranslationMessages(condition=None):
        """Get TranslationMessages in this `IPOFile`.

        If condition is None, return all messages, else narrow the result
        set down using the condition.
        """

    def export(ignore_obsolete=False, export_utf8=False):
        """Export this PO file as string.

        :param ignore_obsolete: Whether the exported PO file does not have
            obsolete entries.
        :param export_utf8: Whether the exported PO file should be exported as
            UTF-8.
        """

    def prepareTranslationCredits(potmsgset):
        """Add Launchpad contributors to translation credit strings.

        It adds to the translation for `potmsgset` if it exists, trying
        not to repeat same people who are already credited.
        """

    def canEditTranslations(person):
        """Whether the given person is able to add/edit translations."""

    def canAddSuggestions(person):
        """Whether the given person is able to add new suggestions."""

    def getStatistics():
        """Summarize this file's cached translation statistics.

        :return: tuple of (`currentcount`, `updatescount`, `rosettacount`,
            `unreviewed_count`), as collected by `updateStatistics`.
        """

    def updateStatistics():
        """Update the cached statistics fields.

        :return: a tuple (`currentcount`, `updatescount`, `rosettacount`,
            `unreviewed_count`), as for `getStatistics`."""

    def updateHeader(new_header):
        """Update the header information.

        new_header is a POHeader object.
        """

    def isTranslationRevisionDateOlder(header):
        """Whether given header revision date is newer then self one."""

    def setPathIfUnique(path):
        """Set path to given one, provided it's a valid, unique path.

        A `POFile`'s path must be unique within its context, i.e. for either
        the same `DistroSeries` and `SourcePackageName`, or for the same
        `ProductSeries`, depending on which the `POFile` is attached to.

        If the new path is not unique, the old path will be retained instead.
        """

    def importFromQueue(entry_to_import, logger=None, txn=None):
        """Import given queue entry.

        :param entry_to_import: `TranslationImportQueueEntry` specifying an
            approved import for this `POFile`
        :param logger: optional logger to report problems to.
        :param txn: optionally, a transaction manager.  It will not be
            used; it's here only for API symmetry with `IPOTemplate`.

        :return: a tuple of the subject line and body for a notification email
            to be sent to the uploader.
        """

    def getFullLanguageCode():
        """Return the language code."""

    def getFullLanguageName():
        """Return the language name."""

    def getTranslationRows():
        """Return exportable rows of translation data.

        :return: a list of `VPOExport` objects.
        """

    def getChangedRows():
        """Return exportable rows that differ from upstream translations.

        :return: a list of `VPOExport` objects.
        """

    def markChanged(translator=None, timestamp=None):
        """Note a change to this `POFile` or its contents.

        :param translator: The person making this change.  If given,
            `lasttranslator` will be updated to refer to this person.
        :param timestamp: Time of the change.  Defaults to "now."
        """


class AlternativeLanguageVocabularyFactory:
    """Gets vocab for user's preferred languages, or all languages if not set.

    This is an `IContextSourceBinder` returning a `Vocabulary`.  It's meant to
    present a short but complete list of languages a user might want to
    translate to or get suggestions from.

    Guessing based on browser languages is probably not a good idea: that list
    may easily be incomplete, and its origin is not obvious.  From the user's
    point of view it would be Launchpad behaviour that cannot be changed by
    pushing buttons in Launchpad.  And even in cases where a guess based on
    browser settings is reasonable, it would mask the need for a useful
    Preferred Languages setting.  We can't encourage people to manage their
    languages shortlist in Launchpad through their global browser
    configuration.

    Instead, if no preferred-languages setting is available (e.g. because the
    visitor is not logged in), this will fall back to a vocabulary containing
    all known translatable languages.
    """
    # XXX: JeroenVermeulen 2007-09-03: It doesn't seem right to define this
    # class in an interface, but it's needed from inside another interface
    # definition.  A factory is definitely the right approach though, since
    # the two kinds of vocabulary are completely different in implementation
    # and class derivation.  Also of course, the distinction applies unchanged
    # throughout the vocabulary object's lifetime.  See interfaces.buglink.py
    # for an example of the same implementation pattern.
    implements(IContextSourceBinder)

    def __call__(self, context):
        """See `IContextSourceBinder`."""
        user = getUtility(ILaunchBag).user
        if user is not None and user.languages:
            translations_user = ITranslationsPerson(user)
            terms = [
                SimpleTerm(language, language.code, language.displayname)
                for language in translations_user.translatable_languages]
            if terms:
                return SimpleVocabulary(terms)
        return getVocabularyRegistry().get(None, "TranslatableLanguage")


class IPOFileAlternativeLanguage(Interface):
    """A PO File's alternative language."""

    alternative_language = Choice(
        title=u'Alternative language',
        description=(u'Language from where we could get alternative'
                     u' translations for this PO file.'),
        source=AlternativeLanguageVocabularyFactory(),
        required=False)


class IPOFileSet(Interface):
    """A set of POFiles."""

    def getDummy(potemplate, language):
        """Return a dummy pofile for the given po template and language."""

    def getPOFilesByPathAndOrigin(path, productseries=None,
        distroseries=None, sourcepackagename=None):
        """Find `IPOFile`s with 'path' in productseries or source package.

        We filter the `IPOFile` objects to check only the ones related to the
        given arguments 'productseries', 'distroseries' and
        'sourcepackagename'.

        :return: A Storm result set of matching `POFile`s.
        """

    def getBatch(starting_id, batch_size):
        """Read up to batch_size `POFile`s, starting at given id.

        Returns a sequence of consecutive `POFile`s (ordered by id), starting
        the smallest id that is no greater than starting_id.

        The number of items in the sequence will only be less than batch_size
        if the end of the table has been reached.
        """

    def getPOFilesWithTranslationCredits(untranslated=False):
        """Get POFiles with potential translation credits messages.

        Returns a ResultSet of (POFile, POTMsgSet) tuples, ordered by
        POFile.id.

        :param untranslated: Look only for `POFile`s with a credits
            message that is not translated.
        """

    def getPOFilesTouchedSince(date):
        """Return IDs for PO files that might have been updated since `date`.

        :param date: A datetime object to use as the starting date.

        :return: a ResultSet over POFile IDs for directly and indirectly
            (through sharing POFiles) touched POFiles since `date`.
        """
