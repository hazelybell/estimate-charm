# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from lazr.enum import (
    EnumeratedType,
    Item,
    )
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Int,
    List,
    Object,
    Text,
    )

from lp import _
from lp.translations.interfaces.pomsgid import IPOMsgID


__metaclass__ = type

__all__ = [
    'IPOTMsgSet',
    'POTMsgSetInIncompatibleTemplatesError',
    'TranslationCreditsType',
    ]


class TranslationCreditsType(EnumeratedType):
    """Identify a POTMsgSet as translation credits."""

    NOT_CREDITS = Item("""
        Not a translation credits message

        This is a standard msgid and not translation credits.
        """)

    GNOME = Item("""
        Gnome credits message

        How they do them in Gnome.
        """)

    KDE_EMAILS = Item("""
        KDE emails credits message

        How they do them in KDE for translator emails.
        """)

    KDE_NAMES = Item("""
        KDE names credits message

        How they do them in KDE for translator names.
        """)


class POTMsgSetInIncompatibleTemplatesError(Exception):
    """Raised when a POTMsgSet appears in multiple incompatible templates.

    Two PO templates are incompatible if one uses English strings for msgids,
    and another doesn't (i.e. it uses English translation instead).
    """


class IPOTMsgSet(Interface):
    """A collection of message IDs."""

    id = Int(
        title=_("The identifier of this POTMsgSet."),
        readonly=True, required=True)

    context = Text(
        title=u"String used to disambiguate messages with identical msgids.")

    msgid_singular = Object(
        title=_("The singular msgid for this message."),
        description=_("""
            A message ID along with the context uniquely identifies the
            template message.
            """), readonly=True, required=True, schema=IPOMsgID)

    msgid_plural = Object(
        title=u"The plural msgid for this message.",
        description=(u"Provides a plural msgid for the message. "
                     u"If it's not a plural form message, this value"
                     u"should be None."),
        required=True,
        readonly=True,
        schema=IPOMsgID)

    commenttext = Attribute("The manual comments this set has.")

    filereferences = Attribute("The files where this set appears.")

    sourcecomment = Attribute("The source code comments this set has.")

    flagscomment = Attribute("The flags this set has.")

    flags = Attribute("List of flags that apply to this message.")

    singular_text = Text(
        title=_("The singular text for this message."), readonly=True)

    plural_text = Text(
        title=_("The plural text for this message or None."), readonly=True)

    uses_english_msgids = Bool(
        title=_("Uses English strings as msgids"), readonly=True,
        description=_("""
            Some formats, such as Mozilla's XPI, use symbolic msgids where
            gettext uses the original English strings to identify messages.
            """))

    credits_message_ids = List(
        title=_("List of possible msgids for translation credits"),
        readonly=True,
        description=_("""
            This class attribute is intended to be used to construct database
            queries that search for credits messages.
            """))

    def clone():
        """Return a new copy of this POTMsgSet."""

    def getCurrentTranslationMessageOrDummy(pofile):
        """Return the current `TranslationMessage`, or a dummy.

        :param pofile: PO template you want a translation message for.
        :return: The current translation for `self` in `pofile`, if
            there is one.  Otherwise, a `DummyTranslationMessage` for
            `self` in `pofile`.
        """

    def getOtherTranslation(language, side):
        """Returns the TranslationMessage that is current on the other side.

        :param language: The language in which to find the message.
        :param side: The side from which this message is seen.
        """

    def getSharedTranslation(language, side):
        """Returns a shared TranslationMessage.

        :param language: The language in which to find the message.
        :param side: The side from which this message is seen.
        """

    def getLocalTranslationMessages(potemplate, language,
                                    include_dismissed=False,
                                    include_unreviewed=True):
        """Return all local unused translation messages for the POTMsgSet.

        Unused are those which are not current or imported, and local are
        those which are directly attached to this POTMsgSet.

        :param language: language we want translations for.
        :param include_dismissed: Also return those translation messages
          that have a creation date older than the review date of the current
          message (== have been dismissed).
        :param include_unreviewed: Also return those translation messages
          that have a creation date newer than the review date of the current
          message (== that are unreviewed). This is the default.
        """

    def getExternallyUsedTranslationMessages(language):
        """Find externally used translations for the same message.

        This is used to find suggestions for translating this
        `POTMsgSet` that are actually used (i.e. current or imported) in
        other templates.

        The suggestions are read-only; they come from the slave store.

        :param language: language we want translations for.
        """

    def getExternallySuggestedTranslationMessages(language):
        """Find externally suggested translations for the same message.

        This is used to find suggestions for translating this
        `POTMsgSet` that were entered in another context, but for the
        same English text, and are not in actual use.

        The suggestions are read-only; they come from the slave store.

        :param language: language we want translations for.
        """

    def getExternallySuggestedOrUsedTranslationMessages(
        suggested_languages=(), used_languages=()):
        """Find externally suggested/used translations for the same message.

        This returns a mapping: language -> namedtuple (suggested, used)
        containing the results of
        self.getExternallySuggestedTranslationMessages and
        self.getExternallyUsedTranslationMessages for each language.

        :param suggested_languages: languages we want suggestions for.
        :param used_languages: languges we want used messages for.
        """

    def hasTranslationChangedInLaunchpad(potemplate, language):
        """Whether an imported translation differs from the current one.

        :param potemplate: potemplate we are asking about.
        :param language: language for which translations we are asking about.

        There has to be an imported translation: if there isn't, this is
        not a 'changed' translation, just a 'new' translation in Launchpad.
        """

    def isTranslationNewerThan(pofile, timestamp):
        """Whether a current translation is newer than the `timestamp`.

        :param pofile: translation file for which translations we are asking
            about.
        :param timestamp: a timestamp we are comparing to.

        Returns True if there is a current and newer translation, and False
        otherwise.
        """

    def validateTranslations(translations):
        """Validate `translations` against gettext.

        :param translations: A dict mapping plural forms to translated
            strings.
        :raises GettextValidationError: if there is a problem with the
            translations.
        """

    def submitSuggestion(pofile, submitter, new_translations,
                         from_import=False):
        """Submit a suggested translation for this message.

        If an identical message is already present, it will be returned
        (and it is not changed).  Otherwise, a new one is created and
        returned.  Suggestions for translation credits messages are
        ignored, and None is returned in that case.
        Setting from_import to true will prevent karma assignment and
        set the origin of the created message to SCM instead of
        ROSETTAWEB.
        """

    def dismissAllSuggestions(pofile, reviewer, lock_timestamp):
        """Dismiss all suggestions for the given pofile.

        :param pofile: a `POFile` to dismiss suggestions from.
        :param reviewer: the person that is doing the dismissal.
        :param lock_timestamp: the timestamp when we checked the values we
            want to update.

        If a translation conflict is detected, TranslationConflict is raised.
        """

    def getCurrentTranslation(potemplate, language, side):
        """Get a current translation message.

        :param potemplate: An `IPOTemplate` to look up a translation for.
            If it's None, ignore diverged translations.
        :param language: translation should be to this `ILanguage`.
        :param side: translation side to look at.  (A `TranslationSide` value)
        """

    def setCurrentTranslation(pofile, submitter, translations, origin,
                              share_with_other_side=False,
                              lock_timestamp=None):
        """Set the message's translation in Ubuntu, or upstream, or both.

        :param pofile: `POFile` you're setting translations in.  Other
            `POFiles` that share translations with this one may also be
            affected.
        :param submitter: `Person` who is setting these translations.
        :param translations: a dict mapping plural-form numbers to the
            translated string for that form.
        :param origin: A `RosettaTranslationOrigin`.
        :param share_with_other_side: When sharing this translation,
            share it with the other `TranslationSide` as well.
        :param lock_timestamp: Timestamp of the original translation state
            that this change is based on.
        """

    def resetCurrentTranslation(pofile, lock_timestamp=None,
                                share_with_other_side=False):
        """Turn the current translation back into a suggestion.

        This deactivates the message's current translation.  The message
        becomes untranslated or, if it was diverged, reverts to its
        shared translation.

        The previously current translation becomes visible as a new
        suggestion again, as do all suggestions that came after it.

        :param pofile: The `POFile` to make the change in.
        :param lock_timestamp: Timestamp of the original translation state
            that this change is based on.
        :param share_with_other_side: Make the same change on the other
            translation side.
        """

    def clearCurrentTranslation(pofile, submitter, origin,
                                share_with_other_side=False,
                                lock_timestamp=None):
        """Set the current message in `pofile` to be untranslated.

        If the current message is shared, this will also clear it in
        other translations that share the same message.

        :param pofile: The translation file that should have its current
            translation for this `POTMsgSet` cleared.  If the message is
            shared, this may not be the only translation file that will
            be affected.
        :param submitter: The person responsible for clearing the message.
        :param origin: `RosettaTranslationOrigin`.
        :param share_with_other_side: If the current message is also
            current on the other side (i.e. the Ubuntu side if working
            upstream, or vice versa) then should it be cleared there as
            well?
        :param lock_timestamp: Timestamp of the original translation state
            that this change is based on.
        """

    hide_translations_from_anonymous = Attribute(
        """Whether the translations for this message should be hidden.

        Messages that are likely to contain email addresses
        are shown only to logged-in users, and not to anonymous users.
        """)

    is_translation_credit = Attribute(
        """Whether this is a message set for crediting translators.""")

    translation_credits_type = Choice(
        title=u"The type of translation credit of this message.",
        required=True,
        vocabulary=TranslationCreditsType)

    def makeHTMLID(suffix=None):
        """Unique name for this `POTMsgSet` for use in HTML element ids.

        The name is an underscore-separated sequence of:
         * the string 'msgset'
         * unpadded, numerical `id`
         * optional caller-supplied suffix.

        :param suffix: an optional suffix to be appended.  Must be suitable
            for use in HTML element ids.
        """

    def updatePluralForm(plural_form_text):
        """Update plural form text for this message.

        :param plural_form_text: Unicode string representing the plural form
            we want to store or None to unset current plural form.
        """

    def getSequence(potemplate):
        """Return the sequence number for this potmsgset in potemplate.

        :param potemplate: `IPOTemplate` where the sequence number applies.
        """

    def setSequence(potemplate, sequence):
        """Set the sequence number for this potmsgset in potemplate.

        :param potemplate: `IPOTemplate` where the sequence number applies.
        :param sequence: The sequence number of this `IPOTMsgSet` in the given
            `IPOTemplate`.
        """

    def setTranslationCreditsToTranslated(pofile):
        """Set the current translation for this translation credits message.

        Sets a fixed dummy string as the current translation, if this is a
        translation credits message, so that these get counted as
        'translated', too.
        Credits messages that already have a translation, imported messages
        and normal messages are left untouched.
        :param pofile: the POFile to set this translation in.
        """

    def getAllTranslationMessages():
        """Retrieve all `TranslationMessage`s for this `POTMsgSet`."""

    def getAllTranslationTemplateItems():
        """Retrieve all `TranslationTemplateItem`s for this `POTMsgSet`."""
