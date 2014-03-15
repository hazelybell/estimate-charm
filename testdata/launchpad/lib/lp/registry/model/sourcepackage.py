# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database classes that implement SourcePackage items."""

__metaclass__ = type

__all__ = [
    'SourcePackage',
    'SourcePackageQuestionTargetMixin',
    ]

from operator import attrgetter

from lazr.restful.utils import smartquote
from storm.locals import (
    And,
    Desc,
    Join,
    Store,
    )
from zope.component import getUtility
from zope.interface import (
    classProvides,
    implements,
    )

from lp.answers.enums import QUESTION_STATUS_DEFAULT_SEARCH
from lp.answers.model.question import (
    QuestionTargetMixin,
    QuestionTargetSearch,
    )
from lp.bugs.interfaces.bugsummary import IBugSummaryDimension
from lp.bugs.interfaces.bugtarget import ISeriesBugTarget
from lp.bugs.interfaces.bugtaskfilter import OrderedBugTask
from lp.bugs.model.bug import get_bug_tags_open_count
from lp.bugs.model.bugtarget import BugTargetBase
from lp.buildmaster.enums import BuildStatus
from lp.code.model.branch import Branch
from lp.code.model.hasbranches import (
    HasBranchesMixin,
    HasCodeImportsMixin,
    HasMergeProposalsMixin,
    )
from lp.code.model.seriessourcepackagebranch import (
    SeriesSourcePackageBranch,
    SeriesSourcePackageBranchSet,
    )
from lp.registry.interfaces.distribution import NoPartnerArchive
from lp.registry.interfaces.packaging import PackagingType
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.sourcepackage import (
    ISourcePackage,
    ISourcePackageFactory,
    )
from lp.registry.model.hasdrivers import HasDriversMixin
from lp.registry.model.packaging import (
    Packaging,
    PackagingUtil,
    )
from lp.registry.model.suitesourcepackage import SuiteSourcePackage
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import (
    flush_database_updates,
    sqlvalues,
    )
from lp.services.webapp.interfaces import ILaunchBag
from lp.soyuz.enums import (
    ArchivePurpose,
    PackagePublishingStatus,
    PackageUploadCustomFormat,
    )
from lp.soyuz.interfaces.archive import IArchiveSet
from lp.soyuz.interfaces.buildrecords import IHasBuildRecords
from lp.soyuz.model.binarypackagebuild import (
    BinaryPackageBuild,
    BinaryPackageBuildSet,
    )
from lp.soyuz.model.distributionsourcepackagerelease import (
    DistributionSourcePackageRelease,
    )
from lp.soyuz.model.distroseriessourcepackagerelease import (
    DistroSeriesSourcePackageRelease,
    )
from lp.soyuz.model.publishing import SourcePackagePublishingHistory
from lp.soyuz.model.sourcepackagerelease import SourcePackageRelease
from lp.translations.model.hastranslationimports import (
    HasTranslationImportsMixin,
    )
from lp.translations.model.hastranslationtemplates import (
    HasTranslationTemplatesMixin,
    )
from lp.translations.model.potemplate import TranslationTemplatesCollection


class SourcePackageQuestionTargetMixin(QuestionTargetMixin):
    """Implementation of IQuestionTarget for SourcePackage."""

    def getTargetTypes(self):
        """See `QuestionTargetMixin`.

        Defines distribution and sourcepackagename as this object's
        distribution and sourcepackagename.
        """
        return {'distribution': self.distribution,
                'sourcepackagename': self.sourcepackagename}

    def questionIsForTarget(self, question):
        """See `QuestionTargetMixin`.

        Return True when the question's distribution and sourcepackagename
        are this object's distribution and sourcepackagename.
        """
        if question.distribution is not self.distribution:
            return False
        if question.sourcepackagename is not self.sourcepackagename:
            return False
        return True

    def searchQuestions(self, search_text=None,
                        status=QUESTION_STATUS_DEFAULT_SEARCH,
                        language=None, sort=None, owner=None,
                        needs_attention_from=None, unsupported=False):
        """See `IQuestionCollection`."""
        if unsupported:
            unsupported_target = self
        else:
            unsupported_target = None

        return QuestionTargetSearch(
            distribution=self.distribution,
            sourcepackagename=self.sourcepackagename,
            search_text=search_text, status=status,
            language=language, sort=sort, owner=owner,
            needs_attention_from=needs_attention_from,
            unsupported_target=unsupported_target).getResults()

    def getAnswerContactsForLanguage(self, language):
        """See `IQuestionTarget`."""
        # Sourcepackages are supported by their distribtions too.
        persons = set(
            self.distribution.getAnswerContactsForLanguage(language))
        persons.update(
            set(QuestionTargetMixin.getAnswerContactsForLanguage(
            self, language)))
        return sorted(
            [person for person in persons], key=attrgetter('displayname'))

    def getAnswerContactRecipients(self, language):
        """See `IQuestionTarget`."""
        # We need to special case the source package case because some are
        # contacts for the distro while others are only registered for the
        # package. And we also want the name of the package in context in
        # the header.
        recipients = self.distribution.getAnswerContactRecipients(language)
        recipients.update(QuestionTargetMixin.getAnswerContactRecipients(
            self, language))
        return recipients

    @property
    def _store(self):
        return Store.of(self.sourcepackagename)

    @property
    def answer_contacts(self):
        """See `IQuestionTarget`."""
        answer_contacts = set()
        answer_contacts.update(self.direct_answer_contacts)
        answer_contacts.update(self.distribution.answer_contacts)
        return sorted(answer_contacts, key=attrgetter('displayname'))

    @property
    def answer_contacts_with_languages(self):
        """Answer contacts with their languages pre-filled.

        Same as answer_contacts but with each answer contact having its
        languages pre-filled so that we don't need to hit the DB again to get
        them.
        """
        answer_contacts = set()
        answer_contacts.update(self.direct_answer_contacts_with_languages)
        answer_contacts.update(
            self.distribution.answer_contacts_with_languages)
        return sorted(answer_contacts, key=attrgetter('displayname'))

    @property
    def owner(self):
        return self.distribution.owner


class SourcePackage(BugTargetBase, HasCodeImportsMixin,
                    HasTranslationImportsMixin, HasTranslationTemplatesMixin,
                    HasBranchesMixin, HasMergeProposalsMixin,
                    HasDriversMixin):
    """A source package, e.g. apache2, in a distroseries.

    This object is not a true database object, but rather attempts to
    represent the concept of a source package in a distro series, with links
    to the relevant database objects.
    """

    implements(
        IBugSummaryDimension, ISourcePackage, IHasBuildRecords,
        ISeriesBugTarget)

    classProvides(ISourcePackageFactory)

    def __init__(self, sourcepackagename, distroseries):
        # We store the ID of the sourcepackagename and distroseries
        # simply because Storm can break when accessing them
        # with implicit flush is blocked (like in a permission check when
        # storing the object in the permission cache).
        self.sourcepackagenameID = sourcepackagename.id
        self.sourcepackagename = sourcepackagename
        self.distroseries = distroseries
        self.distroseriesID = distroseries.id

    @classmethod
    def new(cls, sourcepackagename, distroseries):
        """See `ISourcePackageFactory`."""
        return cls(sourcepackagename, distroseries)

    def __repr__(self):
        return '<%s %r %r %r>' % (self.__class__.__name__,
            self.distribution, self.distroseries, self.sourcepackagename)

    def _getPublishingHistory(self, version=None, include_status=None,
                              exclude_status=None, order_by=None):
        """Build a query and return a list of SourcePackagePublishingHistory.

        This is mainly a helper function for this class so that code is
        not duplicated. include_status and exclude_status must be a sequence.
        """
        clauses = []
        clauses.append(
                """SourcePackagePublishingHistory.sourcepackagerelease =
                   SourcePackageRelease.id AND
                   SourcePackagePublishingHistory.sourcepackagename = %s AND
                   SourcePackagePublishingHistory.distroseries = %s AND
                   SourcePackagePublishingHistory.archive IN %s
                """ % sqlvalues(
                        self.sourcepackagename,
                        self.distroseries,
                        self.distribution.all_distro_archive_ids))
        if version:
            clauses.append(
                "SourcePackageRelease.version = %s" % sqlvalues(version))

        if include_status:
            if not isinstance(include_status, list):
                include_status = list(include_status)
            clauses.append("SourcePackagePublishingHistory.status IN %s"
                       % sqlvalues(include_status))

        if exclude_status:
            if not isinstance(exclude_status, list):
                exclude_status = list(exclude_status)
            clauses.append("SourcePackagePublishingHistory.status NOT IN %s"
                       % sqlvalues(exclude_status))

        query = " AND ".join(clauses)

        if not order_by:
            order_by = '-datepublished'

        return SourcePackagePublishingHistory.select(
            query, orderBy=order_by, clauseTables=['SourcePackageRelease'],
            prejoinClauseTables=['SourcePackageRelease'])

    def _getFirstPublishingHistory(self, version=None, include_status=None,
                                   exclude_status=None, order_by=None):
        """As _getPublishingHistory, but just returns the first item."""
        try:
            package = self._getPublishingHistory(
                version, include_status, exclude_status, order_by)[0]
        except IndexError:
            return None
        else:
            return package

    @property
    def currentrelease(self):
        releases = self.distroseries.getCurrentSourceReleases(
            [self.sourcepackagename])
        return releases.get(self)

    def __getitem__(self, version):
        """See `ISourcePackage`."""
        latest_package = self._getFirstPublishingHistory(version=version)
        if latest_package:
            return DistroSeriesSourcePackageRelease(
                    self.distroseries, latest_package.sourcepackagerelease)
        else:
            return None

    @property
    def path(self):
        """See `ISourcePackage`."""
        return '/'.join([
            self.distribution.name,
            self.distroseries.name,
            self.sourcepackagename.name])

    @property
    def displayname(self):
        return "%s in %s %s" % (
            self.sourcepackagename.name, self.distribution.displayname,
            self.distroseries.displayname)

    @property
    def bugtargetdisplayname(self):
        """See IBugTarget."""
        return "%s (%s)" % (self.name, self.distroseries.fullseriesname)

    @property
    def bugtargetname(self):
        """See `IBugTarget`."""
        return "%s (%s)" % (self.name, self.distroseries.fullseriesname)

    @property
    def bugtarget_parent(self):
        """See `ISeriesBugTarget`."""
        return self.distribution_sourcepackage

    @property
    def title(self):
        """See `ISourcePackage`."""
        return smartquote('"%s" source package in %s') % (
            self.sourcepackagename.name, self.distroseries.displayname)

    @property
    def summary(self):
        """See `ISourcePackage`."""
        releases = self.releases
        if len(releases) == 0:
            return None
        current = releases[0]
        name_summaries = [
            '%s: %s' % (binary.name, binary.summary)
            for binary in current.sample_binary_packages]
        if name_summaries == []:
            return None
        return '\n'.join(name_summaries)

    @property
    def distribution(self):
        return self.distroseries.distribution

    @property
    def format(self):
        if not self.currentrelease:
            return None
        return self.currentrelease.format

    @property
    def releases(self):
        """See `ISourcePackage`."""
        packages = self._getPublishingHistory(
            order_by=["SourcePackageRelease.version",
                      "SourcePackagePublishingHistory.datepublished"])

        return [DistributionSourcePackageRelease(
                distribution=self.distribution,
                sourcepackagerelease=package.sourcepackagerelease)
                   for package in packages]

    @property
    def distinctreleases(self):
        """Return all distinct `SourcePackageReleases` for this sourcepackage.

        The results are ordered by descending version.
        """
        return IStore(SourcePackageRelease).using(
            SourcePackageRelease,
            Join(
                SourcePackagePublishingHistory,
                SourcePackagePublishingHistory.sourcepackagereleaseID ==
                    SourcePackageRelease.id)
            ).find(
                SourcePackageRelease,
                SourcePackagePublishingHistory.archiveID.is_in(
                    self.distribution.all_distro_archive_ids),
                SourcePackagePublishingHistory.distroseries ==
                    self.distroseries,
                SourcePackagePublishingHistory.sourcepackagename ==
                    self.sourcepackagename
            ).config(distinct=True).order_by(
                Desc(SourcePackageRelease.version))

    @property
    def name(self):
        return self.sourcepackagename.name

    @property
    def productseries(self):
        # See if we can find a relevant packaging record
        packaging = self.direct_packaging
        if packaging is None:
            return None
        return packaging.productseries

    @property
    def direct_packaging(self):
        """See `ISourcePackage`."""
        store = Store.of(self.sourcepackagename)
        return store.find(
            Packaging,
            sourcepackagename=self.sourcepackagename,
            distroseries=self.distroseries).one()

    @property
    def packaging(self):
        """See `ISourcePackage`"""
        # First we look to see if there is packaging data for this
        # distroseries and sourcepackagename. If not, we look up through
        # parent distroseries.

        result = self.direct_packaging
        if result is not None:
            return result

        # If we have a parent distroseries, try that.
        if self.distroseries.previous_series is not None:
            sp = SourcePackage(sourcepackagename=self.sourcepackagename,
                               distroseries=self.distroseries.previous_series)
            return sp.packaging

    @property
    def published_by_pocket(self):
        """See `ISourcePackage`."""
        result = self._getPublishingHistory(
            include_status=[PackagePublishingStatus.PUBLISHED])
        # create the dictionary with the set of pockets as keys
        thedict = {}
        for pocket in PackagePublishingPocket.items:
            thedict[pocket] = []
        # add all the sourcepackagereleases in the right place
        for spr in result:
            thedict[spr.pocket].append(DistroSeriesSourcePackageRelease(
                spr.distroseries, spr.sourcepackagerelease))
        return thedict

    @property
    def development_version(self):
        """See `ISourcePackage`."""
        return self.__class__(
            self.sourcepackagename, self.distribution.currentseries)

    @property
    def distribution_sourcepackage(self):
        """See `ISourcePackage`."""
        return self.distribution.getSourcePackage(self.sourcepackagename)

    @property
    def bug_reporting_guidelines(self):
        """See `IBugTarget`."""
        return self.distribution.bug_reporting_guidelines

    @property
    def bug_reported_acknowledgement(self):
        """See `IBugTarget`."""
        return self.distribution.bug_reported_acknowledgement

    @property
    def enable_bugfiling_duplicate_search(self):
        """See `IBugTarget`."""
        return (
            self.distribution_sourcepackage.enable_bugfiling_duplicate_search)

    def _customizeSearchParams(self, search_params):
        """Customize `search_params` for this source package."""
        search_params.setSourcePackage(self)

    def _getOfficialTagClause(self):
        return self.distroseries._getOfficialTagClause()

    @property
    def official_bug_tags(self):
        """See `IHasBugs`."""
        return self.distroseries.official_bug_tags

    def getUsedBugTagsWithOpenCounts(self, user, tag_limit=0,
                                     include_tags=None):
        """See IBugTarget."""
        # Circular fail.
        from lp.bugs.model.bugsummary import BugSummary
        return get_bug_tags_open_count(
            And(BugSummary.distroseries == self.distroseries,
                BugSummary.sourcepackagename == self.sourcepackagename),
            user, tag_limit=tag_limit, include_tags=include_tags)

    @property
    def drivers(self):
        """See `IHasDrivers`."""
        return self.distroseries.drivers

    @property
    def owner(self):
        """See `IHasOwner`."""
        return self.distroseries.owner

    @property
    def pillar(self):
        """See `IBugTarget`."""
        return self.distroseries.distribution

    @property
    def series(self):
        """See `ISeriesBugTarget`."""
        return self.distroseries

    def getBugSummaryContextWhereClause(self):
        """See BugTargetBase."""
        # Circular fail.
        from lp.bugs.model.bugsummary import BugSummary
        return And(
                BugSummary.distroseries == self.distroseries,
                BugSummary.sourcepackagename == self.sourcepackagename)

    def setPackaging(self, productseries, owner):
        """See `ISourcePackage`."""
        target = self.direct_packaging
        if target is not None:
            if target.productseries == productseries:
                return
            # Delete the current packaging and create a new one so
            # that the translation sharing jobs are started.
            self.direct_packaging.destroySelf()
        PackagingUtil.createPackaging(
            distroseries=self.distroseries,
            sourcepackagename=self.sourcepackagename,
            productseries=productseries, owner=owner,
            packaging=PackagingType.PRIME)
        # and make sure this change is immediately available
        flush_database_updates()

    def setPackagingReturnSharingDetailPermissions(self, productseries,
                                                   owner):
        """See `ISourcePackage`."""
        self.setPackaging(productseries, owner)
        return self.getSharingDetailPermissions()

    def getSharingDetailPermissions(self):
        user = getUtility(ILaunchBag).user
        productseries = self.productseries
        permissions = {
                'user_can_change_product_series': False,
                'user_can_change_branch': False,
                'user_can_change_translation_usage': False,
                'user_can_change_translations_autoimport_mode': False}
        if user is None:
            pass
        elif productseries is None:
            permissions['user_can_change_product_series'] = user.canAccess(
                self, 'setPackaging')
        else:
            permissions.update({
                'user_can_change_product_series':
                    self.direct_packaging.userCanDelete(),
                'user_can_change_branch':
                    user.canWrite(productseries, 'branch'),
                'user_can_change_translation_usage':
                    user.canWrite(
                        productseries.product, 'translations_usage'),
                'user_can_change_translations_autoimport_mode':
                    user.canWrite(
                        productseries, 'translations_autoimport_mode'),
                })
        return permissions

    def deletePackaging(self):
        """See `ISourcePackage`."""
        if self.direct_packaging is None:
            return
        self.direct_packaging.destroySelf()

    def __hash__(self):
        """See `ISourcePackage`."""
        return hash(self.distroseriesID) ^ hash(self.sourcepackagenameID)

    def __eq__(self, other):
        """See `ISourcePackage`."""
        return (
            (ISourcePackage.providedBy(other)) and
            (self.distroseries.id == other.distroseries.id) and
            (self.sourcepackagename.id == other.sourcepackagename.id))

    def __ne__(self, other):
        """See `ISourcePackage`."""
        return not self.__eq__(other)

    def getBuildRecords(self, build_state=None, name=None, pocket=None,
                        arch_tag=None, user=None, binary_only=True):
        """See `IHasBuildRecords`"""
        # Ignore "user", since it would not make any difference to the
        # records returned here (private builds are only in PPA right
        # now and this method only returns records for SPRs in a
        # distribution).
        # We also ignore the name parameter (required as part of the
        # IHasBuildRecords interface) and use our own name and the
        # binary_only parameter as a source package can only have
        # binary builds.

        clauseTables = [
            'SourcePackageRelease', 'SourcePackagePublishingHistory']

        condition_clauses = ["""
        BinaryPackageBuild.source_package_release =
            SourcePackageRelease.id AND
        SourcePackagePublishingHistory.sourcepackagename = %s AND
        SourcePackagePublishingHistory.distroseries = %s AND
        SourcePackagePublishingHistory.archive IN %s AND
        SourcePackagePublishingHistory.sourcepackagerelease =
            SourcePackageRelease.id AND
        SourcePackagePublishingHistory.archive = BinaryPackageBuild.archive
        """ % sqlvalues(self.sourcepackagename,
                        self.distroseries,
                        list(self.distribution.all_distro_archive_ids))]

        # We re-use the optional-parameter handling provided by BuildSet
        # here, but pass None for the name argument as we've already
        # matched on exact source package name.
        BinaryPackageBuildSet().handleOptionalParamsForBuildQueries(
            condition_clauses, clauseTables, build_state, name=None,
            pocket=pocket, arch_tag=arch_tag)

        # exclude gina-generated and security (dak-made) builds
        # buildstate == FULLYBUILT && datebuilt == null
        condition_clauses.append(
            "NOT (BinaryPackageBuild.status=%s AND "
            "     BinaryPackageBuild.date_finished is NULL)"
            % sqlvalues(BuildStatus.FULLYBUILT))

        # Ordering according status
        # * NEEDSBUILD, BUILDING & UPLOADING by -lastscore
        # * SUPERSEDED by -datecreated
        # * FULLYBUILT & FAILURES by -datebuilt
        # It should present the builds in a more natural order.
        if build_state in [
            BuildStatus.NEEDSBUILD,
            BuildStatus.BUILDING,
            BuildStatus.UPLOADING,
            ]:
            orderBy = ["-BuildQueue.lastscore"]
            clauseTables.append('BuildPackageJob')
            condition_clauses.append(
                'BuildPackageJob.build = BinaryPackageBuild.id')
            clauseTables.append('BuildQueue')
            condition_clauses.append('BuildQueue.job = BuildPackageJob.job')
        elif build_state == BuildStatus.SUPERSEDED or build_state is None:
            orderBy = [Desc("BinaryPackageBuild.date_created")]
        else:
            orderBy = [Desc("BinaryPackageBuild.date_finished")]

        # Fallback to ordering by -id as a tie-breaker.
        orderBy.append(Desc("id"))

        # End of duplication (see XXX cprov 2006-09-25 above).

        return IStore(BinaryPackageBuild).using(clauseTables).find(
            BinaryPackageBuild, *condition_clauses).order_by(*orderBy)

    @property
    def latest_published_component(self):
        """See `ISourcePackage`."""
        latest_publishing = self._getFirstPublishingHistory(
            include_status=[PackagePublishingStatus.PUBLISHED])
        if latest_publishing is not None:
            return latest_publishing.component
        else:
            return None

    @property
    def latest_published_component_name(self):
        """See `ISourcePackage`."""
        if self.latest_published_component is not None:
            return self.latest_published_component.name
        else:
            return None

    def get_default_archive(self, component=None):
        """See `ISourcePackage`."""
        if component is None:
            component = self.latest_published_component
        distribution = self.distribution
        if component is not None and component.name == 'partner':
            archive = getUtility(IArchiveSet).getByDistroPurpose(
                distribution, ArchivePurpose.PARTNER)
            if archive is None:
                raise NoPartnerArchive(distribution)
            else:
                return archive
        else:
            return distribution.main_archive

    def getTemplatesCollection(self):
        """See `IHasTranslationTemplates`."""
        collection = TranslationTemplatesCollection()
        collection = collection.restrictDistroSeries(self.distroseries)
        return collection.restrictSourcePackageName(self.sourcepackagename)

    def getSharingPartner(self):
        """See `IHasTranslationTemplates`."""
        return self.productseries

    def getBranch(self, pocket):
        """See `ISourcePackage`."""
        store = Store.of(self.sourcepackagename)
        return store.find(
            Branch,
            SeriesSourcePackageBranch.distroseries == self.distroseries.id,
            (SeriesSourcePackageBranch.sourcepackagename
             == self.sourcepackagename.id),
            SeriesSourcePackageBranch.pocket == pocket,
            SeriesSourcePackageBranch.branch == Branch.id).one()

    def setBranch(self, pocket, branch, registrant):
        """See `ISourcePackage`."""
        SeriesSourcePackageBranchSet.delete(self, pocket)
        if branch is not None:
            SeriesSourcePackageBranchSet.new(
                self.distroseries, pocket, self.sourcepackagename, branch,
                registrant)
            # Avoid circular imports.
            from lp.registry.model.distributionsourcepackage import (
                DistributionSourcePackage,
                )
            DistributionSourcePackage.ensure(sourcepackage=self)
        else:
            # Delete the official DSP if there is no publishing history.
            self.distribution_sourcepackage.delete()

    @property
    def linked_branches(self):
        """See `ISourcePackage`."""
        store = Store.of(self.sourcepackagename)
        return store.find(
            (SeriesSourcePackageBranch.pocket, Branch),
            SeriesSourcePackageBranch.distroseries == self.distroseries.id,
            (SeriesSourcePackageBranch.sourcepackagename
             == self.sourcepackagename.id),
            SeriesSourcePackageBranch.branch == Branch.id).order_by(
                SeriesSourcePackageBranch.pocket)

    def getSuiteSourcePackage(self, pocket):
        """See `ISourcePackage`."""
        return SuiteSourcePackage(
            self.distroseries, pocket, self.sourcepackagename)

    def getPocketPath(self, pocket):
        """See `ISourcePackage`."""
        return '%s/%s/%s' % (
            self.distribution.name,
            self.distroseries.getSuite(pocket),
            self.name)

    def getLatestTranslationsUploads(self):
        """See `ISourcePackage`."""
        our_format = PackageUploadCustomFormat.ROSETTA_TRANSLATIONS

        packagename = self.sourcepackagename.name
        distro = self.distroseries.distribution

        histories = distro.main_archive.getPublishedSources(
            name=packagename, distroseries=self.distroseries,
            status=PackagePublishingStatus.PUBLISHED, exact_match=True)
        histories = list(histories)

        builds = []
        for history in histories:
            builds += list(history.getBuilds())

        uploads = [
            build.package_upload
            for build in builds
            if build.package_upload]
        custom_files = []
        for upload in uploads:
            custom_files += [
                custom for custom in upload.customfiles
                if custom.customformat == our_format]

        custom_files.sort(key=attrgetter('id'))
        return [custom.libraryfilealias for custom in custom_files]

    def linkedBranches(self):
        """See `ISourcePackage`."""
        return dict((p.name, b) for (p, b) in self.linked_branches)

    def getBugTaskWeightFunction(self):
        """Provide a weight function to determine optimal bug task.

        We look for the source package task, followed by the distro source
        package, then the distroseries task, and lastly the distro task.
        """
        sourcepackagenameID = self.sourcepackagename.id
        seriesID = self.distroseries.id
        distributionID = self.distroseries.distributionID

        def weight_function(bugtask):
            if bugtask.sourcepackagenameID == sourcepackagenameID:
                if bugtask.distroseriesID == seriesID:
                    return OrderedBugTask(1, bugtask.id, bugtask)
                elif bugtask.distributionID == distributionID:
                    return OrderedBugTask(2, bugtask.id, bugtask)
            elif bugtask.distroseriesID == seriesID:
                return OrderedBugTask(3, bugtask.id, bugtask)
            elif bugtask.distributionID == distributionID:
                return OrderedBugTask(4, bugtask.id, bugtask)
            # Catch the default case, and where there is a task for the same
            # sourcepackage on a different distro.
            return OrderedBugTask(5, bugtask.id, bugtask)
        return weight_function
