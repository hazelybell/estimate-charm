# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests related to bug nominations for an object with a bug supervisor."""

__metaclass__ = type

from lp.bugs.interfaces.bugnomination import (
    NominationError,
    NominationSeriesObsoleteError,
    )
from lp.registry.interfaces.series import SeriesStatus
from lp.testing import (
    celebrity_logged_in,
    login,
    login_person,
    logout,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class AddNominationTestMixin:
    """Test case mixin for IBug.addNomination."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(AddNominationTestMixin, self).setUp()
        login('foo.bar@canonical.com')
        self.user = self.factory.makePerson(name='ordinary-user')
        self.bug_supervisor = self.factory.makePerson(name='no-ordinary-user')
        self.owner = self.factory.makePerson(name='extraordinary-user')
        self.setUpTarget()
        logout()

    def tearDown(self):
        logout()
        super(AddNominationTestMixin, self).tearDown()

    def test_user_addNominationFor_series(self):
        # A bug may not be nominated for a series of a product with an
        # existing task by just anyone.
        login_person(self.user)
        self.assertRaises(NominationError,
            self.bug.addNomination, self.user, self.series)

    def test_bugsupervisor_addNominationFor_series(self):
        # A bug may be nominated for a series of a product with an
        # exisiting task by the product's bug supervisor.
        login_person(self.bug_supervisor)
        self.bug.addNomination(self.bug_supervisor, self.series)
        self.assertTrue(len(self.bug.getNominations()), 1)

    def test_bugsupervisor_addNominationFor_with_existing_nomination(self):
        # A bug cannot be nominated twice for the same series.
        login_person(self.bug_supervisor)
        self.bug.addNomination(self.bug_supervisor, self.series)
        self.assertTrue(len(self.bug.getNominations()), 1)
        self.assertRaises(NominationError,
            self.bug.addNomination, self.user, self.series)

    def test_owner_addNominationFor_series(self):
        # A bug may be nominated for a series of a product with an
        # exisiting task by the product's owner.
        login_person(self.owner)
        self.bug.addNomination(self.owner, self.series)
        self.assertTrue(len(self.bug.getNominations()), 1)


class TestBugAddNominationProductSeries(
    AddNominationTestMixin, TestCaseWithFactory):
    """Test IBug.addNomination for IProductSeries nominations."""

    def setUpTarget(self):
        self.product = self.factory.makeProduct(
            official_malone=True, bug_supervisor=self.bug_supervisor,
            owner=self.owner)
        self.series = self.factory.makeProductSeries(product=self.product)
        self.bug = self.factory.makeBug(target=self.product)
        self.milestone = self.factory.makeMilestone(productseries=self.series)


class TestBugAddNominationDistroSeries(
    AddNominationTestMixin, TestCaseWithFactory):
    """Test IBug.addNomination for IDistroSeries nominations."""

    def setUpTarget(self):
        self.distro = self.factory.makeDistribution(
            bug_supervisor=self.bug_supervisor,
            owner=self.owner)
        self.series = self.factory.makeDistroSeries(distribution=self.distro)
        # The factory can't create a distro bug directly.
        self.bug = self.factory.makeBug()
        self.bug.addTask(self.bug_supervisor, self.distro)
        self.milestone = self.factory.makeMilestone(
            distribution=self.distro)

    def test_bugsupervisor_addNominationFor_with_obsolete_distroseries(self):
        # A bug cannot be nominated for an obsolete series.
        with celebrity_logged_in('admin'):
            self.series.status = SeriesStatus.OBSOLETE
        login_person(self.bug_supervisor)
        self.assertRaises(NominationSeriesObsoleteError,
            self.bug.addNomination, self.user, self.series)
