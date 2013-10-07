# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""View classes for ITranslationMessage interface."""

__metaclass__ = type

__all__ = [
    'BaseTranslationView',
    'contains_translations',
    'convert_translationmessage_to_submission',
    'CurrentTranslationMessageAppMenus',
    'CurrentTranslationMessageFacets',
    'CurrentTranslationMessageIndexView',
    'CurrentTranslationMessagePageView',
    'CurrentTranslationMessageView',
    'CurrentTranslationMessageZoomedView',
    'revert_unselected_translations',
    'TranslationMessageSuggestions',
    ]

import cgi
import datetime
import operator
import re
import urllib

import pytz
from z3c.ptcompat import ViewPageTemplateFile
from zope import datetime as zope_datetime
from zope.component import getUtility
from zope.formlib.interfaces import IInputWidget
from zope.formlib.utility import setUpWidgets
from zope.formlib.widget import CustomWidgetFactory
from zope.formlib.widgets import DropdownWidget
from zope.interface import implements
from zope.schema.vocabulary import getVocabularyRegistry

from lp.app.errors import UnexpectedFormData
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    ApplicationMenu,
    canonical_url,
    enabled_with_permission,
    LaunchpadView,
    Link,
    urlparse,
    )
from lp.services.webapp.batching import BatchNavigator
from lp.services.webapp.escaping import structured
from lp.services.webapp.interfaces import ILaunchBag
from lp.services.webapp.publisher import RedirectionView
from lp.translations.browser.browser_helpers import (
    contract_rosetta_escapes,
    convert_newlines_to_web_form,
    count_lines,
    text_to_html,
    )
from lp.translations.browser.potemplate import POTemplateFacets
from lp.translations.interfaces.pofile import IPOFileAlternativeLanguage
from lp.translations.interfaces.side import ITranslationSideTraitsSet
from lp.translations.interfaces.translationmessage import (
    ITranslationMessage,
    ITranslationMessageSet,
    ITranslationMessageSuggestions,
    RosettaTranslationOrigin,
    TranslationConflict,
    )
from lp.translations.interfaces.translations import TranslationConstants
from lp.translations.interfaces.translationsperson import ITranslationsPerson
from lp.translations.model import pofilestatsjob
from lp.translations.utilities.sanitize import (
    sanitize_translations_from_webui,
    )
from lp.translations.utilities.validate import GettextValidationError


def revert_unselected_translations(translations, current_message,
                                   plural_indices_to_store):
    """Revert translations that the user entered but did not select.

    :param translations: a dict mapping plural forms to their respective
        translation strings.
    :param current_message: the current `TranslationMessage`.  Its
        translations are substituted for corresponding ones that the
        user entered without selecting their radio buttons.
    :param plural_indices_to_store: a sequence of plural form numbers
        that the user did select new translations for.
    :return: a dict similar to `translations`, but with any translations
        that are not in `plural_indices_to_store` reset to what they
        were in `current_message` (if any).
    """
    if current_message is None:
        original_translations = {}
    else:
        original_translations = dict(enumerate(current_message.translations))

    output = {}
    for plural_form, translation in translations.iteritems():
        if plural_form in plural_indices_to_store:
            output[plural_form] = translation
        elif original_translations.get(plural_form) is None:
            output[plural_form] = u''
        else:
            output[plural_form] = original_translations[plural_form]

    return output


def contains_translations(translations):
    """Does `translations` contain any nonempty translations?

    :param translations: a dict mapping plural forms to their respective
        translation strings.
    """
    for text in translations.itervalues():
        if text is not None and len(text) != 0:
            return True
    return False


class POTMsgSetBatchNavigator(BatchNavigator):

    def __init__(self, results, request, start=0, size=1):
        """Constructs a BatchNavigator instance.

        results is an iterable of results. request is the web request
        being processed. size is a default batch size which the callsite
        can choose to provide.

        Why a custom BatchNavigator is required is a great mystery and
        should be documented here.
        """
        schema, netloc, path, parameters, query, fragment = (
            urlparse(str(request.URL)))
        # For safety, delete the start and batch variables, if they
        # appear in the URL. The situation in which 'start' appears
        # today is when the alternative language form is posted back and
        # includes it.
        if 'start' in request:
            del request.form['start']
        if 'batch' in request.form:
            del request.form['batch']
        # Note: the BatchNavigator has now been updated so that it
        # gets the parameters out of the request.query_string_params
        # dict by default. Therefore, we'll remove the 'start' option
        # from request.query_string_params as well.
        if 'start' in request.query_string_params:
            del request.query_string_params['start']
        if 'batch' in request.query_string_params:
            del request.query_string_params['batch']

        # 'path' will be like: 'POTURL/LANGCODE/POTSEQUENCE/+translate' and
        # we are interested on the POTSEQUENCE.
        self.start_path, pot_sequence, self.page = path.rsplit('/', 2)
        try:
            # The URLs we use to navigate thru POTMsgSet objects start with 1,
            # while the batching machinery starts with 0, that's why we need
            # to remove '1'.
            start_value = int(pot_sequence) - 1
        except ValueError:
            start_value = start

        # This batch navigator class only supports batching of 1 element.
        size = 1

        BatchNavigator.__init__(self, results, request, start_value, size)

    def generateBatchURL(self, batch, backwards=False):
        """Return a custom batch URL for `ITranslationMessage`'s views."""
        url = ""
        if batch is None:
            return url

        assert batch.size == 1, 'The batch size must be 1.'

        sequence = batch.startNumber()
        url = '/'.join([self.start_path, str(sequence), self.page])
        # getCleanQueryString ensures we get rid of any bogus 'start' or
        # 'batch' form variables we may have received via the URL.
        qs = self.getCleanQueryString()
        if qs:
            # There are arguments that we should preserve.
            url = '%s?%s' % (url, qs)
        return url


class CustomDropdownWidget(DropdownWidget):

    def _div(self, cssClass, contents, **kw):
        """Render the select widget without the div tag."""
        return contents


class CurrentTranslationMessageFacets(POTemplateFacets):
    usedfor = ITranslationMessage

    def __init__(self, context):
        POTemplateFacets.__init__(self, context.browser_pofile.potemplate)


class CurrentTranslationMessageAppMenus(ApplicationMenu):
    usedfor = ITranslationMessage
    facet = 'translations'
    links = ['overview', 'translate', 'upload', 'download']

    def overview(self):
        text = 'Overview'
        return Link('../', text)

    def translate(self):
        text = 'Translate many'
        return Link('../+translate', text, icon='languages')

    @enabled_with_permission('launchpad.Edit')
    def upload(self):
        text = 'Upload a file'
        return Link('../+upload', text, icon='edit')

    def download(self):
        text = 'Download'
        return Link('../+export', text, icon='download')


class CurrentTranslationMessageIndexView(RedirectionView):
    """A view to forward to the translation form."""

    def __init__(self, context, request):
        target = canonical_url(context, view_name='+translate')
        super(CurrentTranslationMessageIndexView, self).__init__(
            target, request)


def _getSuggestionFromFormId(form_id):
    """Return the suggestion associated with the given form element ID.

    The ID is in the format generated by `POSubmission.makeHTMLID`.
    """
    expr_match = re.search(
        'msgset_(\d+)_(\S+)_suggestion_(\d+)_(\d+)', form_id)
    if expr_match is None:
        raise UnexpectedFormData(
            'The given form ID (%s) is not valid' % form_id)

    # Extract the suggestion ID.
    suggestion_id = int(expr_match.group(3))
    plural_form = int(expr_match.group(4))
    translationmessage = getUtility(ITranslationMessageSet).getByID(
        suggestion_id)
    return translationmessage.translations[plural_form]


class BaseTranslationView(LaunchpadView):
    """Base class that implements a framework for modifying translations.

    This class provides a basis for building a batched translation page.
    It relies on one or more subviews being used to actually display the
    translations and form elements. It processes the form submitted and
    constructs data which can be then fed back into the subviews.

    The subviews must be (or behave like) CurrentTranslationMessageViews.

    Child classes must define:
        - self.pofile
        - _buildBatchNavigator()
        - _initializeTranslationMessageViews()
        - _submitTranslations()
    """

    pofile = None

    @property
    def label(self):
        """The label will be used as the main page heading."""
        if self.form_is_writeable:
            form_label = 'Translating into %s'
        else:
            form_label = 'Browsing %s translation'
        return form_label % self.context.language.englishname

    def initialize(self):
        assert self.pofile, "Child class must define self.pofile"

        self.has_plural_form_information = (
            self.pofile.hasPluralFormInformation())

        # These two dictionaries hold translation data parsed from the
        # form submission. They exist mainly because of the need to
        # redisplay posted translations when they contain errors; if not
        # _submitTranslations could take care of parsing and saving
        # translations without the need to store them in instance
        # variables. To understand more about how they work, see
        # _extractFormPostedTranslations, _prepareView and
        # _storeTranslations.
        self.form_posted_translations = {}
        self.form_posted_translations_has_store_flag = {}
        self.form_posted_needsreview = {}
        self.form_posted_diverge = {}
        self.form_posted_dismiss_suggestions = {}

        if not self.has_plural_form_information:
            # This POFile needs administrator setup.
            self.request.response.addErrorNotification(
                structured("""
            <p>
            Launchpad can&#8217;t handle the plural items in this file,
            because it doesn&#8217;t yet know how plural forms work for %s.
            </p>
            <p>
            If you have this information, please visit the
            <a href="https://answers.launchpad.net/rosetta/">Answers</a>
            application to see whether anyone has submitted it yet.  If not,
            please file the information there as a question.  The preferred
            format for such questions is described in the
            <a href="https://help.launchpad.net/FAQ/Translations">Frequently
            Asked Questions list</a>.
            </p>
            <p>
            This only needs to be done once per language. Thanks for helping
            Launchpad Translations.
            </p>
            """, self.pofile.language.englishname))
            return

        self._initializeAltLanguage()

        method = self.request.method
        if method == 'POST':
            self.lock_timestamp = self._extractLockTimestamp()
            self._checkSubmitConditions()
        else:
            # It's not a POST, so we should generate lock_timestamp.
            UTC = pytz.timezone('UTC')
            self.lock_timestamp = datetime.datetime.now(UTC)

        # The batch navigator needs to be initialized early, before
        # _submitTranslations is called; the reason for this is that
        # _submitTranslations, in the case of no errors, redirects to
        # the next batch page.
        self.batchnav = self._buildBatchNavigator()
        # These two variables are stored for the sole purpose of being
        # output in hidden inputs that preserve the current navigation
        # when submitting forms.
        self.start = self.batchnav.start
        self.size = self.batchnav.currentBatch().size

        if method == 'POST' and 'submit_translations' in self.request.form:
            if self._submitTranslations():
                # If no errors occurred, adios. Otherwise, we need to set up
                # the subviews for error display and correction.
                return

        # Slave view initialization depends on _submitTranslations being
        # called, because the form data needs to be passed in to it --
        # again, because of error handling.
        self._initializeTranslationMessageViews()

    def _extractLockTimestamp(self):
        """Extract the lock timestamp from the request.

        The lock_timestamp is used to detect conflicting concurrent
        translation updates: if the translation that is being changed
        has been set after the current form was generated, the user
        chose a translation based on outdated information.  In that
        case there is a conflict.
        """
        try:
            return zope_datetime.parseDatetimetz(
                self.request.form.get('lock_timestamp', u''))
        except zope_datetime.DateTimeError:
            # invalid format. Either we don't have the timestamp in the
            # submitted form or it has the wrong format.
            return None

    def _checkSubmitConditions(self):
        """Verify that this submission is possible and valid.

        :raises: `UnexpectedFormData` if conditions are not met.  In
            principle the user should not have been given the option to
            submit the current request.
        """
        if self.user is None:
            raise UnexpectedFormData("You are not logged in.")

        # Users who have declined the licensing agreement can't post
        # translations.  We don't stop users who haven't made a decision
        # yet at this point; they may be project owners making
        # corrections.
        translations_person = ITranslationsPerson(self.user)
        relicensing = translations_person.translations_relicensing_agreement
        if relicensing is not None and not relicensing:
            raise UnexpectedFormData(
                "You can't post translations since you have not agreed to "
                "our translations licensing terms.")

        if self.lock_timestamp is None:
            raise UnexpectedFormData(
                "Your form submission did not contain the lock_timestamp "
                "that tells Launchpad when the submitted form was generated.")

    @cachedproperty
    def share_with_other_side(self):
        """Should these translations be shared with the other side?"""
        template = self.pofile.potemplate
        language = self.pofile.language
        policy = template.getTranslationPolicy()
        return policy.sharesTranslationsWithOtherSide(
            self.user, language, sourcepackage=template.sourcepackage)

    #
    # API Hooks
    #

    def _buildBatchNavigator(self):
        """Construct a BatchNavigator of POTMsgSets and return it."""
        raise NotImplementedError

    def _initializeTranslationMessageViews(self):
        """Construct subviews as necessary."""
        raise NotImplementedError

    def _submitTranslations(self):
        """Handle translations submitted via a form.

        Return True if processing went fine; return False if errors
        occurred.

        Implementing this method is complicated. It needs to find out
        what TranslationMessage were updated in the form post, call
        _receiveTranslations() for each of those, check for errors that
        may have occurred during that (displaying them using
        addErrorNotification), and otherwise call _redirectToNextPage if
        everything went fine.
        """
        raise NotImplementedError

    #
    # Helper methods that should be used for TranslationMessageView.__init__()
    # and _submitTranslations().
    #

    def _receiveTranslations(self, potmsgset):
        """Process and store submitted translations for `potmsgset`.

        :return: An error string in case of failure, or None otherwise.
        """
        try:
            self._storeTranslations(potmsgset)
        except GettextValidationError as e:
            return unicode(e)
        except TranslationConflict:
            # The translations are demoted to suggestions, but they may
            # still affect the "messages with new suggestions" filter.
            self._observeTranslationUpdate(potmsgset)
            return """
                This translation has changed since you last saw it.  To avoid
                accidentally reverting work done by others, we added your
                translations as suggestions.  Please review the current
                values.
                """
        else:
            self._observeTranslationUpdate(potmsgset)
            return None

    def _storeTranslations(self, potmsgset):
        """Store the translation submitted for a POTMsgSet.

        :raises GettextValidationError: if the submitted translation
            fails gettext validation.  The translation is not stored.
        :raises TranslationConflict: if the current translations have
            changed since the translator/reviewer last saw them.  The
            submitted translations are stored as suggestions.
        """
        self._extractFormPostedTranslations(potmsgset)

        if self.form_posted_dismiss_suggestions.get(potmsgset, False):
            potmsgset.dismissAllSuggestions(
                self.pofile, self.user, self.lock_timestamp)
            return

        translations = self.form_posted_translations.get(potmsgset, {})
        if not translations:
            # A post with no content -- not an error, but nothing to be
            # done.
            return

        template = self.pofile.potemplate
        language = self.pofile.language

        current_message = potmsgset.getCurrentTranslation(
            template, language, template.translation_side)

        translations = revert_unselected_translations(
            translations, current_message,
            self.form_posted_translations_has_store_flag.get(potmsgset, []))

        translations = sanitize_translations_from_webui(
            potmsgset.singular_text, translations, self.pofile.plural_forms)

        has_translations = contains_translations(translations)
        if current_message is None and not has_translations:
            # There is no current translation yet, neither we get any
            # translation submitted, so we don't need to store anything.
            return

        force_suggestion = self.form_posted_needsreview.get(potmsgset, False)
        force_diverge = self.form_posted_diverge.get(potmsgset, False)

        potmsgset.validateTranslations(translations)

        is_suggestion = (
            force_suggestion or not self.user_is_official_translator)
        if has_translations or not is_suggestion:
            message = potmsgset.submitSuggestion(
                self.pofile, self.user, translations)

        if self.user_is_official_translator:
            if force_suggestion:
                # The translator has requested that this translation
                # be reviewed.  That means we clear the current
                # translation, demoting the existing message to a
                # suggestion.
                if not has_translations:
                    # Forcing a suggestion has a different meaning
                    # for an empty translation: "someone should review
                    # the _existing_ translation."  Which also means
                    # that the existing translation is demoted to a
                    # suggestion.
                    potmsgset.resetCurrentTranslation(
                        self.pofile, lock_timestamp=self.lock_timestamp,
                        share_with_other_side=self.share_with_other_side)
            else:
                self._approveTranslation(
                    message, force_diverge=force_diverge)

    def _approveTranslation(self, message, force_diverge=False):
        """Approve `message`."""
        if force_diverge:
            message.approveAsDiverged(
                self.pofile, self.user, lock_timestamp=self.lock_timestamp)
        else:
            message.approve(
                self.pofile, self.user,
                share_with_other_side=self.share_with_other_side,
                lock_timestamp=self.lock_timestamp)

    def _areSuggestionsEmpty(self, suggestions):
        """Return true if all suggestions are empty strings or None."""
        for index in suggestions:
            if (suggestions[index] is not None and suggestions[index] != ""):
                return False
        return True

    def _prepareView(self, view_class, current_translation_message,
                     pofile, can_edit, error=None):
        """Collect data and build a `TranslationMessageView` for display."""
        # XXX: kiko 2006-09-27:
        # It would be nice if we could easily check if this is being
        # called in the right order, after _storeTranslations().
        translations = {}
        # Get translations that the user typed in the form.
        posted = self.form_posted_translations.get(
            current_translation_message.potmsgset, None)
        # Get the flags set by the user to note whether 'New suggestion'
        # should be taken in consideration.
        plural_indices_to_store = (
            self.form_posted_translations_has_store_flag.get(
                current_translation_message.potmsgset, []))
        # We are going to prepare the content of the translation form.
        for plural_index in range(current_translation_message.plural_forms):
            if posted is not None and posted[plural_index] is not None:
                # We have something submitted by the user, we use that value.
                translations[plural_index] = posted[plural_index]
            else:
                # We didn't get anything from the user for this translation,
                # so we store nothing for it.
                translations[plural_index] = None

        # Check the values we got with the submit for the 'Needs review' flag
        # so we prepare the new render with the same values.
        if current_translation_message.potmsgset in (
            self.form_posted_needsreview):
            force_suggestion = self.form_posted_needsreview[
                current_translation_message.potmsgset]
        else:
            force_suggestion = False

        # Check if the current translation message is marked
        # as needing to be diverged.
        if current_translation_message.potmsgset in (
            self.form_posted_diverge):
            force_diverge = self.form_posted_needsreview[
                current_translation_message.potmsgset]
        else:
            force_diverge = False

        return view_class(
            current_translation_message, self.request,
            plural_indices_to_store, translations, force_suggestion,
            force_diverge, error, self.second_lang_code,
            self.form_is_writeable, pofile=pofile, can_edit=can_edit)

    #
    # Internals
    #

    def _initializeAltLanguage(self):
        """Initialize the alternative language widget and check form data."""
        alternative_language = None
        second_lang_code = self.request.form.get("field.alternative_language")
        fallback_language = self.pofile.language.alt_suggestion_language
        if isinstance(second_lang_code, list):
            # self._redirect() was generating duplicate params in the URL.
            # We may be able to remove this guard.
            raise UnexpectedFormData(
                "You specified more than one alternative language; "
                "only one is currently supported.")

        if second_lang_code:
            try:
                translatable_vocabulary = getVocabularyRegistry().get(
                    None, 'TranslatableLanguage')
                language_term = (
                    translatable_vocabulary.getTermByToken(second_lang_code))
                alternative_language = language_term.value
            except LookupError:
                # Oops, a bogus code was provided in the request.
                # This is UnexpectedFormData caused by a hacked URL, or an
                # old URL. The alternative_language field used to use
                # LanguageVocabulary that contained untranslatable languages.
                second_lang_code = None
        elif fallback_language is not None:
            # If there's a standard alternative language and no
            # user-specified language was provided, preselect it.
            alternative_language = fallback_language
            second_lang_code = fallback_language.code
        else:
            # The second_lang_code is None and there is no fallback_language.
            # This is probably a parent language or an English variant.
            pass

        # Whatever alternative language choice came out of all that, ignore it
        # if the user has preferred languages and the alternative language
        # isn't among them.  Otherwise we'd be initializing this dropdown to a
        # choice it didn't in fact contain, resulting in an oops.
        if alternative_language is not None:
            user = getUtility(ILaunchBag).user
            if user is not None:
                translations_person = ITranslationsPerson(user)
                choices = set(translations_person.translatable_languages)
                if choices and alternative_language not in choices:
                    editlanguages_url = canonical_url(
                        self.user, view_name="+editlanguages")
                    self.request.response.addInfoNotification(structured(
                        u"Not showing suggestions from selected alternative "
                        "language %(alternative)s.  If you wish to see "
                        "suggestions from this language, "
                        '<a href="%(editlanguages_url)s">'
                        "add it to your preferred languages</a> first.",
                            alternative=alternative_language.displayname,
                            editlanguages_url=editlanguages_url,
                            ))
                    alternative_language = None
                    second_lang_code = None

        initial_values = {}
        if alternative_language is not None:
            initial_values['alternative_language'] = alternative_language

        self.alternative_language_widget = CustomWidgetFactory(
            CustomDropdownWidget)
        setUpWidgets(
            self, IPOFileAlternativeLanguage, IInputWidget,
            names=['alternative_language'], initial=initial_values)

        # We store second_lang_code for use in hidden inputs in the
        # other forms in the translation pages.
        self.second_lang_code = second_lang_code

    @property
    def user_is_official_translator(self):
        """Determine whether the current user is an official translator."""
        return self.pofile.canEditTranslations(self.user)

    @cachedproperty
    def form_is_writeable(self):
        """Whether the form should accept write operations."""
        return self.pofile.canAddSuggestions(self.user)

    def _extractFormPostedTranslations(self, potmsgset):
        """Look for translations for this `POTMsgSet` in the form submitted.

        Store the new translations at self.form_posted_translations and its
        fuzzy status at self.form_posted_needsreview, keyed on the
        `POTMsgSet`.

        In this method, we look for various keys in the form, and use them as
        follows:

        * 'msgset_ID' to know if self is part of the submitted form. If it
          isn't found, we stop parsing the form and return.
        * 'msgset_ID_LANGCODE_translation_PLURALFORM': Those will be the
          submitted translations and we will have as many entries as plural
          forms the language self.context.language has.  This identifier
          format is generated by `TranslationMessage.makeHTMLID`.
        * 'msgset_ID_LANGCODE_needsreview': If present, will note that the
          'needs review' flag has been set for the given translations.

        In all those form keys, 'ID' is the ID of the `POTMsgSet`.
        """
        form = self.request.form
        potmsgset_ID = potmsgset.id
        language_code = self.pofile.language.code

        msgset_ID = 'msgset_%d' % potmsgset_ID
        if msgset_ID not in form:
            # If this form does not have data about the msgset id, then
            # do nothing at all.
            return

        msgset_ID_LANGCODE_needsreview = 'msgset_%d_%s_needsreview' % (
            potmsgset_ID, language_code)
        self.form_posted_needsreview[potmsgset] = (
            msgset_ID_LANGCODE_needsreview in form)

        msgset_ID_diverge = 'msgset_%d_diverge' % (
            potmsgset_ID)
        self.form_posted_diverge[potmsgset] = (
            msgset_ID_diverge in form)

        msgset_ID_dismiss = 'msgset_%d_dismiss' % potmsgset_ID
        self.form_posted_dismiss_suggestions[potmsgset] = (
            msgset_ID_dismiss in form)

        # Note the trailing underscore: we append the plural form
        # number later.
        msgset_ID_LANGCODE_translation_ = 'msgset_%d_%s_translation_' % (
            potmsgset_ID, language_code)

        msgset_ID_LANGCODE_translation_GREATER_PLURALFORM_new = '%s%d_new' % (
            msgset_ID_LANGCODE_translation_,
            TranslationConstants.MAX_PLURAL_FORMS)
        if msgset_ID_LANGCODE_translation_GREATER_PLURALFORM_new in form:
            # The plural form translation generation rules created too many
            # fields, or the form was hacked.
            raise AssertionError(
                'More than %d plural forms were submitted!'
                % TranslationConstants.MAX_PLURAL_FORMS)

        # Extract the translations from the form, and store them in
        # self.form_posted_translations. We try plural forms in turn,
        # starting at 0.
        for pluralform in xrange(TranslationConstants.MAX_PLURAL_FORMS):
            msgset_ID_LANGCODE_translation_PLURALFORM_new = '%s%d_new' % (
                msgset_ID_LANGCODE_translation_, pluralform)
            if msgset_ID_LANGCODE_translation_PLURALFORM_new not in form:
                # Stop when we reach the first plural form which is
                # missing from the form.
                break

            # Get new value introduced by the user.
            raw_value = form[msgset_ID_LANGCODE_translation_PLURALFORM_new]
            value = contract_rosetta_escapes(raw_value)

            if self.user_is_official_translator:
                # Let's see the section that we are interested on based on the
                # radio button that is selected.
                msgset_ID_LANGCODE_translation_PLURALFORM_radiobutton = (
                    '%s%d_radiobutton' % (
                        msgset_ID_LANGCODE_translation_, pluralform))
                selected_translation_key = form.get(
                    msgset_ID_LANGCODE_translation_PLURALFORM_radiobutton)
                if selected_translation_key is None:
                    # The radiobutton was missing from the form; either
                    # it wasn't rendered to the end-user or no buttons
                    # were selected.
                    continue

                # We are going to check whether the radio button is for
                # current translation, suggestion or the new translation
                # field.
                current_translation_message = (
                    potmsgset.getCurrentTranslationMessageOrDummy(
                        self.pofile))
                if (selected_translation_key !=
                    msgset_ID_LANGCODE_translation_PLURALFORM_new):
                    # It's either current translation or an existing
                    # suggestion.
                    # Let's override 'value' with the selected suggestion
                    # value.
                    if 'suggestion' in selected_translation_key:
                        value = _getSuggestionFromFormId(
                            selected_translation_key)
                    elif current_translation_message.translations[
                        pluralform] is not None:
                        # It's current translation.
                        value = current_translation_message.translations[
                            pluralform]
                    else:
                        # Current translation is None, this code expects u''
                        # when there is no translation.
                        value = u''
                # Current user is an official translator and the radio button
                # for 'New translation' is selected, so we are sure we want to
                # store this submission.
                store = True
            else:
                # Note whether this translation should be stored in our
                # database as a new suggestion.
                msgset_ID_LANGCODE_translation_PLURALFORM_new_checkbox = (
                    '%s_checkbox'
                    % msgset_ID_LANGCODE_translation_PLURALFORM_new)
                store = (
                    msgset_ID_LANGCODE_translation_PLURALFORM_new_checkbox
                    in form)

            if potmsgset not in self.form_posted_translations:
                self.form_posted_translations[potmsgset] = {}
            self.form_posted_translations[potmsgset][pluralform] = value

            if potmsgset not in self.form_posted_translations_has_store_flag:
                self.form_posted_translations_has_store_flag[potmsgset] = []
            if store:
                self.form_posted_translations_has_store_flag[
                    potmsgset].append(pluralform)

    def _observeTranslationUpdate(self, potmsgset):
        """Observe that a translation was updated for the potmsgset.

        Subclasses should redefine this method if they need to watch the
        successful calls to `potmsgset.updateTranslation`.
        """
        pass

    #
    # Redirection
    #

    def _buildRedirectParams(self):
        """Construct parameters for redirection.

        Redefine this method if you have additional parameters to preserve.
        """
        parameters = {}
        if self.second_lang_code:
            parameters['field.alternative_language'] = self.second_lang_code
        return parameters

    def _redirect(self, new_url):
        """Redirect to the given url adding the selected filtering rules."""
        assert new_url is not None, ('The new URL cannot be None.')
        if not new_url:
            new_url = str(self.request.URL)
            if self.request.get('QUERY_STRING'):
                new_url += '?%s' % self.request.get('QUERY_STRING')

        # Get the default values for several parameters.
        parameters = self._buildRedirectParams()

        if '?' in new_url:
            # Get current query string
            base_url, old_query_string = new_url.split('?')
            query_parts = cgi.parse_qsl(
                old_query_string, strict_parsing=False)

            # Combine parameters provided by _buildRedirectParams with those
            # that came with our page request.  The latter take precedence.
            combined_parameters = {}
            combined_parameters.update(parameters)
            for (key, value) in query_parts:
                combined_parameters[key] = value
            parameters = combined_parameters
        else:
            base_url = new_url

        new_query = urllib.urlencode(sorted(parameters.items()))

        if new_query:
            new_url = '%s?%s' % (base_url, new_query)

        self.request.response.redirect(new_url)

    def _redirectToNextPage(self):
        """After a successful submission, redirect to the next batch page."""
        # Schedule this POFile to have its statistics updated.
        pofilestatsjob.schedule(self.pofile)
        next_url = self.batchnav.nextBatchURL()
        if next_url is None or next_url == '':
            # We are already at the end of the batch, forward to the
            # first one.
            next_url = self.batchnav.firstBatchURL()
        if next_url is None:
            # Stay in whatever URL we are atm.
            next_url = ''
        self._redirect(next_url)


class CurrentTranslationMessagePageView(BaseTranslationView):
    """A view for the page that renders a single translation.

    See `BaseTranslationView` for details on how this works.
    """

    def initialize(self):
        self.pofile = self.context.browser_pofile

        # Since we are only displaying a single message, we only hold on to
        # one error for it. The variable is set to the failing
        # TranslationMessage (a device of
        # BaseTranslationView._storeTranslations) via _submitTranslations.
        self.error = None
        self.translationmessage_view = None

        BaseTranslationView.initialize(self)

    #
    # BaseTranslationView API
    #

    def _buildBatchNavigator(self):
        """See `BaseTranslationView._buildBatchNavigator`."""
        return POTMsgSetBatchNavigator(self.pofile.potemplate.getPOTMsgSets(),
                                       self.request, size=1)

    def _initializeTranslationMessageViews(self):
        """See `BaseTranslationView._initializeTranslationMessageViews`."""
        pofile = self.pofile
        can_edit = pofile.canEditTranslations(self.user)
        self.translationmessage_view = self._prepareView(
            CurrentTranslationMessageZoomedView, self.context, pofile=pofile,
            can_edit=can_edit, error=self.error)

    def _submitTranslations(self):
        """See `BaseTranslationView._submitTranslations`."""
        self.error = self._receiveTranslations(self.context.potmsgset)
        if self.error:
            self.request.response.addErrorNotification(
                "There is an error in the translation you provided. "
                "Please correct it before continuing.")
            return False

        self._redirectToNextPage()
        return True

    def _messages_html_id(self):
        order = []
        message = self.translationmessage_view
        # If we don't know about plural forms, or there are some other
        # reason that prevent translations, translationmessage_view is
        # not created
        if ((message is not None) and (message.form_is_writeable)):
            for dictionary in message.translation_dictionaries:
                order.append(
                    dictionary['html_id_translation'] + '_new')
        return order

    @property
    def autofocus_html_id(self):
        if (len(self._messages_html_id()) > 0):
            return self._messages_html_id()[0]
        else:
            return ""

    @property
    def translations_order(self):
        return ' '.join(self._messages_html_id())


class CurrentTranslationMessageView(LaunchpadView):
    """Holds all data needed to show an ITranslationMessage.

    This view class could be used directly or as part of the POFileView class
    in which case, we would have up to 100 instances of this class using the
    same information at self.form.
    """

    # Instead of registering in ZCML, we indicate the template here and avoid
    # the adapter lookup when constructing these subviews.
    template = ViewPageTemplateFile(
        '../templates/currenttranslationmessage-translate-one.pt')

    def __init__(self, current_translation_message, request,
                 plural_indices_to_store, translations, force_suggestion,
                 force_diverge, error, second_lang_code, form_is_writeable,
                 pofile, can_edit):
        """Primes the view with information that is gathered by a parent view.

        :param plural_indices_to_store: A dictionary that indicates whether
            the translation associated should be stored in our database or
            ignored. It's indexed by plural form.
        :param translations: A dictionary indexed by plural form index;
            BaseTranslationView constructed it based on form-submitted
            translations.
        :param force_suggestion: Should this be a suggestion even for editors.
        :param force_diverge: Should this translation be diverged.
        :param error: The error related to self.context submission or None.
        :param second_lang_code: The result of submiting
            field.alternative_value.
        :param form_is_writeable: Whether the form should accept write
            operations
        :param pofile: The `POFile` that's being displayed or edited.
        :param can_edit: Whether the user has editing privileges on `pofile`.
        """
        LaunchpadView.__init__(self, current_translation_message, request)

        self.pofile = pofile
        self.plural_indices_to_store = plural_indices_to_store
        self.translations = translations
        self.error = error
        self.force_suggestion = force_suggestion
        self.force_diverge = force_diverge
        self.user_is_official_translator = can_edit
        self.form_is_writeable = form_is_writeable

        side_traits = getUtility(ITranslationSideTraitsSet).getForTemplate(
            pofile.potemplate)
        if side_traits.other_side_traits.getFlag(self.context):
            # The shared translation for the other side matches the current
            # one.
            self.other_translationmessage = None
        else:
            self.other_translationmessage = (
                self.context.potmsgset.getCurrentTranslation(
                    self.pofile.potemplate, self.pofile.language,
                    side_traits.other_side_traits.side))

        if self.context.potemplate is None:
            # Current translation is shared.
            self.shared_translationmessage = None
        else:
            # Current translation is diverged, find the shared one.
            shared_translationmessage = (
                self.context.potmsgset.getCurrentTranslation(
                    None, self.pofile.language, side_traits.side))
            if (shared_translationmessage == self.other_translationmessage):
                # If it matches the other message, we don't care.
                self.shared_translationmessage = None
            else:
                self.shared_translationmessage = shared_translationmessage

        self.other_title = "In %s:" % (
            side_traits.other_side_traits.displayname)
        self.can_confirm_and_dismiss = False
        self.can_dismiss_on_empty = False
        self.can_dismiss_on_plural = False
        self.can_dismiss_other = False

        # Initialize to True, allowing POFileTranslateView to override.
        self.zoomed_in_view = True

        # Set up alternative language variables.
        # XXX: kiko 2006-09-27:
        # This could be made much simpler if we built suggestions externally
        # in the parent view, as suggested in initialize() below.
        self.sec_lang = None
        self.second_lang_potmsgset = None
        if second_lang_code is not None:
            potemplate = self.pofile.potemplate
            second_lang_pofile = potemplate.getPOFileByLang(second_lang_code)
            if second_lang_pofile:
                self.sec_lang = second_lang_pofile.language

    def initialize(self):
        # XXX: kiko 2006-09-27:
        # The heart of the optimization problem here is that
        # _buildAllSuggestions() is very expensive. We need to move to
        # building suggestions and active texts in one fell swoop in the
        # parent view, and then supplying them all via __init__(). This
        # would cut the number of (expensive) queries per-page by an
        # order of 30.

        # This code is where we hit the database collecting suggestions for
        # this ITranslationMessage.

        # We store lists of TranslationMessageSuggestions objects in a
        # suggestion_blocks dictionary, keyed on plural form index; this
        # allows us later to just iterate over them in the view code
        # using a generic template.
        self.pluralform_indices = range(self.context.plural_forms)

        self._buildAllSuggestions()

        # If existing translation is shared, and a user is
        # an official translator, they can diverge a translation.
        self.allow_diverging = (self.zoomed_in_view and
                                self.user_is_official_translator and
                                self.context.potemplate is None)
        if self.allow_diverging:
            if self.pofile.potemplate.productseries is not None:
                self.current_series = self.pofile.potemplate.productseries
                self.current_series_title = "%s %s" % (
                    self.current_series.product.displayname,
                    self.current_series.name)
            else:
                self.current_series = self.pofile.potemplate.distroseries
                self.current_series_title = "%s %s" % (
                    self.current_series.distribution.displayname,
                    self.current_series.name)

        # Initialize the translation dictionaries used from the
        # translation form.
        self.translation_dictionaries = []
        for index in self.pluralform_indices:
            current_translation = self.getCurrentTranslation(index)
            other_translation = self.getOtherTranslation(index)
            shared_translation = self.getSharedTranslation(index)
            submitted_translation = self.getSubmittedTranslation(index)
            is_multi_line = (count_lines(current_translation) > 1 or
                             count_lines(submitted_translation) > 1 or
                             count_lines(self.singular_text) > 1 or
                             count_lines(self.plural_text) > 1)
            is_same_translator = (
                self.context.submitter == self.context.reviewer)
            is_same_date = (
                self.context.date_created == self.context.date_reviewed)
            if self.other_translationmessage is None:
                other_submission = None
            else:
                pofile = (
                    self.other_translationmessage.ensureBrowserPOFile())
                if pofile is None:
                    other_submission = None
                else:
                    other_submission = (
                        convert_translationmessage_to_submission(
                            message=self.other_translationmessage,
                            current_message=self.context,
                            plural_form=index,
                            pofile=pofile,
                            legal_warning_needed=False,
                            is_empty=False,
                            other_side=True,
                            local_to_pofile=True))

            diverged_and_have_shared = (
                self.context.potemplate is not None and
                self.shared_translationmessage is not None)
            if diverged_and_have_shared:
                pofile = self.shared_translationmessage.ensureBrowserPOFile()
                if pofile is None:
                    shared_submission = None
                else:
                    shared_submission = (
                        convert_translationmessage_to_submission(
                            message=self.shared_translationmessage,
                            current_message=self.context,
                            plural_form=index,
                            pofile=pofile,
                            legal_warning_needed=False,
                            is_empty=False,
                            local_to_pofile=True))
            else:
                shared_submission = None

            translation_entry = {
                'plural_index': index,
                'current_translation': text_to_html(
                    current_translation, self.context.potmsgset.flags),
                'submitted_translation': submitted_translation,
                'other_translation': text_to_html(
                    other_translation, self.context.potmsgset.flags),
                'other_translation_message': other_submission,
                'shared_translation': text_to_html(
                    shared_translation, self.context.potmsgset.flags),
                'shared_translation_message': shared_submission,
                'suggestion_block': self.suggestion_blocks[index],
                'suggestions_count': self.suggestions_count[index],
                'store_flag': index in self.plural_indices_to_store,
                'is_multi_line': is_multi_line,
                'same_translator_and_reviewer': (is_same_translator and
                                                 is_same_date),
                'html_id_translation':
                    self.context.makeHTMLID('translation_%d' % index),
                }

            if self.message_must_be_hidden:
                # We must hide the translation because it may have private
                # info that we don't want to show to anonymous users.
                translation_entry['current_translation'] = u'''
                    To prevent privacy issues, this translation is not
                    available to anonymous users,<br />
                    if you want to see it, please, <a href="+login">log in</a>
                    first.'''

            self.translation_dictionaries.append(translation_entry)

        self.html_id = self.context.potmsgset.makeHTMLID()
        # HTML id for singular form of this message
        self.html_id_singular = self.context.makeHTMLID('translation_0')

    def _set_dismiss_flags(self, local_suggestions, other):
        """Set dismissal flags.

        The flags have been initialized to False in the constructor. This
        method activates the right ones.

        :param local_suggestions: The list of local suggestions.
        :param other: The translation on the other side for this
            message or None if there is no such translation.
        """
        # Only official translators can dismiss anything.
        if not self.user_is_official_translator:
            return

        # If there is an other-side translation that is newer than the
        # context, it can be dismissed.
        self.can_dismiss_other = other is not None and (
            self.context.date_reviewed is None or
            self.context.date_reviewed < other.date_created)

        # If there are no local suggestion and no new other-side translation
        # nothing can be dismissed.
        if len(local_suggestions) == 0 and not self.can_dismiss_other:
            return

        if self.is_plural:
            self.can_dismiss_on_plural = True
        else:
            if self.getCurrentTranslation(0) is None:
                self.can_dismiss_on_empty = True
            else:
                self.can_confirm_and_dismiss = True

    def _setOnePOFile(self, messages):
        """Return a list of messages that all have a browser_pofile set.

        If a pofile cannot be found for a message, it is not included in
        the resulting list.
        """
        result = []
        for message in messages:
            if message.browser_pofile is None:
                pofile = message.getOnePOFile()
                if pofile is None:
                    # Do not include in result.
                    continue
                else:
                    message.setPOFile(pofile)
            result.append(message)
        return result

    def _buildAllSuggestions(self):
        """Builds all suggestions and puts them into suggestions_block.

        This method does the ugly nitty gritty of making sure we don't
        display duplicated suggestions; this is done by checking the
        translation strings in each submission and grabbing only one
        submission per string.

        The decreasing order of preference this method encodes is:
            - Non-active translations to this context and to the pofile
              from which this translation was imported (non_editor)
            - Active translations to other contexts (elsewhere)
            - Non-editor translations to other contexts (wiki)
        """
        # Prepare suggestions storage.
        self.suggestion_blocks = {}
        self.suggestions_count = {}

        if self.message_must_be_hidden:
            # We must hide all suggestions because this message may contain
            # private information that we don't want to show to anonymous
            # users, such as email addresses.
            for index in self.pluralform_indices:
                self.suggestion_blocks[index] = []
                self.suggestions_count[index] = 0
            return

        language = self.pofile.language
        potmsgset = self.context.potmsgset
        other = self.other_translationmessage

        # Show suggestions only when you can actually do something with them
        # (i.e. you are logged in and have access to at least submit
        # suggestions).
        if self.form_is_writeable:
            # Get a list of local suggestions for this message: local are
            # those who have been submitted directly against it and are
            # newer than the date of the last review.
            local = sorted(
                potmsgset.getLocalTranslationMessages(
                    self.pofile.potemplate,
                    language),
                key=operator.attrgetter("date_created"),
                reverse=True)

            self._set_dismiss_flags(local, other)

            for suggestion in local:
                suggestion.setPOFile(self.pofile)

            # Get a list of translations which are _used_ as translations
            # for this same message in a different translation template.
            used_languages = [language]
            if self.sec_lang is not None:
                used_languages.append(self.sec_lang)
            translations = (
                potmsgset.getExternallySuggestedOrUsedTranslationMessages(
                    suggested_languages=[language],
                    used_languages=used_languages))
            alt_external = translations[self.sec_lang].used
            externally_used = self._setOnePOFile(sorted(
                translations[language].used,
                key=operator.attrgetter("date_created"),
                reverse=True))

            # Get a list of translations which are suggested as
            # translations for this same message in a different translation
            # template, but are not used.
            externally_suggested = self._setOnePOFile(sorted(
                translations[language].suggested,
                key=operator.attrgetter("date_created"),
                reverse=True))
        else:
            # Don't show suggestions for anonymous users.
            local = externally_used = externally_suggested = []

        # Fetch a list of current and externally used translations for
        # this message in an alternative language.
        alt_submissions = []
        if self.sec_lang is None:
            alt_title = None
        else:
            # User is asking for alternative language suggestions.
            alt_pofile = self.pofile.potemplate.getPOFileByLang(
                self.sec_lang.code)
            alt_current = potmsgset.getCurrentTranslation(
                self.pofile.potemplate, self.sec_lang,
                self.pofile.potemplate.translation_side)
            if alt_current is not None:
                alt_submissions.append(alt_current)
            if not self.form_is_writeable:
                alt_external = list(
                    potmsgset.getExternallyUsedTranslationMessages(
                        self.sec_lang))
            alt_submissions.extend(alt_external)
            for suggestion in alt_submissions:
                suggestion.setPOFile(alt_pofile)
            alt_title = self.sec_lang.englishname

        # To maintain compatibility with the old DB model as much as possible,
        # let's split out all the submissions by their plural form.
        # Builds ITranslationMessageSuggestions for each type of the
        # suggestion per plural form.
        for index in self.pluralform_indices:
            self.seen_translations = set([self.context.translations[index]])
            if other is not None:
                self.seen_translations.add(other.translations[index])
            local_suggestions = (
                self._buildTranslationMessageSuggestions(
                    'Suggestions', local, index, local_to_pofile=True))
            externally_used_suggestions = (
                self._buildTranslationMessageSuggestions(
                    'Used in', externally_used, index, legal_warning=True))
            externally_suggested_suggestions = (
                self._buildTranslationMessageSuggestions(
                    'Suggested in', externally_suggested, index,
                    legal_warning=True))
            alternate_language_suggestions = (
                self._buildTranslationMessageSuggestions(
                    alt_title, alt_submissions, index))

            self.suggestion_blocks[index] = [
                local_suggestions, externally_used_suggestions,
                externally_suggested_suggestions,
                alternate_language_suggestions]
            self.suggestions_count[index] = (
                len(local_suggestions.submissions) +
                len(externally_used_suggestions.submissions) +
                len(externally_suggested_suggestions.submissions) +
                len(alternate_language_suggestions.submissions))

    def _buildTranslationMessageSuggestions(self, title, suggestions, index,
                                            legal_warning=False,
                                            local_to_pofile=False):
        """Build filtered list of submissions to be shown in the view.

        `title` is the title for the suggestion type, `suggestions` is
        a list of suggestions, and `index` is the plural form.
        """
        iterable_submissions = TranslationMessageSuggestions(
            title, self.context,
            suggestions[:self.max_entries],
            self.user_is_official_translator, self.form_is_writeable,
            index, self.seen_translations, legal_warning=legal_warning,
            local_to_pofile=local_to_pofile)
        self.seen_translations = iterable_submissions.seen_translations
        return iterable_submissions

    def getOfficialTranslation(self, index, is_other=False, is_shared=False):
        """Return current translation on either side for plural form 'index'.
        """
        assert index in self.pluralform_indices, (
            'There is no plural form #%d for %s language' % (
                index, self.pofile.language.displayname))

        if is_shared:
            if self.shared_translationmessage is None:
                return None
            translation = self.shared_translationmessage.translations[index]
        elif is_other and self.other_translationmessage is not None:
            translation = self.other_translationmessage.translations[index]
        else:
            translation = self.context.translations[index]
        # We store newlines as '\n', '\r' or '\r\n', depending on the
        # msgid but forms should have them as '\r\n' so we need to change
        # them before showing them.
        if translation is not None:
            return convert_newlines_to_web_form(translation)
        else:
            return None

    def getCurrentTranslation(self, index):
        """Return the current translation for the pluralform 'index'."""
        return self.getOfficialTranslation(index)

    def getOtherTranslation(self, index):
        """Return the other-side translation for the pluralform 'index'."""
        return self.getOfficialTranslation(index, is_other=True)

    def getSharedTranslation(self, index):
        """Return the shared translation for the pluralform 'index'."""
        return self.getOfficialTranslation(index, is_shared=True)

    def getSubmittedTranslation(self, index):
        """Return the translation submitted for the pluralform 'index'."""
        assert index in self.pluralform_indices, (
            'There is no plural form #%d for %s language' % (
                index, self.pofile.language.displayname))

        translation = self.translations[index]
        # We store newlines as '\n', '\r' or '\r\n', depending on the text to
        # translate; but forms should have them as '\r\n' so we need to change
        # line endings before showing them.
        return convert_newlines_to_web_form(translation)

    #
    # Display-related methods
    #

    @cachedproperty
    def is_plural(self):
        """Return whether there are plural forms."""
        return self.context.potmsgset.plural_text is not None

    @cachedproperty
    def message_must_be_hidden(self):
        """Whether this message must be hidden from anonymous viewers.

        Messages are always shown to logged-in users.  However, messages that
        are likely to contain email addresses must not be shown to anonymous
        visitors in order to keep them out of search engines, spam lists etc.
        """
        if self.user is not None:
            # Always show messages to logged-in users.
            return False
        # For anonymous users, check the msgid.
        return self.context.potmsgset.hide_translations_from_anonymous

    @property
    def translation_credits(self):
        """Return automatically created translation if defined, or None."""
        assert self.context.potmsgset.is_translation_credit
        return text_to_html(
            self.pofile.prepareTranslationCredits(
                self.context.potmsgset),
            self.context.potmsgset.flags)

    @cachedproperty
    def sequence(self):
        """Return the position number of this potmsgset in the pofile."""
        return self.context.potmsgset.getSequence(
            self.pofile.potemplate)

    @property
    def singular_text(self):
        """Return the singular form prepared to render in a web page."""
        return text_to_html(
            self.context.potmsgset.singular_text,
            self.context.potmsgset.flags)

    @property
    def plural_text(self):
        """Return a plural form prepared to render in a web page.

        If there is no plural form, return None.
        """
        return text_to_html(
            self.context.potmsgset.plural_text,
            self.context.potmsgset.flags)

    # XXX mpt 2006-09-15: Detecting tabs, newlines, and leading/trailing
    # spaces is being done one way here, and another way in the functions
    # above.
    @property
    def text_has_tab(self):
        """Whether the text to translate contain tab chars."""
        return ('\t' in self.context.potmsgset.singular_text or
            (self.context.potmsgset.plural_text is not None and
             '\t' in self.context.potmsgset.plural_text))

    @property
    def text_has_newline(self):
        """Whether the text to translate contain newline chars."""
        return ('\n' in self.context.potmsgset.singular_text or
            (self.context.potmsgset.plural_text is not None and
             '\n' in self.context.potmsgset.plural_text))

    @property
    def text_has_leading_or_trailing_space(self):
        """Whether the text to translate contain leading/trailing spaces."""
        texts = [self.context.potmsgset.singular_text]
        if self.context.potmsgset.plural_text is not None:
            texts.append(self.context.potmsgset.plural_text)
        for text in texts:
            for line in text.splitlines():
                if line.startswith(' ') or line.endswith(' '):
                    return True
        return False

    @property
    def source_comment(self):
        """Return the source code comments for this ITranslationMessage."""
        return self.context.potmsgset.sourcecomment

    @property
    def comment(self):
        """Return the translator comments for this ITranslationMessage."""
        return self.context.comment

    @property
    def file_references(self):
        """Return the file references for this ITranslationMessage."""
        return self.context.potmsgset.filereferences

    @property
    def zoom_url(self):
        """Return the URL where we should from the zoom icon."""
        # XXX: kiko 2006-09-27: Preserve second_lang_code and other form
        # parameters?
        return canonical_url(self.context) + '/+translate'

    @property
    def zoom_alt(self):
        return 'View all details of this message'

    @property
    def zoom_link_id(self):
        return "zoom-%s" % self.context.id

    @property
    def zoom_icon(self):
        return 'zoom-in'

    @property
    def max_entries(self):
        """Return the max number of entries to show as suggestions.

        If there is no limit, we return None.
        """
        return 3

    @property
    def dismissable_class(self):
        """The class string for dismissable parts."""
        return "%s_dismissable %s_dismissable_button" % (
                    self.html_id, self.html_id)

    @property
    def dismissable_class_other(self):
        """The class string for dismissable other translations."""
        if self.can_dismiss_other:
            return self.dismissable_class
        # Buttons are always dismissable.
        return "%s_dismissable_button" % self.html_id


class CurrentTranslationMessageZoomedView(CurrentTranslationMessageView):
    """A view that displays a `TranslationMessage`, but zoomed in.

    See `TranslationMessagePageView`.
    """
    zoom_link_id = 'zoom-out'

    @property
    def zoom_url(self):
        # We are viewing this class directly from an ITranslationMessage, we
        # should point to the parent batch of messages.
        # XXX: kiko 2006-09-27: Preserve second_lang_code and other form
        # parameters?
        batch_url = '/+translate?start=%d' % (self.sequence - 1)
        return canonical_url(self.pofile) + batch_url

    @property
    def zoom_alt(self):
        return 'Return to multiple messages view.'

    @property
    def zoom_icon(self):
        return 'zoom-out'

    @property
    def max_entries(self):
        return None


class TranslationMessageSuggestions:
    """See `ITranslationMessageSuggestions`."""

    implements(ITranslationMessageSuggestions)

    def __init__(self, title, translation, submissions,
                 user_is_official_translator, form_is_writeable,
                 plural_form, seen_translations=None, legal_warning=False,
                 local_to_pofile=False):
        self.title = title
        self.potmsgset = translation.potmsgset
        self.pofile = translation.browser_pofile
        self.user_is_official_translator = user_is_official_translator
        self.form_is_writeable = form_is_writeable
        self.submissions = []
        if seen_translations is None:
            seen_translations = set()

        for submission in submissions:
            total_plural_forms = submission.language.pluralforms
            if total_plural_forms is None:
                total_plural_forms = 2
            has_form = (plural_form < total_plural_forms and
                plural_form < len(submission.translations))
            if not has_form:
                # This submission does not have a translation for the
                # requested plural form.  It's not a viable suggestion here.
                continue
            this_translation = submission.translations[plural_form]
            if (this_translation is None or
                this_translation in seen_translations):
                continue
            else:
                seen_translations.add(this_translation)
            self.submissions.append(
                convert_translationmessage_to_submission(
                    submission,
                    translation,
                    plural_form,
                    self.pofile,
                    legal_warning,
                    is_empty=False,
                    local_to_pofile=local_to_pofile))
        self.seen_translations = seen_translations


class Submission:
    """A submission generated from a TranslationMessage"""


def convert_translationmessage_to_submission(
    message, current_message, plural_form, pofile, legal_warning_needed,
    is_empty=False, other_side=False, local_to_pofile=False):
    """Turn a TranslationMessage to an object used for rendering a submission.

    :param message: A TranslationMessage.
    :param plural_form: A plural form to prepare a submission for.
    :param pofile: A containing PO file where suggestion is being rendered.
    :param legal_warning_needed: Whether a warning check is needed.
    :param is_empty: Is the submission empty or not.
    """

    submission = Submission()
    submission.is_traversable = (message.sequence != 0)
    submission.translationmessage = message
    for attribute in ['id', 'language', 'potmsgset', 'date_created']:
        setattr(submission, attribute, getattr(message, attribute))

    submission.pofile = message.browser_pofile
    submission.person = message.submitter

    submission.is_empty = is_empty
    submission.plural_index = plural_form
    submission.suggestion_text = text_to_html(
        message.translations[plural_form],
        message.potmsgset.flags)
    submission.is_local_to_pofile = local_to_pofile
    submission.legal_warning = legal_warning_needed and (
        message.origin == RosettaTranslationOrigin.SCM)
    submission.suggestion_html_id = (
        current_message.potmsgset.makeHTMLID(u'%s_suggestion_%s_%s' % (
            message.language.code, message.id,
            plural_form)))
    if other_side:
        submission.row_html_id = current_message.potmsgset.makeHTMLID(
            'other')
        submission.origin_html_id = submission.row_html_id + '_origin'
    else:
        submission.row_html_id = ''
        submission.origin_html_id = submission.suggestion_html_id + '_origin'
    submission.translation_html_id = (
        current_message.makeHTMLID(
            u'translation_%s' % (plural_form)))

    suggestion_dismissable_class = message.potmsgset.makeHTMLID(
        u'dismissable_button')
    if submission.is_local_to_pofile:
        suggestion_dismissable_class += u' ' + message.potmsgset.makeHTMLID(
            u'dismissable')
    submission.suggestion_dismissable_class = suggestion_dismissable_class

    return submission
