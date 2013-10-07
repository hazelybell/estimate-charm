# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for feature rule editor"""

__metaclass__ = type

from textwrap import dedent

from testtools.matchers import Equals
from zope.component import getUtility
from zope.security.interfaces import Unauthorized

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.services.features.browser.edit import FeatureControlView
from lp.services.features.changelog import ChangeLog
from lp.services.features.rulesource import StormFeatureRuleSource
from lp.services.webapp import canonical_url
from lp.services.webapp.escaping import html_escape
from lp.services.webapp.interfaces import ILaunchpadRoot
from lp.testing import (
    BrowserTestCase,
    person_logged_in,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import Contains
from lp.testing.pages import (
    find_main_content,
    find_tag_by_id,
    )


class FauxForm:
    """The simplest fake form, used for testing."""
    context = None


class TestFeatureControlPage(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def getUserBrowserAsTeamMember(self, teams):
        """Make a TestBrowser authenticated as a team member.

        :param teams: List of teams to add the new user to.
        """
        self.user = self.factory.makePerson()
        for team in teams:
            with person_logged_in(team.teamowner):
                team.addMember(self.user, reviewer=team.teamowner)
        return self.getUserBrowser(url=None, user=self.user)

    def getUserBrowserAsAdmin(self):
        """Make a new TestBrowser logged in as an admin user."""
        admin_team = getUtility(ILaunchpadCelebrities).admin
        return self.getUserBrowserAsTeamMember([admin_team])

    def getFeatureRulesViewURL(self):
        root = getUtility(ILaunchpadRoot)
        return canonical_url(root, view_name='+feature-rules')

    def getFeatureRulesEditURL(self):
        root = getUtility(ILaunchpadRoot)
        return canonical_url(root, view_name='+feature-rules')

    def test_feature_page_default_value(self):
        """No rules in the sampledata gives no content in the page"""
        browser = self.getUserBrowserAsAdmin()
        browser.open(self.getFeatureRulesViewURL())
        textarea = browser.getControl(name="field.feature_rules")
        # and by default, since there are no rules in the sample data, it's
        # empty
        self.assertThat(textarea.value, Equals(''))

    def test_feature_page_from_database(self):
        StormFeatureRuleSource().setAllRules([
            ('ui.icing', 'default', 100, u'3.0'),
            ('ui.icing', 'beta_user', 300, u'4.0'),
            ])
        browser = self.getUserBrowserAsAdmin()
        browser.open(self.getFeatureRulesViewURL())
        textarea = browser.getControl(name="field.feature_rules")
        self.assertThat(
            textarea.value.replace('\r', ''),
            Equals(
                "ui.icing\tbeta_user\t300\t4.0\n"
                "ui.icing\tdefault\t100\t3.0\n"))

    def test_feature_rules_anonymous_unauthorized(self):
        browser = self.getUserBrowser()
        self.assertRaises(Unauthorized,
            browser.open,
            self.getFeatureRulesViewURL())

    def test_feature_rules_plebian_unauthorized(self):
        """Logged in, but not a member of any interesting teams."""
        browser = self.getUserBrowserAsTeamMember([])
        self.assertRaises(Unauthorized,
            browser.open,
            self.getFeatureRulesViewURL())

    def test_feature_page_can_view(self):
        """User that can only view the rules do not see the form."""
        browser = self.getUserBrowserAsTeamMember(
            [getUtility(ILaunchpadCelebrities).registry_experts])
        browser.open(self.getFeatureRulesViewURL())
        content = find_main_content(browser.contents)
        self.assertEqual(
            None, find_tag_by_id(content, 'field.feature_rules'))
        self.assertEqual(
            None, find_tag_by_id(content, 'field.actions.change'))
        self.assertTrue(
            find_tag_by_id(content, 'feature-rules'))

    def test_feature_page_submit_changes(self):
        """Submitted changes show up in the db."""
        browser = self.getUserBrowserAsAdmin()
        browser.open(self.getFeatureRulesEditURL())
        new_value = 'beta_user some_key 10 some value with spaces'
        textarea = browser.getControl(name="field.feature_rules")
        textarea.value = new_value
        browser.getControl(name="field.comment").value = 'Bob is testing.'
        browser.getControl(name="field.actions.change").click()
        self.assertThat(
            list(StormFeatureRuleSource().getAllRulesAsTuples()),
            Equals([
                ('beta_user', 'some_key', 10, 'some value with spaces'),
                ]))
        changes = list(ChangeLog.get())
        self.assertEqual(1, len(changes))
        self.assertEqual(
            '+beta_user\tsome_key\t10\tsome value with spaces',
            changes[0].diff)
        self.assertEqual('Bob is testing.', changes[0].comment)
        self.assertEqual(self.user, changes[0].person)

    def test_change_message(self):
        """Submitting shows a message that the changes have been applied."""
        browser = self.getUserBrowserAsAdmin()
        browser.open(self.getFeatureRulesEditURL())
        textarea = browser.getControl(name="field.feature_rules")
        textarea.value = 'beta_user some_key 10 some value with spaces'
        browser.getControl(name="field.comment").value = 'comment'
        browser.getControl(name="field.actions.change").click()
        self.assertThat(
            browser.contents,
            Contains('Your changes have been applied'))

    def test_change_diff(self):
        """Submitting shows a diff of the changes."""
        browser = self.getUserBrowserAsAdmin()
        browser.open(self.getFeatureRulesEditURL())
        browser.getControl(name="field.feature_rules").value = (
            'beta_user some_key 10 some value with spaces')
        browser.getControl(name="field.comment").value = 'comment'
        browser.getControl(name="field.actions.change").click()
        browser.getControl(name="field.comment").value = 'comment'
        browser.getControl(name="field.feature_rules").value = (
            'beta_user some_key 10 another value with spaces')
        browser.getControl(name="field.actions.change").click()
        # The diff is formatted nicely using CSS.
        self.assertThat(
            browser.contents,
            Contains('<td class="diff-added text">'))
        # Removed rules are displayed as being removed.
        self.assertThat(
            browser.contents.replace('\t', ' '),
            Contains('-beta_user some_key 10 some value with spaces'))
        # Added rules are displayed as being added.
        self.assertThat(
            browser.contents.replace('\t', ' '),
            Contains('+beta_user some_key 10 another value with spaces'))

    def test_change_logging_note(self):
        """When submitting changes the name of the logger is shown."""
        browser = self.getUserBrowserAsAdmin()
        browser.open(self.getFeatureRulesEditURL())
        browser.getControl(name="field.feature_rules").value = (
            'beta_user some_key 10 some value with spaces')
        browser.getControl(name="field.comment").value = 'comment'
        browser.getControl(name="field.actions.change").click()
        self.assertThat(
            browser.contents,
            Contains('logged by the lp.services.features logger'))

    def test_feature_page_submit_change_to_empty(self):
        """Correctly handle submitting an empty value."""
        # Zope has the quirk of conflating empty with absent; make sure we
        # handle it properly.
        browser = self.getUserBrowserAsAdmin()
        browser.open(self.getFeatureRulesEditURL())
        new_value = ''
        textarea = browser.getControl(name="field.feature_rules")
        textarea.value = new_value
        browser.getControl(name="field.comment").value = 'comment'
        browser.getControl(name="field.actions.change").click()
        self.assertThat(
            list(StormFeatureRuleSource().getAllRulesAsTuples()),
            Equals([]))

    def test_feature_page_submit_change_when_unauthorized(self):
        """Correctly handling attempted value changes when not authorized."""
        # The action is not available to unauthorized users.
        view = FeatureControlView(None, None)
        self.assertFalse(view.change_action.available())

    def test_error_for_duplicate_priority(self):
        """Duplicate priority values for a flag result in a nice error."""
        browser = self.getUserBrowserAsAdmin()
        browser.open(self.getFeatureRulesEditURL())
        textarea = browser.getControl(name="field.feature_rules")
        textarea.value = dedent("""\
            key foo 10 foo
            key bar 10 bar
            """)
        browser.getControl(name="field.comment").value = 'comment'
        browser.getControl(name="field.actions.change").click()
        self.assertThat(
            browser.contents,
            Contains(
                html_escape(
                    'Invalid rule syntax: duplicate priority for flag "key": '
                    '10')))
