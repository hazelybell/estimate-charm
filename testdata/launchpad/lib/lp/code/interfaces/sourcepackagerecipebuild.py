# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for source package builds."""

__metaclass__ = type
__all__ = [
    'ISourcePackageRecipeBuild',
    'ISourcePackageRecipeBuildSource',
    'ISourcePackageRecipeBuildJob',
    'ISourcePackageRecipeBuildJobSource',
    ]

from lazr.restful.declarations import export_as_webservice_entry
from lazr.restful.fields import (
    CollectionField,
    Reference,
    )
from zope.interface import Interface
from zope.schema import (
    Bool,
    Int,
    Object,
    )

from lp import _
from lp.buildmaster.interfaces.buildfarmjob import ISpecificBuildFarmJobSource
from lp.buildmaster.interfaces.packagebuild import IPackageBuild
from lp.code.interfaces.sourcepackagerecipe import (
    ISourcePackageRecipe,
    ISourcePackageRecipeData,
    )
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.person import IPerson
from lp.services.job.interfaces.job import IJob
from lp.soyuz.interfaces.binarypackagebuild import IBinaryPackageBuild
from lp.soyuz.interfaces.buildfarmbuildjob import IBuildFarmBuildJob
from lp.soyuz.interfaces.sourcepackagerelease import ISourcePackageRelease


class ISourcePackageRecipeBuild(IPackageBuild):
    """A build of a source package."""
    export_as_webservice_entry()

    id = Int(title=_("Identifier for this build."))

    binary_builds = CollectionField(
        Reference(IBinaryPackageBuild),
        title=_("The binary builds that resulted from this."), readonly=True)

    distroseries = Reference(
        IDistroSeries, title=_("The distroseries being built for"),
        readonly=True)

    requester = Object(
        schema=IPerson, required=False,
        title=_("The person who wants this to be done."))

    recipe = Object(
        schema=ISourcePackageRecipe, title=_("The recipe being built."))

    manifest = Object(
        schema=ISourcePackageRecipeData, title=_(
            'A snapshot of the recipe for this build.'))

    def getManifestText():
        """The text of the manifest for this build."""

    source_package_release = Reference(
        ISourcePackageRelease, title=_("The produced source package release"),
        readonly=True)

    is_virtualized = Bool(title=_('If True, this build is virtualized.'))

    def getFileByName(filename):
        """Return the file under +files with specified name."""

    def cancelBuild():
        """Cancel the build."""

    def destroySelf():
        """Delete the build itself."""


class ISourcePackageRecipeBuildSource(ISpecificBuildFarmJobSource):
    """A utility of this interface be used to create source package builds."""

    def new(distroseries, recipe, requester, archive, date_created=None):
        """Create an `ISourcePackageRecipeBuild`.

        :param distroseries: The `IDistroSeries` that this is building
            against.
        :param recipe: The `ISourcePackageRecipe` that this is building.
        :param requester: The `IPerson` who wants to build it.
        :param date_created: The date this build record was created. If not
            provided, defaults to now.
        :return: `ISourcePackageRecipeBuild`.
        """

    def makeDailyBuilds(logger=None):
        """Create and return builds for stale ISourcePackageRecipes.

        :param logger: An optional logger to write debug info to.
        """


class ISourcePackageRecipeBuildJob(IBuildFarmBuildJob):
    """A read-only interface for recipe build jobs."""

    job = Reference(
        IJob, title=_("Job"), required=True, readonly=True,
        description=_("Data common to all job types."))


class ISourcePackageRecipeBuildJobSource(Interface):
    """A utility of this interface used to create _things_."""

    def new(build, job):
        """Create a new `ISourcePackageRecipeBuildJob`.

        :param build: An `ISourcePackageRecipeBuild`.
        :param job: An `IJob`.
        :return: `ISourcePackageRecipeBuildJob`.
        """
