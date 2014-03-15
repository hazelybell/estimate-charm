# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for feature rule editor"""

__metaclass__ = type


from testtools.matchers import Not
from zope.component import getUtility
from zope.security.interfaces import Unauthorized

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.services.features.flags import (
    documented_flags,
    flag_info,
    NullFeatureController,
    undocumented_flags,
    value_domain_info,
    )
from lp.services.features.scopes import (
    HANDLERS,
    undocumented_scopes,
    )
from lp.services.webapp import canonical_url
from lp.services.webapp.interfaces import ILaunchpadRoot
from lp.testing import (
    BrowserTestCase,
    person_logged_in,
    TestCase,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import Contains


class TestFeatureControlPage(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def getFeatureInfoUrl(self):
        """Find the URL to the feature info page."""
        root = getUtility(ILaunchpadRoot)
        return canonical_url(root, view_name='+feature-info')

    def getUserBrowserAsAdmin(self):
        """Make a new TestBrowser logged in as an admin user."""
        admin_team = getUtility(ILaunchpadCelebrities).admin
        return self.getUserBrowserAsTeamMember([admin_team])

    def getUserBrowserAsTeamMember(self, teams):
        """Make a TestBrowser authenticated as a team member."""
        user = self.factory.makePerson()
        for team in teams:
            with person_logged_in(team.teamowner):
                team.addMember(user, reviewer=team.teamowner)
        return self.getUserBrowser(url=None, user=user)

    def test_feature_documentation_displayed(self):
        """The feature flag documentation is displayed on the page."""
        browser = self.getUserBrowserAsAdmin()
        browser.open(self.getFeatureInfoUrl())
        for record in flag_info:
            for item in record[:4]:
                self.assertThat(browser.contents, Contains(item))

    def test_value_domain_documentation_displayed(self):
        """The value domain documentation is displayed on the page."""
        browser = self.getUserBrowserAsAdmin()
        browser.open(self.getFeatureInfoUrl())
        for record in value_domain_info:
            for item in record:
                self.assertThat(browser.contents, Contains(item))

    def test_scope_documentation_displayed(self):
        """The scope documentation is displayed on the page."""
        browser = self.getUserBrowserAsAdmin()
        browser.open(self.getFeatureInfoUrl())
        for pattern in [handler.pattern for handler in HANDLERS]:
            self.assertThat(browser.contents, Contains(pattern))

    def test_undocumented_features_displayed(self):
        """The undocumented feature flag names are displayed on the page."""
        browser = self.getUserBrowserAsAdmin()
        # Stash away any already encountered undocumented flags.
        saved_undocumented = undocumented_flags.copy()
        undocumented_flags.clear()
        undocumented_flags.update(['first', 'second'])
        browser.open(self.getFeatureInfoUrl())
        # Put the saved undocumented flags back.
        undocumented_flags.clear()
        undocumented_flags.update(saved_undocumented)
        # Are the (injected) undocumented flags shown in the page?
        self.assertThat(browser.contents, Contains('first'))
        self.assertThat(browser.contents, Contains('second'))

    def test_undocumented_scope_displayed(self):
        """The undocumented scope names are displayed on the page."""
        browser = self.getUserBrowserAsAdmin()
        # Stash away any already encountered undocumented scopes.
        saved_undocumented = undocumented_scopes.copy()
        undocumented_scopes.clear()
        undocumented_scopes.update(['first', 'second'])
        browser.open(self.getFeatureInfoUrl())
        # Put the saved undocumented scopes back.
        undocumented_scopes.clear()
        undocumented_scopes.update(saved_undocumented)
        # Are the (injected) undocumented scopes shown in the page?
        self.assertThat(browser.contents, Contains('first'))
        self.assertThat(browser.contents, Contains('second'))

    def test_feature_info_anonymous_unauthorized(self):
        """Anonymous users can not view the feature flag info page."""
        browser = self.getUserBrowser()
        self.assertRaises(Unauthorized,
            browser.open,
            self.getFeatureInfoUrl())

    def test_feature_rules_plebian_unauthorized(self):
        """Unauthorized logged-in users can't view the info page."""
        browser = self.getUserBrowserAsTeamMember([])
        self.assertRaises(Unauthorized,
            browser.open,
            self.getFeatureInfoUrl())


class TestUndocumentedFeatureFlags(TestCase):
    """Test the code that records accessing of undocumented feature flags."""

    def setUp(self):
        super(TestUndocumentedFeatureFlags, self).setUp()
        # Stash away any already encountered undocumented flags.
        saved_undocumented = undocumented_flags.copy()
        saved_documented = documented_flags.copy()
        undocumented_flags.clear()
        documented_flags.clear()

        def clean_up_undocumented_flags():
            # Put the saved undocumented flags back.
            undocumented_flags.clear()
            documented_flags.clear()
            undocumented_flags.update(saved_undocumented)
            documented_flags.update(saved_documented)

        self.addCleanup(clean_up_undocumented_flags)

    def test_reading_undocumented_feature_flags(self):
        """Reading undocumented feature flags records them as undocumented."""
        controller = NullFeatureController()
        # This test assumes there is no flag named "does-not-exist".
        assert 'does-not-exist' not in documented_flags
        controller.getFlag('does-not-exist')
        self.assertThat(undocumented_flags, Contains('does-not-exist'))

    def test_reading_documented_feature_flags(self):
        """Reading documented flags does not record them as undocumented."""
        controller = NullFeatureController()
        # Make sure there is no flag named "documented-flag-name" before we
        # start testing.
        assert 'documented-flag-name' not in documented_flags
        documented_flags.update(['documented-flag-name'])
        controller.getFlag('documented-flag-name')
        self.assertThat(
            undocumented_flags,
            Not(Contains('documented-flag-name')))
