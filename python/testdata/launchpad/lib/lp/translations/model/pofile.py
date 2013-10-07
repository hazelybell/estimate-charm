# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""`SQLObject` implementation of `IPOFile` interface."""

__metaclass__ = type
__all__ = [
    'POFile',
    'DummyPOFile',
    'POFileSet',
    'POFileToChangedFromPackagedAdapter',
    'POFileToTranslationFileDataAdapter',
    ]

import datetime

import pytz
from sqlobject import (
    BoolCol,
    ForeignKey,
    IntCol,
    StringCol,
    )
from storm.expr import (
    And,
    Coalesce,
    Desc,
    Exists,
    Join,
    LeftJoin,
    Not,
    Or,
    Select,
    SQL,
    )
from storm.info import ClassAlias
from storm.store import (
    EmptyResultSet,
    Store,
    )
from zope.component import (
    getAdapter,
    getUtility,
    )
from zope.interface import implements
from zope.security.proxy import removeSecurityProxy

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.interfaces.person import validate_public_person
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    )
from lp.services.database.sqlbase import (
    flush_database_updates,
    quote,
    quote_like,
    SQLBase,
    sqlvalues,
    )
from lp.services.mail.helpers import get_email_template
from lp.services.propertycache import cachedproperty
from lp.services.webapp.publisher import canonical_url
from lp.translations.enums import RosettaImportStatus
from lp.translations.interfaces.pofile import (
    IPOFile,
    IPOFileSet,
    )
from lp.translations.interfaces.potmsgset import TranslationCreditsType
from lp.translations.interfaces.side import (
    ITranslationSideTraitsSet,
    TranslationSide,
    )
from lp.translations.interfaces.translationcommonformat import (
    ITranslationFileData,
    )
from lp.translations.interfaces.translationexporter import (
    ITranslationExporter,
    )
from lp.translations.interfaces.translationimporter import (
    ITranslationImporter,
    NotExportedFromLaunchpad,
    OutdatedTranslationError,
    TooManyPluralFormsError,
    TranslationFormatInvalidInputError,
    TranslationFormatSyntaxError,
    )
from lp.translations.interfaces.translationmessage import (
    RosettaTranslationOrigin,
    )
from lp.translations.interfaces.translations import TranslationConstants
from lp.translations.model.pomsgid import POMsgID
from lp.translations.model.potmsgset import (
    credits_message_str,
    POTMsgSet,
    )
from lp.translations.model.translationimportqueue import collect_import_info
from lp.translations.model.translationmessage import (
    make_plurals_sql_fragment,
    TranslationMessage,
    )
from lp.translations.model.translationtemplateitem import (
    TranslationTemplateItem,
    )
from lp.translations.utilities.rosettastats import RosettaStats
from lp.translations.utilities.sanitize import MixedNewlineMarkersError
from lp.translations.utilities.translation_common_format import (
    TranslationMessageData,
    )


def compose_sql_translationmessage_has_translations(tm_sql_identifier):
    """Compose SQL for "`TranslationMessage` is nonempty.".

    :param tm_sql_identifier: The SQL identifier for the
        `TranslationMessage` in the query that's to be tested.
    """
    return "COALESCE(%s) IS NOT NULL" % ", ".join([
        "%s.msgstr%d" % (tm_sql_identifier, form)
        for form in xrange(TranslationConstants.MAX_PLURAL_FORMS)])


class POFileMixIn(RosettaStats):
    """Base class for `POFile` and `DummyPOFile`.

    Provides machinery for retrieving `TranslationMessage`s and populating
    their submissions caches.  That machinery is needed even for
    `DummyPOFile`s.
    """

    @property
    def plural_forms(self):
        """See `IPOFile`."""
        return self.language.guessed_pluralforms

    def hasPluralFormInformation(self):
        """See `IPOFile`."""
        if self.language.pluralforms is None:
            # We have no plural information for this language.  It
            # doesn't actually matter unless the template contains
            # messages with plural forms.
            return not self.potemplate.hasPluralMessage()
        else:
            return True

    def canEditTranslations(self, person):
        """See `IPOFile`."""
        policy = self.potemplate.getTranslationPolicy()
        return policy.allowsTranslationEdits(person, self.language)

    def canAddSuggestions(self, person):
        """See `IPOFile`."""
        policy = self.potemplate.getTranslationPolicy()
        return policy.allowsTranslationSuggestions(person, self.language)

    def getHeader(self):
        """See `IPOFile`."""
        translation_importer = getUtility(ITranslationImporter)
        format_importer = translation_importer.getTranslationFormatImporter(
            self.potemplate.source_file_format)
        header = format_importer.getHeaderFromString(self.header)
        header.comment = self.topcomment
        header.has_plural_forms = self.potemplate.hasPluralMessage()
        return header

    def _getTranslationSearchQuery(self, pofile, plural_form, text):
        """Query to find `text` in `plural_form` translations of a `pofile`.

        This produces a list of clauses that can be used to search for
        TranslationMessages containing `text` in their msgstr[`plural_form`].
        Returned values are POTMsgSet ids containing them, expected to be
        used in a UNION across all plural forms.
        """
        translation_match = """
        -- Find translations containing `text`.
        -- Like in findPOTMsgSetsContaining(), to avoid seqscans on
        -- POTranslation table, we do ILIKE comparison on them in
        -- a subselect which is first filtered by the POFile.
          SELECT TranslationMessage.potmsgset
            FROM TranslationMessage
            JOIN TranslationTemplateItem
              ON TranslationMessage.potmsgset
                   = TranslationTemplateItem.potmsgset
            WHERE
              TranslationTemplateItem.potemplate = %(potemplate)s AND
              TranslationMessage.language = %(language)s AND
              TranslationMessage.msgstr%(plural_form)d IN (
                SELECT POTranslation.id FROM POTranslation WHERE
                  POTranslation.id IN (
                    SELECT DISTINCT(msgstr%(plural_form)d)
                      FROM TranslationMessage AS tm_ids
                      JOIN TranslationTemplateItem
                        ON tm_ids.potmsgset=TranslationTemplateItem.potmsgset
                      WHERE
                        TranslationTemplateItem.potemplate
                          = %(potemplate)s AND
                        TranslationTemplateItem.sequence > 0 AND
                        tm_ids.language=%(language)s
                  ) AND
                  POTranslation.translation
                    ILIKE '%%' || %(text)s || '%%')
                    """ % dict(potemplate=quote(pofile.potemplate),
                               language=quote(pofile.language),
                               plural_form=plural_form,
                               text=quote_like(text))
        return translation_match

    def _getTemplateSearchQuery(self, text):
        """Query for finding `text` in msgids of this POFile.
        """
        english_match = """
        -- Step 1a: get POTMsgSets where msgid_singular contains `text`
        -- To avoid seqscans on POMsgID table (what LIKE usually
        -- does), we do ILIKE comparison on them in a subselect first
        -- filtered by this POTemplate.
          SELECT POTMsgSet.id
            FROM POTMsgSet
            JOIN TranslationTemplateItem
              ON TranslationTemplateItem.potmsgset=POTMsgSet.id AND
                 TranslationTemplateItem.potemplate=%s
            WHERE
              (POTMsgSet.msgid_singular IS NOT NULL AND
               POTMsgSet.msgid_singular IN (
                 SELECT POMsgID.id FROM POMsgID
                   WHERE id IN (
                     SELECT DISTINCT(msgid_singular)
                       FROM POTMsgSet
                       JOIN TranslationTemplateItem
                         ON TranslationTemplateItem.potmsgset = POTMsgSet.id
                       WHERE
                         TranslationTemplateItem.potemplate=%s AND
                         TranslationTemplateItem.sequence > 0
                   ) AND
                   msgid ILIKE '%%' || %s || '%%'))
          UNION
        -- Step 1b: like above, just on msgid_plural.
          SELECT POTMsgSet.id
            FROM POTMsgSet
            JOIN TranslationTemplateItem
              ON TranslationTemplateItem.potmsgset=POTMsgSet.id AND
                 TranslationTemplateItem.potemplate=%s
            WHERE
              (POTMsgSet.msgid_plural IS NOT NULL AND
               POTMsgSet.msgid_plural IN (
                 SELECT POMsgID.id FROM POMsgID
                   WHERE id IN (
                     SELECT DISTINCT(msgid_plural)
                       FROM POTMsgSet
                       JOIN TranslationTemplateItem
                         ON TranslationTemplateItem.potmsgset = POTMsgSet.id
                       WHERE
                         TranslationTemplateItem.potemplate=%s AND
                         TranslationTemplateItem.sequence > 0
                   ) AND
                   msgid ILIKE '%%' || %s || '%%'))
            """ % (quote(self.potemplate), quote(self.potemplate),
                   quote_like(text),
                   quote(self.potemplate), quote(self.potemplate),
                   quote_like(text))
        return english_match

    def _getOrderedPOTMsgSets(self, origin_tables, query):
        """Find all POTMsgSets matching `query` from `origin_tables`.

        Orders the result by TranslationTemplateItem.sequence which must
        be among `origin_tables`.
        """
        results = IMasterStore(POTMsgSet).using(origin_tables).find(
            POTMsgSet, SQL(query))
        return results.order_by(TranslationTemplateItem.sequence)

    def findPOTMsgSetsContaining(self, text):
        """See `IPOFile`."""
        clauses = [
            'TranslationTemplateItem.potemplate = %s' % sqlvalues(
                self.potemplate),
            'TranslationTemplateItem.potmsgset = POTMsgSet.id',
            'TranslationTemplateItem.sequence > 0',
            ]

        if text is not None:
            assert len(text) > 1, (
                "You can not search for strings shorter than 2 characters.")

            if self.potemplate.uses_english_msgids:
                english_match = self._getTemplateSearchQuery(text)
            else:
                # If msgids are not in English, use English PO file
                # to fetch original strings instead.
                en_pofile = self.potemplate.getPOFileByLang('en')
                english_match = self._getTranslationSearchQuery(
                    en_pofile, 0, text)

            # Do not look for translations in a DummyPOFile.
            search_clauses = [english_match]
            if self.id is not None:
                for plural_form in range(self.plural_forms):
                    translation_match = self._getTranslationSearchQuery(
                        self, plural_form, text)
                    search_clauses.append(translation_match)

            clauses.append(
                "POTMsgSet.id IN (" + " UNION ".join(search_clauses) + ")")

        return self._getOrderedPOTMsgSets(
            [POTMsgSet, TranslationTemplateItem], ' AND '.join(clauses))

    def getFullLanguageCode(self):
        """See `IPOFile`."""
        return self.language.code

    def getFullLanguageName(self):
        """See `IPOFile`."""
        return self.language.englishname

    def markChanged(self, translator=None, timestamp=None):
        """See `IPOFile`."""
        if timestamp is None:
            timestamp = UTC_NOW
        self.date_changed = timestamp
        if translator is not None:
            self.lasttranslator = translator


class POFile(SQLBase, POFileMixIn):
    implements(IPOFile)

    _table = 'POFile'

    potemplate = ForeignKey(foreignKey='POTemplate',
                            dbName='potemplate',
                            notNull=True)
    language = ForeignKey(foreignKey='Language',
                          dbName='language',
                          notNull=True)
    description = StringCol(dbName='description',
                            notNull=False,
                            default=None)
    topcomment = StringCol(dbName='topcomment',
                           notNull=False,
                           default=None)
    header = StringCol(dbName='header',
                       notNull=False,
                       default=None)
    fuzzyheader = BoolCol(dbName='fuzzyheader',
                          notNull=True)
    lasttranslator = ForeignKey(
        dbName='lasttranslator', foreignKey='Person',
        storm_validator=validate_public_person, notNull=False, default=None)

    date_changed = UtcDateTimeCol(
        dbName='date_changed', notNull=True, default=UTC_NOW)

    currentcount = IntCol(dbName='currentcount',
                          notNull=True,
                          default=0)
    updatescount = IntCol(dbName='updatescount',
                          notNull=True,
                          default=0)
    rosettacount = IntCol(dbName='rosettacount',
                          notNull=True,
                          default=0)
    unreviewed_count = IntCol(dbName='unreviewed_count',
                              notNull=True,
                              default=0)
    lastparsed = UtcDateTimeCol(dbName='lastparsed',
                                notNull=False,
                                default=None)
    owner = ForeignKey(
        dbName='owner', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)
    path = StringCol(dbName='path',
                     notNull=True)
    datecreated = UtcDateTimeCol(notNull=True, default=UTC_NOW)

    from_sourcepackagename = ForeignKey(foreignKey='SourcePackageName',
        dbName='from_sourcepackagename', notNull=False, default=None)

    @property
    def translation_messages(self):
        """See `IPOFile`."""
        return self.getTranslationMessages()

    def getOtherSidePOFile(self):
        """See `IPOFile`."""
        other_potemplate = self.potemplate.getOtherSidePOTemplate()
        if other_potemplate is None:
            return None
        return other_potemplate.getPOFileByLang(self.language.code)

    def getTranslationMessages(self, condition=None):
        """See `IPOFile`."""
        applicable_template = Coalesce(
            TranslationMessage.potemplateID, self.potemplate.id)
        clauses = [
            TranslationTemplateItem.potmsgsetID ==
                TranslationMessage.potmsgsetID,
            TranslationTemplateItem.potemplate == self.potemplate,
            TranslationMessage.language == self.language,
            applicable_template == self.potemplate.id,
            ]
        if condition is not None:
            clauses.append(condition)

        return IStore(self).find(
            TranslationMessage, *clauses).order_by(TranslationMessage.id)

    @property
    def title(self):
        """See `IPOFile`."""
        title = '%s translation of %s' % (
            self.language.displayname, self.potemplate.displayname)
        return title

    @property
    def translators(self):
        """See `IPOFile`."""
        translators = set()
        for group in self.potemplate.translationgroups:
            translator = group.query_translator(self.language)
            if translator is not None:
                translators.add(translator)
        return sorted(list(translators), key=lambda x: x.translator.name)

    @property
    def translationpermission(self):
        """See `IPOFile`."""
        return self.potemplate.translationpermission

    @property
    def contributors(self):
        """See `IPOFile`."""
        # Avoid circular import.
        from lp.registry.model.person import Person

        # Translation credit messages are "translated" by
        # rosetta_experts.  Shouldn't show up in contributors lists
        # though.
        admin_team = getUtility(ILaunchpadCelebrities).rosetta_experts

        contributors = Person.select("""
            POFileTranslator.person = Person.id AND
            POFileTranslator.person <> %s AND
            POFileTranslator.pofile = %s""" % sqlvalues(admin_team, self),
            clauseTables=["POFileTranslator"],
            distinct=True,
            # XXX: kiko 2006-10-19:
            # We can't use Person.sortingColumns because this is a
            # distinct query. To use it we'd need to add the sorting
            # function to the column results and then ignore it -- just
            # like selectAlso does, ironically.
            orderBy=["Person.displayname", "Person.name"])

        return contributors

    def prepareTranslationCredits(self, potmsgset):
        """See `IPOFile`."""
        LP_CREDIT_HEADER = u'Launchpad Contributions:'
        SPACE = u' '
        credits_type = potmsgset.translation_credits_type
        assert credits_type != TranslationCreditsType.NOT_CREDITS, (
            "Calling prepareTranslationCredits on a message with "
            "msgid '%s'." % potmsgset.singular_text)
        upstream = potmsgset.getCurrentTranslation(
            None, self.language, TranslationSide.UPSTREAM)
        if (upstream is None or
            upstream.origin == RosettaTranslationOrigin.LAUNCHPAD_GENERATED or
            upstream.translations[0] == credits_message_str):
            text = None
        else:
            text = upstream.translations[0]

        if credits_type == TranslationCreditsType.KDE_EMAILS:
            emails = []
            if text is not None:
                emails.append(text)

            # Add two empty email fields to make formatting nicer.
            # See bug #133817 for details.
            emails.extend([u'', u''])

            for contributor in self.contributors:
                preferred_email = contributor.preferredemail
                if (contributor.hide_email_addresses or
                    preferred_email is None):
                    emails.append('')
                else:
                    emails.append(preferred_email.email)
            return u','.join(emails)
        elif credits_type == TranslationCreditsType.KDE_NAMES:
            names = []

            if text is not None:
                if text == u'':
                    text = SPACE
                names.append(text)
            # Add an empty name as a separator, and 'Launchpad
            # Contributions' header; see bug #133817 for details.
            names.extend([SPACE, LP_CREDIT_HEADER])
            names.extend([
                contributor.displayname
                for contributor in self.contributors])
            return u','.join(names)
        elif credits_type == TranslationCreditsType.GNOME:
            if len(list(self.contributors)):
                if text is None:
                    text = u''
                else:
                    # Strip existing Launchpad contribution lists.
                    header_index = text.find(LP_CREDIT_HEADER)
                    if header_index != -1:
                        text = text[:header_index]
                    else:
                        text += u'\n\n'

                text += LP_CREDIT_HEADER
                for contributor in self.contributors:
                    text += ("\n  %s %s" %
                             (contributor.displayname,
                              canonical_url(contributor)))
            return text
        else:
            raise AssertionError(
                "Calling prepareTranslationCredits on a message with "
                "unknown credits type '%s'." % credits_type.title)

    def _getClausesForPOFileMessages(self, current=True):
        """Get TranslationMessages for the POFile via TranslationTemplateItem.

        Call-site will have to have appropriate clauseTables.
        """
        # When all the code that uses this method is moved to Storm,
        # we can replace it with _getStormClausesForPOFileMessages
        # and then remove it.
        clauses = [
            'TranslationTemplateItem.potemplate = %s' % sqlvalues(
                self.potemplate),
            ('TranslationTemplateItem.potmsgset'
             ' = TranslationMessage.potmsgset'),
            'TranslationMessage.language = %s' % sqlvalues(self.language)]
        if current:
            clauses.append('TranslationTemplateItem.sequence > 0')

        return clauses

    def _getStormClausesForPOFileMessages(self, current=True):
        """Get TranslationMessages for the POFile via TranslationTemplateItem.
        """
        clauses = [
            TranslationTemplateItem.potemplate == self.potemplate,
            (TranslationTemplateItem.potmsgsetID ==
             TranslationMessage.potmsgsetID),
            TranslationMessage.language == self.language,
            ]
        if current:
            clauses.append(TranslationTemplateItem.sequence > 0)

        return clauses

    def getTranslationsFilteredBy(self, person):
        """See `IPOFile`."""
        assert person is not None, "You must provide a person to filter by."
        clauses = self._getStormClausesForPOFileMessages(current=False)
        clauses.append(
            TranslationMessage.submitter == person)

        results = Store.of(self).find(
            TranslationMessage,
            *clauses)
        return results.order_by(
            TranslationTemplateItem.sequence,
            Desc(TranslationMessage.date_created))

    def _getTranslatedMessagesQuery(self):
        """Get query data for fetching all POTMsgSets with translations.

        Return a tuple of SQL (clauses, clause_tables) to be used with
        POTMsgSet.select().
        """
        flag_name = getUtility(ITranslationSideTraitsSet).getForTemplate(
            self.potemplate).flag_name
        clause_tables = ['TranslationTemplateItem', 'TranslationMessage']
        clauses = self._getClausesForPOFileMessages()
        clauses.append('TranslationMessage.%s IS TRUE' % flag_name)
        self._appendCompletePluralFormsConditions(clauses)

        # A message is current in this pofile if:
        #  * it's current (above) AND
        #  * (it's diverged AND non-empty)
        #     OR (it's shared AND non-empty AND no diverged one exists)
        diverged_translation_clauses = [
            'TranslationMessage.potemplate = %s' % sqlvalues(self.potemplate),
        ]
        diverged_translation_query = ' AND '.join(
            diverged_translation_clauses)

        shared_translation_clauses = [
            'TranslationMessage.potemplate IS NULL',
            '''NOT EXISTS (
                 SELECT * FROM TranslationMessage AS diverged
                   WHERE
                     diverged.potemplate=%(potemplate)s AND
                     diverged.%(flag_name)s IS TRUE AND
                     diverged.language = %(language)s AND
                     diverged.potmsgset=TranslationMessage.potmsgset)''' % (
                dict(
                     flag_name=flag_name,
                     language=quote(self.language),
                     potemplate=quote(self.potemplate),
                     )
                ),
        ]
        shared_translation_query = ' AND '.join(shared_translation_clauses)

        translated_query = ('( (' + diverged_translation_query + ') OR ('
                            + shared_translation_query + ') )')
        clauses.append(translated_query)
        return (clauses, clause_tables)

    def getPOTMsgSetTranslated(self):
        """See `IPOFile`."""
        clauses, clause_tables = self._getTranslatedMessagesQuery()
        clauses.append('TranslationTemplateItem.potmsgset = POTMsgSet.id')

        query = ' AND '.join(clauses)
        clause_tables.insert(0, POTMsgSet)
        return self._getOrderedPOTMsgSets(clause_tables, query)

    def getPOTMsgSetUntranslated(self):
        """See `IPOFile`."""
        # We get all POTMsgSet.ids with translations, and later
        # exclude them using a NOT IN subselect.
        translated_clauses, clause_tables = self._getTranslatedMessagesQuery()
        translated_clauses.append(
            'POTMsgSet.id=TranslationTemplateItem.potmsgset')
        # Even though this seems silly, Postgres prefers
        # TranslationTemplateItem index if we add it (and on staging we
        # get more than a 10x speed improvement: from 8s to 0.7s).  We
        # also need to put it before any other clauses to be actually useful.
        translated_clauses.insert(0,
            'TranslationTemplateItem.potmsgset ='
            ' TranslationTemplateItem.potmsgset')
        translated_query = (
            "(SELECT POTMsgSet.id"
            "   FROM TranslationTemplateItem, TranslationMessage, POTMsgSet"
            "   WHERE " + " AND ".join(translated_clauses) + ")")
        clauses = [
            'TranslationTemplateItem.potemplate = %s' % sqlvalues(
                self.potemplate),
            'TranslationTemplateItem.potmsgset = POTMsgSet.id',
            'TranslationTemplateItem.sequence > 0',
            ]
        clauses.append(
            'TranslationTemplateItem.potmsgset NOT IN (%s)' % (
                translated_query))

        query = ' AND '.join(clauses)
        return self._getOrderedPOTMsgSets(
            [POTMsgSet, TranslationTemplateItem], query)

    def getPOTMsgSetWithNewSuggestions(self):
        """See `IPOFile`."""
        flag_name = getUtility(ITranslationSideTraitsSet).getForTemplate(
            self.potemplate).flag_name
        clauses = self._getClausesForPOFileMessages()
        msgstr_clause = make_plurals_sql_fragment(
            "TranslationMessage.msgstr%(form)d IS NOT NULL", "OR")
        clauses.extend([
            'TranslationTemplateItem.potmsgset = POTMsgSet.id',
            'TranslationMessage.%s IS NOT TRUE' % flag_name,
            "(%s)" % msgstr_clause,
            ])

        diverged_translation_query = (
            '''(SELECT COALESCE(diverged.date_reviewed, diverged.date_created)
                 FROM TranslationMessage AS diverged
                 WHERE
                   diverged.%(flag_name)s IS TRUE AND
                   diverged.potemplate = %(potemplate)s AND
                   diverged.language = %(language)s AND
                   diverged.potmsgset=POTMsgSet.id)''' % dict(
            flag_name=flag_name,
            potemplate=quote(self.potemplate),
            language=quote(self.language)))

        shared_translation_query = (
            '''(SELECT COALESCE(shared.date_reviewed, shared.date_created)
                 FROM TranslationMessage AS shared
                 WHERE
                   shared.%(flag_name)s IS TRUE AND
                   shared.potemplate IS NULL AND
                   shared.language = %(language)s AND
                   shared.potmsgset=POTMsgSet.id)''' % dict(
            flag_name=flag_name,
            language=quote(self.language)))
        beginning_of_time = "TIMESTAMP '1970-01-01 00:00:00'"
        newer_than_query = (
            "TranslationMessage.date_created > COALESCE(" +
            ",".join([diverged_translation_query,
                      shared_translation_query,
                      beginning_of_time]) + ")")
        clauses.append(newer_than_query)

        # A POT set has "new" suggestions if there is a non current
        # TranslationMessage newer than the current reviewed one.
        query = (
            """POTMsgSet.id IN (SELECT DISTINCT TranslationMessage.potmsgset
                 FROM TranslationMessage, TranslationTemplateItem, POTMsgSet
                 WHERE (%(query)s)) AND
               POTMsgSet.id=TranslationTemplateItem.potmsgset AND
               TranslationTemplateItem.potemplate=%(potemplate)s
            """ % dict(query=' AND '.join(clauses),
                       potemplate=quote(self.potemplate)))
        return self._getOrderedPOTMsgSets(
            [POTMsgSet, TranslationTemplateItem], query)

    def getPOTMsgSetDifferentTranslations(self):
        """See `IPOFile`."""
        # A `POTMsgSet` has different translations if both sides have a
        # translation. If one of them is empty, the POTMsgSet is not included
        # in this list.

        clauses, clause_tables = self._getTranslatedMessagesQuery()
        other_side_flag_name = getUtility(
            ITranslationSideTraitsSet).getForTemplate(
                self.potemplate).other_side_traits.flag_name
        clauses.extend([
            'TranslationTemplateItem.potmsgset = POTMsgSet.id',
            'TranslationMessage.%s IS FALSE' % other_side_flag_name,
            ])

        imported_no_diverged = (
            '''NOT EXISTS (
                 SELECT * FROM TranslationMessage AS diverged
                   WHERE
                     diverged.%(flag_name)s IS TRUE AND
                     diverged.id <> imported.id AND
                     diverged.potemplate = %(potemplate)s AND
                     diverged.language = %(language)s AND
                     diverged.potmsgset=TranslationMessage.potmsgset)''' % (
                dict(
                    flag_name=other_side_flag_name,
                    potemplate=quote(self.potemplate),
                    language=quote(self.language),
                    )))
        imported_clauses = [
            'imported.id <> TranslationMessage.id',
            'imported.potmsgset = POTMsgSet.id',
            'imported.language = %s' % sqlvalues(self.language),
            'imported.%s IS TRUE' % other_side_flag_name,
            '(imported.potemplate=%s OR ' % sqlvalues(self.potemplate) +
            '   (imported.potemplate IS NULL AND ' + imported_no_diverged
            + '  ))',
            ]
        self._appendCompletePluralFormsConditions(imported_clauses,
                                                  'imported')
        exists_imported_query = (
            'EXISTS ('
            '  SELECT * FROM TranslationMessage AS imported'
            '      WHERE ' + ' AND '.join(imported_clauses) + ')')
        clauses.append(exists_imported_query)

        clause_tables.insert(0, POTMsgSet)
        query = ' AND '.join(clauses)
        return self._getOrderedPOTMsgSets(clause_tables, query)

    def messageCount(self):
        """See `IRosettaStats`."""
        return self.potemplate.messageCount()

    def currentCount(self, language=None):
        """See `IRosettaStats`."""
        return self.currentcount

    def updatesCount(self, language=None):
        """See `IRosettaStats`."""
        return self.updatescount

    def rosettaCount(self, language=None):
        """See `IRosettaStats`."""
        return self.rosettacount

    def unreviewedCount(self):
        """See `IRosettaStats`."""
        return self.unreviewed_count

    def getStatistics(self):
        """See `IPOFile`."""
        return (
            self.currentcount,
            self.updatescount,
            self.rosettacount,
            self.unreviewed_count)

    def _appendCompletePluralFormsConditions(self, query,
                                             table_name='TranslationMessage'):
        """Add conditions to implement ITranslationMessage.is_complete in SQL.

        :param query: A list of AND SQL conditions where the implementation of
            ITranslationMessage.is_complete will be appended as SQL
            conditions.
        """
        query.append('%(table_name)s.msgstr0 IS NOT NULL' % {
            'table_name': table_name})
        if self.language.pluralforms > 1:
            plurals_query = ' AND '.join(
                '%(table_name)s.msgstr%(plural_form)d IS NOT NULL' % {
                  'plural_form': plural_form,
                  'table_name': table_name,
                } for plural_form in range(1, self.plural_forms))
            query.append(
                '(POTMsgSet.msgid_plural IS NULL OR (%s))' % plurals_query)
        return query

    def _countTranslations(self):
        """Count `currentcount`, `updatescount`, and `rosettacount`."""
        if self.potemplate.messageCount() == 0:
            # Shortcut: if the template is empty, as it is when it is
            # first created, we know the answers without querying the
            # database.
            return 0, 0, 0

        side_traits = getUtility(ITranslationSideTraitsSet).getForTemplate(
            self.potemplate)
        complete_plural_clause_this_side = ' AND '.join(
            self._appendCompletePluralFormsConditions(
                [], table_name='Current'))
        complete_plural_clause_other_side = ' AND '.join(
            self._appendCompletePluralFormsConditions(
                [], table_name='Other'))
        params = {
            'potemplate': quote(self.potemplate),
            'language': quote(self.language),
            'flag': side_traits.flag_name,
            'other_flag': side_traits.other_side_traits.flag_name,
            'has_msgstrs': complete_plural_clause_this_side,
            'has_other_msgstrs': complete_plural_clause_other_side,
        }
        # The "distinct on" combined with the "order by potemplate nulls
        # last" makes diverged messages mask their shared equivalents.
        query = """
            SELECT has_other_msgstrs, same_on_both_sides, count(*)
            FROM (
                SELECT
                    DISTINCT ON (TTI.potmsgset)
                    %(has_other_msgstrs)s AS has_other_msgstrs,
                    (Other.id = Current.id) AS same_on_both_sides
                FROM TranslationTemplateItem AS TTI
                JOIN POTMsgSet ON POTMsgSet.id = TTI.potmsgset
                JOIN TranslationMessage AS Current ON
                    Current.potmsgset = TTI.potmsgset AND
                    Current.language = %(language)s AND
                    COALESCE(Current.potemplate, %(potemplate)s) =
                        %(potemplate)s AND
                    Current.%(flag)s IS TRUE
                LEFT OUTER JOIN TranslationMessage AS Other ON
                    Other.potmsgset = TTI.potmsgset AND
                    Other.language = %(language)s AND
                    Other.%(other_flag)s IS TRUE AND
                    Other.potemplate IS NULL
                WHERE
                    TTI.potemplate = %(potemplate)s AND
                    TTI.sequence > 0 AND
                    %(has_msgstrs)s
                ORDER BY
                    TTI.potmsgset,
                    Current.potemplate NULLS LAST
            ) AS translated_messages
            GROUP BY has_other_msgstrs, same_on_both_sides
            """ % params

        this_side_only = 0
        translated_differently = 0
        translated_same = 0
        for row in IStore(self).execute(query):
            (has_other_msgstrs, same_on_both_sides, count) = row
            if not has_other_msgstrs:
                this_side_only += count
            elif same_on_both_sides:
                translated_same += count
            else:
                translated_differently += count

        return (
            translated_same,
            translated_differently,
            translated_differently + this_side_only,
            )

    def _countNewSuggestions(self):
        """Count messages with new suggestions."""
        if self.potemplate.messageCount() == 0:
            # Shortcut: if the template is empty, as it is when it is
            # first created, we know the answers without querying the
            # database.
            return 0

        flag_name = getUtility(ITranslationSideTraitsSet).getForTemplate(
            self.potemplate).flag_name
        suggestion_nonempty = "COALESCE(%s) IS NOT NULL" % ', '.join([
            'Suggestion.msgstr%d' % form
            for form in xrange(TranslationConstants.MAX_PLURAL_FORMS)])
        params = {
            'language': quote(self.language),
            'potemplate': quote(self.potemplate),
            'flag': flag_name,
            'suggestion_nonempty': suggestion_nonempty,
        }
        # The "distinct on" combined with the "order by potemplate nulls
        # last" makes diverged messages mask their shared equivalents.
        query = """
            SELECT count(*)
            FROM (
                SELECT DISTINCT ON (TTI.potmsgset) *
                FROM TranslationTemplateItem TTI
                LEFT OUTER JOIN TranslationMessage AS Current ON
                    Current.potmsgset = TTI.potmsgset AND
                    Current.language = %(language)s AND
                    COALESCE(Current.potemplate, %(potemplate)s) =
                        %(potemplate)s AND
                    Current.%(flag)s IS TRUE
                WHERE
                    TTI.potemplate = %(potemplate)s AND
                    TTI.sequence > 0 AND
                    EXISTS (
                        SELECT *
                        FROM TranslationMessage Suggestion
                        WHERE
                            Suggestion.potmsgset = TTI.potmsgset AND
                            Suggestion.language = %(language)s AND
                            Suggestion.%(flag)s IS FALSE AND
                            %(suggestion_nonempty)s AND
                            Suggestion.date_created > COALESCE(
                                Current.date_reviewed,
                                Current.date_created,
                                TIMESTAMP 'epoch') AND
                            COALESCE(Suggestion.potemplate, %(potemplate)s) =
                                %(potemplate)s
                    )
                ORDER BY TTI.potmsgset, Current.potemplate NULLS LAST
            ) AS messages_with_suggestions
        """ % params
        return IStore(self).execute(query).get_one()[0]

    def updateStatistics(self):
        """See `IPOFile`."""
        if self.potemplate.messageCount() == 0:
            self.potemplate.updateMessageCount()

        (
            self.currentcount,
            self.updatescount,
            self.rosettacount,
        ) = self._countTranslations()
        self.unreviewed_count = self._countNewSuggestions()
        return self.getStatistics()

    def updateHeader(self, new_header):
        """See `IPOFile`."""
        if new_header is None:
            return

        self.topcomment = new_header.comment
        self.header = new_header.getRawContent()
        self.fuzzyheader = new_header.is_fuzzy

    def isTranslationRevisionDateOlder(self, header):
        """See `IPOFile`."""
        old_header = self.getHeader()

        # Get the old and new PO-Revision-Date entries as datetime objects.
        old_date = old_header.translation_revision_date
        new_date = header.translation_revision_date
        if old_date is None or new_date is None:
            # If one of the headers has an unknown revision date, they cannot
            # be compared, so we consider the new one as the most recent.
            return False

        # Check whether the date is older.
        return old_date > new_date

    def setPathIfUnique(self, path):
        """See `IPOFile`."""
        if path != self.path and self.potemplate.isPOFilePathAvailable(path):
            self.path = path

    def importFromQueue(self, entry_to_import, logger=None, txn=None):
        """See `IPOFile`."""
        assert entry_to_import is not None, "Attempt to import None entry."
        assert entry_to_import.import_into.id == self.id, (
            "Attempt to import entry to POFile it doesn't belong to.")
        assert entry_to_import.status == RosettaImportStatus.APPROVED, (
            "Attempt to import non-approved entry.")

        # XXX: JeroenVermeulen 2007-11-29: This method is called from the
        # import script, which can provide the right object but can only
        # obtain it in security-proxied form.  We need full, unguarded access
        # to complete the import.
        entry_to_import = removeSecurityProxy(entry_to_import)

        translation_importer = getUtility(ITranslationImporter)

        # While importing a file, there are two kinds of errors:
        #
        # - Errors that prevent us to parse the file. That's a global error,
        #   is handled with exceptions and will not change any data other than
        #   the status of that file to note the fact that its import failed.
        #
        # - Errors in concrete messages included in the file to import. That's
        #   a more localised error that doesn't affect the whole file being
        #   imported. It allows us to accept other translations so we accept
        #   everything but the messages with errors. We handle it returning a
        #   list of faulty messages.
        import_rejected = False
        needs_notification_for_imported = False
        error_text = None
        errors, warnings = None, None
        try:
            errors, warnings = (
                translation_importer.importFile(entry_to_import, logger))
        except NotExportedFromLaunchpad:
            # We got a file that was neither an upstream upload nor exported
            # from Launchpad. We log it and select the email template.
            if logger:
                logger.info(
                    'Error importing %s' % self.title, exc_info=1)
            template_mail = 'poimport-not-exported-from-rosetta.txt'
            import_rejected = True
            entry_to_import.setErrorOutput(
                "File was not exported from Launchpad.")
        except (MixedNewlineMarkersError, TranslationFormatSyntaxError,
                TranslationFormatInvalidInputError, UnicodeDecodeError) as (
                exception):
            # The import failed with a format error. We log it and select the
            # email template.
            if logger:
                logger.info(
                    'Error importing %s' % self.title, exc_info=1)
            if isinstance(exception, UnicodeDecodeError):
                template_mail = 'poimport-bad-encoding.txt'
            else:
                template_mail = 'poimport-syntax-error.txt'
            import_rejected = True
            error_text = str(exception)
            entry_to_import.setErrorOutput(error_text)
            needs_notification_for_imported = True
        except OutdatedTranslationError as exception:
            # The attached file is older than the last imported one, we ignore
            # it. We also log this problem and select the email template.
            if logger:
                logger.info('Got an old version for %s' % self.title)
            template_mail = 'poimport-got-old-version.txt'
            import_rejected = True
            error_text = str(exception)
            entry_to_import.setErrorOutput(
                "Outdated translation.  " + error_text)
        except TooManyPluralFormsError:
            if logger:
                logger.warning("Too many plural forms.")
            template_mail = 'poimport-too-many-plural-forms.txt'
            import_rejected = True
            entry_to_import.setErrorOutput("Too many plural forms.")
        else:
            # The import succeeded.  There may still be non-fatal errors
            # or warnings for individual messages (kept as a list in
            # "errors"), but we compose the text for that later.
            entry_to_import.setErrorOutput(None)

        # Prepare the mail notification.
        msgsets_imported = self.getTranslationMessages(
            TranslationMessage.was_obsolete_in_last_import == False).count()

        replacements = collect_import_info(entry_to_import, self, warnings)
        replacements.update({
            'import_title': '%s translations for %s' % (
                self.language.displayname, self.potemplate.displayname),
            'language': self.language.displayname,
            'language_code': self.language.code,
            'numberofmessages': msgsets_imported,
            })

        if error_text is not None:
            replacements['error'] = error_text

        entry_to_import.addWarningOutput(replacements['warnings'])

        if import_rejected:
            # We got an error that prevented us to import any translation, we
            # need to notify the user.
            subject = 'Import problem - %s - %s' % (
                self.language.displayname, self.potemplate.displayname)
        elif len(errors) > 0:
            data = self._prepare_pomessage_error_message(errors, replacements)
            subject, template_mail, errorsdetails = data
            entry_to_import.setErrorOutput(
                "Imported, but with errors:\n" + errorsdetails)
        else:
            # The import was successful.
            template_mail = 'poimport-confirmation.txt'
            subject = 'Translation import - %s - %s' % (
                self.language.displayname, self.potemplate.displayname)

        rosetta_experts = getUtility(ILaunchpadCelebrities).rosetta_experts
        if import_rejected:
            # There were no imports at all and the user needs to review that
            # file, we tag it as FAILED.
            entry_to_import.setStatus(
                RosettaImportStatus.FAILED, rosetta_experts)
        else:
            if (entry_to_import.by_maintainer and
                not needs_notification_for_imported):
                # If it's an upload by the maintainer of the project or
                # package, do not send success notifications unless they
                # are needed.
                subject = None

            entry_to_import.setStatus(
                RosettaImportStatus.IMPORTED, rosetta_experts)
            # Assign karma to the importer if this is not an automatic import
            # (all automatic imports come from the rosetta expert user) and
            # was done by the maintainer.
            if (entry_to_import.by_maintainer and
                entry_to_import.importer.id != rosetta_experts.id):
                entry_to_import.importer.assignKarma(
                    'translationimportupstream',
                    product=self.potemplate.product,
                    distribution=self.potemplate.distribution,
                    sourcepackagename=self.potemplate.sourcepackagename)

            # Synchronize to database so we can calculate fresh statistics on
            # the server side.
            flush_database_updates()

            # Now we update the statistics after this new import
            self.updateStatistics()

        template = get_email_template(template_mail, 'translations')
        message = template % replacements
        return (subject, message)

    def _prepare_pomessage_error_message(self, errors, replacements):
        # Return subject, template_mail, and errorsdetails to make
        # an error email message.
        error_count = len(errors)
        error_text = []
        for error in errors:
            potmsgset = error['potmsgset']
            pomessage = error['pomessage']
            sequence = potmsgset.getSequence(self.potemplate) or -1
            error_message = error['error-message']
            error_text.append('%d. "%s":\n\n%s\n\n' % (
                sequence, error_message, pomessage))
        errorsdetails = ''.join(error_text)
        replacements['numberoferrors'] = error_count
        replacements['errorsdetails'] = errorsdetails
        replacements['numberofcorrectmessages'] = (
            replacements['numberofmessages'] - error_count)
        template_mail = 'poimport-with-errors.txt'
        subject = 'Translation problems - %s - %s' % (
            self.language.displayname, self.potemplate.displayname)
        return subject, template_mail, errorsdetails

    def export(self, ignore_obsolete=False, force_utf8=False):
        """See `IPOFile`."""
        translation_exporter = getUtility(ITranslationExporter)
        translation_file_data = getAdapter(
            self, ITranslationFileData, 'all_messages')
        exported_file = translation_exporter.exportTranslationFiles(
            [translation_file_data], ignore_obsolete=ignore_obsolete,
            force_utf8=force_utf8)

        try:
            file_content = exported_file.read()
        finally:
            exported_file.close()

        return file_content

    def _selectRows(self, where=None, ignore_obsolete=True):
        """Select translation message data.

        Diverged messages come before shared ones.  The exporter relies
        on this.
        """
        # Avoid circular import.
        from lp.translations.model.vpoexport import VPOExport

        # Prefetch all POTMsgSets for this template in one go.
        potmsgsets = {}
        for potmsgset in self.potemplate.getPOTMsgSets(ignore_obsolete):
            potmsgsets[potmsgset.id] = potmsgset

        # Names of columns that are selected and passed (in this order) to
        # the VPOExport constructor.
        column_names = [
            'TranslationTemplateItem.potmsgset',
            'TranslationTemplateItem.sequence',
            'TranslationMessage.comment',
            'TranslationMessage.is_current_ubuntu',
            'TranslationMessage.is_current_upstream',
            'TranslationMessage.potemplate',
            'potranslation0.translation',
            'potranslation1.translation',
            'potranslation2.translation',
            'potranslation3.translation',
            'potranslation4.translation',
            'potranslation5.translation',
        ]
        columns = ', '.join(column_names)

        # Obsolete translations are marked with a sequence number of 0,
        # so they would get sorted to the front of the file during
        # export. To avoid that, sequence numbers of 0 are translated to
        # NULL and ordered to the end with NULLS LAST so that they
        # appear at the end of the file.
        sort_column_names = [
            'TranslationMessage.potemplate NULLS LAST',
            'CASE '
                'WHEN TranslationTemplateItem.sequence = 0 THEN NULL '
                'ELSE TranslationTemplateItem.sequence '
            'END NULLS LAST',
            'TranslationMessage.id',
        ]
        sort_columns = ', '.join(sort_column_names)

        main_select = "SELECT %s" % columns

        flag_name = getUtility(ITranslationSideTraitsSet).getForTemplate(
            self.potemplate).flag_name
        template_id = quote(self.potemplate)
        params = {
            'flag': flag_name,
            'language': quote(self.language),
            'template': template_id,
        }
        query = main_select + """
            FROM TranslationTemplateItem
            LEFT JOIN TranslationMessage ON
                (TranslationMessage.potemplate IS NULL
                 OR TranslationMessage.potemplate = %(template)s) AND
                TranslationMessage.potmsgset =
                    TranslationTemplateItem.potmsgset AND
                TranslationMessage.%(flag)s IS TRUE AND
                TranslationMessage.language = %(language)s
            """ % params

        for form in xrange(TranslationConstants.MAX_PLURAL_FORMS):
            alias = "potranslation%d" % form
            field = "TranslationMessage.msgstr%d" % form
            query += "LEFT JOIN POTranslation AS %s ON %s.id = %s\n" % (
                    alias, alias, field)

        conditions = ["TranslationTemplateItem.potemplate = %s" % template_id]

        if ignore_obsolete:
            conditions.append("TranslationTemplateItem.sequence <> 0")

        if where:
            conditions.append("(%s)" % where)

        query += "WHERE %s" % ' AND '.join(conditions)
        query += ' ORDER BY %s' % sort_columns

        for row in Store.of(self).execute(query):
            export_data = VPOExport(*row)
            export_data.setRefs(self, potmsgsets)
            yield export_data

    def getTranslationRows(self):
        """See `IVPOExportSet`."""
        # Only fetch rows that belong to this POFile and are "interesting":
        # they must either be in the current template (sequence != 0, so not
        # "obsolete") or be in the current imported version of the translation
        # (is_current_upstream), or both.
        traits = getUtility(ITranslationSideTraitsSet).getForTemplate(
            self.potemplate)
        flag = traits.flag_name
        where = "TranslationTemplateItem.sequence <> 0 OR %s IS TRUE" % flag
        return self._selectRows(ignore_obsolete=False, where=where)

    def getChangedRows(self):
        """See `IVPOExportSet`."""
        return self._selectRows(where="is_current_upstream IS FALSE")


class DummyPOFile(POFileMixIn):
    """Represents a POFile where we do not yet actually HAVE a POFile for
    that language for this template.
    """
    implements(IPOFile)

    def __init__(self, potemplate, language, owner=None):
        self.id = None
        self.potemplate = potemplate
        self.language = language
        self.description = None
        self.topcomment = None
        self.header = None
        self.fuzzyheader = False
        self.lasttranslator = None
        UTC = pytz.timezone('UTC')
        self.date_changed = None
        self.lastparsed = None

        if owner is None:
            owner = getUtility(ILaunchpadCelebrities).rosetta_experts
        # The "owner" is really just the creator, without any extra
        # privileges.
        self.owner = owner

        self.path = u'unknown'
        self.datecreated = datetime.datetime.now(UTC)
        self.last_touched_pomsgset = None
        self.contributors = []
        self.from_sourcepackagename = None
        self.translation_messages = None

    def messageCount(self):
        return self.potemplate.messageCount()

    @property
    def title(self):
        """See `IPOFile`."""
        title = '%s translation of %s' % (
            self.language.displayname, self.potemplate.displayname)
        return title

    @property
    def translators(self):
        tgroups = self.potemplate.translationgroups
        ret = []
        for group in tgroups:
            translator = group.query_translator(self.language)
            if translator is not None:
                ret.append(translator)
        return ret

    @property
    def translationpermission(self):
        """See `IPOFile`."""
        return self.potemplate.translationpermission

    def getOtherSidePOFile(self):
        """See `IPOFile`."""
        return None

    def getTranslationsFilteredBy(self, person):
        """See `IPOFile`."""
        return None

    def getPOTMsgSetTranslated(self):
        """See `IPOFile`."""
        return EmptyResultSet()

    def getPOTMsgSetUntranslated(self):
        """See `IPOFile`."""
        return self.potemplate.getPOTMsgSets()

    def getPOTMsgSetWithNewSuggestions(self):
        """See `IPOFile`."""
        return EmptyResultSet()

    def getPOTMsgSetDifferentTranslations(self):
        """See `IPOFile`."""
        return EmptyResultSet()

    def getTranslationMessages(self, condition=None):
        """See `IPOFile`."""
        return EmptyResultSet()

    def hasMessageID(self, msgid):
        """See `IPOFile`."""
        raise NotImplementedError

    def currentCount(self, language=None):
        """See `IRosettaStats`."""
        return 0

    def rosettaCount(self, language=None):
        """See `IRosettaStats`."""
        return 0

    def updatesCount(self, language=None):
        """See `IRosettaStats`."""
        return 0

    def unreviewedCount(self, language=None):
        """See `IPOFile`."""
        return 0

    def newCount(self, language=None):
        """See `IRosettaStats`."""
        return 0

    def translatedCount(self, language=None):
        """See `IRosettaStats`."""
        return 0

    def untranslatedCount(self, language=None):
        """See `IRosettaStats`."""
        return self.messageCount()

    def currentPercentage(self, language=None):
        """See `IRosettaStats`."""
        return 0.0

    def rosettaPercentage(self, language=None):
        """See `IRosettaStats`."""
        return 0.0

    def updatesPercentage(self, language=None):
        """See `IRosettaStats`."""
        return 0.0

    def newPercentage(self, language=None):
        """See `IRosettaStats`."""
        return 0.0

    def translatedPercentage(self, language=None):
        """See `IRosettaStats`."""
        return 0.0

    def untranslatedPercentage(self, language=None):
        """See `IRosettaStats`."""
        return 100.0

    def export(self, ignore_obsolete=False, force_utf8=False):
        """See `IPOFile`."""
        raise NotImplementedError

    def createMessageSetFromMessageSet(self, potmsgset):
        """See `IPOFile`."""
        raise NotImplementedError

    def getStatistics(self):
        """See `IPOFile`."""
        return (0, 0, 0, )

    def updateStatistics(self):
        """See `IPOFile`."""
        raise NotImplementedError

    def updateHeader(self, new_header):
        """See `IPOFile`."""
        raise NotImplementedError

    def isTranslationRevisionDateOlder(self, header):
        """See `IPOFile`."""
        raise NotImplementedError

    def setPathIfUnique(self, path):
        """See `IPOFile`."""
        # Any path will do for a DummyPOFile.
        self.path = path

    def getNextToImport(self):
        """See `IPOFile`."""
        raise NotImplementedError

    def importFromQueue(self, entry_to_import, logger=None, txn=None):
        """See `IPOFile`."""
        raise NotImplementedError

    def prepareTranslationCredits(self, potmsgset):
        """See `IPOFile`."""
        return None

    def getTranslationRows(self):
        """See `IPOFile`."""
        return []

    def getChangedRows(self):
        """See `IPOFile`."""
        return []


class POFileSet:
    implements(IPOFileSet)

    def getDummy(self, potemplate, language):
        return DummyPOFile(potemplate, language)

    def getPOFilesByPathAndOrigin(self, path, productseries=None,
                                  distroseries=None, sourcepackagename=None,
                                  ignore_obsolete=False):
        """See `IPOFileSet`."""
        # Avoid circular imports.
        from lp.translations.model.potemplate import POTemplate

        assert productseries is not None or distroseries is not None, (
            'Either productseries or sourcepackagename arguments must be'
            ' not None.')
        assert productseries is None or distroseries is None, (
            'productseries and sourcepackagename/distroseries cannot be used'
            ' at the same time.')
        assert (
            (sourcepackagename is None and distroseries is None) or
             (sourcepackagename is not None and distroseries is not None)), (
                'sourcepackagename and distroseries must be None or not'
                   ' None at the same time.')

        store = IStore(POFile)

        conditions = [
            POFile.path == path,
            POFile.potemplate == POTemplate.id,
            ]
        if ignore_obsolete:
            conditions.append(POTemplate.iscurrent == True)

        if productseries is not None:
            conditions.append(POTemplate.productseries == productseries)
        else:
            conditions.append(POTemplate.distroseries == distroseries)

            # The POFile belongs to a distribution and it could come from
            # another package that its POTemplate is linked to, so we first
            # check to find it at IPOFile.from_sourcepackagename
            linked_conditions = conditions + [
                POFile.from_sourcepackagename == sourcepackagename]

            matches = store.find(POFile, *linked_conditions)
            if not matches.is_empty():
                return matches

            # There is no pofile in that 'path' and
            # 'IPOFile.from_sourcepackagename' so we do a search using the
            # usual sourcepackagename.
            conditions.append(
                POTemplate.sourcepackagename == sourcepackagename)

        return store.find(POFile, *conditions)

    def getBatch(self, starting_id, batch_size):
        """See `IPOFileSet`."""
        return POFile.select(
            "id >= %s" % quote(starting_id), orderBy="id", limit=batch_size)

    def getPOFilesWithTranslationCredits(self, untranslated=False):
        """See `IPOFileSet`."""
        # Avoid circular imports.
        from lp.translations.model.potemplate import POTemplate

        clauses = [
            TranslationTemplateItem.potemplateID == POFile.potemplateID,
            POTMsgSet.id == TranslationTemplateItem.potmsgsetID,
            POTMsgSet.msgid_singular == POMsgID.id,
            POMsgID.msgid.is_in(POTMsgSet.credits_message_ids),
            ]
        if untranslated:
            message_select = Select(
                True,
                And(
                    TranslationMessage.potmsgsetID == POTMsgSet.id,
                    TranslationMessage.potemplate == None,
                    POFile.languageID == TranslationMessage.languageID,
                    Or(
                        And(
                            POTemplate.productseries == None,
                            TranslationMessage.is_current_ubuntu == True),
                        And(
                            POTemplate.productseries != None,
                            TranslationMessage.is_current_upstream == True))),
                (TranslationMessage))
            clauses.append(POTemplate.id == POFile.potemplateID)
            clauses.append(Not(Exists(message_select)))
        result = IMasterStore(POFile).find((POFile, POTMsgSet), clauses)
        return result.order_by('POFile.id')

    def getPOFilesTouchedSince(self, date):
        """See `IPOFileSet`."""
        # Avoid circular imports.
        from lp.translations.model.potemplate import POTemplate
        from lp.registry.model.distroseries import DistroSeries
        from lp.registry.model.productseries import ProductSeries

        store = IMasterStore(POTemplate)

        # Find a matching POTemplate and its ProductSeries
        # and DistroSeries, if they are defined.
        MatchingPOT = ClassAlias(POTemplate)
        MatchingPOTJoin = Join(
            MatchingPOT, POFile.potemplate == MatchingPOT.id)
        MatchingProductSeries = ClassAlias(ProductSeries)
        MatchingProductSeriesJoin = LeftJoin(
            MatchingProductSeries,
            MatchingPOT.productseriesID == MatchingProductSeries.id)
        MatchingDistroSeries = ClassAlias(DistroSeries)
        MatchingDistroSeriesJoin = LeftJoin(
            MatchingDistroSeries,
            MatchingPOT.distroseriesID == MatchingDistroSeries.id)

        # Find any sharing POTemplate corresponding to MatchingPOT
        # and its ProductSeries and DistroSeries, if they are defined.
        OtherPOT = ClassAlias(POTemplate)
        OtherPOTJoin = Join(
            OtherPOT, And(OtherPOT.name == MatchingPOT.name))
        OtherProductSeries = ClassAlias(ProductSeries)
        OtherProductSeriesJoin = LeftJoin(
            OtherProductSeries,
            OtherPOT.productseriesID == OtherProductSeries.id)
        OtherDistroSeries = ClassAlias(DistroSeries)
        OtherDistroSeriesJoin = LeftJoin(
            OtherDistroSeries,
            OtherPOT.distroseriesID == OtherDistroSeries.id)

        # And find a sharing POFile corresponding to a sharing POTemplate,
        # i.e. OtherPOT.
        OtherPOFile = ClassAlias(POFile)
        OtherPOFileJoin = Join(
            OtherPOFile,
            And(OtherPOFile.languageID == POFile.languageID,
                OtherPOFile.potemplateID == OtherPOT.id))

        source = store.using(
            POFile, MatchingPOTJoin, MatchingProductSeriesJoin,
            MatchingDistroSeriesJoin, OtherPOTJoin,
            OtherProductSeriesJoin, OtherDistroSeriesJoin, OtherPOFileJoin)

        results = source.find(
            OtherPOFile,
            And(POFile.date_changed >= date,
                Or(
                    # OtherPOT is a sharing template with MatchingPOT
                    # in the same distribution and sourcepackagename.
                    And(MatchingPOT.distroseriesID is not None,
                        OtherPOT.distroseriesID is not None,
                        (MatchingDistroSeries.distributionID ==
                         OtherDistroSeries.distributionID),
                        (MatchingPOT.sourcepackagenameID ==
                         OtherPOT.sourcepackagenameID)),
                    # OtherPOT is a sharing template with MatchingPOT
                    # in the same product.
                    And(MatchingPOT.productseriesID is not None,
                        OtherPOT.productseriesID is not None,
                        (MatchingProductSeries.productID ==
                         OtherProductSeries.productID)))))
        results.config(distinct=True)
        return results


class POFileToTranslationFileDataAdapter:
    """Adapter from `IPOFile` to `ITranslationFileData`."""
    implements(ITranslationFileData)

    def __init__(self, pofile):
        self._pofile = pofile
        self.messages = self._getMessages()
        self.format = pofile.potemplate.source_file_format

    @cachedproperty
    def path(self):
        """See `ITranslationFileData`."""
        return self._pofile.path

    @cachedproperty
    def translation_domain(self):
        """See `ITranslationFileData`."""
        return self._pofile.potemplate.translation_domain

    @property
    def is_template(self):
        """See `ITranslationFileData`."""
        return False

    @cachedproperty
    def language_code(self):
        """See `ITranslationFile`."""
        if self.is_template:
            return None

        return self._pofile.language.code

    def _isWesternPluralForm(self, number, expression):
        # Western style is nplurals=2;plural=n!=1.
        if number != 2:
            return False
        if expression is None:
            return False
        # Normalize: Remove spaces.
        expression = expression.replace(' ', '')
        # Normalize: Remove enclosing brackets.
        expression = expression.strip('()')
        return expression in ('n!=1', '1!=n', 'n>1', '1<n')

    def _updateHeaderPluralInfo(self, header):
        header_nplurals = header.number_plural_forms
        database_nplurals = self._pofile.language.pluralforms
        # These checks are here to catch cases where the plural information
        # from the header might be more acurate than what we have in the
        # database. This is usually the case when the number of plural forms
        # has grown but not if it's the standard western form.
        # See bug 565294
        if header_nplurals is not None and database_nplurals is not None:
            if header_nplurals > database_nplurals:
                is_western = self._isWesternPluralForm(
                    header_nplurals, header.plural_form_expression)
                if not is_western:
                    # Use existing information from the header.
                    return
        if database_nplurals is None:
            # In all other cases we never use the plural info from the header.
            header.number_plural_forms = None
            header.plural_form_expression = None
        else:
            # We have pluralforms information for this language so we
            # update the header to be sure that we use the language
            # information from our database instead of using the one
            # that we got from upstream. We check this information so
            # we are sure it's valid.
            header.number_plural_forms = self._pofile.language.pluralforms
            header.plural_form_expression = (
                self._pofile.language.pluralexpression)

    @cachedproperty
    def header(self):
        """See `ITranslationFileData`."""
        template_header = self._pofile.potemplate.getHeader()
        translation_header = self._pofile.getHeader()
        # Update default fields based on its values in the template header.
        translation_header.updateFromTemplateHeader(template_header)
        translation_header.translation_revision_date = (
            self._pofile.date_changed)

        translation_header.comment = self._pofile.topcomment

        if self._pofile.potemplate.hasPluralMessage():
            self._updateHeaderPluralInfo(translation_header)
        if (self._pofile.lasttranslator is not None):
            email = self._pofile.lasttranslator.safe_email_or_blank
            if not email:
                # We are supposed to have always a valid email address, but
                # with removed accounts or people not wanting to show his
                # email that's not true anymore so we just set it to 'Unknown'
                # to note we don't know it.
                email = 'Unknown'
            displayname = self._pofile.lasttranslator.displayname
            translation_header.setLastTranslator(email, name=displayname)

        # We need to tag every export from Launchpad so we know whether a
        # later upload should change every translation in our database or
        # that we got a change between the export and the upload with
        # modifications.
        UTC = pytz.timezone('UTC')
        datetime_now = datetime.datetime.now(UTC)
        translation_header.launchpad_export_date = datetime_now

        return translation_header

    def _getMessages(self, changed_rows_only=False):
        """Return a list of `ITranslationMessageData` for the `IPOFile`
        adapted."""
        pofile = self._pofile
        # Get all rows related to this file. We do this to speed the export
        # process so we have a single DB query to fetch all needed
        # information.
        if changed_rows_only:
            rows = pofile.getChangedRows()
        else:
            rows = pofile.getTranslationRows()

        messages = []
        diverged_messages = set()
        for row in rows:
            assert row.pofile == pofile, 'Got a row for a different IPOFile.'

            msg_key = (row.msgid_singular, row.msgid_plural, row.context)
            if row.diverged is not None:
                diverged_messages.add(msg_key)
            else:
                # If we are exporting a shared message, make sure we
                # haven't added a diverged one to the list already.
                if msg_key in diverged_messages:
                    continue

            # Create new message set
            msgset = TranslationMessageData()
            msgset.is_obsolete = (row.sequence == 0)
            msgset.msgid_singular = row.msgid_singular
            msgset.singular_text = row.potmsgset.singular_text
            msgset.msgid_plural = row.msgid_plural
            msgset.plural_text = row.potmsgset.plural_text

            forms = list(enumerate([
                getattr(row, "translation%d" % form)
                for form in xrange(TranslationConstants.MAX_PLURAL_FORMS)]))
            max_forms = pofile.plural_forms
            for (pluralform, translation) in forms[:max_forms]:
                if translation is not None:
                    msgset.addTranslation(pluralform, translation)

            msgset.context = row.context
            msgset.comment = row.comment
            msgset.source_comment = row.source_comment
            msgset.file_references = row.file_references

            if row.flags_comment:
                msgset.flags = set([
                    flag.strip()
                    for flag in row.flags_comment.split(',')
                    if flag])

            messages.append(msgset)

        return messages


class POFileToChangedFromPackagedAdapter(POFileToTranslationFileDataAdapter):
    """Adapter from `IPOFile` to `ITranslationFileData`."""

    def __init__(self, pofile):
        self._pofile = pofile
        self.messages = self._getMessages(True)
