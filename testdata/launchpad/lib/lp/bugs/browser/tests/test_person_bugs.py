# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version (see the file LICENSE).

"""Unit tests for person bug views."""

__metaclass__ = type

from lp.app.browser.tales import MenuAPI
from lp.app.errors import UnexpectedFormData
from lp.bugs.browser import person
from lp.bugs.interfaces.bugtask import BugTaskStatus
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.views import create_initialized_view


class PersonBugsMenuTestCase(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_user(self):
        user = self.factory.makePerson()
        menu_api = MenuAPI(user)
        menu_api._selectedfacetname = 'bugs'
        enabled_links = sorted(
            link.name for link in menu_api.navigation.values()
            if link.enabled)
        expected_links = [
            'affectingbugs', 'assignedbugs', 'commentedbugs',
            'relatedbugs', 'reportedbugs', 'softwarebugs', 'subscribedbugs']
        self.assertEqual(expected_links, enabled_links)

    def test_team(self):
        team = self.factory.makeTeam()
        menu_api = MenuAPI(team)
        menu_api._selectedfacetname = 'bugs'
        enabled_links = sorted(
            link.name for link in menu_api.navigation.values()
            if link.enabled)
        expected_links = [
            'assignedbugs', 'relatedbugs', 'softwarebugs', 'subscribedbugs']
        self.assertEqual(expected_links, enabled_links)


class TestBugSubscriberPackageBugsSearchListingView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugSubscriberPackageBugsSearchListingView, self).setUp()
        self.person = self.factory.makePerson()
        self.distribution = self.factory.makeDistribution()
        self.spn = self.factory.makeSourcePackageName()
        self.dsp = self.distribution.getSourcePackage(self.spn)

    def makeForm(self, package_name, distribution_name):
        return {
            'field.sourcepackagename': package_name,
            'field.distribution': distribution_name,
            'search': 'Search',
            }

    def test_current_package_known(self):
        # current_package contains the distribution source package that
        # matches the source package name.
        form = self.makeForm(self.spn.name, self.distribution.name)
        view = create_initialized_view(
            self.person, name='+packagebugs-search', form=form)
        self.assertEqual(self.dsp, view.current_package)

    def test_current_package_missing_distribution(self):
        # UnexpectedFormData is raised if the distribution is not provided.
        form = self.makeForm(self.spn.name, '')
        self.assertRaises(
            UnexpectedFormData, create_initialized_view, self.person,
            name='+packagebugs-search', form=form)

    def test_current_package_unknown_distribution(self):
        # UnexpectedFormData is raised if the distribution is not known.
        form = self.makeForm(self.spn.name, 'unknown-distribution')
        self.assertRaises(
            UnexpectedFormData, create_initialized_view, self.person,
            name='+packagebugs-search', form=form)

    def test_current_package_missing_sourcepackagename(self):
        # UnexpectedFormData is raised if the package name is not provided.
        form = self.makeForm('', self.distribution.name)
        self.assertRaises(
            UnexpectedFormData, create_initialized_view, self.person,
            name='+packagebugs-search', form=form)

    def test_current_package_unknown_sourcepackagename(self):
        # UnexpectedFormData is raised if the package name is not known.
        form = self.makeForm('unknown-package', self.distribution.name)
        self.assertRaises(
            UnexpectedFormData, create_initialized_view, self.person,
            name='+packagebugs-search', form=form)

    def test_one_call_of_canonical_url(self):
        # canonical_url(self.context) is frequently needed to build
        # URLs pointing to specific search listings in the
        # +packagebugs page. These URLs are returned, among other
        # data, by
        # BugSubscriberPackageBugsSearchListingView.package_bug_counts
        # This call is relatively expensive, hence a cached value is
        # used.
        view = create_initialized_view(self.person, name='+packagebugs')
        self.factory.makeBug(target=self.dsp, status=BugTaskStatus.INPROGRESS)
        with person_logged_in(self.person):
            self.dsp.addSubscription(self.person, subscribed_by=self.person)
        # Monkey-patch the version of canonical_url used by the registry
        # person browser module.
        fake_canonical_url = FakeMethod(result='')
        real_canonical_url = person.canonical_url
        person.canonical_url = fake_canonical_url
        try:
            view.package_bug_counts
            self.assertEqual(1, fake_canonical_url.call_count)
        finally:
            person.canonical_url = real_canonical_url

    def test_package_bugs_context_description(self):
        # BugSubscriberPackageBugsSearchListingView.context_description
        # returns the string $package in $distribution related to $person
        form = self.makeForm(self.spn.name, self.distribution.name)
        view = create_initialized_view(
            self.person, name='+packagebugs-search', form=form)
        expected = 'in %s in %s related to %s' % (
            self.spn.name, self.distribution.displayname,
            self.person.displayname)
        self.assertEqual(expected, view.context_description)
