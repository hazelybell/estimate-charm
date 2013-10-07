# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests related to bug nominations."""

__metaclass__ = type

from zope.component import getUtility

from lp.app.errors import NotFoundError
from lp.bugs.interfaces.bugnomination import (
    BugNominationStatus,
    BugNominationStatusError,
    IBugNomination,
    IBugNominationSet,
    )
from lp.soyuz.interfaces.publishing import PackagePublishingStatus
from lp.testing import (
    celebrity_logged_in,
    login,
    logout,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class BugNominationTestCase(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_implementation(self):
        # BugNomination implements IBugNomination.
        target = self.factory.makeSourcePackage()
        series = target.distroseries
        bug = self.factory.makeBug(target=target.distribution_sourcepackage)
        with person_logged_in(series.distribution.owner):
            nomination = bug.addNomination(series.distribution.owner, series)
            self.assertProvides(nomination, IBugNomination)
        self.assertEqual(series.distribution.owner, nomination.owner)
        self.assertEqual(bug, nomination.bug)
        self.assertEqual(series, nomination.distroseries)
        self.assertIsNone(nomination.productseries)
        self.assertEqual(BugNominationStatus.PROPOSED, nomination.status)
        self.assertIsNone(nomination.date_decided)
        self.assertEqual('UTC', nomination.date_created.tzname())

    def test_target_distroseries(self):
        # The target property returns the distroseries if it is not None.
        target = self.factory.makeSourcePackage()
        series = target.distroseries
        with person_logged_in(series.distribution.owner):
            nomination = self.factory.makeBugNomination(target=target)
        self.assertEqual(series, nomination.distroseries)
        self.assertEqual(series, nomination.target)

    def test_target_productseries(self):
        # The target property returns the productseries if it is not None.
        series = self.factory.makeProductSeries()
        with person_logged_in(series.product.owner):
            nomination = self.factory.makeBugNomination(target=series)
        self.assertEqual(series, nomination.productseries)
        self.assertEqual(series, nomination.target)

    def test_status_proposed(self):
        # isProposed is True when the status is PROPOSED.
        series = self.factory.makeProductSeries()
        with person_logged_in(series.product.owner):
            nomination = self.factory.makeBugNomination(target=series)
        self.assertEqual(BugNominationStatus.PROPOSED, nomination.status)
        self.assertIs(True, nomination.isProposed())
        self.assertIs(False, nomination.isDeclined())
        self.assertIs(False, nomination.isApproved())

    def test_status_declined(self):
        # isDeclined is True when the status is DECLINED.
        series = self.factory.makeProductSeries()
        with person_logged_in(series.product.owner):
            nomination = self.factory.makeBugNomination(target=series)
            nomination.decline(series.product.owner)
        self.assertEqual(BugNominationStatus.DECLINED, nomination.status)
        self.assertIs(True, nomination.isDeclined())
        self.assertIs(False, nomination.isProposed())
        self.assertIs(False, nomination.isApproved())

    def test_status_approved(self):
        # isApproved is True when the status is APPROVED.
        series = self.factory.makeProductSeries()
        with person_logged_in(series.product.owner):
            nomination = self.factory.makeBugNomination(target=series)
            nomination.approve(series.product.owner)
        self.assertEqual(BugNominationStatus.APPROVED, nomination.status)
        self.assertIs(True, nomination.isApproved())
        self.assertIs(False, nomination.isDeclined())
        self.assertIs(False, nomination.isProposed())

    def test_decline(self):
        # The decline method updates the status and other data.
        series = self.factory.makeProductSeries()
        with person_logged_in(series.product.owner):
            nomination = self.factory.makeBugNomination(target=series)
            bug_tasks = nomination.bug.bugtasks
            nomination.decline(series.product.owner)
        self.assertEqual(BugNominationStatus.DECLINED, nomination.status)
        self.assertIsNotNone(nomination.date_decided)
        self.assertEqual(series.product.owner, nomination.decider)
        self.assertContentEqual(bug_tasks, nomination.bug.bugtasks)

    def test_decline_error(self):
        # A nomination cannot be declined if it is approved.
        series = self.factory.makeProductSeries()
        with person_logged_in(series.product.owner):
            nomination = self.factory.makeBugNomination(target=series)
            nomination.approve(series.product.owner)
            self.assertRaises(
                BugNominationStatusError,
                nomination.decline, series.product.owner)

    def test_approve_productseries(self):
        # Approving a product nomination creates a productseries bug task.
        series = self.factory.makeProductSeries()
        with person_logged_in(series.product.owner):
            nomination = self.factory.makeBugNomination(target=series)
            bug_tasks = nomination.bug.bugtasks
            nomination.approve(series.product.owner)
        self.assertEqual(BugNominationStatus.APPROVED, nomination.status)
        self.assertIsNotNone(nomination.date_decided)
        self.assertEqual(series.product.owner, nomination.decider)
        expected_targets = [bt.target for bt in bug_tasks] + [series]
        self.assertContentEqual(
            expected_targets, [bt.target for bt in nomination.bug.bugtasks])

    def test_approve_distroseries_source_package(self):
        # Approving a package nomination creates a distroseries
        # source package bug task.
        target = self.factory.makeSourcePackage()
        series = target.distroseries
        with person_logged_in(series.distribution.owner):
            nomination = self.factory.makeBugNomination(target=target)
            bug_tasks = nomination.bug.bugtasks
            nomination.approve(series.distribution.owner)
        self.assertEqual(BugNominationStatus.APPROVED, nomination.status)
        self.assertIsNotNone(nomination.date_decided)
        self.assertEqual(series.distribution.owner, nomination.decider)
        expected_targets = [bt.target for bt in bug_tasks] + [target]
        self.assertContentEqual(
            expected_targets, [bt.target for bt in nomination.bug.bugtasks])

    def test_approve_distroseries_source_package_many(self):
        # Approving a package nomination creates a distroseries
        # source package bug task for each affect package in the same distro.
        # See bug 110195 which argues this is wrong.
        target = self.factory.makeSourcePackage()
        series = target.distroseries
        target2 = self.factory.makeSourcePackage(distroseries=series)
        bug = self.factory.makeBug(target=target.distribution_sourcepackage)
        self.factory.makeBugTask(
            bug=bug, target=target2.distribution_sourcepackage)
        bug_tasks = bug.bugtasks
        with person_logged_in(series.distribution.owner):
            nomination = self.factory.makeBugNomination(bug=bug, target=target)
            nomination.approve(series.distribution.owner)
        expected_targets = [bt.target for bt in bug_tasks] + [target, target2]
        self.assertContentEqual(
            expected_targets, [bt.target for bt in bug.bugtasks])

    def test_approve_twice(self):
        # Approving a nomination twice is a no-op.
        series = self.factory.makeProductSeries()
        with person_logged_in(series.product.owner):
            nomination = self.factory.makeBugNomination(target=series)
            nomination.approve(series.product.owner)
        self.assertEqual(BugNominationStatus.APPROVED, nomination.status)
        date_decided = nomination.date_decided
        self.assertIsNotNone(date_decided)
        self.assertEqual(series.product.owner, nomination.decider)
        with celebrity_logged_in('admin') as admin:
            nomination.approve(admin)
        self.assertEqual(date_decided, nomination.date_decided)
        self.assertEqual(series.product.owner, nomination.decider)

    def test_approve_distroseries_source_package_then_retarget(self):
        # Retargeting a bugtarget with and approved nomination also
        # retargets the master bug target.
        target = self.factory.makeSourcePackage()
        series = target.distroseries
        with person_logged_in(series.distribution.owner):
            nomination = self.factory.makeBugNomination(target=target)
            nomination.approve(series.distribution.owner)
        target2 = self.factory.makeSourcePackage(
            distroseries=series, publish=True)
        product_target = nomination.bug.bugtasks[0].target
        expected_targets = [
            product_target, target2, target2.distribution_sourcepackage]
        bug_task = nomination.bug.bugtasks[-1]
        with person_logged_in(series.distribution.owner):
            bug_task.transitionToTarget(target2, series.distribution.owner)
        self.assertContentEqual(
            expected_targets, [bt.target for bt in nomination.bug.bugtasks])


class CanBeNominatedForTestMixin:
    """Test case mixin for IBug.canBeNominatedFor."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(CanBeNominatedForTestMixin, self).setUp()
        login('foo.bar@canonical.com')
        self.eric = self.factory.makePerson(name='eric')
        self.setUpTarget()

    def tearDown(self):
        logout()
        super(CanBeNominatedForTestMixin, self).tearDown()

    def test_canBeNominatedFor_series(self):
        # A bug may be nominated for a series of a product with an existing
        # task.
        self.assertTrue(self.bug.canBeNominatedFor(self.series))

    def test_not_canBeNominatedFor_already_nominated_series(self):
        # A bug may not be nominated for a series with an existing nomination.
        self.assertTrue(self.bug.canBeNominatedFor(self.series))
        self.bug.addNomination(self.eric, self.series)
        self.assertFalse(self.bug.canBeNominatedFor(self.series))

    def test_not_canBeNominatedFor_non_series(self):
        # A bug may not be nominated for something other than a series.
        self.assertFalse(self.bug.canBeNominatedFor(self.milestone))

    def test_not_canBeNominatedFor_already_targeted_series(self):
        # A bug may not be nominated for a series if a task already exists.
        # This case should be caught by the check for an existing nomination,
        # but there are some historical cases where a series task exists
        # without a nomination.
        self.assertTrue(self.bug.canBeNominatedFor(self.series))
        self.bug.addTask(self.eric, self.series)
        self.assertFalse(self.bug.canBeNominatedFor(self.series))

    def test_not_canBeNominatedFor_random_series(self):
        # A bug may only be nominated for a series if that series' pillar
        # already has a task.
        self.assertFalse(self.bug.canBeNominatedFor(self.random_series))


class TestBugCanBeNominatedForProductSeries(
    CanBeNominatedForTestMixin, TestCaseWithFactory):
    """Test IBug.canBeNominated for IProductSeries nominations."""

    def setUpTarget(self):
        self.series = self.factory.makeProductSeries()
        self.bug = self.factory.makeBug(target=self.series.product)
        self.milestone = self.factory.makeMilestone(productseries=self.series)
        self.random_series = self.factory.makeProductSeries()


class TestBugCanBeNominatedForDistroSeries(
    CanBeNominatedForTestMixin, TestCaseWithFactory):
    """Test IBug.canBeNominated for IDistroSeries nominations."""

    def setUpTarget(self):
        self.series = self.factory.makeDistroSeries()
        # The factory can't create a distro bug directly.
        self.bug = self.factory.makeBug()
        self.bug.addTask(self.eric, self.series.distribution)
        self.milestone = self.factory.makeMilestone(
            distribution=self.series.distribution)
        self.random_series = self.factory.makeDistroSeries()

    def test_not_canBeNominatedFor_source_package(self):
        # A bug may not be nominated directly for a source package. The
        # distroseries must be nominated instead.
        spn = self.factory.makeSourcePackageName()
        source_package = self.series.getSourcePackage(spn)
        self.assertFalse(self.bug.canBeNominatedFor(source_package))

    def test_canBeNominatedFor_with_only_distributionsourcepackage(self):
        # A distribution source package task is sufficient to allow nomination
        # to a series of that distribution.
        sp_bug = self.factory.makeBug()
        spn = self.factory.makeSourcePackageName()
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=self.series, sourcepackagename=spn)

        self.assertFalse(sp_bug.canBeNominatedFor(self.series))
        sp_bug.addTask(
            self.eric, self.series.distribution.getSourcePackage(spn))
        self.assertTrue(sp_bug.canBeNominatedFor(self.series))


class TestCanApprove(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_normal_user_cannot_approve(self):
        nomination = self.factory.makeBugNomination(
            target=self.factory.makeProductSeries())
        self.assertFalse(nomination.canApprove(self.factory.makePerson()))

    def test_privileged_users_can_approve(self):
        product = self.factory.makeProduct(driver=self.factory.makePerson())
        series = self.factory.makeProductSeries(product=product)
        with celebrity_logged_in('admin'):
            series.driver = self.factory.makePerson()
        nomination = self.factory.makeBugNomination(target=series)
        self.assertTrue(nomination.canApprove(product.owner))
        self.assertTrue(nomination.canApprove(product.driver))
        self.assertTrue(nomination.canApprove(series.driver))

    def publishSource(self, series, sourcepackagename, component):
        return self.factory.makeSourcePackagePublishingHistory(
            archive=series.main_archive,
            distroseries=series,
            sourcepackagename=sourcepackagename,
            component=component,
            status=PackagePublishingStatus.PUBLISHED)

    def test_component_uploader_can_approve(self):
        # A component uploader can approve a nomination for a package in
        # that component, but not those in other components
        series = self.factory.makeDistroSeries()
        package_name = self.factory.makeSourcePackageName()
        with celebrity_logged_in('admin'):
            perm = series.main_archive.newComponentUploader(
                self.factory.makePerson(), self.factory.makeComponent())
            other_perm = series.main_archive.newComponentUploader(
                self.factory.makePerson(), self.factory.makeComponent())
        nomination = self.factory.makeBugNomination(
            target=series.getSourcePackage(package_name))

        # Publish the package in one of the uploaders' components. The
        # uploader for the other component cannot approve the nomination.
        self.publishSource(series, package_name, perm.component)
        self.assertFalse(nomination.canApprove(other_perm.person))
        self.assertTrue(nomination.canApprove(perm.person))

    def test_any_component_uploader_can_approve_for_no_package(self):
        # An uploader for any component can approve a nomination without
        # a package.
        series = self.factory.makeDistroSeries()
        with celebrity_logged_in('admin'):
            perm = series.main_archive.newComponentUploader(
                self.factory.makePerson(), self.factory.makeComponent())
        nomination = self.factory.makeBugNomination(target=series)

        self.assertFalse(nomination.canApprove(self.factory.makePerson()))
        self.assertTrue(nomination.canApprove(perm.person))

    def test_package_uploader_can_approve(self):
        # A package uploader can approve a nomination for that package,
        # but not others.
        series = self.factory.makeDistroSeries()
        package_name = self.factory.makeSourcePackageName()
        with celebrity_logged_in('admin'):
            perm = series.main_archive.newPackageUploader(
                self.factory.makePerson(), package_name)
            other_perm = series.main_archive.newPackageUploader(
                self.factory.makePerson(),
                self.factory.makeSourcePackageName())
        nomination = self.factory.makeBugNomination(
            target=series.getSourcePackage(package_name))

        self.assertFalse(nomination.canApprove(other_perm.person))
        self.assertTrue(nomination.canApprove(perm.person))

    def test_packageset_uploader_can_approve(self):
        # A packageset uploader can approve a nomination for anything in
        # that packageset.
        series = self.factory.makeDistroSeries()
        package_name = self.factory.makeSourcePackageName()
        ps = self.factory.makePackageset(
            distroseries=series, packages=[package_name])
        with celebrity_logged_in('admin'):
            perm = series.main_archive.newPackagesetUploader(
                self.factory.makePerson(), ps)
        nomination = self.factory.makeBugNomination(
            target=series.getSourcePackage(package_name))

        self.assertFalse(nomination.canApprove(self.factory.makePerson()))
        self.assertTrue(nomination.canApprove(perm.person))

    def test_any_uploader_can_approve(self):
        # If there are multiple tasks for a distribution, an uploader to
        # any of the involved packages or components can approve the
        # nomination.
        series = self.factory.makeDistroSeries()
        package_name = self.factory.makeSourcePackageName()
        comp_package_name = self.factory.makeSourcePackageName()
        with celebrity_logged_in('admin'):
            package_perm = series.main_archive.newPackageUploader(
                self.factory.makePerson(), package_name)
            comp_perm = series.main_archive.newComponentUploader(
                self.factory.makePerson(), self.factory.makeComponent())
        nomination = self.factory.makeBugNomination(
            target=series.getSourcePackage(package_name))
        self.factory.makeBugTask(
            bug=nomination.bug,
            target=series.distribution.getSourcePackage(comp_package_name))

        self.publishSource(series, package_name, comp_perm.component)
        self.assertFalse(nomination.canApprove(self.factory.makePerson()))
        self.assertTrue(nomination.canApprove(package_perm.person))
        self.assertTrue(nomination.canApprove(comp_perm.person))


class BugNominationSetTestCase(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_get(self):
        series = self.factory.makeProductSeries()
        with person_logged_in(series.product.owner):
            nomination = self.factory.makeBugNomination(target=series)
        bug_nomination_set = getUtility(IBugNominationSet)
        self.assertEqual(nomination, bug_nomination_set.get(nomination.id))

    def test_get_none(self):
        bug_nomination_set = getUtility(IBugNominationSet)
        self.assertRaises(NotFoundError, bug_nomination_set.get, -1)
