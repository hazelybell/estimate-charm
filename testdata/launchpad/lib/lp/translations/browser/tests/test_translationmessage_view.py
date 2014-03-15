# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from __future__ import with_statement

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )

import pytz
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.errors import UnexpectedFormData
from lp.services.webapp.publisher import canonical_url
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    anonymous_logged_in,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    ZopelessDatabaseLayer,
    )
from lp.testing.views import create_view
from lp.translations.browser.translationmessage import (
    contains_translations,
    convert_translationmessage_to_submission,
    CurrentTranslationMessagePageView,
    CurrentTranslationMessageView,
    revert_unselected_translations,
    )
from lp.translations.enums import TranslationPermission
from lp.translations.interfaces.side import ITranslationSideTraitsSet
from lp.translations.interfaces.translations import TranslationConstants
from lp.translations.interfaces.translationsperson import ITranslationsPerson
from lp.translations.publisher import TranslationsLayer


class TestCurrentTranslationMessage_can_dismiss(TestCaseWithFactory):
    """Test the can_dismiss_* properties of CurrentTranslationMessageView."""

    layer = ZopelessDatabaseLayer

    def _gen_now(self):
        now = datetime.now(pytz.UTC)
        while True:
            yield now
            now += timedelta(milliseconds=1)

    def setUp(self):
        super(TestCurrentTranslationMessage_can_dismiss, self).setUp()
        self.owner = self.factory.makePerson()
        self.potemplate = self.factory.makePOTemplate(owner=self.owner)
        self.pofile = self.factory.makePOFile(potemplate=self.potemplate)
        self.potmsgset = self.factory.makePOTMsgSet(self.potemplate)
        self.view = None
        self.now = self._gen_now().next

    def _createView(self, message):
        self.view = CurrentTranslationMessageView(
            message, LaunchpadTestRequest(),
            {}, dict(enumerate(message.translations)),
            False, False, None, None, True, pofile=self.pofile, can_edit=True)
        self.view.initialize()

    def _makeTranslation(self, translation=None,
                         suggestion=False, is_other=False):
        if translation is None:
            translations = None
        elif isinstance(translation, list):
            translations = translation
        else:
            translations = [translation]
        date_created = self.now()
        date_reviewed = date_created
        if suggestion or is_other:
            message = self.factory.makeSuggestion(
                self.pofile, self.potmsgset,
                translations=translations,
                translator=self.owner,
                date_created=date_created)
            if is_other:
                # Activate and review on the other side.
                side_traits = getUtility(
                    ITranslationSideTraitsSet).getForTemplate(
                        self.pofile.potemplate)
                side_traits.other_side_traits.setFlag(message, True)
                message.markReviewed(
                    self.factory.makePerson(), date_reviewed)
        else:
            message = self.factory.makeCurrentTranslationMessage(
                self.pofile, self.potmsgset, translator=self.owner,
                translations=translations,
                date_created=date_created, date_reviewed=date_reviewed)

        message.browser_pofile = self.pofile
        return message

    def _assertConfirmEmptyPluralOther(self,
                                          can_confirm_and_dismiss,
                                          can_dismiss_on_empty,
                                          can_dismiss_on_plural,
                                          can_dismiss_other):
        """ Test the state of all four flags.

        In the view and the template the flags are used to determine if and
        where the "dismiss suggestion" checkbox is displayed. There are
        three locations for it, depending on whether the translation is empty
        or not or if it has plurals. They are therefore mutually exclusive
        and the tests show that. In addition, the "can_dismiss_other" flag
        allows for the "In Ubuntu" or "In Upstream" line to be grayed out
        upon dismissal. This flag is only used in the view to select the
        right css class to achieve that.

        :param can_confirm_and_dismiss: The expected stage of that flag.
        :param can_dismiss_on_empty: The expected stage of that flag.
        :param can_dismiss_on_plural: The expected stage of that flag.
        :param can_dismiss_other: The expected stage of that flag.
        """
        assert self.view is not None
        self.assertEqual(
            [can_confirm_and_dismiss,
               can_dismiss_on_empty,
               can_dismiss_on_plural,
               can_dismiss_other],
            [self.view.can_confirm_and_dismiss,
               self.view.can_dismiss_on_empty,
               self.view.can_dismiss_on_plural,
               self.view.can_dismiss_other])

    def test_no_suggestion(self):
        # If there is no suggestion, nothing can be dismissed.
        message = self._makeTranslation()
        self._createView(message)
        self._assertConfirmEmptyPluralOther(False, False, False, False)

    def test_local_suggestion(self):
        # If there is a local suggestion, it can be dismissed.
        message = self._makeTranslation()
        self._makeTranslation(suggestion=True)
        self._createView(message)
        self._assertConfirmEmptyPluralOther(True, False, False, False)

    def test_local_suggestion_on_empty(self):
        # If there is a local suggestion on an empty message, it is dismissed
        # in a different place.
        message = self._makeTranslation("")
        self._makeTranslation(suggestion=True)
        self._createView(message)
        self._assertConfirmEmptyPluralOther(False, True, False, False)

    def test_local_suggestion_on_plural(self):
        # If there is a suggestion on a plural message, it is dismissed
        # in yet a different place.
        self.potmsgset = self.factory.makePOTMsgSet(
            self.potemplate, singular="msgid_singular", plural="msgid_plural")
        message = self._makeTranslation(["singular_trans", "plural_trans"])
        self._makeTranslation(
            ["singular_sugg", "plural_sugg"], suggestion=True)
        self._createView(message)
        self._assertConfirmEmptyPluralOther(False, False, True, False)

    def test_other_translation(self):
        # If there is an other-side translation that is newer than the
        # current translation, it can be dismissed.
        message = self._makeTranslation()
        self._makeTranslation(is_other=True)
        self._createView(message)
        self._assertConfirmEmptyPluralOther(True, False, False, True)

    def test_other_translation_on_empty(self):
        # With an empty message, it is dismissed in a different place.
        message = self._makeTranslation("")
        self._makeTranslation(is_other=True)
        self._createView(message)
        self._assertConfirmEmptyPluralOther(False, True, False, True)

    def test_other_translation_on_plural(self):
        # If there is a suggestion on a plural message, it is dismissed
        # in yet a different place.
        self.potmsgset = self.factory.makePOTMsgSet(
            self.potemplate, singular="msgid_singular", plural="msgid_plural")
        message = self._makeTranslation(["singular_trans", "plural_trans"])
        self._makeTranslation(["singular_new", "plural_new"], is_other=True)
        self._createView(message)
        self._assertConfirmEmptyPluralOther(False, False, True, True)

    def test_other_translation_old(self):
        # If there is an older other-side translation, it cannot be dismissed.
        self._makeTranslation(is_other=True)
        message = self._makeTranslation()
        self._createView(message)
        self._assertConfirmEmptyPluralOther(False, False, False, False)

    def test_other_translation_old_local_new(self):
        # If there is an older other-side translation, but a newer local
        # suggestion, only the local suggestion can be dismissed.
        self._makeTranslation(is_other=True)
        message = self._makeTranslation()
        self._makeTranslation(suggestion=True)
        self._createView(message)
        self._assertConfirmEmptyPluralOther(True, False, False, False)


class TestResetTranslations(TestCaseWithFactory):
    """Test resetting of the current translation.

    A reviewer can reset a current translation by submitting an empty
    translation and forcing it to be a suggestion.

    :ivar pofile: A `POFile` for an Ubuntu source package.
    :ivar current_translation: A current `TranslationMessage` in `POFile`,
        submitted and reviewed sometime in the past.
    """
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestResetTranslations, self).setUp()
        package = self.factory.makeSourcePackage()
        template = self.factory.makePOTemplate(
            distroseries=package.distroseries,
            sourcepackagename=package.sourcepackagename)
        self.pofile = self.factory.makePOFile(potemplate=template)
        self.current_translation = self.factory.makeCurrentTranslationMessage(
            pofile=self.pofile)
        self.current_translation.setPOFile(self.pofile)

        naked_tm = removeSecurityProxy(self.current_translation)
        naked_tm.date_created -= timedelta(1)
        naked_tm.date_reviewed = naked_tm.date_created

    def closeTranslations(self):
        """Disallow editing of `self.pofile` translations by regular users."""
        policy = removeSecurityProxy(
            self.pofile.potemplate.getTranslationPolicy())
        policy.translationpermission = TranslationPermission.CLOSED

    def getLocalSuggestions(self):
        """Get local suggestions for `self.current_translation`."""
        return list(
            self.current_translation.potmsgset.getLocalTranslationMessages(
                self.pofile.potemplate, self.pofile.language))

    def submitForcedEmptySuggestion(self):
        """Submit an empty suggestion for `self.current_translation`."""
        empty_translation = u''

        msgset_id = 'msgset_' + str(self.current_translation.potmsgset.id)
        msgset_id_lang = msgset_id + '_' + self.pofile.language.code
        widget_id_base = msgset_id_lang + '_translation_0_'

        form = {
            'lock_timestamp': datetime.now(pytz.utc).isoformat(),
            'alt': None,
            msgset_id: None,
            widget_id_base + 'radiobutton': widget_id_base + 'new',
            widget_id_base + 'new': empty_translation,
            'submit_translations': 'Save &amp; Continue',
            msgset_id_lang + '_needsreview': 'force_suggestion',
        }

        url = canonical_url(self.current_translation) + '/+translate'
        view = create_view(
            self.current_translation, '+translate', form=form,
            layer=TranslationsLayer, server_url=url)
        view.request.method = 'POST'
        view.initialize()

    def test_disables_current_translation(self):
        # Resetting the current translation clears its "current" flag.
        self.assertTrue(self.current_translation.is_current_ubuntu)
        with person_logged_in(self.factory.makePerson()):
            self.submitForcedEmptySuggestion()
        self.assertFalse(self.current_translation.is_current_ubuntu)

    def test_turns_current_translation_into_suggestion(self):
        # Resetting the current translation demotes it back to the
        # status of a suggestion.
        self.assertEqual([], self.getLocalSuggestions())
        with person_logged_in(self.factory.makePerson()):
            self.submitForcedEmptySuggestion()
        self.assertEqual(
            [self.current_translation], self.getLocalSuggestions())

    def test_unprivileged_user_cannot_reset(self):
        # When a user without editing privileges on the translation
        # submits an empty suggestion, that does not clear the
        # translation.
        self.closeTranslations()
        self.assertTrue(self.current_translation.is_current_ubuntu)
        with person_logged_in(self.factory.makePerson()):
            self.submitForcedEmptySuggestion()
        self.assertTrue(self.current_translation.is_current_ubuntu)


class TestCurrentTranslationMessagePageView(TestCaseWithFactory):
    """Test `CurrentTranslationMessagePageView` and its base class."""

    layer = ZopelessDatabaseLayer

    def _makeView(self, with_form=False):
        potemplate = self.factory.makePOTemplate()
        pofile = self.factory.makePOFile(potemplate=potemplate)
        potmsgset = self.factory.makePOTMsgSet(potemplate)
        message = self.factory.makeCurrentTranslationMessage(
            pofile=pofile, potmsgset=potmsgset)
        message.browser_pofile = pofile
        form = {}
        if with_form:
            msgset_id_field = 'msgset_%d' % potmsgset.id
            form[msgset_id_field] = u'poit'
            base_field_name = 'msgset_%d_%s_translation_' % (
                message.potmsgset.id, pofile.language.code)
            # Add the expected plural forms fields.
            for plural_form in xrange(TranslationConstants.MAX_PLURAL_FORMS):
                field_name = '%s%d_new' % (base_field_name, plural_form)
                form[field_name] = u'snarf'
        url = '/%s/%s/%s/+translate' % (
            canonical_url(potemplate), pofile.language.code, 1)
        request = LaunchpadTestRequest(SERVER_URL=url, form=form)
        view = CurrentTranslationMessagePageView(message, request)
        view.lock_timestamp = datetime.now(pytz.utc)
        return view

    def test_extractLockTimestamp(self):
        view = self._makeView()
        view.request.form['lock_timestamp'] = u'2010-01-01 00:00:00 UTC'
        self.assertEqual(
            datetime(2010, 01, 01, tzinfo=pytz.utc),
            view._extractLockTimestamp())

    def test_extractLockTimestamp_returns_None_by_default(self):
        view = self._makeView()
        self.assertIs(None, view._extractLockTimestamp())

    def test_extractLockTimestamp_returns_None_for_bogus_timestamp(self):
        view = self._makeView()
        view.request.form['lock_timestamp'] = u'Hi mom!'
        self.assertIs(None, view._extractLockTimestamp())

    def test_checkSubmitConditions_passes(self):
        with person_logged_in(self.factory.makePerson()):
            view = self._makeView()
            view._checkSubmitConditions()

    def test_checkSubmitConditions_requires_lock_timestamp(self):
        with person_logged_in(self.factory.makePerson()):
            view = self._makeView()
            view.lock_timestamp = None
            self.assertRaises(UnexpectedFormData, view._checkSubmitConditions)

    def test_checkSubmitConditions_rejects_anonymous_request(self):
        with anonymous_logged_in():
            view = self._makeView()
            self.assertRaises(UnexpectedFormData, view._checkSubmitConditions)

    def test_checkSubmitConditions_rejects_license_decliners(self):
        # Users who have declined the relicensing agreement can't post
        # translations.
        decliner = self.factory.makePerson()
        ITranslationsPerson(decliner).translations_relicensing_agreement = (
            False)
        with person_logged_in(decliner):
            view = self._makeView()
            self.assertRaises(UnexpectedFormData, view._checkSubmitConditions)

    def test_max_plural_forms_fields_accepted(self):
        # The plural forms translation fields are accepted if there are less
        # than or equal to TranslationConstants.MAX_PLURAL_FORM.
        view = self._makeView(with_form=True)
        view.initialize()
        self.assertEqual(
            None, view._extractFormPostedTranslations(view.context.potmsgset))

    def test_max_plural_forms_fields_greater_error(self):
        # An AssertionError is raised if the number of plural forms
        # translation fields exceed TranslationConstants.MAX_PLURAL_FORMS.
        view = self._makeView(with_form=True)
        view.initialize()
        # Add a field that is greater than the expected MAX_PLURAL_FORMS.
        field_name = 'msgset_%d_%s_translation_%d_new' % (
            view.context.potmsgset.id, view.pofile.language.code,
            TranslationConstants.MAX_PLURAL_FORMS)
        view.request.form[field_name] = u'snarf'
        self.assertRaises(AssertionError,
            view._extractFormPostedTranslations, view.context.potmsgset)


class TestHelpers(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def test_contains_translations_is_false_for_empty_dict(self):
        self.assertFalse(contains_translations({}))

    def test_contains_translations_finds_any_translations(self):
        for plural_form in xrange(TranslationConstants.MAX_PLURAL_FORMS):
            self.assertTrue(
                contains_translations({plural_form: self.getUniqueString()}))

    def test_contains_translations_ignores_empty_strings(self):
        self.assertFalse(contains_translations({0: u''}))

    def test_contains_translations_ignores_nones(self):
        self.assertFalse(contains_translations({0: None}))

    def test_revert_unselected_translations_accepts_selected(self):
        # Translations for plural forms in plural_indices_to_store stay
        # intact.
        translations = {0: self.getUniqueString()}
        self.assertEqual(
            translations,
            revert_unselected_translations(translations, None, [0]))

    def test_revert_unselected_translations_handles_plurals(self):
        translated_forms = range(3)
        translations = dict(
            (form, self.getUniqueString()) for form in translated_forms)

        self.assertEqual(
            translations,
            revert_unselected_translations(
                translations, None, translated_forms))

    def test_revert_unselected_translations_selects_forms_separately(self):
        # If some of the translated forms are accepted and some aren't,
        # revert_unselected_translations will keep those that were and
        # revert the rest.
        translations = {
            0: self.getUniqueString(),
            1: self.getUniqueString(),
        }
        resulting_translations = revert_unselected_translations(
            translations, None, [0])
        self.assertEqual(translations[0], resulting_translations[0])
        self.assertNotEqual(translations[1], resulting_translations[1])
        self.assertEqual(u'', resulting_translations[1])

    def test_revert_unselected_translations_ignores_untranslated_form(self):
        translations = {0: self.getUniqueString()}
        self.assertNotIn(
            1, revert_unselected_translations(translations, None, [1]))

    def test_revert_unselected_translations_reverts_to_existing(self):
        # Translations for plural forms not in plural_indices_to_store
        # are reverted to those found in the current translation
        # message, if any.
        new_translations = {0: self.getUniqueString()}
        original_translations = {0: self.getUniqueString()}
        current_message = self.factory.makeCurrentTranslationMessage(
            translations=original_translations)
        self.assertEqual(
            original_translations,
            revert_unselected_translations(
                new_translations, current_message, []))

    def test_revert_unselected_translations_reverts_to_empty_string(self):
        # If there is no current message, any translation not in
        # plural_indices_to_store is set to the empty string.
        translations = {0: self.getUniqueString()}
        self.assertEqual(
            {0: u''}, revert_unselected_translations(translations, None, []))

    def test_revert_unselected_translations_handles_missing_plurals(self):
        # When reverting based on a current message that does not
        # translate the given plural form, the new translation is the
        # empty string.
        new_translations = {1: self.getUniqueString()}
        original_translations = {0: self.getUniqueString()}
        current_message = self.factory.makeCurrentTranslationMessage(
            translations=original_translations)
        self.assertEqual(
            {1: u''},
            revert_unselected_translations(
                new_translations, current_message, []))

class TestBadSubmission(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def getSubmission(self, good=True):
        original_translations = {0: self.getUniqueString()}
        pofile = self.factory.makePOFile()
        current = self.factory.makeCurrentTranslationMessage(pofile=pofile)
        message = self.factory.makeSuggestion(pofile=pofile)
        if good:
            message.setPOFile(pofile)
        submission = convert_translationmessage_to_submission(
            message=message,
            current_message=current,
            plural_form=0,
            pofile=pofile,
            legal_warning_needed=False)
        return submission

    def test_submission_traversable_guard(self):
        # If a submission doesn't have a sequence greater than 1, it's not
        # traversable.
        bad_sub = self.getSubmission(good=False)
        self.assertEqual(0, bad_sub.translationmessage.sequence)
        self.assertFalse(bad_sub.is_traversable)

        good_sub = self.getSubmission()
        self.assertNotEqual(0, good_sub.translationmessage.sequence)
        self.assertTrue(good_sub.is_traversable)
