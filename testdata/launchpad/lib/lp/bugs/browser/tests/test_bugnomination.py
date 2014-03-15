# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for bug nomination views."""

__metaclass__ = type

import re

import soupmatchers
from testtools.matchers import Not
from zope.component import getUtility

from lp.registry.interfaces.series import SeriesStatus
from lp.services.webapp.interaction import get_current_principal
from lp.services.webapp.interfaces import (
    BrowserNotificationLevel,
    ILaunchBag,
    )
from lp.services.webapp.publisher import canonical_url
from lp.testing import (
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import Contains
from lp.testing.views import create_initialized_view


class TestBugNominationView(TestCaseWithFactory):
    """Tests for BugNominationView."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugNominationView, self).setUp()
        self.distribution = self.factory.makeDistribution()
        owner = self.distribution.owner
        bug_team = self.factory.makeTeam(owner=owner)
        self.bug_worker = self.factory.makePerson()
        with person_logged_in(owner):
            bug_team.addMember(self.bug_worker, owner)
            self.distribution.bug_supervisor = bug_team
            self.distribution.driver = self.factory.makePerson()
        self.bug_task = self.factory.makeBugTask(target=self.distribution)
        launchbag = getUtility(ILaunchBag)
        launchbag.add(self.distribution)
        launchbag.add(self.bug_task)

    def _makeBugSupervisorTeam(self, person, owner, target):
        """Create a bug supervisor team which includes the person argument."""
        members = [self.factory.makePerson() for i in range(2)]
        members.append(person)
        bug_supervisor = self.factory.makeTeam(members=members, owner=owner)
        with person_logged_in(owner):
            target.bug_supervisor = bug_supervisor

    def test_submit_action_bug_supervisor(self):
        # A bug supervisor sees the Nominate action label.
        login_person(self.bug_worker)
        view = create_initialized_view(self.bug_task, name='+nominate')
        action = view.__class__.actions.byname['actions.submit']
        self.assertEqual('Nominate', action.label)

    def test_submit_action_driver(self):
        # A driver sees the Target action label.
        login_person(self.distribution.driver)
        view = create_initialized_view(self.bug_task, name='+nominate')
        action = view.__class__.actions.byname['actions.submit']
        self.assertEqual('Target', action.label)

    def test_submit_action_unauthorised(self):
        # An unauthorised user sees an error on the bug target page.
        login_person(None)
        view = create_initialized_view(self.bug_task, name='+nominate')
        self.assertEqual(
            canonical_url(self.bug_task),
            view.request.response.getHeader('Location'))
        notifications = view.request.notifications
        self.assertEqual(1, len(notifications))
        self.assertEqual(
            BrowserNotificationLevel.ERROR, notifications[0].level)
        self.assertEqual(
            "You do not have permission to nominate this bug.",
            notifications[0].message)

    def test_bug_supervisor_nominate_distribution_does_not_error(self):
        # A bug supervisor should not receive error notifications
        # from the BugNominationView for a distro series.
        person = self.factory.makePerson(name='main-person-test')
        distro = self.factory.makeDistribution()
        owner = distro.owner
        self._makeBugSupervisorTeam(person, owner, distro)
        current_series = self.factory.makeDistroSeries(
            distribution=distro, status=SeriesStatus.CURRENT)
        # Ensure we have some older series so test data better reflects
        # actual usage.
        for index in range(3):
            self.factory.makeDistroSeries(distribution=distro)
        bug = self.factory.makeBug(target=distro, series=current_series)
        series_bugtask = bug.bugtasks[1]
        login_person(person)
        view = create_initialized_view(series_bugtask, name='+nominate')
        self.assertEqual(0, len(view.request.notifications))

    def test_bug_supervisor_nominate_source_package_does_not_error(self):
        # A bug supervisor should not receive error notifications
        # from the BugNominationView for a source package distro series.
        person = self.factory.makePerson(name='main-person-test')
        distro = self.factory.makeDistribution()
        owner = distro.owner
        self._makeBugSupervisorTeam(person, owner, distro)
        current_series = self.factory.makeDistroSeries(
            distribution=distro, status=SeriesStatus.CURRENT)
        # Ensure we have some older series so test data better reflects
        # actual usage.
        for index in range(3):
            self.factory.makeDistroSeries(distribution=distro)
        package = self.factory.makeDistributionSourcePackage(
            distribution=distro)
        bug = self.factory.makeBug(target=package, series=current_series)
        series_bugtask = bug.bugtasks[1]
        login_person(person)
        view = create_initialized_view(series_bugtask, name='+nominate')
        self.assertEqual(0, len(view.request.notifications))

    def test_bug_supervisor_nominate_product_does_not_error(self):
        # A bug supervisor should not receive error notifications
        # from the BugNominationView for a product series.
        person = self.factory.makePerson(name='main-person-test-product')
        product = self.factory.makeProduct()
        owner = product.owner
        self._makeBugSupervisorTeam(person, owner, product)
        current_series = self.factory.makeProductSeries(product=product)
        # Ensure we have some older series so test data better reflects
        # actual usage.
        for index in range(3):
            self.factory.makeProductSeries(product=product)
        bug = self.factory.makeBug(target=product, series=current_series)
        series_bugtask = bug.bugtasks[1]
        login_person(person)
        view = create_initialized_view(series_bugtask, name='+nominate')
        self.assertEqual(0, len(view.request.notifications))

    def test_series_targets_allow_nomination(self):
        # When a bug is already nominated for a series, the view checks
        # for bug supervisor permission on the series correctly.
        person = self.factory.makePerson()
        dsp = self.factory.makeDistributionSourcePackage()
        series = self.factory.makeDistroSeries(distribution=dsp.distribution)
        self._makeBugSupervisorTeam(
            person, dsp.distribution.owner, dsp.distribution)
        bug = self.factory.makeBug(target=dsp)
        with person_logged_in(dsp.distribution.owner):
            nomination = bug.addNomination(dsp.distribution.owner, series)
            nomination.approve(person)
        series_bugtask = bug.bugtasks[1]
        with person_logged_in(person):
            view = create_initialized_view(series_bugtask, name='+nominate')
            self.assertEqual(0, len(view.request.notifications))


class TestBugEditLinks(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    edit_link_matcher = soupmatchers.HTMLContains(
        soupmatchers.Tag(
            'Edit link', 'a',
            attrs={'class': 'assignee-edit',
                   'href': re.compile('\+editstatus$')}))

    def _createBug(self, bug_task_number=1):
        series = self.factory.makeProductSeries()
        bug = self.factory.makeBug(series=series)
        for i in range(bug_task_number):
            self.factory.makeBugTask(bug=bug)
        launchbag = getUtility(ILaunchBag)
        launchbag.add(series.product)
        launchbag.add(bug)
        launchbag.add(bug.default_bugtask)
        return bug

    def test_assignee_edit_link_with_many_bugtasks(self):
        # When the number of bug tasks is >= 10, a link should be
        # displayed to edit the assignee.
        bug = self._createBug(11)
        with person_logged_in(bug.owner):
            page = create_initialized_view(
                bug, name='+bugtasks-and-nominations-table',
                principal=bug.owner).render()
        self.assertThat(page, self.edit_link_matcher)

    def test_assignee_edit_link_with_only_a_few_bugtasks(self):
        # When the number of bug tasks is < 10, editing the assignee is
        # done with a js picker.
        bug = self._createBug(3)
        with person_logged_in(bug.owner):
            page = create_initialized_view(
                bug, name='+bugtasks-and-nominations-table',
                principal=bug.owner).render()
        self.assertThat(page, Not(self.edit_link_matcher))

    def test_assignee_edit_link_no_user_no_link(self):
        # No link is displayed when the request is from an anonymous
        # user.
        bug = self._createBug(11)
        page = create_initialized_view(
            bug, name='+bugtasks-and-nominations-table').render()
        self.assertThat(page, Not(self.edit_link_matcher))


class TestBugNominationEditView(TestCaseWithFactory):
    """Tests for BugNominationEditView."""

    layer = DatabaseFunctionalLayer

    def getNomination(self):
        nomination = self.factory.makeBugNomination(
            target=self.factory.makeProductSeries())
        login_person(nomination.productseries.product.owner)
        return nomination

    def getNominationEditView(self, nomination, form):
        getUtility(ILaunchBag).add(nomination.bug.default_bugtask)
        view = create_initialized_view(
            nomination, name='+editstatus',
            current_request=True,
            principal=get_current_principal(),
            form=form)
        return view

    def assertApproves(self, nomination):
        self.assertEquals(
            302,
            self.getNominationEditView(
                nomination,
                {'field.actions.approve': 'Approve'},
                ).request.response.getStatus())
        self.assertTrue(nomination.isApproved())

    def test_label(self):
        nomination = self.getNomination()
        target = nomination.target
        view = self.getNominationEditView(nomination, {})
        self.assertEqual(
            'Approve or decline nomination for bug #%d in %s' % (
                nomination.bug.id, target.bugtargetdisplayname),
            view.label)

    def test_page_title(self):
        nomination = self.getNomination()
        target = nomination.target
        view = self.getNominationEditView(nomination, {})
        self.assertEqual(
            'Review nomination for %s' % target.bugtargetdisplayname,
            view.page_title)

    def test_next_url(self):
        nomination = self.getNomination()
        view = self.getNominationEditView(nomination, {})
        self.assertEqual(canonical_url(view.current_bugtask), view.next_url)

    def test_approving_twice_is_noop(self):
        nomination = self.getNomination()
        self.assertApproves(nomination)
        self.assertThat(
            self.getNominationEditView(
                nomination,
                {'field.actions.approve': 'Approve'}).render(),
            Contains("This nomination has already been approved."))

    def test_declining_approved_is_noop(self):
        nomination = self.getNomination()
        self.assertApproves(nomination)
        self.assertThat(
            self.getNominationEditView(
                nomination,
                {'field.actions.decline': 'Decline'}).render(),
            Contains("This nomination has already been approved."))
