# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Project Milestone related test helper."""

__metaclass__ = type

from datetime import datetime
import unittest

from lazr.restfulclient.errors import ClientError
import pytz
from storm.store import Store
from zope.component import getUtility

from lp.blueprints.enums import (
    SpecificationDefinitionStatus,
    SpecificationPriority,
    )
from lp.blueprints.interfaces.specification import ISpecificationSet
from lp.bugs.interfaces.bug import CreateBugParams
from lp.bugs.interfaces.bugtask import (
    BugTaskStatus,
    IBugTaskSet,
    )
from lp.bugs.interfaces.bugtasksearch import BugTaskSearchParams
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.product import IProductSet
from lp.registry.interfaces.projectgroup import IProjectGroupSet
from lp.registry.model.milestone import MultipleProductReleases
from lp.testing import (
    launchpadlib_for,
    login,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )


class ProjectMilestoneTest(unittest.TestCase):
    """Setup of several milestones and associated data.

    A project milestone aggreates information from similar product milestones.
    This class creates:
      - up to three milestones in three products which belong to the
        Gnome project
      - specs and bugs in these products and associates them with the
        milestones.

    Visibility:
      - All milestones named '1.1' are active
      - One milestone named '1.2' is active, the other is not active
      - All milestones named '1.3' are not active

    Additionally, a milestone with a "typo" in its name and a milestone
    for firefox, i.e., for the mozilla project, named '1.1' is created.
    """

    layer = LaunchpadFunctionalLayer

    def __init__(self, methodName='runTest', helper_only=False):
        """If helper_only is True, set up it only as a helper class."""
        if not helper_only:
            unittest.TestCase.__init__(self, methodName)

    def setUp(self):
        """Login an admin user to perform the tests."""
        # From the persons defined in the test data, only those with
        # admin rights can change the 'active' attribute of milestones.
        login('foo.bar@canonical.com')

    def createProductMilestone(
        self, milestone_name, product_name, date_expected):
        """Create a milestone in the trunk series of a product."""
        product_set = getUtility(IProductSet)
        product = product_set[product_name]
        series = product.getSeries('trunk')
        milestone = series.newMilestone(
            name=milestone_name, dateexpected=date_expected)
        Store.of(milestone).flush()
        return milestone

    def test_milestone_name(self):
        """The names of project milestones.

        A project milestone named `A` exists, if at least one product of this
        project has a milestone named `A`.
        """
        gnome = getUtility(IProjectGroupSet)['gnome']
        product_milestones = []
        for product in gnome.products:
            product_milestones += [milestone.name
                                   for milestone in product.all_milestones]

        # Gnome has one entry for each unique milestone name that its
        # products have, so it is not a 1-to-1 relationship.
        projectgroup_milestones = [milestone.name
                                   for milestone in gnome.all_milestones]
        self.assertEqual(sorted(projectgroup_milestones),
                         sorted(set(product_milestones)))

        # When a milestone for a Gnome product is created, gnome has a
        # milestone of the same name.
        gnome_milestone_names = [
            milestone.name for milestone in gnome.all_milestones]
        self.assertEqual(gnome_milestone_names, [u'2.1.6', u'1.0'])
        self.createProductMilestone('1.1', 'evolution', None)
        gnome_milestone_names = [
            milestone.name for milestone in gnome.all_milestones]
        self.assertEqual(gnome_milestone_names, [u'2.1.6', u'1.1', u'1.0'])

        # There is only one project milestone named '1.1', regardless of the
        # number of product milestones with this name.
        self.createProductMilestone('1.1', 'gnomebaker', None)
        gnome_milestone_names = [
            milestone.name for milestone in gnome.all_milestones]
        self.assertEqual(gnome_milestone_names, [u'2.1.6', u'1.1', u'1.0'])

    def test_milestone_date_expected(self):
        """The dateexpected attribute.

        dateexpected is set to min(productmilestones.dateexpected).
        """
        gnome = getUtility(IProjectGroupSet)['gnome']
        evolution_milestone = self.createProductMilestone(
            '1.1', 'evolution', None)
        gnomebaker_milestone = self.createProductMilestone(
            '1.1', 'gnomebaker', None)
        gnome_milestone = gnome.getMilestone('1.1')

        self.assertEqual(evolution_milestone.dateexpected, None)
        self.assertEqual(gnomebaker_milestone.dateexpected, None)
        self.assertEqual(gnome_milestone.dateexpected, None)

        evolution_milestone.dateexpected = datetime(2007, 4, 2)
        gnome_milestone = gnome.getMilestone('1.1')
        self.assertEqual(gnome_milestone.dateexpected, datetime(2007, 4, 2))

        gnomebaker_milestone.dateexpected = datetime(2007, 4, 1)
        gnome_milestone = gnome.getMilestone('1.1')
        self.assertEqual(gnome_milestone.dateexpected, datetime(2007, 4, 1))

    def test_milestone_activity(self):
        """A project milestone is active, if at least one product milestone
        is active."""
        gnome = getUtility(IProjectGroupSet)['gnome']
        evolution_milestone = self.createProductMilestone(
            '1.1', 'evolution', None)
        gnomebaker_milestone = self.createProductMilestone(
            '1.1', 'gnomebaker', None)

        self.assertEqual(evolution_milestone.active, True)
        self.assertEqual(gnomebaker_milestone.active, True)
        gnome_milestone = gnome.getMilestone('1.1')
        self.assertEqual(gnome_milestone.active, True)

        gnomebaker_milestone.active = False
        gnome_milestone = gnome.getMilestone('1.1')
        self.assertEqual(gnome_milestone.active, True)

        evolution_milestone.active = False
        gnome_milestone = gnome.getMilestone('1.1')
        self.assertEqual(gnome_milestone.active, False)

        # Since the milestone 1.1 is now inactive, it will not show
        # up in the gnome.milestones attribute.
        self.assertEqual(
            [milestone.name for milestone in gnome.milestones], [])

        # ... while project.all_milestones lists inactive milestones too.
        self.assertEqual(
            [milestone.name for milestone in gnome.all_milestones],
            [u'2.1.6', u'1.1', u'1.0'])

    def test_no_foreign_milestones(self):
        """Milestones in "foreign" products.

        Milestones from products which do not belong to a project are not
        returned by project.milestones and project.all_milestones.
        """
        # firefox does not belong to the Gnome project.
        firefox = getUtility(IProductSet)['firefox']
        self.assertNotEqual(firefox.project.name, 'gnome')

        self.createProductMilestone('1.1', 'firefox', None)
        gnome = getUtility(IProjectGroupSet)['gnome']
        self.assertEqual(
            [milestone.name for milestone in gnome.all_milestones],
            [u'2.1.6', u'1.0'])

    def createSpecification(self, milestone_name, product_name):
        """Create a specification, assigned to a milestone, for a product."""
        specset = getUtility(ISpecificationSet)
        personset = getUtility(IPersonSet)
        sample_person = personset.getByEmail('test@canonical.com')
        product = getUtility(IProductSet)[product_name]

        spec = specset.new(
            name='%s-specification' % product_name,
            title='Title %s specification' % product_name,
            specurl='http://www.example.com/spec/%s' % product_name,
            summary='summary',
            definition_status=SpecificationDefinitionStatus.APPROVED,
            priority=SpecificationPriority.HIGH,
            owner=sample_person,
            product=product)
        spec.milestone = product.getMilestone(milestone_name)
        return spec

    def test_milestone_specifications(self):
        """Specifications of a project milestone.

        Specifications defined for products and assigned to a milestone
        are also assigned to the milestone of the project.
        """
        self.createProductMilestone('1.1', 'evolution', None)
        self.createProductMilestone('1.1', 'gnomebaker', None)
        self.createProductMilestone('1.1', 'firefox', None)
        self.createSpecification('1.1', 'evolution')
        self.createSpecification('1.1', 'gnomebaker')
        self.createSpecification('1.1', 'firefox')

        gnome_project_group = getUtility(IProjectGroupSet)['gnome']
        gnome_milestone = gnome_project_group.getMilestone('1.1')
        # The spec for firefox (not a gnome product) is not included
        # in the specifications, while the other two specs are included.
        self.assertEqual(
            [spec.name for spec in gnome_milestone.getSpecifications(None)],
            ['evolution-specification', 'gnomebaker-specification'])

    def _createProductBugtask(self, product_name, milestone_name):
        """Create a bugtask for a product, assign the task to a milestone."""
        personset = getUtility(IPersonSet)
        sample_person = personset.getByEmail('test@canonical.com')
        product = getUtility(IProductSet)[product_name]
        milestone = product.getMilestone(milestone_name)
        params = CreateBugParams(
            title='Milestone test bug for %s' % product_name,
            comment='comment',
            owner=sample_person,
            status=BugTaskStatus.CONFIRMED)
        bug = product.createBug(params)
        [bugtask] = bug.bugtasks
        bugtask.milestone = milestone

    def _createProductSeriesBugtask(self, product_name, product_series_name,
                                    milestone_name):
        """Create a bugtask for a productseries, assign it to a milestone."""
        personset = getUtility(IPersonSet)
        sample_person = personset.getByEmail('test@canonical.com')
        product = getUtility(IProductSet)[product_name]
        series = product.getSeries(product_series_name)
        milestone = product.getMilestone(milestone_name)
        params = CreateBugParams(
            title='Milestone test bug for %s series' % product_name,
            comment='comment',
            owner=sample_person,
            status=BugTaskStatus.CONFIRMED)
        bug = product.createBug(params)
        getUtility(IBugTaskSet).createTask(bug, sample_person, series)
        for bugtask in bug.bugtasks:
            if bugtask.productseries is not None:
                bugtask.milestone = milestone

    def test_milestone_bugtasks(self):
        """Bugtasks and project milestones.

        Bugtasks assigned to product milestones are also assigned to
        the corresponding project milestone.
        """
        self.createProductMilestone('1.1', 'evolution', None)
        self.createProductMilestone('1.1', 'gnomebaker', None)
        self.createProductMilestone('1.1', 'firefox', None)
        self._createProductBugtask('evolution', '1.1')
        self._createProductBugtask('gnomebaker', '1.1')
        self._createProductBugtask('firefox', '1.1')

        milestone = getUtility(IProjectGroupSet)['gnome'].getMilestone('1.1')
        searchparams = BugTaskSearchParams(user=None, milestone=milestone)
        bugtasks = list(getUtility(IBugTaskSet).search(searchparams))

        # Only the first two bugs created here belong to the gnome project.
        self.assertEqual(
            [bugtask.bug.title for bugtask in bugtasks],
            ['Milestone test bug for evolution',
             'Milestone test bug for gnomebaker'])

    def setUpProjectMilestoneTests(self):
        """Create product milestones for project milestone doctests."""
        self.createProductMilestone('1.1', 'evolution', datetime(2010, 4, 1))
        self.createProductMilestone('1.1', 'gnomebaker', datetime(2010, 4, 2))
        self.createProductMilestone('1.1.', 'netapplet', datetime(2010, 4, 2))

        self.createProductMilestone('1.2', 'evolution', datetime(2011, 4, 1))
        gnomebaker_milestone = self.createProductMilestone(
            '1.2', 'gnomebaker', datetime(2011, 4, 2))
        gnomebaker_milestone.active = False

        evolution_milestone = self.createProductMilestone(
            '1.3', 'evolution', datetime(2012, 4, 1))
        evolution_milestone.active = False
        gnomebaker_milestone = self.createProductMilestone(
            '1.3', 'gnomebaker', datetime(2012, 4, 2))
        gnomebaker_milestone.active = False

        self.createSpecification('1.1', 'evolution')
        self.createSpecification('1.1', 'gnomebaker')

        self._createProductBugtask('evolution', '1.1')
        self._createProductBugtask('gnomebaker', '1.1')
        self._createProductSeriesBugtask('evolution', 'trunk', '1.1')


class TestDuplicateProductReleases(TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def test_inappropriate_release_raises(self):
        # A milestone that already has a ProductRelease can not be given
        # another one.
        login('foo.bar@canonical.com')
        product_set = getUtility(IProductSet)
        product = product_set['evolution']
        series = product.getSeries('trunk')
        milestone = series.newMilestone(name='1.1', dateexpected=None)
        now = datetime.now(pytz.UTC)
        milestone.createProductRelease(1, now)
        self.assertRaises(MultipleProductReleases,
            milestone.createProductRelease, 1, now)
        try:
            milestone.createProductRelease(1, now)
        except MultipleProductReleases as e:
            self.assert_(
                str(e), 'A milestone can only have one ProductRelease.')

    def test_inappropriate_deactivation_does_not_cause_an_OOPS(self):
        # Make sure a 400 error and not an OOPS is returned when an exception
        # is raised when trying to create a product release when a milestone
        # already has one.
        launchpad = launchpadlib_for("test", "salgado", "WRITE_PUBLIC")

        project = launchpad.projects['evolution']
        milestone = project.getMilestone(name='2.1.6')
        now = datetime.now(pytz.UTC)

        e = self.assertRaises(
            ClientError, milestone.createProductRelease, date_released=now)

        # no OOPS was generated as a result of the exception
        self.assertEqual([], self.oopses)
        self.assertEqual(400, e.response.status)
        self.assertIn(
            'A milestone can only have one ProductRelease.', e.content)
