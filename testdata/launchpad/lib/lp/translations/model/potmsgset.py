# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'credits_message_str',
    'POTMsgSet',
    ]

from collections import (
    defaultdict,
    namedtuple,
    )
import logging
import re

from sqlobject import (
    ForeignKey,
    SQLObjectNotFound,
    StringCol,
    )
from storm.expr import (
    Coalesce,
    Desc,
    Or,
    SQL,
    )
from storm.store import (
    EmptyResultSet,
    Store,
    )
from zope.component import getUtility
from zope.interface import implements
from zope.security.proxy import removeSecurityProxy

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.services.config import config
from lp.services.database.constants import DEFAULT
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import (
    cursor,
    quote,
    SQLBase,
    sqlvalues,
    )
from lp.services.helpers import shortlist
from lp.services.propertycache import get_property_cache
from lp.translations.interfaces.potmsgset import (
    IPOTMsgSet,
    POTMsgSetInIncompatibleTemplatesError,
    TranslationCreditsType,
    )
from lp.translations.interfaces.side import (
    ITranslationSideTraitsSet,
    TranslationSide,
    )
from lp.translations.interfaces.translationfileformat import (
    TranslationFileFormat,
    )
from lp.translations.interfaces.translationimporter import (
    ITranslationImporter,
    )
from lp.translations.interfaces.translationmessage import (
    RosettaTranslationOrigin,
    TranslationConflict,
    TranslationValidationStatus,
    )
from lp.translations.interfaces.translations import TranslationConstants
from lp.translations.model.pomsgid import POMsgID
from lp.translations.model.potranslation import POTranslation
from lp.translations.model.translationmessage import (
    DummyTranslationMessage,
    make_plurals_sql_fragment,
    TranslationMessage,
    )
from lp.translations.model.translationtemplateitem import (
    TranslationTemplateItem,
    )
from lp.translations.utilities.validate import validate_translation

# Msgids that indicate translation credit messages, and their
# contexts and type.
credits_message_info = {
    # Regular gettext credits messages.
    u'translation-credits': (None, TranslationCreditsType.GNOME),
    u'translator-credits': (None, TranslationCreditsType.GNOME),
    u'translator_credits': (None, TranslationCreditsType.GNOME),

    # KDE credits messages.
    u'Your emails':
        (u'EMAIL OF TRANSLATORS', TranslationCreditsType.KDE_EMAILS),
    u'Your names':
        (u'NAME OF TRANSLATORS', TranslationCreditsType.KDE_NAMES),

    # Old KDE credits messages.
    u'_: EMAIL OF TRANSLATORS\nYour emails':
        (None, TranslationCreditsType.KDE_EMAILS),
    u'_: NAME OF TRANSLATORS\nYour names':
        (None, TranslationCreditsType.KDE_NAMES),
    }

# String to be used as msgstr for translation credits messages.
credits_message_str = (u'This is a dummy translation so that the '
                       u'credits are counted as translated.')


# Marker for "no incumbent message found yet."
incumbent_unknown = object()


def dictify_translations(translations):
    """Represent `translations` as a normalized dict.

    :param translations: a dict or sequence of `POTranslation`s or
        translation strings per plural form.
    :return: a dict mapping each translated plural form to an item in
        the original list.  Untranslated forms are omitted.
    """
    if not isinstance(translations, dict):
        # Turn a sequence into a dict.
        translations = dict(enumerate(translations))
    # Filter out None values.
    return dict(
        (form, translation)
        for form, translation in translations.iteritems()
        if translation is not None)


class POTMsgSet(SQLBase):
    implements(IPOTMsgSet)

    _table = 'POTMsgSet'

    context = StringCol(dbName='context', notNull=False)
    msgid_singular = ForeignKey(foreignKey='POMsgID', dbName='msgid_singular',
        notNull=True)
    msgid_plural = ForeignKey(foreignKey='POMsgID', dbName='msgid_plural',
        notNull=False, default=DEFAULT)
    commenttext = StringCol(dbName='commenttext', notNull=False)
    filereferences = StringCol(dbName='filereferences', notNull=False)
    sourcecomment = StringCol(dbName='sourcecomment', notNull=False)
    flagscomment = StringCol(dbName='flagscomment', notNull=False)

    credits_message_ids = credits_message_info.keys()

    def clone(self):
        return POTMsgSet(
            context=self.context,
            msgid_singular=self.msgid_singular,
            msgid_plural=self.msgid_plural,
            commenttext=self.commenttext,
            filereferences=self.filereferences,
            sourcecomment=self.sourcecomment,
            flagscomment=self.flagscomment,
        )

    def _conflictsExistingSourceFileFormats(self, source_file_format=None):
        """Return whether `source_file_format` conflicts with existing ones
        for this `POTMsgSet`.

        If `source_file_format` is None, just check the overall consistency
        of all the source_file_format values.  Otherwise, it should be
        a `TranslationFileFormat` value.
        """

        translation_importer = getUtility(ITranslationImporter)

        if source_file_format is not None:
            format = translation_importer.getTranslationFormatImporter(
                source_file_format)
            uses_english_msgids = not format.uses_source_string_msgids
        else:
            uses_english_msgids = None

        # Now let's find all the source_file_formats for all the
        # POTemplates this POTMsgSet is part of.
        query = """
           SELECT DISTINCT POTemplate.source_file_format
             FROM TranslationTemplateItem
                  JOIN POTemplate
                    ON POTemplate.id = TranslationTemplateItem.potemplate
             WHERE TranslationTemplateItem.potmsgset = %s""" % (
            sqlvalues(self))
        cur = cursor()
        cur.execute(query)
        source_file_formats = cur.fetchall()
        for source_file_format, in source_file_formats:
            format = translation_importer.getTranslationFormatImporter(
                TranslationFileFormat.items[source_file_format])
            format_uses_english_msgids = not format.uses_source_string_msgids

            if uses_english_msgids is None:
                uses_english_msgids = format_uses_english_msgids
            else:
                if uses_english_msgids != format_uses_english_msgids:
                    # There are conflicting source_file_formats for this
                    # POTMsgSet.
                    return (True, None)
                else:
                    uses_english_msgids = format_uses_english_msgids

        # No conflicting POTemplate entries were found.
        return (False, uses_english_msgids)

    @property
    def uses_english_msgids(self):
        """See `IPOTMsgSet`."""
        # Make explicit use of the property cache.
        cache = get_property_cache(self)
        if "uses_english_msgids" in cache:
            return cache.uses_english_msgids

        conflicts, uses_english_msgids = (
            self._conflictsExistingSourceFileFormats())

        if conflicts:
            raise POTMsgSetInIncompatibleTemplatesError(
                "This POTMsgSet participates in two POTemplates which "
                "have conflicting values for uses_english_msgids.")
        else:
            if uses_english_msgids is None:
                # Default is to use English in msgids, as opposed
                # to using unique identifiers (like XPI files do) and
                # having a separate English translation.
                # However, we are not caching anything when there's
                # no value to cache.
                return True
            cache.uses_english_msgids = uses_english_msgids
        return cache.uses_english_msgids

    @property
    def singular_text(self):
        """See `IPOTMsgSet`."""
        # Make explicit use of the property cache.
        cache = get_property_cache(self)
        if "singular_text"in cache:
            return cache.singular_text

        if self.uses_english_msgids:
            cache.singular_text = self.msgid_singular.msgid
            return cache.singular_text

        # Singular text is stored as an "English translation." Search on
        # both sides but prefer upstream translations.
        translation_message = self.getCurrentTranslation(
            None, getUtility(ILaunchpadCelebrities).english,
            TranslationSide.UPSTREAM)
        if translation_message is None:
            translation_message = self.getCurrentTranslation(
                None, getUtility(ILaunchpadCelebrities).english,
                TranslationSide.UBUNTU)
        if translation_message is not None:
            msgstr0 = translation_message.msgstr0
            if msgstr0 is not None:
                cache.singular_text = msgstr0.translation
                return cache.singular_text

        # There is no "English translation," at least not yet.  Return
        # symbolic msgid, but do not cache--an English text may still be
        # imported.
        return self.msgid_singular.msgid

    @property
    def plural_text(self):
        """See `IPOTMsgSet`."""
        if self.msgid_plural is None:
            return None
        else:
            return self.msgid_plural.msgid

    def getCurrentTranslationMessageOrDummy(self, pofile):
        """See `IPOTMsgSet`."""
        template = pofile.potemplate
        current = self.getCurrentTranslation(
            template, pofile.language, template.translation_side)
        if current is None:
            dummy = DummyTranslationMessage(pofile, self)
            side = pofile.potemplate.translation_side
            traits = getUtility(ITranslationSideTraitsSet).getTraits(side)
            traits.setFlag(dummy, True)
            return dummy
        else:
            current.setPOFile(pofile)
            return current

    def getOtherTranslation(self, language, side):
        """See `IPOTMsgSet`."""
        traits = getUtility(
            ITranslationSideTraitsSet).getTraits(side)
        return self.getCurrentTranslation(
            None, language, traits.other_side_traits.side)

    def getSharedTranslation(self, language, side):
        """See `IPOTMsgSet`."""
        return self.getCurrentTranslation(
            None, language, side)

    def getCurrentTranslation(self, potemplate, language, side):
        """See `IPOTMsgSet`."""
        traits = getUtility(ITranslationSideTraitsSet).getTraits(side)
        flag = removeSecurityProxy(traits.getFlag(TranslationMessage))

        clauses = [
            flag == True,
            TranslationMessage.potmsgsetID == self.id,
            TranslationMessage.languageID == language.id,
            ]

        if potemplate is None:
            # Look only for a shared translation.
            clauses.append(TranslationMessage.potemplate == None)
        else:
            clauses.append(Or(
                TranslationMessage.potemplate == None,
                TranslationMessage.potemplateID == potemplate.id))

        # Return a diverged translation if it exists, and fall back
        # to the shared one otherwise.
        result = Store.of(self).find(
            TranslationMessage, *clauses).order_by(
              Desc(Coalesce(TranslationMessage.potemplateID, -1))).first()
        return result

    def getLocalTranslationMessages(self, potemplate, language,
                                    include_dismissed=False,
                                    include_unreviewed=True):
        """See `IPOTMsgSet`."""
        query = """
            is_current_ubuntu IS NOT TRUE AND
            is_current_upstream IS NOT TRUE AND
            potmsgset = %s AND
            language = %s
            """ % sqlvalues(self, language)
        msgstr_clause = make_plurals_sql_fragment(
            "msgstr%(form)d IS NOT NULL", "OR")
        query += " AND (%s)" % msgstr_clause
        if include_dismissed != include_unreviewed:
            current = self.getCurrentTranslation(
                potemplate, language, potemplate.translation_side)
            if current is not None:
                if current.date_reviewed is None:
                    comparing_date = current.date_created
                else:
                    comparing_date = current.date_reviewed
                if include_unreviewed:
                    term = " AND date_created > %s"
                else:
                    term = " AND date_created <= %s"
                query += term % sqlvalues(comparing_date)
        elif include_dismissed and include_unreviewed:
            # Return all messages
            pass
        else:
            # No need to run a query.
            return EmptyResultSet()

        return TranslationMessage.select(query)

    def _getExternalTranslationMessages(self, suggested_languages=(),
        used_languages=()):
        """Return external suggestions for this message.

        External suggestions are all TranslationMessages for the
        same english string which are used or suggested in other templates.

        A message is used if it's either imported or current, and unused
        otherwise.

        Suggestions are read-only, so these objects come from the slave
        store.

        :param suggested_languages: Languages that suggestions should be found
            for.
        :param used_languages: Languages that used messages should be found
            for.
        """
        if not config.rosetta.global_suggestions_enabled:
            return []

        # Return empty list (no suggestions) for translation credit strings
        # because they are automatically translated.
        if self.is_translation_credit:
            return []
        # Watch out when changing this condition: make sure it's done in
        # a way so that indexes are indeed hit when the query is executed.
        # Also note that there is a NOT(in_use_clause) index.
        in_use_clause = (
            "(is_current_ubuntu IS TRUE OR is_current_upstream IS TRUE)")
        # Present a list of language + usage constraints to sql. A language
        # can either be unconstrained, used, or suggested depending on which
        # of suggested_languages, used_languages it appears in.
        suggested_languages = set(lang.id for lang in suggested_languages)
        used_languages = set(lang.id for lang in used_languages)
        both_languages = suggested_languages.intersection(used_languages)
        suggested_languages = suggested_languages - both_languages
        used_languages = used_languages - both_languages
        lang_used = []
        if both_languages:
            lang_used.append('TranslationMessage.language IN %s' %
                quote(both_languages))
        if used_languages:
            lang_used.append('(TranslationMessage.language IN %s AND %s)' % (
                quote(used_languages), in_use_clause))
        if suggested_languages:
            lang_used.append(
                '(TranslationMessage.language IN %s AND NOT %s)' % (
                quote(suggested_languages), in_use_clause))

        msgsets = SQL('''msgsets AS (
                SELECT POTMsgSet.id
                FROM POTMsgSet
                JOIN TranslationTemplateItem ON
                    TranslationTemplateItem.potmsgset = POTMsgSet.id
                JOIN SuggestivePOTemplate ON
                    TranslationTemplateItem.potemplate =
                        SuggestivePOTemplate.potemplate
                WHERE msgid_singular = %s and potmsgset.id <> %s
            )''' % sqlvalues(self.msgid_singular, self))

        # Subquery to find the ids of TranslationMessages that are
        # matching suggestions.
        # We're going to get a lot of duplicates, sometimes resulting in
        # thousands of suggestions.  Weed out most of that duplication by
        # excluding older messages that are identical to newer ones in
        # all translated forms.  The Python code can later sort out the
        # distinct translations per form.
        msgstrs = ', '.join([
            'COALESCE(msgstr%d, -1)' % form
            for form in xrange(TranslationConstants.MAX_PLURAL_FORMS)])
        ids_query_params = {
            'msgstrs': msgstrs,
            'where': '(' + ' OR '.join(lang_used) + ')',
        }
        ids_query = '''
            SELECT DISTINCT ON (%(msgstrs)s)
                TranslationMessage.id
            FROM TranslationMessage
            JOIN msgsets ON msgsets.id = TranslationMessage.potmsgset
            WHERE %(where)s
            ORDER BY %(msgstrs)s, date_created DESC
            ''' % ids_query_params

        result = IStore(TranslationMessage).with_(msgsets).find(
            TranslationMessage,
            TranslationMessage.id.is_in(SQL(ids_query)))

        return shortlist(result, longest_expected=100, hardlimit=2000)

    def getExternallyUsedTranslationMessages(self, language):
        """See `IPOTMsgSet`."""
        return self._getExternalTranslationMessages(used_languages=[language])

    def getExternallySuggestedTranslationMessages(self, language):
        """See `IPOTMsgSet`."""
        return self._getExternalTranslationMessages(
            suggested_languages=[language])

    def getExternallySuggestedOrUsedTranslationMessages(self,
            suggested_languages=(), used_languages=()):
        """See `IPOTMsgSet`."""
        # This method exists because suggestions + used == all external
        # messages : its better not to do the work twice. We could use a
        # temp table and query twice, but as the list length is capped at
        # 2000, doing a single pass in python should be insignificantly
        # slower.
        result_type = namedtuple('SuggestedOrUsed', 'suggested used')
        result = defaultdict(lambda: result_type([], []))
        for message in self._getExternalTranslationMessages(
            suggested_languages=suggested_languages,
            used_languages=used_languages):
            in_use = message.is_current_ubuntu or message.is_current_upstream
            language_result = result[message.language]
            if in_use:
                language_result.used.append(message)
            else:
                language_result.suggested.append(message)
        return result

    @property
    def flags(self):
        if self.flagscomment is None:
            return []
        else:
            return [flag
                    for flag in self.flagscomment.replace(' ', '').split(',')
                    if flag != '']

    def hasTranslationChangedInLaunchpad(self, potemplate, language):
        """See `IPOTMsgSet`."""
        other_translation = self.getOtherTranslation(
            language, potemplate.translation_side)
        current_translation = self.getCurrentTranslation(
            potemplate, language, potemplate.translation_side)
        return (other_translation is not None and
                other_translation != current_translation)

    def isTranslationNewerThan(self, pofile, timestamp):
        """See `IPOTMsgSet`."""
        if timestamp is None:
            return False
        template = pofile.potemplate
        current = self.getCurrentTranslation(
            template, pofile.language, template.translation_side)
        if current is None:
            return False
        date_updated = current.date_created
        if (current.date_reviewed is not None and
            current.date_reviewed > date_updated):
            date_updated = current.date_reviewed
        return (date_updated is not None and date_updated > timestamp)

    def validateTranslations(self, translations):
        """See `IPOTMsgSet`."""
        validate_translation(
            self.singular_text, self.plural_text, translations, self.flags)

    def _findPOTranslations(self, translations):
        """Find all POTranslation records for passed `translations`."""
        potranslations = {}
        # Set all POTranslations we can have (up to MAX_PLURAL_FORMS)
        for pluralform in xrange(TranslationConstants.MAX_PLURAL_FORMS):
            translation = translations.get(pluralform)
            if translation is not None:
                # Find or create a POTranslation for the specified text
                potranslations[pluralform] = (
                    POTranslation.getOrCreateTranslation(translation))
            else:
                potranslations[pluralform] = None
        return potranslations

    def findTranslationMessage(self, pofile, translations=None,
                               prefer_shared=False):
        """Find the best matching message in this `pofile`.

        The returned message matches exactly the given `translations`
        strings (except plural forms not supported by `pofile`, which
        are ignored in the comparison).

        :param translations: A dict mapping plural forms to translation
            strings.
        :param prefer_shared: Whether to prefer a shared match over a
            diverged one.
        """
        potranslations = self._findPOTranslations(translations)
        return self._findMatchingTranslationMessage(
            pofile, potranslations, prefer_shared=prefer_shared)

    def _findMatchingTranslationMessage(self, pofile, potranslations,
                                        prefer_shared=False):
        """Find the best matching message in this `pofile`.

        :param pofile: The `POFile` to look in.
        :param potranslations: a list of `POTranslation`s.  Forms that
            are not translated should have None instead.
        :param prefer_shared: Whether to prefer a shared match over a
            diverged one.
        """
        clauses = ['potmsgset = %s' % sqlvalues(self),
                   'language = %s' % sqlvalues(pofile.language),
                   '(potemplate IS NULL OR potemplate = %s)' % sqlvalues(
                                                        pofile.potemplate)]

        for pluralform in range(pofile.plural_forms):
            if potranslations[pluralform] is None:
                clauses.append('msgstr%s IS NULL' % sqlvalues(pluralform))
            else:
                clauses.append('msgstr%s=%s' % (
                    sqlvalues(pluralform, potranslations[pluralform])))

        remaining_plural_forms = range(
            pofile.plural_forms, TranslationConstants.MAX_PLURAL_FORMS)

        # Prefer either shared or diverged messages, depending on
        # arguments.
        if prefer_shared:
            order = ['potemplate NULLS FIRST']
        else:
            order = ['potemplate NULLS LAST']

        # Normally at most one message should match.  But if there is
        # more than one, prefer the one that adds the fewest extraneous
        # plural forms.
        order.extend([
            'msgstr%s NULLS FIRST' % quote(form)
            for form in remaining_plural_forms])
        matches = list(
            TranslationMessage.select(' AND '.join(clauses), orderBy=order))

        if len(matches) > 0:
            if len(matches) > 1:
                logging.info(
                    "Translation for POTMsgSet %s into %s "
                    "matches %s existing translations." % sqlvalues(
                        self, pofile.language.code, len(matches)))
            return matches[0]
        else:
            return None

    def submitSuggestion(self, pofile, submitter, new_translations,
                         from_import=False):
        """See `IPOTMsgSet`."""
        if self.is_translation_credit:
            # We don't support suggestions on credits messages.
            return None
        potranslations = self._findPOTranslations(new_translations)

        existing_message = self._findMatchingTranslationMessage(
            pofile, potranslations, prefer_shared=True)
        if existing_message is not None:
            return existing_message

        forms = dict(
            ('msgstr%d' % form, potranslation)
            for form, potranslation in potranslations.iteritems())

        if from_import:
            origin = RosettaTranslationOrigin.SCM
        else:
            origin = RosettaTranslationOrigin.ROSETTAWEB
            pofile.potemplate.awardKarma(
                submitter, 'translationsuggestionadded')

        return TranslationMessage(
            potmsgset=self, language=pofile.language,
            origin=origin, submitter=submitter,
            **forms)

    def _checkForConflict(self, current_message, lock_timestamp,
                          potranslations=None):
        """Check `message` for conflicting changes since `lock_timestamp`.

        Call this before changing this message's translations, to ensure
        that a read-modify-write operation on a message does not
        accidentally overwrite newer changes based on older information.

        One example of a read-modify-write operation is: user downloads
        translation file, translates a message, then re-uploads.
        Another is: user looks at a message in the web UI, decides that
        neither the current translation nor any of the suggestions are
        right, and clears the message.

        In these scenarios, it's possible for someone else to come along
        and change the message's translation between the time we provide
        the user with a view of the current state and the time we
        receive a change from the user.  We call this a conflict.

        Raises `TranslationConflict` if a conflict exists.

        :param currentmessage: The `TranslationMessage` that is current
            now.  This is where we'll see any conflicting changes
            reflected in the date_reviewed timestamp.
        :param lock_timestamp: The timestamp of the translation state
            that the change is based on.
        :param potranslations: `POTranslation`s dict for the new
            translation.  If these are given, and identical to those of
            `current_message`, there is no conflict.
        """
        if lock_timestamp is None:
            # We're not really being asked to check for conflicts.
            return
        if current_message is None:
            # There is no current message to conflict with.
            return
        try:
            self._maybeRaiseTranslationConflict(
                current_message, lock_timestamp)
        except TranslationConflict:
            if potranslations is None:
                # We don't know what translations are going to be set;
                # based on the timestamps this is a conflict.
                raise
            old_msgstrs = dictify_translations(current_message.all_msgstrs)
            new_msgstrs = dictify_translations(potranslations)
            if new_msgstrs != old_msgstrs:
                # Yup, there really is a difference.  This is a proper
                # conflict.
                raise
            else:
                # Two identical translations crossed.  Not a conflict.
                pass

    def _maybeRaiseTranslationConflict(self, message, lock_timestamp):
        """Checks if there is a translation conflict for the message.

        If a translation conflict is detected, TranslationConflict is raised.
        """
        if message.date_reviewed is not None:
            use_date = message.date_reviewed
        else:
            use_date = message.date_created
        if use_date >= lock_timestamp:
            raise TranslationConflict(
                'While you were reviewing these suggestions, somebody '
                'else changed the actual translation. This is not an '
                'error but you might want to re-review the strings '
                'concerned.')
        else:
            return

    def dismissAllSuggestions(self, pofile, reviewer, lock_timestamp):
        """See `IPOTMsgSet`."""
        assert lock_timestamp is not None, "lock_timestamp is required."

        template = pofile.potemplate
        language = pofile.language
        side = template.translation_side
        current = self.getCurrentTranslation(template, language, side)

        if current is None:
            # Create or activate an empty translation message.
            current = self.setCurrentTranslation(
                pofile, reviewer, {}, RosettaTranslationOrigin.ROSETTAWEB,
                lock_timestamp=lock_timestamp)
        else:
            # Check for translation conflicts and update review fields.
            self._maybeRaiseTranslationConflict(current, lock_timestamp)
        current.markReviewed(reviewer, lock_timestamp)
        assert self.getCurrentTranslation(template, language, side)

    def _nameMessageStatus(self, message, translation_side_traits):
        """Figure out the decision-matrix status of a message.

        This is used in navigating the decision matrix in
        `setCurrentTranslation`.
        """
        if message is None:
            return 'none'
        elif message.is_diverged:
            return 'diverged'
        elif translation_side_traits.other_side_traits.getFlag(message):
            return 'other_shared'
        else:
            return 'shared'

    def _makeTranslationMessage(self, pofile, submitter, translations, origin,
                                diverged=False):
        """Create a new `TranslationMessage`.

        The message will not be made current on either side (Ubuntu or
        upstream), but it can be diverged.  Only messages that are
        current should be diverged, but it's up to the caller to ensure
        the right state.
        """
        if diverged:
            potemplate = pofile.potemplate
        else:
            potemplate = None

        translation_args = dict(
            ('msgstr%d' % form, translation)
            for form, translation in translations.iteritems())

        return TranslationMessage(
            potmsgset=self,
            potemplate=potemplate,
            pofile=pofile,
            language=pofile.language,
            origin=origin,
            submitter=submitter,
            validation_status=TranslationValidationStatus.OK,
            **translation_args)

    def approveSuggestion(self, pofile, suggestion, reviewer,
                          share_with_other_side=False, lock_timestamp=None):
        """Approve a suggestion.

        :param pofile: The `POFile` that the suggestion is being approved for.
        :param suggestion: The `TranslationMessage` being approved.
        :param reviewer: The `Person` responsible for approving the
            suggestion.
        :param share_with_other_side: Policy selector: share this change with
            the other translation side if possible?
        :param lock_timestamp: Timestamp of the original translation state
            that this change is based on.
        """
        template = pofile.potemplate
        current = self.getCurrentTranslation(
            template, pofile.language, template.translation_side)
        if current == suggestion:
            # Message is already current.
            return

        translator = suggestion.submitter
        potranslations = dictify_translations(suggestion.all_msgstrs)
        activated_message = self._setTranslation(
            pofile, translator, suggestion.origin, potranslations,
            share_with_other_side=share_with_other_side,
            identical_message=suggestion, lock_timestamp=lock_timestamp)

        activated_message.markReviewed(reviewer)
        if reviewer != translator:
            template.awardKarma(translator, 'translationsuggestionapproved')
            template.awardKarma(reviewer, 'translationreview')

    def acceptFromImport(self, pofile, suggestion,
                       share_with_other_side=False, lock_timestamp=None):
        """Accept a suggestion coming from a translation import.

        When importing translations, these are first added as a suggestion
        and only after successful validation they are made current. This is
        slightly different to approving a suggestion because no reviewer is
        credited.

        :param pofile: The `POFile` that the suggestion is being approved for.
        :param suggestion: The `TranslationMessage` being approved.
        :param share_with_other_side: Policy selector: share this change with
            the other translation side if possible?
        :param lock_timestamp: Timestamp of the original translation state
            that this change is based on.
        """
        template = pofile.potemplate
        traits = getUtility(ITranslationSideTraitsSet).getTraits(
            template.translation_side)
        if traits.getFlag(suggestion):
            # Message is already current.
            return

        translator = suggestion.submitter
        potranslations = dictify_translations(suggestion.all_msgstrs)
        self._setTranslation(
            pofile, translator, suggestion.origin, potranslations,
            share_with_other_side=share_with_other_side,
            identical_message=suggestion, lock_timestamp=lock_timestamp)

    def acceptFromUpstreamImportOnPackage(self, pofile, suggestion,
                                        lock_timestamp=None):
        """Accept a suggestion coming from a translation import.

        This method allow to store translation as upstream translation
        even though there is no upstream template. It is similar to
        acceptFromImport but will make sure not to overwrite existing
        translations. Rather, it will mark the translation as being current
        in upstream.

        :param pofile: The `POFile` that the suggestion is being approved for.
        :param suggestion: The `TranslationMessage` being approved.
        :param lock_timestamp: Timestamp of the original translation state
            that this change is based on.
        """
        template = pofile.potemplate
        assert template.translation_side == TranslationSide.UBUNTU, (
            "Do not use this method for an upstream project.")

        if suggestion.is_current_ubuntu and suggestion.is_current_upstream:
            # Message is already current.
            return

        current = self.getCurrentTranslation(
            template, pofile.language, template.translation_side)
        other = self.getOtherTranslation(
            pofile.language, template.translation_side)
        if current is None or other is None or current == other:
            translator = suggestion.submitter
            potranslations = dictify_translations(suggestion.all_msgstrs)
            if other is not None:
                # Steal flag beforehand.
                other.is_current_upstream = False
            self._setTranslation(
                pofile, translator, suggestion.origin, potranslations,
                share_with_other_side=True,
                identical_message=suggestion,
                lock_timestamp=lock_timestamp)
        else:
            # Make it only current in upstream.
            if suggestion != other:
                other.is_current_upstream = False
                suggestion.is_current_upstream = True
                pofile.markChanged(translator=suggestion.submitter)

    def _cloneAndDiverge(self, original_message, pofile):
        """Create a diverged clone of a `TranslationMessage`.

        The message is not made current; the caller must do so in order
        to keep the message in a consistent state.
        """
        potranslations = self._findPOTranslations(
            dict(enumerate(original_message.translations)))
        message = self._makeTranslationMessage(
            pofile, original_message.submitter, potranslations,
            original_message.origin, diverged=True)
        return message

    def approveAsDiverged(self, pofile, suggestion, reviewer,
                          lock_timestamp=None):
        """Approve a suggestion to become a diverged translation."""
        template = pofile.potemplate
        traits = getUtility(ITranslationSideTraitsSet).getTraits(
            template.translation_side)

        diverged = suggestion.is_diverged
        used_here = traits.getFlag(suggestion)
        used_on_other_side = traits.other_side_traits.getFlag(suggestion)

        if used_here and suggestion.potemplate == template:
            # The suggestion is already current and diverged for the
            # right template.
            return suggestion

        incumbent = traits.getCurrentMessage(self, template, pofile.language)
        if incumbent is not None:
            # Ensure that the current message hasn't changed from the
            # state the reviewer inspected before making this change.
            self._checkForConflict(incumbent, lock_timestamp)

        if incumbent is not None and incumbent.is_diverged:
            # The incumbent is also diverged, so it's in the way of the
            # suggestion we're trying to diverge.  Disable it.
            traits.setFlag(incumbent, False)
            incumbent.markReviewed(reviewer)
            incumbent.shareIfPossible()
            pofile.markChanged()

        if used_here and not diverged and not used_on_other_side:
            # This message is already the shared current message.  If it
            # was previously masked by a diverged message, it no longer
            # is.  This is probably the behaviour the user would expect.
            return suggestion

        if used_here or used_on_other_side:
            # The suggestion is already current somewhere else.  Can't
            # reuse it as a diverged message in this template, so clone
            # it.
            message = self._cloneAndDiverge(suggestion, pofile)
        else:
            # No obstacles.  Diverge.
            message = suggestion
            message.potemplate = template

        traits.setFlag(message, True)
        message.markReviewed(reviewer)
        pofile.markChanged()
        return message

    def setCurrentTranslation(self, pofile, submitter, translations, origin,
                              share_with_other_side=False,
                              lock_timestamp=None):
        """See `IPOTMsgSet`."""
        potranslations = self._findPOTranslations(translations)
        identical_message = self._findMatchingTranslationMessage(
            pofile, potranslations, prefer_shared=False)
        return self._setTranslation(
            pofile, submitter, origin, potranslations,
            share_with_other_side=share_with_other_side,
            identical_message=identical_message,
            lock_timestamp=lock_timestamp)

    def _setTranslation(self, pofile, submitter, origin, potranslations,
                        identical_message=None, share_with_other_side=False,
                        lock_timestamp=None):
        """Set the current translation.

        https://dev.launchpad.net/Translations/Specs/setCurrentTranslation

        :param pofile: The `POFile` to set the translation in.
        :param submitter: The `Person` who produced this translation.
        :param origin: The translation's `RosettaTranslationOrigin`.
        :param potranslations: A dict mapping plural-form numbers to the
            respective `POTranslation`s for those forms.
        :param identical_message: The already existing message, if any,
            that's either shared or diverged for `pofile.potemplate`,
            whose translations are identical to the ones we're setting.
        :param share_with_other_side: Propagate this change to the other
            translation side if appropriate.
        :param lock_timestamp: The timestamp of the translation state
            that the change is based on.
        :return: The `TranslationMessage` that is current after
            completion.
        """
        twin = identical_message

        traits = getUtility(ITranslationSideTraitsSet).getTraits(
            pofile.potemplate.translation_side)

        # The current message on this translation side, if any.
        incumbent_message = traits.getCurrentMessage(
            self, pofile.potemplate, pofile.language)

        self._checkForConflict(
            incumbent_message, lock_timestamp, potranslations=potranslations)

        # Summary of the matrix:
        #  * If the incumbent message is diverged and we're setting a
        #    translation that's already shared: converge.
        #  * If the incumbent message is diverged and we're setting a
        #    translation that's not already shared: maintain divergence.
        #  * If the incumbent message is shared, replace it.
        #  * If there is no twin, simply create a new message (shared or
        #    diverged depending; see above).
        #  * If there is a shared twin, activate it (but also diverge if
        #    necessary; see above).
        #  * If there is a diverged twin, activate it (and converge it
        #    if appropriate; see above).
        #  * If there is a twin that's shared on the other side,

        decision_matrix = {
            'incumbent_none': {
                'twin_none': 'Z1*',
                'twin_shared': 'Z4*',
                'twin_diverged': 'Z7*',
                'twin_other_shared': 'Z4',
            },
            'incumbent_shared': {
                'twin_none': 'B1*',
                'twin_shared': 'B4*',
                'twin_diverged': 'B7*',
                'twin_other_shared': 'B4',
            },
            'incumbent_diverged': {
                'twin_none': 'A2',
                'twin_shared': 'A5',
                'twin_diverged': 'A4',
                'twin_other_shared': 'A6',
            },
            'incumbent_other_shared': {
                'twin_none': 'B1+',
                'twin_shared': 'B4+',
                'twin_diverged': 'B7+',
                'twin_other_shared': '',
            },
        }

        incumbent_state = "incumbent_%s" % self._nameMessageStatus(
            incumbent_message, traits)
        twin_state = "twin_%s" % self._nameMessageStatus(twin, traits)

        decisions = decision_matrix[incumbent_state][twin_state]
        assert re.match('[ABZ]?[124567]?[+*]?$', decisions), (
            "Bad decision string.")

        for character in decisions:
            if character == 'A':
                # Deactivate & converge.
                # There may be an identical shared message.
                traits.setFlag(incumbent_message, False)
                incumbent_message.shareIfPossible()
            elif character == 'B':
                # Deactivate.
                traits.setFlag(incumbent_message, False)
            elif character == 'Z':
                # There is no incumbent message, so do nothing to it.
                assert incumbent_message is None, (
                    "Incorrect Z in decision matrix.")
            elif character == '1':
                # Create & activate.
                message = self._makeTranslationMessage(
                    pofile, submitter, potranslations, origin)
            elif character == '2':
                # Create, diverge, activate.
                message = self._makeTranslationMessage(
                    pofile, submitter, potranslations, origin, diverged=True)
            elif character == '4':
                # Activate.
                message = twin
            elif character == '5':
                # If other is a suggestion, diverge and activate.
                # (If not, it's already active and has been unmasked by
                # our deactivating the incumbent).
                message = twin
                if not traits.getFlag(twin):
                    assert not traits.other_side_traits.getFlag(twin), (
                        "Trying to diverge a message that is current on the "
                        "other side.")
                    message.potemplate = pofile.potemplate
            elif character == '6':
                # If other is not active, fork a diverged message.
                if traits.getFlag(twin):
                    message = twin
                else:
                    # The twin is used on the other side, so we can't
                    # just reuse it for our diverged message.  Create a
                    # new one.
                    message = self._makeTranslationMessage(
                        pofile, submitter, potranslations, origin,
                        diverged=True)
            elif character == '7':
                # Converge & activate.
                message = twin
                message.shareIfPossible()
            elif character == '*':
                if share_with_other_side:
                    other_incumbent = (
                        traits.other_side_traits.getCurrentMessage(
                            self, pofile.potemplate, pofile.language))
                    if other_incumbent is None:
                        # Untranslated on the other side; use the new
                        # translation there as well.
                        traits.other_side_traits.setFlag(message, True)
                    elif (incumbent_message is None and
                          traits.side == TranslationSide.UPSTREAM):
                        # Translating upstream, and the message was
                        # previously untranslated.  Any translation in
                        # Ubuntu is probably different, but only because
                        # no upstream translation was available.  In
                        # this special case the upstream translation
                        # overrides the Ubuntu translation.
                        traits.other_side_traits.setFlag(
                            other_incumbent, False)
                        Store.of(message).add_flush_order(
                            other_incumbent, message)
                        traits.other_side_traits.setFlag(message, True)
            elif character == '+':
                if share_with_other_side:
                    traits.other_side_traits.setFlag(incumbent_message, False)
                    traits.other_side_traits.setFlag(message, True)
            else:
                raise AssertionError(
                    "Bad character in decision string: %s" % character)

        if decisions == '':
            message = twin

        if not traits.getFlag(message):
            if incumbent_message is not None and message != incumbent_message:
                Store.of(message).add_flush_order(incumbent_message, message)
            traits.setFlag(message, True)
            pofile.markChanged(translator=submitter)

        return message

    def resetCurrentTranslation(self, pofile, lock_timestamp=None,
                                share_with_other_side=False):
        """See `IPOTMsgSet`."""
        traits = getUtility(ITranslationSideTraitsSet).getTraits(
            pofile.potemplate.translation_side)
        current_message = traits.getCurrentMessage(
            self, pofile.potemplate, pofile.language)

        if current_message is None:
            # Nothing to do here.
            return

        self._checkForConflict(current_message, lock_timestamp)
        traits.setFlag(current_message, False)
        if share_with_other_side:
            traits.other_side_traits.setFlag(current_message, False)
        current_message.shareIfPossible()
        pofile.markChanged()

    def clearCurrentTranslation(self, pofile, submitter, origin,
                                share_with_other_side=False,
                                lock_timestamp=None):
        """See `IPOTMsgSet`."""
        message = self.setCurrentTranslation(
            pofile, submitter, {}, origin,
            share_with_other_side=share_with_other_side,
            lock_timestamp=lock_timestamp)
        message.markReviewed(submitter)

    @property
    def hide_translations_from_anonymous(self):
        """See `IPOTMsgSet`."""
        # msgid_singular.msgid is pre-joined everywhere where
        # hide_translations_from_anonymous is used
        return self.is_translation_credit

    @property
    def is_translation_credit(self):
        """See `IPOTMsgSet`."""
        credit_type = self.translation_credits_type
        return credit_type != TranslationCreditsType.NOT_CREDITS

    @property
    def translation_credits_type(self):
        """See `IPOTMsgSet`."""
        if self.msgid_singular.msgid not in credits_message_info:
            return TranslationCreditsType.NOT_CREDITS

        expected_context, credits_type = (
            credits_message_info[self.msgid_singular.msgid])
        if expected_context is None or (self.context == expected_context):
            return credits_type
        return TranslationCreditsType.NOT_CREDITS

    def makeHTMLID(self, suffix=None):
        """See `IPOTMsgSet`."""
        elements = ['msgset', str(self.id)]
        if suffix is not None:
            elements.append(suffix)
        return '_'.join(elements)

    def updatePluralForm(self, plural_form_text):
        """See `IPOTMsgSet`."""
        if plural_form_text is None:
            self.msgid_plural = None
            return
        else:
            # Store the given plural form.
            try:
                pomsgid = POMsgID.byMsgid(plural_form_text)
            except SQLObjectNotFound:
                pomsgid = POMsgID(msgid=plural_form_text)
            self.msgid_plural = pomsgid

    def setTranslationCreditsToTranslated(self, pofile):
        """See `IPOTMsgSet`."""
        if not self.is_translation_credit:
            return

        shared_upstream_translation = self.getSharedTranslation(
            pofile.language, TranslationSide.UPSTREAM)

        if shared_upstream_translation is not None:
            return

        # The credits message has a fixed "translator."
        translator = getUtility(ILaunchpadCelebrities).rosetta_experts

        generated_translation = self.setCurrentTranslation(
            pofile, translator, {0: credits_message_str},
            RosettaTranslationOrigin.LAUNCHPAD_GENERATED,
            share_with_other_side=True)
        generated_translation.shareIfPossible()

    def setSequence(self, potemplate, sequence):
        """See `IPOTMsgSet`."""
        translation_template_item = TranslationTemplateItem.selectOneBy(
            potmsgset=self, potemplate=potemplate)
        if translation_template_item is not None:
            # Update the sequence for the translation template item.
            translation_template_item.sequence = sequence
            return translation_template_item
        elif sequence >= 0:
            # Introduce this new entry into the TranslationTemplateItem for
            # later usage.
            conflicts, uses_english_msgids = (
                self._conflictsExistingSourceFileFormats(
                    potemplate.source_file_format))
            if conflicts:
                # We are not allowing POTMsgSets to participate
                # in incompatible POTemplates.  Call-sites should
                # not try to introduce them, or they'll get an exception.
                raise POTMsgSetInIncompatibleTemplatesError(
                    "Attempt to add a POTMsgSet into a POTemplate which "
                    "has a conflicting value for uses_english_msgids.")

            return TranslationTemplateItem(
                potemplate=potemplate,
                sequence=sequence,
                potmsgset=self)
        else:
            # There is no entry for this potmsgset in TranslationTemplateItem
            # table, neither we need to create one, given that the sequence is
            # less than zero.
            return None

    def getSequence(self, potemplate):
        """See `IPOTMsgSet`."""
        translation_template_item = TranslationTemplateItem.selectOneBy(
            potmsgset=self, potemplate=potemplate)
        if translation_template_item is not None:
            return translation_template_item.sequence
        else:
            return 0

    def getAllTranslationMessages(self):
        """See `IPOTMsgSet`."""
        return Store.of(self).find(
            TranslationMessage, TranslationMessage.potmsgset == self)

    def getAllTranslationTemplateItems(self):
        """See `IPOTMsgSet`."""
        return TranslationTemplateItem.selectBy(
            potmsgset=self, orderBy=['id'])
