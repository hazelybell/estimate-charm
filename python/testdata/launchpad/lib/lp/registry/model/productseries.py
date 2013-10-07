# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Models for `IProductSeries`."""

__metaclass__ = type

__all__ = [
    'ProductSeries',
    'ProductSeriesSet',
    'TimelineProductSeries',
    ]

import datetime

from lazr.delegates import delegates
from sqlobject import (
    ForeignKey,
    SQLMultipleJoin,
    SQLObjectNotFound,
    StringCol,
    )
from storm.expr import (
    Max,
    Sum,
    )
from storm.locals import (
    And,
    Desc,
    )
from storm.store import Store
from zope.component import getUtility
from zope.interface import implements

from lp.app.enums import service_uses_launchpad
from lp.app.errors import NotFoundError
from lp.app.interfaces.launchpad import (
    ILaunchpadCelebrities,
    IServiceUsage,
    )
from lp.blueprints.interfaces.specificationtarget import ISpecificationTarget
from lp.blueprints.model.specification import (
    HasSpecificationsMixin,
    Specification,
    )
from lp.blueprints.model.specificationsearch import search_specifications
from lp.bugs.interfaces.bugsummary import IBugSummaryDimension
from lp.bugs.interfaces.bugtarget import ISeriesBugTarget
from lp.bugs.interfaces.bugtaskfilter import OrderedBugTask
from lp.bugs.model.bugtarget import BugTargetBase
from lp.bugs.model.structuralsubscription import (
    StructuralSubscriptionTargetMixin,
    )
from lp.registry.errors import ProprietaryProduct
from lp.registry.interfaces.packaging import PackagingType
from lp.registry.interfaces.person import validate_person
from lp.registry.interfaces.productrelease import IProductReleaseSet
from lp.registry.interfaces.productseries import (
    IProductSeries,
    IProductSeriesSet,
    ITimelineProductSeries,
    )
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.model.milestone import (
    HasMilestonesMixin,
    Milestone,
    )
from lp.registry.model.packaging import PackagingUtil
from lp.registry.model.productrelease import ProductRelease
from lp.registry.model.series import SeriesMixin
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.database.enumcol import EnumCol
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from lp.services.propertycache import cachedproperty
from lp.services.webapp.publisher import canonical_url
from lp.services.webapp.sorting import sorted_dotted_numbers
from lp.services.worlddata.model.language import Language
from lp.translations.interfaces.translations import (
    TranslationsBranchImportMode,
    )
from lp.translations.model.hastranslationimports import (
    HasTranslationImportsMixin,
    )
from lp.translations.model.hastranslationtemplates import (
    HasTranslationTemplatesMixin,
    )
from lp.translations.model.pofile import POFile
from lp.translations.model.potemplate import (
    POTemplate,
    TranslationTemplatesCollection,
    )
from lp.translations.model.productserieslanguage import ProductSeriesLanguage


MAX_TIMELINE_MILESTONES = 20


def landmark_key(landmark):
    """Sorts landmarks by date and name."""
    if landmark['date'] is None:
        # Null dates are assumed to be in the future.
        date = '9999-99-99'
    else:
        date = landmark['date']
    return date + landmark['name']


class ProductSeries(SQLBase, BugTargetBase, HasMilestonesMixin,
                    HasSpecificationsMixin, HasTranslationImportsMixin,
                    HasTranslationTemplatesMixin,
                    StructuralSubscriptionTargetMixin, SeriesMixin):
    """A series of product releases."""
    implements(
        IBugSummaryDimension, IProductSeries, IServiceUsage,
        ISeriesBugTarget)

    delegates(ISpecificationTarget, 'product')

    _table = 'ProductSeries'

    product = ForeignKey(dbName='product', foreignKey='Product', notNull=True)
    status = EnumCol(
        notNull=True, schema=SeriesStatus,
        default=SeriesStatus.DEVELOPMENT)
    name = StringCol(notNull=True)
    datecreated = UtcDateTimeCol(notNull=True, default=UTC_NOW)
    owner = ForeignKey(
        dbName="owner", foreignKey="Person",
        storm_validator=validate_person,
        notNull=True)

    driver = ForeignKey(
        dbName="driver", foreignKey="Person",
        storm_validator=validate_person,
        notNull=False, default=None)
    branch = ForeignKey(foreignKey='Branch', dbName='branch',
                             default=None)

    def validate_autoimport_mode(self, attr, value):
        # Perform the normal validation for None
        if value is None:
            return value
        if (self.product.private and
            value != TranslationsBranchImportMode.NO_IMPORT):
            raise ProprietaryProduct('Translations are disabled for'
                                     ' proprietary projects.')
        return value

    translations_autoimport_mode = EnumCol(
        dbName='translations_autoimport_mode',
        notNull=True,
        schema=TranslationsBranchImportMode,
        default=TranslationsBranchImportMode.NO_IMPORT,
        storm_validator=validate_autoimport_mode)
    translations_branch = ForeignKey(
        dbName='translations_branch', foreignKey='Branch', notNull=False,
        default=None)
    # where are the tarballs released from this branch placed?
    releasefileglob = StringCol(default=None)
    releaseverstyle = StringCol(default=None)

    packagings = SQLMultipleJoin('Packaging', joinColumn='productseries',
                            orderBy=['-id'])

    @property
    def pillar(self):
        """See `IBugTarget`."""
        return self.product

    @property
    def series(self):
        """See `ISeriesBugTarget`."""
        return self

    @property
    def answers_usage(self):
        """See `IServiceUsage.`"""
        return self.product.answers_usage

    @property
    def blueprints_usage(self):
        """See `IServiceUsage.`"""
        return self.product.blueprints_usage

    @property
    def translations_usage(self):
        """See `IServiceUsage.`"""
        return self.product.translations_usage

    @property
    def codehosting_usage(self):
        """See `IServiceUsage.`"""
        return self.product.codehosting_usage

    @property
    def bug_tracking_usage(self):
        """See `IServiceUsage.`"""
        return self.product.bug_tracking_usage

    @property
    def uses_launchpad(self):
        """ See `IServiceUsage.`"""
        return (
            service_uses_launchpad(self.blueprints_usage) or
            service_uses_launchpad(self.translations_usage) or
            service_uses_launchpad(self.answers_usage) or
            service_uses_launchpad(self.codehosting_usage) or
            service_uses_launchpad(self.bug_tracking_usage))

    def _getMilestoneCondition(self):
        """See `HasMilestonesMixin`."""
        return (Milestone.productseries == self)

    @property
    def releases(self):
        """See `IProductSeries`."""
        store = Store.of(self)

        # The Milestone is cached too because most uses of a ProductRelease
        # need it. The decorated resultset returns just the ProductRelease.
        def decorate(row):
            product_release, milestone = row
            return product_release

        result = store.find(
            (ProductRelease, Milestone),
            Milestone.productseries == self,
            ProductRelease.milestone == Milestone.id)
        result = result.order_by(Desc('datereleased'))
        return DecoratedResultSet(result, decorate)

    @cachedproperty
    def _cached_releases(self):
        return self.releases

    def getCachedReleases(self):
        """See `IProductSeries`."""
        return self._cached_releases

    @property
    def release_files(self):
        """See `IProductSeries`."""
        files = set()
        for release in self.releases:
            files = files.union(release.files)
        return files

    @property
    def displayname(self):
        return self.name

    @property
    def parent(self):
        """See IProductSeries."""
        return self.product

    @property
    def bugtargetdisplayname(self):
        """See IBugTarget."""
        return "%s %s" % (self.product.displayname, self.name)

    @property
    def bugtargetname(self):
        """See IBugTarget."""
        return "%s/%s" % (self.product.name, self.name)

    @property
    def bugtarget_parent(self):
        """See `ISeriesBugTarget`."""
        return self.parent

    def getPOTemplate(self, name):
        """See IProductSeries."""
        return POTemplate.selectOne(
            "productseries = %s AND name = %s" % sqlvalues(self.id, name))

    @property
    def title(self):
        return '%s %s series' % (self.product.displayname, self.displayname)

    @property
    def bug_reporting_guidelines(self):
        """See `IBugTarget`."""
        return self.product.bug_reporting_guidelines

    @property
    def bug_reported_acknowledgement(self):
        """See `IBugTarget`."""
        return self.product.bug_reported_acknowledgement

    @property
    def enable_bugfiling_duplicate_search(self):
        """See `IBugTarget`."""
        return self.product.enable_bugfiling_duplicate_search

    @property
    def sourcepackages(self):
        """See IProductSeries"""
        from lp.registry.model.sourcepackage import SourcePackage
        ret = self.packagings
        ret = [SourcePackage(sourcepackagename=r.sourcepackagename,
                             distroseries=r.distroseries)
                    for r in ret]
        ret.sort(key=lambda a: a.distribution.name + a.distroseries.version
                 + a.sourcepackagename.name)
        return ret

    @property
    def is_development_focus(self):
        """See `IProductSeries`."""
        return self == self.product.development_focus

    def specifications(self, user, sort=None, quantity=None, filter=None,
                       need_people=True, need_branches=True,
                       need_workitems=False):
        """See IHasSpecifications.

        The rules for filtering are that there are three areas where you can
        apply a filter:

          - acceptance, which defaults to ACCEPTED if nothing is said,
          - completeness, which defaults to showing BOTH if nothing is said
          - informational, which defaults to showing BOTH if nothing is said

        """
        base_clauses = [Specification.productseriesID == self.id]
        return search_specifications(
            self, base_clauses, user, sort, quantity, filter,
            default_acceptance=True, need_people=need_people,
            need_branches=need_branches, need_workitems=need_workitems)

    @property
    def all_specifications(self):
        return Store.of(self).find(
            Specification, Specification.productseriesID == self.id)

    def _customizeSearchParams(self, search_params):
        """Customize `search_params` for this product series."""
        search_params.setProductSeries(self)

    def _getOfficialTagClause(self):
        return self.product._getOfficialTagClause()

    @property
    def official_bug_tags(self):
        """See `IHasBugs`."""
        return self.product.official_bug_tags

    def getBugSummaryContextWhereClause(self):
        """See BugTargetBase."""
        # Circular fail.
        from lp.bugs.model.bugsummary import BugSummary
        return BugSummary.productseries_id == self.id

    def getLatestRelease(self):
        """See `IProductRelease.`"""
        try:
            return self.releases[0]
        except IndexError:
            return None

    def getRelease(self, version):
        return getUtility(IProductReleaseSet).getBySeriesAndVersion(
            self, version)

    def getPackage(self, distroseries):
        """See IProductSeries."""
        for pkg in self.sourcepackages:
            if pkg.distroseries == distroseries:
                return pkg
        # XXX sabdfl 2005-06-23: This needs to search through the ancestry of
        # the distroseries to try to find a relevant packaging record
        raise NotFoundError(distroseries)

    def getUbuntuTranslationFocusPackage(self):
        """See `IProductSeries`."""
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        translation_focus = ubuntu.translation_focus
        current_series = ubuntu.currentseries
        candidate = None
        for package in self.sourcepackages:
            if package.distroseries == translation_focus:
                return package
            if package.distroseries == current_series:
                candidate = package
            elif package.distroseries.distribution == ubuntu:
                if candidate is None:
                    candidate = package
        return candidate

    def setPackaging(self, distroseries, sourcepackagename, owner):
        """See IProductSeries."""
        if distroseries.distribution.full_functionality:
            source_package = distroseries.getSourcePackage(sourcepackagename)
            if source_package.currentrelease is None:
                raise AssertionError(
                    "The source package is not published in %s." %
                    distroseries.displayname)
        for pkg in self.packagings:
            if (pkg.distroseries == distroseries and
                pkg.sourcepackagename == sourcepackagename):
                # we have found a matching Packaging record
                # and it has the same source package name
                return pkg

        # ok, we didn't find a packaging record that matches, let's go ahead
        # and create one
        pkg = PackagingUtil.createPackaging(
            distroseries=distroseries,
            sourcepackagename=sourcepackagename,
            productseries=self,
            packaging=PackagingType.PRIME,
            owner=owner)
        pkg.sync()  # convert UTC_NOW to actual datetime
        return pkg

    def getPackagingInDistribution(self, distribution):
        """See IProductSeries."""
        history = []
        for pkging in self.packagings:
            if pkging.distroseries.distribution == distribution:
                history.append(pkging)
        return history

    def newMilestone(self, name, dateexpected=None, summary=None,
                     code_name=None, tags=None):
        """See IProductSeries."""
        milestone = Milestone(
            name=name, dateexpected=dateexpected, summary=summary,
            product=self.product, productseries=self, code_name=code_name)
        if tags:
            milestone.setTags(tags.split())
        return milestone

    def getTemplatesCollection(self):
        """See `IHasTranslationTemplates`."""
        return TranslationTemplatesCollection().restrictProductSeries(self)

    def getSharingPartner(self):
        """See `IHasTranslationTemplates`."""
        return self.getUbuntuTranslationFocusPackage()

    @property
    def potemplate_count(self):
        """See `IProductSeries`."""
        return self.getCurrentTranslationTemplates().count()

    @property
    def productserieslanguages(self):
        """See `IProductSeries`."""
        store = Store.of(self)

        english = getUtility(ILaunchpadCelebrities).english

        results = []
        if self.potemplate_count == 1:
            # If there is only one POTemplate in a ProductSeries, fetch
            # Languages and corresponding POFiles with one query, along
            # with their stats, and put them into ProductSeriesLanguage
            # objects.
            origin = [Language, POFile, POTemplate]
            query = store.using(*origin).find(
                (Language, POFile),
                POFile.language == Language.id,
                Language.visible == True,
                POFile.potemplate == POTemplate.id,
                POTemplate.productseries == self,
                POTemplate.iscurrent == True,
                Language.id != english.id)

            ordered_results = query.order_by(['Language.englishname'])

            for language, pofile in ordered_results:
                psl = ProductSeriesLanguage(self, language, pofile=pofile)
                total = pofile.potemplate.messageCount()
                imported = pofile.currentCount()
                changed = pofile.updatesCount()
                rosetta = pofile.rosettaCount()
                unreviewed = pofile.unreviewedCount()
                translated = imported + rosetta
                new = rosetta - changed
                psl.setCounts(total, translated, new, changed, unreviewed)
                psl.last_changed_date = pofile.date_changed
                results.append(psl)
        else:
            # If there is more than one template, do a single
            # query to count total messages in all templates.
            query = store.find(
                Sum(POTemplate.messagecount),
                POTemplate.productseries == self,
                POTemplate.iscurrent == True)
            total, = query
            # And another query to fetch all Languages with translations
            # in this ProductSeries, along with their cumulative stats
            # for imported, changed, rosetta-provided and unreviewed
            # translations.
            query = store.find(
                (Language,
                 Sum(POFile.currentcount),
                 Sum(POFile.updatescount),
                 Sum(POFile.rosettacount),
                 Sum(POFile.unreviewed_count),
                 Max(POFile.date_changed)),
                POFile.language == Language.id,
                Language.visible == True,
                POFile.potemplate == POTemplate.id,
                POTemplate.productseries == self,
                POTemplate.iscurrent == True,
                Language.id != english.id).group_by(Language)

            ordered_results = query.order_by(['Language.englishname'])

            for (language, imported, changed, rosetta, unreviewed,
                 last_changed) in ordered_results:
                psl = ProductSeriesLanguage(self, language)
                translated = imported + rosetta
                new = rosetta - changed
                psl.setCounts(total, translated, new, changed, unreviewed)
                psl.last_changed_date = last_changed
                results.append(psl)

        return results

    def getTimeline(self, include_inactive=False):
        landmarks = []
        for milestone in self.all_milestones[:MAX_TIMELINE_MILESTONES]:
            if milestone.product_release is None:
                # Skip inactive milestones, but include releases,
                # even if include_inactive is False.
                if not include_inactive and not milestone.active:
                    continue
                node_type = 'milestone'
                date = milestone.dateexpected
                uri = canonical_url(milestone, path_only_if_possible=True)
            else:
                node_type = 'release'
                date = milestone.product_release.datereleased
                uri = canonical_url(
                    milestone.product_release, path_only_if_possible=True)

            if isinstance(date, datetime.datetime):
                date = date.date().isoformat()
            elif isinstance(date, datetime.date):
                date = date.isoformat()

            entry = dict(
                name=milestone.name,
                code_name=milestone.code_name,
                type=node_type,
                date=date,
                uri=uri)
            landmarks.append(entry)

        landmarks = sorted_dotted_numbers(landmarks, key=landmark_key)
        landmarks.reverse()
        return TimelineProductSeries(
            name=self.name,
            is_development_focus=self.is_development_focus,
            status=self.status,
            uri=canonical_url(self, path_only_if_possible=True),
            landmarks=landmarks,
            product=self.product)

    def getBugTaskWeightFunction(self):
        """Provide a weight function to determine optimal bug task.

        Full weight is given to tasks for this product series.

        If the series isn't found, the product task is better than others.
        """
        seriesID = self.id
        productID = self.productID

        def weight_function(bugtask):
            if bugtask.productseriesID == seriesID:
                return OrderedBugTask(1, bugtask.id, bugtask)
            elif bugtask.productID == productID:
                return OrderedBugTask(2, bugtask.id, bugtask)
            else:
                return OrderedBugTask(3, bugtask.id, bugtask)
        return weight_function

    def userCanView(self, user):
        """See `IproductSeriesPublic`."""
        # Deleate the permission check to the parent product.
        return self.product.userCanView(user)


class TimelineProductSeries:
    """See `ITimelineProductSeries`."""
    implements(ITimelineProductSeries)

    def __init__(self, name, status, is_development_focus, uri, landmarks,
                 product):
        self.name = name
        self.status = status
        self.is_development_focus = is_development_focus
        self.uri = uri
        self.landmarks = landmarks
        self.product = product


class ProductSeriesSet:
    """See IProductSeriesSet."""

    implements(IProductSeriesSet)

    def __getitem__(self, series_id):
        """See IProductSeriesSet."""
        series = self.get(series_id)
        if series is None:
            raise NotFoundError(series_id)
        return series

    def get(self, series_id, default=None):
        """See IProductSeriesSet."""
        try:
            return ProductSeries.get(series_id)
        except SQLObjectNotFound:
            return default

    def findByTranslationsImportBranch(
            self, branch, force_translations_upload=False):
        """See IProductSeriesSet."""
        conditions = [ProductSeries.branch == branch]
        if not force_translations_upload:
            import_mode = ProductSeries.translations_autoimport_mode
            conditions.append(
                import_mode != TranslationsBranchImportMode.NO_IMPORT)

        return Store.of(branch).find(ProductSeries, And(*conditions))
