# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interface for linking source packages in distroseries to branches."""

__metaclass__ = type
__all__ = [
    'IFindOfficialBranchLinks',
    'ISeriesSourcePackageBranch',
    ]


from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Choice,
    Datetime,
    Int,
    )

from lp import _
from lp.registry.interfaces.pocket import PackagePublishingPocket


class ISeriesSourcePackageBranch(Interface):
    """Link /<distro>/<suite>/<package> to a branch."""

    id = Int()

    distroseries = Choice(
        title=_("Series"), required=True, readonly=True,
        vocabulary='DistroSeries')

    pocket = Choice(
        title=_("Pocket"), required=True, readonly=True,
        vocabulary=PackagePublishingPocket)

    sourcepackage = Attribute('The source package')

    suite_sourcepackage = Attribute('The suite source package')

    sourcepackagename = Choice(
        title=_("Package"), required=True,
        readonly=True, vocabulary='SourcePackageName')

    branchID = Attribute('The ID of the branch.')
    branch = Choice(
        title=_("Branch"), vocabulary="Branch", required=True, readonly=True)

    registrant = Attribute("The person who registered this link.")

    date_created = Datetime(
        title=_("When the branch was linked to the distribution suite."),
        readonly=True)


class IFindOfficialBranchLinks(Interface):
    """Find the links for official branches for pockets on source packages.
    """

    def findForBranch(branch):
        """Get the links to source packages from a branch.

        :param branch: An `IBranch`.
        :return: An `IResultSet` of `ISeriesSourcePackageBranch` objects.
        """

    def findForBranches(branches):
        """Get the links to source packages from a branch.

        :param branches: A an iterable of `IBranch`.
        :return: An `IResultSet` of `ISeriesSourcePackageBranch` objects.
        """

    def findForSourcePackage(sourcepackage):
        """Get the links to branches from a source package.

        :param sourcepackage: An `ISourcePackage`.
        :return: An `IResultSet` of `ISeriesSourcePackageBranch` objects.
        """

    def findForDistributionSourcePackage(distrosourcepackage):
        """Get the links to branches for a distribution source package.

        :param distrosourcepackage: An `IDistributionSourcePackage`.
        :return: An `IResultSet` of `ISeriesSourcePackageBranch` objects.
        """
