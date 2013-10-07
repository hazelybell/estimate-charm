# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lp.app.errors import UnexpectedFormData
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    BrowserTestCase,
    login,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    ZopelessDatabaseLayer,
    )
from lp.translations.browser.pofile import POFileTranslateView
from lp.translations.enums import TranslationPermission


class TestPOFileTranslateViewInvalidFiltering(TestCaseWithFactory):
    """Test how POFile views reacts to malformed GET requests.

    Since any number of parameters can be entered throug the URL, the view
    should be robust about them and not produce OOPSes. This is achieved by
    raising UnexpectedFormData which is communicated to the user instead of
    being recorded as an OOPS.
    """
    layer = ZopelessDatabaseLayer
    view_class = POFileTranslateView

    def setUp(self):
        super(TestPOFileTranslateViewInvalidFiltering, self).setUp()
        self.pofile = self.factory.makePOFile('eo')

    def _test_parameter_list(self, parameter_name):
        # When a parameter is entered multiple times in an URL, it will be
        # converted to a list. This view has no such parameters but it must
        # not throw a TypeError when it gets a list.
        form = {parameter_name: ['foo', 'bar']}
        view = self.view_class(self.pofile, LaunchpadTestRequest(form=form))
        self.assertRaises(UnexpectedFormData, view.initialize)

    def test_parameter_list_old_show(self):
        self._test_parameter_list('old_show')

    def test_parameter_list_search(self):
        self._test_parameter_list('search')

    def test_parameter_list_show(self):
        self._test_parameter_list('show')


class TestPOFileTranslateViewDocumentation(TestCaseWithFactory):
    layer = ZopelessDatabaseLayer
    view_class = POFileTranslateView

    def _makeLoggedInUser(self):
        """Create a user, and log in as that user."""
        email = self.factory.getUniqueString() + '@example.com'
        user = self.factory.makePerson(email=email)
        login(email)
        return user

    def _useNonnewTranslator(self):
        """Create a user who's done translations, and log in as that user."""
        user = self._makeLoggedInUser()
        self.factory.makeSuggestion(translator=user)
        return user

    def _makeView(self, pofile=None, request=None):
        """Create a view of type `view_class`.

        :param pofile: An optional `POFile`.  If not given, one will be
            created.
        :param request: An optional `LaunchpadTestRequest`.  If not
            given, one will be created.
        """
        if pofile is None:
            pofile = self.factory.makePOFile('cy')
        if request is None:
            request = LaunchpadTestRequest()
        return self.view_class(pofile, request)

    def _makeTranslationGroup(self, pofile):
        """Set up a translation group for pofile if it doesn't have one."""
        product = pofile.potemplate.productseries.product
        if product.translationgroup is None:
            product.translationgroup = self.factory.makeTranslationGroup()
        return product.translationgroup

    def _makeTranslationTeam(self, pofile):
        """Create a translation team applying to pofile."""
        language = pofile.language.code
        group = self._makeTranslationGroup(pofile)
        return self.factory.makeTranslator(language, group=group)

    def _setGroupGuide(self, pofile):
        """Set the translation group guide URL for pofile."""
        guide = "http://%s.example.com/" % self.factory.getUniqueString()
        self._makeTranslationGroup(pofile).translation_guide_url = guide
        return guide

    def _setTeamGuide(self, pofile, team=None):
        """Set the translation team style guide URL for pofile."""
        guide = "http://%s.example.com/" % self.factory.getUniqueString()
        if team is None:
            team = self._makeTranslationTeam(pofile)
        team.style_guide_url = guide
        return guide

    def _showsIntro(self, bubble_text):
        """Does bubble_text show the intro for new translators?"""
        return "New to translating in Launchpad?" in bubble_text

    def _showsGuides(self, bubble_text):
        """Does bubble_text show translation group/team guidelines?"""
        return "Before translating" in bubble_text

    def test_user_is_new_translator_anonymous(self):
        # An anonymous user is not a new translator.
        self.assertFalse(self._makeView().user_is_new_translator)

    def test_user_is_new_translator_new(self):
        # A user who's never done any translations is a new translator.
        self._makeLoggedInUser()
        self.assertTrue(self._makeView().user_is_new_translator)

    def test_user_is_new_translator_not_new(self):
        # A user who has done translations is not a new translator.
        self._useNonnewTranslator()
        self.assertFalse(self._makeView().user_is_new_translator)

    def test_translation_group_guide_nogroup(self):
        # If there's no translation group, there is no
        # translation_group_guide.
        self.assertIs(None, self._makeView().translation_group_guide)

    def test_translation_group_guide_noguide(self):
        # The translation group may not have a translation guide.
        pofile = self.factory.makePOFile('ca')
        self._makeTranslationGroup(pofile)

        view = self._makeView(pofile=pofile)
        self.assertIs(None, view.translation_group_guide)

    def test_translation_group_guide(self):
        # translation_group_guide returns the translation group's style
        # guide URL if there is one.
        pofile = self.factory.makePOFile('ce')
        url = self._setGroupGuide(pofile)

        view = self._makeView(pofile=pofile)
        self.assertEqual(url, view.translation_group_guide)

    def test_translation_team_guide_nogroup(self):
        # If there is no translation group, there is no translation team
        # style guide.
        self.assertIs(None, self._makeView().translation_team_guide)

    def test_translation_team_guide_noteam(self):
        # If there is no translation team for this language, there is on
        # translation team style guide.
        pofile = self.factory.makePOFile('ch')
        self._makeTranslationGroup(pofile)

        view = self._makeView(pofile=pofile)
        self.assertIs(None, view.translation_team_guide)

    def test_translation_team_guide_noguide(self):
        # A translation team may not have a translation style guide.
        pofile = self.factory.makePOFile('co')
        self._makeTranslationTeam(pofile)

        view = self._makeView(pofile=pofile)
        self.assertIs(None, view.translation_team_guide)

    def test_translation_team_guide(self):
        # translation_team_guide returns the translation team's
        # style guide, if there is one.
        pofile = self.factory.makePOFile('cy')
        url = self._setTeamGuide(pofile)

        view = self._makeView(pofile=pofile)
        self.assertEqual(url, view.translation_team_guide)

    def test_documentation_link_bubble_empty(self):
        # If the user is not a new translator and neither a translation
        # group nor a team style guide applies, the documentation bubble
        # is empty.
        pofile = self.factory.makePOFile('da')
        self._useNonnewTranslator()

        view = self._makeView(pofile=pofile)
        self.assertEqual('', view.documentation_link_bubble)
        self.assertFalse(self._showsIntro(view.documentation_link_bubble))
        self.assertFalse(self._showsGuides(view.documentation_link_bubble))

    def test_documentation_link_bubble_intro(self):
        # New users are shown an intro link.
        self._makeLoggedInUser()

        view = self._makeView()
        self.assertTrue(self._showsIntro(view.documentation_link_bubble))
        self.assertFalse(self._showsGuides(view.documentation_link_bubble))

    def test_documentation_link_bubble_group_guide(self):
        # A translation group's guide shows up in the documentation
        # bubble.
        pofile = self.factory.makePOFile('de')
        self._setGroupGuide(pofile)

        view = self._makeView(pofile=pofile)
        self.assertFalse(self._showsIntro(view.documentation_link_bubble))
        self.assertTrue(self._showsGuides(view.documentation_link_bubble))

    def test_documentation_link_bubble_team_guide(self):
        # A translation team's style guide shows up in the documentation
        # bubble.
        pofile = self.factory.makePOFile('de')
        self._setTeamGuide(pofile)

        view = self._makeView(pofile=pofile)
        self.assertFalse(self._showsIntro(view.documentation_link_bubble))
        self.assertTrue(self._showsGuides(view.documentation_link_bubble))

    def test_documentation_link_bubble_both_guides(self):
        # The documentation bubble can show both a translation group's
        # guidelines and a translation team's style guide.
        pofile = self.factory.makePOFile('dv')
        self._setGroupGuide(pofile)
        self._setTeamGuide(pofile)

        view = self._makeView(pofile=pofile)
        self.assertFalse(self._showsIntro(view.documentation_link_bubble))
        self.assertTrue(self._showsGuides(view.documentation_link_bubble))
        self.assertIn(" and ", view.documentation_link_bubble)

    def test_documentation_link_bubble_shows_all(self):
        # So in all, the bubble can show 3 different documentation
        # links.
        pofile = self.factory.makePOFile('dz')
        self._makeLoggedInUser()
        self._setGroupGuide(pofile)
        self._setTeamGuide(pofile)

        view = self._makeView(pofile=pofile)
        self.assertTrue(self._showsIntro(view.documentation_link_bubble))
        self.assertTrue(self._showsGuides(view.documentation_link_bubble))
        self.assertIn(" and ", view.documentation_link_bubble)

    def test_documentation_link_bubble_escapes_group_title(self):
        # Translation group titles in the bubble are HTML-escaped.
        pofile = self.factory.makePOFile('eo')
        group = self._makeTranslationGroup(pofile)
        self._setGroupGuide(pofile)
        group.title = "<blink>X</blink>"

        view = self._makeView(pofile=pofile)
        self.assertIn(
            "&lt;blink&gt;X&lt;/blink&gt;", view.documentation_link_bubble)
        self.assertNotIn(group.title, view.documentation_link_bubble)

    def test_documentation_link_bubble_escapes_team_name(self):
        # Translation team names in the bubble are HTML-escaped.
        pofile = self.factory.makePOFile('ie')
        translator_entry = self._makeTranslationTeam(pofile)
        self._setTeamGuide(pofile, team=translator_entry)
        translator_entry.translator.displayname = "<blink>Y</blink>"

        view = self._makeView(pofile=pofile)
        self.assertIn(
            "&lt;blink&gt;Y&lt;/blink&gt;", view.documentation_link_bubble)
        self.assertNotIn(
            translator_entry.translator.displayname,
            view.documentation_link_bubble)

    def test_documentation_link_bubble_escapes_language_name(self):
        # Language names in the bubble are HTML-escaped.
        language = self.factory.makeLanguage(
            language_code='wtf', name="<blink>Z</blink>")
        pofile = self.factory.makePOFile('wtf')
        self._setGroupGuide(pofile)
        self._setTeamGuide(pofile)

        view = self._makeView(pofile=pofile)
        self.assertIn(
            "&lt;blink&gt;Z&lt;/blink&gt;", view.documentation_link_bubble)
        self.assertNotIn(language.englishname, view.documentation_link_bubble)


class TestBrowser(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def test_unwritable_translation_credits(self):
        """Text of credits should be sane for non-editors."""
        # Make the user a translator so they can see translations.
        self.factory.makeTranslator(person=self.user)
        pofile = self.factory.makePOFile()
        # Restrict translations so that the translator cannot change it.
        product = pofile.potemplate.productseries.product
        with person_logged_in(product.owner):
            product.translationpermission = TranslationPermission.CLOSED
        # Add credits so that they show in the UI
        credits = self.factory.makePOTMsgSet(
            potemplate=pofile.potemplate, singular='translator-credits')
        browser = self.getViewBrowser(pofile)
        self.assertNotIn('This is a dummy translation', browser.contents)
        self.assertIn('(no translation yet)', browser.contents)

    def test_anonymous_translation_credits(self):
        """Credits should be hidden for non-logged-in users."""
        pofile = self.factory.makePOFile()
        # Restrict translations so that the translator cannot change it.
        product = pofile.potemplate.productseries.product
        # Add credits so that they show in the UI
        credits = self.factory.makePOTMsgSet(
            potemplate=pofile.potemplate, singular='translator-credits')
        browser = self.getViewBrowser(pofile, no_login=True)
        self.assertTextMatchesExpressionIgnoreWhitespace(
            'To prevent privacy issues, this translation is not available to'
            ' anonymous users', browser.contents)
