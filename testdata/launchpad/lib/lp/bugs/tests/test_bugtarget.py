# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test harness for running tests agains IBugTarget implementations.

This module runs the interface test against the Product, ProductSeries
ProjectGroup, DistributionSourcePackage, and DistroSeries implementations
IBugTarget. It runs the bugtarget-questiontarget.txt test.
"""
__metaclass__ = type

__all__ = []

import random
import unittest

from zope.component import getUtility

from lp.bugs.interfaces.bug import CreateBugParams
from lp.bugs.interfaces.bugtask import (
    BugTaskStatus,
    IBugTaskSet,
    )
from lp.registry.interfaces.distribution import (
    IDistribution,
    IDistributionSet,
    )
from lp.registry.interfaces.product import IProductSet
from lp.registry.interfaces.projectgroup import IProjectGroupSet
from lp.services.webapp.interfaces import ILaunchBag
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.systemdocs import (
    LayeredDocFileSuite,
    setUp,
    tearDown,
    )


def bugtarget_filebug(bugtarget, summary, status=None):
    """File a bug as the current user on the bug target and return it."""
    return bugtarget.createBug(CreateBugParams(
        getUtility(ILaunchBag).user, summary, comment=summary, status=status))


def productSetUp(test):
    """Setup the `IProduct` test."""
    setUp(test)
    test.globs['bugtarget'] = getUtility(IProductSet).getByName('firefox')
    test.globs['filebug'] = bugtarget_filebug
    test.globs['question_target'] = test.globs['bugtarget']


def project_filebug(project, summary, status=None):
    """File a bug on a project.

    Since it's not possible to file a bug on a project directly, the bug
    will be filed on one of its products.
    """
    # It doesn't matter which product the bug is filed on.
    product = random.choice(list(project.products))
    bug = bugtarget_filebug(product, summary, status=status)
    return bug


def projectSetUp(test):
    """Setup the `IProjectGroup` test."""
    setUp(test)
    projectgroups = getUtility(IProjectGroupSet)
    test.globs['bugtarget'] = projectgroups.getByName('mozilla')
    test.globs['filebug'] = project_filebug


def productseries_filebug(productseries, summary, status=None):
    """File a bug on a product series.

    Since it's not possible to file a bug on a product series directly,
    the bug will first be filed on its product, then a series task will
    be created.
    """
    bug = bugtarget_filebug(productseries.product, summary, status=status)
    getUtility(IBugTaskSet).createTask(
        bug, getUtility(ILaunchBag).user, productseries, status=status)
    return bug


def productSeriesSetUp(test):
    """Setup the `IProductSeries` test."""
    setUp(test)
    firefox = getUtility(IProductSet).getByName('firefox')
    test.globs['bugtarget'] = firefox.getSeries('trunk')
    test.globs['filebug'] = productseries_filebug
    test.globs['question_target'] = firefox


def distributionSetUp(test):
    """Setup the `IDistribution` test."""
    setUp(test)
    test.globs['bugtarget'] = getUtility(IDistributionSet).getByName('ubuntu')
    test.globs['filebug'] = bugtarget_filebug
    test.globs['question_target'] = test.globs['bugtarget']


def distributionSourcePackageSetUp(test):
    """Setup the `IDistributionSourcePackage` test."""
    setUp(test)
    ubuntu = getUtility(IDistributionSet).getByName('ubuntu')
    test.globs['bugtarget'] = ubuntu.getSourcePackage('mozilla-firefox')
    test.globs['filebug'] = bugtarget_filebug
    test.globs['question_target'] = test.globs['bugtarget']


def distroseries_filebug(distroseries, summary, sourcepackagename=None,
                          status=None):
    """File a bug on a distroseries.

    Since bugs can't be filed on distroseriess directly, a bug will
    first be filed on its distribution, and then a series task will be
    added.
    """
    target = distroseries
    if sourcepackagename:
        target = target.getSourcePackage(sourcepackagename)
    bug = bugtarget_filebug(distroseries.distribution, summary, status=status)
    getUtility(IBugTaskSet).createTask(
        bug, getUtility(ILaunchBag).user, target, status=status)
    return bug


def distributionSeriesSetUp(test):
    """Setup the `IDistroSeries` test."""
    setUp(test)
    ubuntu = getUtility(IDistributionSet).getByName('ubuntu')
    test.globs['bugtarget'] = ubuntu.getSeries('hoary')
    test.globs['filebug'] = distroseries_filebug
    test.globs['question_target'] = ubuntu


def sourcepackage_filebug(source_package, summary, status=None):
    """File a bug on a source package in a distroseries."""
    bug = distroseries_filebug(
        source_package.distroseries, summary,
        sourcepackagename=source_package.sourcepackagename, status=status)
    return bug


def sourcepackage_filebug_for_question(source_package, summary, status=None):
    """Setup a bug with only one BugTask that can provide a QuestionTarget."""
    bug = sourcepackage_filebug(source_package, summary, status=status)
    # The distribution bugtask interferes with bugtarget-questiontarget.txt.
    for bugtask in bug.bugtasks:
        if IDistribution.providedBy(bugtask.target):
            bugtask.transitionToStatus(
                BugTaskStatus.INVALID, getUtility(ILaunchBag).user)
    return bug


def sourcePackageSetUp(test):
    """Setup the `ISourcePackage` test."""
    setUp(test)
    ubuntu = getUtility(IDistributionSet).getByName('ubuntu')
    warty = ubuntu.getSeries('warty')
    test.globs['bugtarget'] = warty.getSourcePackage('mozilla-firefox')
    test.globs['filebug'] = sourcepackage_filebug
    test.globs['question_target'] = ubuntu.getSourcePackage('mozilla-firefox')


class BugTargetQuestionTargetTestCase(TestCaseWithFactory):
    """Converting a bug into a question."""

    layer = DatabaseFunctionalLayer

    def test_canBeAQuestion_does_not_use_bugs(self):
        bug = self.factory.makeBug()
        pillar = bug.bugtasks[0].pillar
        with person_logged_in(pillar.owner):
            pillar.official_malone = False
            pillar.official_answers = True
        self.assertFalse(bug.canBeAQuestion())

    def test_canBeAQuestion_does_not_use_answers(self):
        bug = self.factory.makeBug()
        pillar = bug.bugtasks[0].pillar
        with person_logged_in(pillar.owner):
            pillar.official_malone = True
            pillar.official_answers = False
        self.assertFalse(bug.canBeAQuestion())

    def test_canBeAQuestion_uses_answers_and_bugs(self):
        bug = self.factory.makeBug()
        pillar = bug.bugtasks[0].pillar
        with person_logged_in(pillar.owner):
            pillar.official_malone = True
            pillar.official_answers = True
        self.assertTrue(bug.canBeAQuestion())


def test_suite():
    """Return the `IBugTarget` TestSuite."""
    suite = unittest.TestSuite()

    setUpMethods = [
        productSetUp,
        productSeriesSetUp,
        distributionSetUp,
        distributionSourcePackageSetUp,
        distributionSeriesSetUp,
        ]

    testname = 'bugtarget-questiontarget.txt'
    for setUpMethod in setUpMethods:
        id_ext = "%s-%s" % (testname, setUpMethod.func_name)
        test = LayeredDocFileSuite(
            testname,
            id_extensions=[id_ext],
            setUp=setUpMethod, tearDown=tearDown,
            layer=DatabaseFunctionalLayer)
        suite.addTest(test)

    suite.addTest(unittest.TestLoader().loadTestsFromName(__name__))
    return suite
