# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database classes for a distribution series."""

__metaclass__ = type

__all__ = [
    'DistroSeries',
    'DistroSeriesSet',
    ]

import collections
from cStringIO import StringIO
import logging

import apt_pkg
from lazr.delegates import delegates
from sqlobject import (
    BoolCol,
    ForeignKey,
    IntCol,
    SQLMultipleJoin,
    SQLObjectNotFound,
    SQLRelatedJoin,
    StringCol,
    )
from storm.expr import (
    And,
    Desc,
    Join,
    Or,
    SQL,
    )
from storm.store import (
    EmptyResultSet,
    Store,
    )
from zope.component import getUtility
from zope.interface import implements

from lp.app.enums import service_uses_launchpad
from lp.app.errors import NotFoundError
from lp.app.interfaces.launchpad import IServiceUsage
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
from lp.registry.errors import NoSuchDistroSeries
from lp.registry.interfaces.distroseries import (
    DerivationError,
    IDistroSeries,
    IDistroSeriesSet,
    )
from lp.registry.interfaces.distroseriesdifference import (
    IDistroSeriesDifferenceSource,
    )
from lp.registry.interfaces.distroseriesdifferencecomment import (
    IDistroSeriesDifferenceCommentSource,
    )
from lp.registry.interfaces.person import validate_public_person
from lp.registry.interfaces.pocket import (
    PackagePublishingPocket,
    pocketsuffix,
    )
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.interfaces.sourcepackage import (
    ISourcePackage,
    ISourcePackageFactory,
    )
from lp.registry.interfaces.sourcepackagename import (
    ISourcePackageName,
    ISourcePackageNameSet,
    )
from lp.registry.model.milestone import (
    HasMilestonesMixin,
    Milestone,
    )
from lp.registry.model.packaging import Packaging
from lp.registry.model.person import Person
from lp.registry.model.series import SeriesMixin
from lp.registry.model.sourcepackage import SourcePackage
from lp.registry.model.sourcepackagename import SourcePackageName
from lp.services.database.constants import (
    DEFAULT,
    UTC_NOW,
    )
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import (
    flush_database_caches,
    flush_database_updates,
    SQLBase,
    sqlvalues,
    )
from lp.services.database.stormexpr import fti_search
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.librarian.model import LibraryFileAlias
from lp.services.mail.signedmessage import signed_message_from_string
from lp.services.propertycache import (
    cachedproperty,
    get_property_cache,
    )
from lp.services.worlddata.model.language import Language
from lp.soyuz.enums import (
    ArchivePurpose,
    PackagePublishingStatus,
    PackageUploadStatus,
    )
from lp.soyuz.interfaces.binarypackagebuild import IBinaryPackageBuildSet
from lp.soyuz.interfaces.binarypackagename import IBinaryPackageName
from lp.soyuz.interfaces.buildrecords import IHasBuildRecords
from lp.soyuz.interfaces.distributionjob import (
    IInitializeDistroSeriesJobSource,
    )
from lp.soyuz.interfaces.publishing import (
    active_publishing_status,
    ICanPublishPackages,
    )
from lp.soyuz.interfaces.queue import (
    IHasQueueItems,
    IPackageUploadSet,
    )
from lp.soyuz.interfaces.sourcepackageformat import (
    ISourcePackageFormatSelectionSet,
    )
from lp.soyuz.model.binarypackagename import BinaryPackageName
from lp.soyuz.model.component import Component
from lp.soyuz.model.distroarchseries import (
    DistroArchSeries,
    PocketChroot,
    )
from lp.soyuz.model.distroseriesbinarypackage import DistroSeriesBinaryPackage
from lp.soyuz.model.distroseriespackagecache import DistroSeriesPackageCache
from lp.soyuz.model.distroseriessourcepackagerelease import (
    DistroSeriesSourcePackageRelease,
    )
from lp.soyuz.model.publishing import (
    BinaryPackagePublishingHistory,
    get_current_source_releases,
    SourcePackagePublishingHistory,
    )
from lp.soyuz.model.queue import (
    PackageUpload,
    PackageUploadQueue,
    )
from lp.soyuz.model.section import Section
from lp.soyuz.model.sourcepackagerelease import SourcePackageRelease
from lp.translations.enums import LanguagePackType
from lp.translations.model.distroseries_translations_copy import (
    copy_active_translations,
    )
from lp.translations.model.distroserieslanguage import (
    DistroSeriesLanguage,
    DummyDistroSeriesLanguage,
    )
from lp.translations.model.hastranslationimports import (
    HasTranslationImportsMixin,
    )
from lp.translations.model.hastranslationtemplates import (
    HasTranslationTemplatesMixin,
    )
from lp.translations.model.languagepack import LanguagePack
from lp.translations.model.pofile import POFile
from lp.translations.model.pofiletranslator import POFileTranslator
from lp.translations.model.potemplate import (
    POTemplate,
    TranslationTemplatesCollection,
    )


class DistroSeries(SQLBase, BugTargetBase, HasSpecificationsMixin,
                   HasTranslationImportsMixin, HasTranslationTemplatesMixin,
                   HasMilestonesMixin, SeriesMixin,
                   StructuralSubscriptionTargetMixin):
    """A particular series of a distribution."""
    implements(
        ICanPublishPackages, IBugSummaryDimension, IDistroSeries,
        IHasBuildRecords, IHasQueueItems, IServiceUsage,
        ISeriesBugTarget)

    delegates(ISpecificationTarget, 'distribution')

    _table = 'DistroSeries'
    _defaultOrder = ['distribution', 'version']

    distribution = ForeignKey(
        dbName='distribution', foreignKey='Distribution', notNull=True)
    name = StringCol(notNull=True)
    displayname = StringCol(notNull=True)
    title = StringCol(notNull=True)
    description = StringCol(notNull=True)
    version = StringCol(notNull=True)
    status = EnumCol(
        dbName='releasestatus', notNull=True, schema=SeriesStatus)
    date_created = UtcDateTimeCol(notNull=False, default=UTC_NOW)
    datereleased = UtcDateTimeCol(notNull=False, default=None)
    previous_series = ForeignKey(
        dbName='parent_series', foreignKey='DistroSeries', notNull=False)
    registrant = ForeignKey(
        dbName='registrant', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)
    driver = ForeignKey(
        dbName="driver", foreignKey="Person",
        storm_validator=validate_public_person, notNull=False, default=None)
    changeslist = StringCol(notNull=False, default=None)
    nominatedarchindep = ForeignKey(
        dbName='nominatedarchindep', foreignKey='DistroArchSeries',
        notNull=False, default=None)
    messagecount = IntCol(notNull=True, default=0)
    binarycount = IntCol(notNull=True, default=DEFAULT)
    sourcecount = IntCol(notNull=True, default=DEFAULT)
    defer_translation_imports = BoolCol(notNull=True, default=True)
    hide_all_translations = BoolCol(notNull=True, default=True)
    language_pack_base = ForeignKey(
        foreignKey="LanguagePack", dbName="language_pack_base", notNull=False,
        default=None)
    language_pack_delta = ForeignKey(
        foreignKey="LanguagePack", dbName="language_pack_delta",
        notNull=False, default=None)
    language_pack_proposed = ForeignKey(
        foreignKey="LanguagePack", dbName="language_pack_proposed",
        notNull=False, default=None)
    language_pack_full_export_requested = BoolCol(notNull=True, default=False)
    backports_not_automatic = BoolCol(notNull=True, default=False)
    include_long_descriptions = BoolCol(notNull=True, default=True)

    language_packs = SQLMultipleJoin(
        'LanguagePack', joinColumn='distroseries', orderBy='-date_exported')
    sections = SQLRelatedJoin(
        'Section', joinColumn='distroseries', otherColumn='section',
        intermediateTable='SectionSelection')

    @property
    def pillar(self):
        """See `IBugTarget`."""
        return self.distribution

    @property
    def series(self):
        """See `ISeriesBugTarget`."""
        return self

    @property
    def named_version(self):
        return '%s (%s)' % (self.displayname, self.version)

    @property
    def upload_components(self):
        """See `IDistroSeries`."""
        return Component.select("""
            ComponentSelection.distroseries = %s AND
            Component.id = ComponentSelection.component
            """ % self.id,
            clauseTables=["ComponentSelection"])

    @cachedproperty
    def components(self):
        """See `IDistroSeries`."""
        # XXX julian 2007-06-25
        # This is filtering out the partner component for now, until
        # the second stage of the partner repo arrives in 1.1.8.
        return list(Component.select("""
            ComponentSelection.distroseries = %s AND
            Component.id = ComponentSelection.component AND
            Component.name != 'partner'
            """ % self.id,
            clauseTables=["ComponentSelection"]))

    @cachedproperty
    def component_names(self):
        """See `IDistroSeries`."""
        return [component.name for component in self.components]

    @cachedproperty
    def suite_names(self):
        """See `IDistroSeries`."""
        return [unicode(pocket) for pocket in PackagePublishingPocket.items]

    @property
    def answers_usage(self):
        """See `IServiceUsage.`"""
        return self.distribution.answers_usage

    @property
    def blueprints_usage(self):
        """See `IServiceUsage.`"""
        return self.distribution.blueprints_usage

    @property
    def translations_usage(self):
        """See `IServiceUsage.`"""
        return self.distribution.translations_usage

    @property
    def codehosting_usage(self):
        """See `IServiceUsage.`"""
        return self.distribution.codehosting_usage

    @property
    def bug_tracking_usage(self):
        """See `IServiceUsage.`"""
        return self.distribution.bug_tracking_usage

    @property
    def uses_launchpad(self):
        """ See `IServiceUsage.`"""
        return (
            service_uses_launchpad(self.blueprints_usage) or
            service_uses_launchpad(self.translations_usage) or
            service_uses_launchpad(self.answers_usage) or
            service_uses_launchpad(self.codehosting_usage) or
            service_uses_launchpad(self.bug_tracking_usage))

    # DistroArchSeries lookup properties/methods.
    architectures = SQLMultipleJoin(
        'DistroArchSeries', joinColumn='distroseries',
        orderBy='architecturetag')

    def __getitem__(self, archtag):
        """See `IDistroSeries`."""
        return self.getDistroArchSeries(archtag)

    def __repr__(self):
        return '<%s %r>' % (self.__class__.__name__, self.name)

    def __str__(self):
        return '%s %s' % (self.distribution.name, self.name)

    def getDistroArchSeries(self, archtag):
        """See `IDistroSeries`."""
        item = DistroArchSeries.selectOneBy(
            distroseries=self, architecturetag=archtag)
        if item is None:
            raise NotFoundError('Unknown architecture %s for %s %s' % (
                archtag, self.distribution.name, self.name))
        return item

    def getDistroArchSeriesByProcessor(self, processor):
        """See `IDistroSeries`."""
        return Store.of(self).find(
            DistroArchSeries,
            DistroArchSeries.distroseriesID == self.id,
            DistroArchSeries.processor_id == processor.id).one()

    @property
    def enabled_architectures(self):
        return Store.of(self).find(
            DistroArchSeries,
            DistroArchSeries.distroseries == self,
            DistroArchSeries.enabled == True).order_by(
                DistroArchSeries.architecturetag)

    @property
    def buildable_architectures(self):
        store = Store.of(self)
        origin = [
            DistroArchSeries,
            Join(PocketChroot,
                 PocketChroot.distroarchseries == DistroArchSeries.id),
            Join(LibraryFileAlias,
                 PocketChroot.chroot == LibraryFileAlias.id),
            ]
        results = store.using(*origin).find(
            DistroArchSeries,
            DistroArchSeries.distroseries == self)
        return results.order_by(DistroArchSeries.architecturetag)

    @property
    def virtualized_architectures(self):
        store = Store.of(self)
        results = store.find(
            DistroArchSeries,
            DistroArchSeries.distroseries == self,
            DistroArchSeries.supports_virtualized == True)
        return results.order_by(DistroArchSeries.architecturetag)
    # End of DistroArchSeries lookup methods

    @property
    def parent(self):
        """See `IDistroSeries`."""
        return self.distribution

    @property
    def owner(self):
        """See `IDistroSeries`."""
        return self.distribution.owner

    @property
    def sortkey(self):
        """A string to be used for sorting distro seriess.

        This is designed to sort alphabetically by distro and series name,
        except that Ubuntu will be at the top of the listing.
        """
        result = ''
        if self.distribution.name == 'ubuntu':
            result += '-'
        result += self.distribution.name + self.name
        return result

    @cachedproperty
    def _all_packagings(self):
        """Get an unordered list of all packagings.

        :return: A ResultSet which can be decorated or tuned further. Use
            DistroSeries._packaging_row_to_packaging to extract the
            packaging objects out.
        """
        # We join to SourcePackageName, ProductSeries, and Product to cache
        # the objects that are implicitly needed to work with a
        # Packaging object.
        # NB: precaching objects like this method tries to do has a very poor
        # hit rate with storm - many queries will still be executed; consider
        # ripping this out and instead allowing explicit inclusion of things
        # like Person._members does - returning a cached object graph.
        # -- RBC 20100810
        # Avoid circular import failures.
        from lp.registry.model.product import Product
        from lp.registry.model.productseries import ProductSeries
        find_spec = (Packaging, SourcePackageName, ProductSeries, Product)
        origin = [
            Packaging,
            Join(
                SourcePackageName,
                Packaging.sourcepackagename == SourcePackageName.id),
            Join(
                ProductSeries,
                Packaging.productseries == ProductSeries.id),
            Join(
                Product,
                ProductSeries.product == Product.id)]
        condition = Packaging.distroseries == self.id
        results = IStore(self).using(*origin).find(find_spec, condition)
        return results

    @staticmethod
    def _packaging_row_to_packaging(row):
        # each row has:
        #  (packaging, spn, product_series, product)
        return row[0]

    @property
    def packagings(self):
        """See `IDistroSeries`."""
        results = self._all_packagings
        results = results.order_by(SourcePackageName.name)
        return DecoratedResultSet(results,
            DistroSeries._packaging_row_to_packaging)

    def getPrioritizedUnlinkedSourcePackages(self):
        """See `IDistroSeries`.

        The prioritization is a heuristic rule using bug count,
        translatable messages, and the source package release's component.
        """
        find_spec = (
            SourcePackageName,
            SQL("""
                coalesce(bug_count * 10, 0) + coalesce(po_messages, 0) +
                CASE WHEN component = 1 THEN 1000 ELSE 0 END AS score"""),
            SQL("coalesce(bug_count, 0) AS bug_count"),
            SQL("coalesce(total_messages, 0) AS total_messages"))
        # This does not use _current_sourcepackage_joins_and_conditions
        # because the two queries are working on different data sets -
        # +needs-packaging was timing out and +packaging wasn't, and
        # destabilising things unnecessarily is not good.
        origin = SQL("""
            SourcePackageName, (SELECT
        spr.sourcepackagename,
        spr.component,
        bug_count,
        SUM(POTemplate.messagecount) * %(po_message_weight)s AS po_messages,
        SUM(POTemplate.messagecount) AS total_messages
    FROM
        SourcePackageRelease AS spr
        JOIN SourcePackagePublishingHistory AS spph
            ON spr.id = spph.sourcepackagerelease
        JOIN Archive
            ON spph.archive = Archive.id
        JOIN Section
            ON spph.section = Section.id
        JOIN DistroSeries
            ON spph.distroseries = DistroSeries.id
        LEFT OUTER JOIN DistributionSourcePackage AS dsp
            ON dsp.sourcepackagename = spr.sourcepackagename
                AND dsp.distribution = DistroSeries.distribution
        LEFT OUTER JOIN POTemplate
            ON POTemplate.sourcepackagename = spr.sourcepackagename
                AND POTemplate.distroseries = DistroSeries.id
    WHERE
        DistroSeries.id = %(distroseries)s
        AND spph.status IN %(active_status)s
        AND Archive.purpose = %(primary)s
        AND Section.name <> 'translations'
        AND NOT EXISTS (
            SELECT TRUE FROM Packaging
            WHERE
                Packaging.sourcepackagename = spr.sourcepackagename
                AND Packaging.distroseries = spph.distroseries)
    GROUP BY
        spr.sourcepackagename, spr.component, bug_count
    ) AS spn_info""" % sqlvalues(
            po_message_weight=self._current_sourcepackage_po_weight,
            distroseries=self,
            active_status=active_publishing_status,
            primary=ArchivePurpose.PRIMARY))
        condition = SQL("sourcepackagename.id = spn_info.sourcepackagename")
        results = IStore(self).using(origin).find(find_spec, condition)
        results = results.order_by('score DESC', SourcePackageName.name)
        results = results.config(distinct=('score', SourcePackageName.name))

        def decorator(row):
            spn, score, bug_count, total_messages = row
            return {
                'package': SourcePackage(
                    sourcepackagename=spn, distroseries=self),
                'bug_count': bug_count,
                'total_messages': total_messages,
                }
        return DecoratedResultSet(results, decorator)

    def getPrioritizedPackagings(self):
        """See `IDistroSeries`.

        The prioritization is a heuristic rule using the branch, bug heat,
        translatable messages, and the source package release's component.
        """
        # We join to SourcePackageName, ProductSeries, and Product to cache
        # the objects that are implcitly needed to work with a
        # Packaging object.
        joins, conditions = self._current_sourcepackage_joins_and_conditions
        # XXX: EdwinGrubbs 2010-07-29 bug=374777
        # Storm doesn't support DISTINCT ON.
        origin = SQL('''
            (
            SELECT DISTINCT ON (Packaging.id)
                Packaging.*,
                spr.component AS spr_component,
                SourcePackageName.name AS spn_name,
                bug_count,
                po_messages
            FROM %(joins)s
            WHERE %(conditions)s
                AND packaging.id IS NOT NULL
            ) AS Packaging
            JOIN ProductSeries
                ON Packaging.productseries = ProductSeries.id
            JOIN Product
                ON ProductSeries.product = Product.id
            ''' % dict(joins=joins, conditions=conditions))
        return IStore(self).using(origin).find(Packaging).order_by('''
                (CASE WHEN spr_component = 1 THEN 1000 ELSE 0 END
                + CASE WHEN Product.bugtracker IS NULL
                    THEN coalesce(bug_count * 10, 10) ELSE 0 END
                + CASE WHEN ProductSeries.translations_autoimport_mode = 1
                    THEN coalesce(po_messages, 10) ELSE 0 END
                + CASE WHEN ProductSeries.branch IS NULL THEN 500 ELSE 0 END
                ) DESC,
                spn_name ASC
                ''')

    @property
    def _current_sourcepackage_po_weight(self):
        """See getPrioritized*."""
        # Bugs and PO messages are heuristically scored. These queries
        # can easily timeout so filters and weights are used to create
        # an acceptable prioritization of packages that is fast to excecute.
        return .5

    @property
    def _current_sourcepackage_joins_and_conditions(self):
        """The SQL joins and conditions to prioritize source packages.

        Used for getPrioritizedPackagings only.
        """
        # Bugs and PO messages are heuristically scored. These queries
        # can easily timeout so filters and weights are used to create
        # an acceptable prioritization of packages that is fast to excecute.
        po_message_weight = self._current_sourcepackage_po_weight
        message_score = ("""
            LEFT JOIN (
                SELECT
                    POTemplate.sourcepackagename,
                    POTemplate.distroseries,
                    SUM(POTemplate.messagecount) * %(po_message_weight)s
                        AS po_messages,
                    SUM(POTemplate.messagecount) AS total_messages
                FROM POTemplate
                WHERE
                    POTemplate.sourcepackagename is not NULL
                    AND POTemplate.distroseries = %(distroseries)s
                GROUP BY
                    POTemplate.sourcepackagename,
                    POTemplate.distroseries
                ) messages
                ON SourcePackageName.id = messages.sourcepackagename
                AND DistroSeries.id = messages.distroseries
            """ % sqlvalues(
                distroseries=self,
                po_message_weight=po_message_weight))
        joins = ("""
            SourcePackageName
            JOIN SourcePackageRelease spr
                ON SourcePackageName.id = spr.sourcepackagename
            JOIN SourcePackagePublishingHistory spph
                ON spr.id = spph.sourcepackagerelease
            JOIN archive
                ON spph.archive = Archive.id
            JOIN section
                ON spph.section = section.id
            JOIN DistroSeries
                ON spph.distroseries = DistroSeries.id
            LEFT JOIN Packaging
                ON SourcePackageName.id = Packaging.sourcepackagename
                AND Packaging.distroseries = DistroSeries.id
            LEFT JOIN DistributionSourcePackage dsp
                ON dsp.sourcepackagename = spr.sourcepackagename
                    AND dsp.distribution = DistroSeries.distribution
            """ + message_score)
        conditions = ("""
            DistroSeries.id = %(distroseries)s
            AND spph.status IN %(active_status)s
            AND archive.purpose = %(primary)s
            AND section.name != 'translations'
            """ % sqlvalues(
                distroseries=self,
                active_status=active_publishing_status,
                primary=ArchivePurpose.PRIMARY))
        return (joins, conditions)

    def getMostRecentlyLinkedPackagings(self):
        """See `IDistroSeries`."""
        results = self._all_packagings
        # Order by creation date with a secondary ordering by sourcepackage
        # name to ensure the ordering for test data where many packagings have
        # identical creation dates.
        results = results.order_by(Desc(Packaging.datecreated),
                                   SourcePackageName.name)[:5]
        return DecoratedResultSet(results,
            DistroSeries._packaging_row_to_packaging)

    @property
    def supported(self):
        return self.status in [
            SeriesStatus.CURRENT,
            SeriesStatus.SUPPORTED,
            ]

    @property
    def distroserieslanguages(self):
        result = DistroSeriesLanguage.select(
            "DistroSeriesLanguage.language = Language.id AND "
            "DistroSeriesLanguage.distroseries = %d AND "
            "Language.visible = TRUE" % self.id,
            prejoinClauseTables=["Language"],
            clauseTables=["Language"],
            prejoins=["distroseries"],
            orderBy=["Language.englishname"])
        return result

    @property
    def bug_reporting_guidelines(self):
        """See `IBugTarget`."""
        return self.distribution.bug_reporting_guidelines

    @property
    def bug_reported_acknowledgement(self):
        """See `IBugTarget`."""
        return self.distribution.bug_reported_acknowledgement

    def _getMilestoneCondition(self):
        """See `HasMilestonesMixin`."""
        return (Milestone.distroseries == self)

    def updatePackageCount(self):
        """See `IDistroSeries`."""
        self.sourcecount = IStore(SourcePackagePublishingHistory).find(
            SourcePackagePublishingHistory.sourcepackagenameID,
            SourcePackagePublishingHistory.distroseries == self,
            SourcePackagePublishingHistory.archiveID.is_in(
                self.distribution.all_distro_archive_ids),
            SourcePackagePublishingHistory.status.is_in(
                active_publishing_status),
            SourcePackagePublishingHistory.pocket ==
                PackagePublishingPocket.RELEASE).config(distinct=True).count()

        self.binarycount = IStore(BinaryPackagePublishingHistory).find(
            BinaryPackagePublishingHistory.binarypackagenameID,
            DistroArchSeries.distroseries == self,
            BinaryPackagePublishingHistory.distroarchseriesID ==
                DistroArchSeries.id,
            BinaryPackagePublishingHistory.archiveID.is_in(
                self.distribution.all_distro_archive_ids),
            BinaryPackagePublishingHistory.status.is_in(
                active_publishing_status),
            BinaryPackagePublishingHistory.pocket ==
                PackagePublishingPocket.RELEASE).config(distinct=True).count()

    @property
    def architecturecount(self):
        """See `IDistroSeries`."""
        return self.architectures.count()

    @property
    def fullseriesname(self):
        return "%s %s" % (
            self.distribution.name.capitalize(), self.name.capitalize())

    @property
    def bugtargetname(self):
        """See IBugTarget."""
        # XXX mpt 2007-07-10 bugs 113258, 113262:
        # The distribution's and series' names should be used instead
        # of fullseriesname.
        return self.fullseriesname

    @property
    def bugtargetdisplayname(self):
        """See IBugTarget."""
        return self.fullseriesname

    @property
    def bugtarget_parent(self):
        """See `ISeriesBugTarget`."""
        return self.parent

    @property
    def last_full_language_pack_exported(self):
        return LanguagePack.selectFirstBy(
            distroseries=self, type=LanguagePackType.FULL,
            orderBy='-date_exported')

    @property
    def last_delta_language_pack_exported(self):
        return LanguagePack.selectFirstBy(
            distroseries=self, type=LanguagePackType.DELTA,
            updates=self.language_pack_base, orderBy='-date_exported')

    def _customizeSearchParams(self, search_params):
        """Customize `search_params` for this distribution series."""
        search_params.setDistroSeries(self)

    def _getOfficialTagClause(self):
        return self.distribution._getOfficialTagClause()

    @property
    def official_bug_tags(self):
        """See `IHasBugs`."""
        return self.distribution.official_bug_tags

    def specifications(self, user, sort=None, quantity=None, filter=None,
                       need_people=True, need_branches=True,
                       need_workitems=False):
        """See IHasSpecifications.

        In this case the rules for the default behaviour cover three things:

          - acceptance: if nothing is said, ACCEPTED only
          - completeness: if nothing is said, ANY
          - informationalness: if nothing is said, ANY

        """
        base_clauses = [Specification.distroseriesID == self.id]
        return search_specifications(
            self, base_clauses, user, sort, quantity, filter,
            default_acceptance=True, need_people=need_people,
            need_branches=need_branches, need_workitems=need_workitems)

    def getDistroSeriesLanguage(self, language):
        """See `IDistroSeries`."""
        return DistroSeriesLanguage.selectOneBy(
            distroseries=self, language=language)

    def getDistroSeriesLanguageOrDummy(self, language):
        """See `IDistroSeries`."""
        drl = self.getDistroSeriesLanguage(language)
        if drl is not None:
            return drl
        return DummyDistroSeriesLanguage(self, language)

    def updateStatistics(self, ztm):
        """See `IDistroSeries`."""
        # first find the set of all languages for which we have pofiles in
        # the distribution that are visible and not English
        langidset = set(IStore(Language).find(
            Language.id,
            Language.visible == True,
            Language.id == POFile.languageID,
            Language.code != 'en',
            POFile.potemplateID == POTemplate.id,
            POTemplate.distroseries == self,
            POTemplate.iscurrent == True).config(distinct=True))

        # now run through the existing DistroSeriesLanguages for the
        # distroseries, and update their stats, and remove them from the
        # list of languages we need to have stats for
        for distroserieslanguage in self.distroserieslanguages:
            distroserieslanguage.updateStatistics(ztm)
            langidset.discard(distroserieslanguage.language.id)
        # now we should have a set of languages for which we NEED
        # to have a DistroSeriesLanguage
        for langid in langidset:
            drl = DistroSeriesLanguage(distroseries=self, languageID=langid)
            drl.updateStatistics(ztm)
        # lastly, we need to update the message count for this distro
        # series itself
        messagecount = 0
        for potemplate in self.getCurrentTranslationTemplates():
            messagecount += potemplate.messageCount()
        self.messagecount = messagecount
        ztm.commit()

    def getSourcePackage(self, name):
        """See `IDistroSeries`."""
        if not ISourcePackageName.providedBy(name):
            try:
                name = SourcePackageName.byName(name)
            except SQLObjectNotFound:
                return None
        return getUtility(ISourcePackageFactory).new(
            sourcepackagename=name, distroseries=self)

    def getBinaryPackage(self, name):
        """See `IDistroSeries`."""
        if not IBinaryPackageName.providedBy(name):
            try:
                name = BinaryPackageName.byName(name)
            except SQLObjectNotFound:
                return None
        return DistroSeriesBinaryPackage(self, name)

    def getSourcePackageRelease(self, sourcepackagerelease):
        """See `IDistroSeries`."""
        return DistroSeriesSourcePackageRelease(self, sourcepackagerelease)

    def getCurrentSourceReleases(self, source_package_names):
        """See `IDistroSeries`."""
        return getUtility(IDistroSeriesSet).getCurrentSourceReleases(
            {self: source_package_names})

    def getTranslatableSourcePackages(self):
        """See `IDistroSeries`."""
        query = """
            POTemplate.sourcepackagename = SourcePackageName.id AND
            POTemplate.iscurrent = TRUE AND
            POTemplate.distroseries = %s""" % sqlvalues(self.id)
        result = SourcePackageName.select(query, clauseTables=['POTemplate'],
            orderBy=['name'], distinct=True)
        return [SourcePackage(sourcepackagename=spn, distroseries=self) for
            spn in result]

    def getUnlinkedTranslatableSourcePackages(self):
        """See `IDistroSeries`."""
        # Note that both unlinked packages and
        # linked-with-no-productseries packages are considered to be
        # "unlinked translatables".
        query = """
            SourcePackageName.id NOT IN (SELECT DISTINCT
             sourcepackagename FROM Packaging WHERE distroseries = %s) AND
            POTemplate.sourcepackagename = SourcePackageName.id AND
            POTemplate.distroseries = %s""" % sqlvalues(self.id, self.id)
        unlinked = SourcePackageName.select(
            query, clauseTables=['POTemplate'], orderBy=['name'])
        query = """
            Packaging.sourcepackagename = SourcePackageName.id AND
            Packaging.productseries = NULL AND
            POTemplate.sourcepackagename = SourcePackageName.id AND
            POTemplate.distroseries = %s""" % sqlvalues(self.id)
        linked_but_no_productseries = SourcePackageName.select(
            query, clauseTables=['POTemplate', 'Packaging'], orderBy=['name'])
        result = unlinked.union(linked_but_no_productseries)
        return [SourcePackage(sourcepackagename=spn, distroseries=self) for
            spn in result]

    def getPublishedSources(self, sourcepackage_or_name, version=None,
                             pocket=None, include_pending=False,
                             archive=None):
        """See `IDistroSeries`."""
        # Deprecated.  Use IArchive.getPublishedSources instead.

        # XXX cprov 2006-02-13 bug 31317:
        # We need a standard and easy API, no need
        # to support multiple type arguments, only string name should be
        # the best choice in here, the call site will be clearer.
        if ISourcePackage.providedBy(sourcepackage_or_name):
            spn = sourcepackage_or_name.name
        elif ISourcePackageName.providedBy(sourcepackage_or_name):
            spn = sourcepackage_or_name
        else:
            spns = getUtility(ISourcePackageNameSet)
            spn = spns.queryByName(sourcepackage_or_name)
            if spn is None:
                return EmptyResultSet()

        queries = ["""
        sourcepackagerelease=sourcepackagerelease.id AND
        sourcepackagepublishinghistory.sourcepackagename=%s AND
        distroseries=%s
        """ % sqlvalues(spn.id, self.id)]

        if pocket is not None:
            queries.append("pocket=%s" % sqlvalues(pocket.value))

        if version is not None:
            queries.append("version=%s" % sqlvalues(version))

        if include_pending:
            queries.append("status in (%s, %s)" % sqlvalues(
                PackagePublishingStatus.PUBLISHED,
                PackagePublishingStatus.PENDING))
        else:
            queries.append("status=%s" % sqlvalues(
                PackagePublishingStatus.PUBLISHED))

        archives = self.distribution.getArchiveIDList(archive)
        queries.append("archive IN %s" % sqlvalues(archives))

        published = SourcePackagePublishingHistory.select(
            " AND ".join(queries), clauseTables=['SourcePackageRelease'],
            orderBy=['-id'])

        return published

    def isUnstable(self):
        """See `IDistroSeries`."""
        return self.status in [
            SeriesStatus.FROZEN,
            SeriesStatus.DEVELOPMENT,
            SeriesStatus.EXPERIMENTAL,
        ]

    def _getAllSources(self):
        """Get all sources ever published in this series' main archives."""
        return IStore(SourcePackagePublishingHistory).find(
            SourcePackagePublishingHistory,
            SourcePackagePublishingHistory.distroseriesID == self.id,
            SourcePackagePublishingHistory.archiveID.is_in(
                self.distribution.all_distro_archive_ids),
            ).order_by(SourcePackagePublishingHistory.id)

    def _getAllBinaries(self):
        """Get all binaries ever published in this series' main archives."""
        return IStore(BinaryPackagePublishingHistory).find(
            BinaryPackagePublishingHistory,
            DistroArchSeries.distroseriesID == self.id,
            BinaryPackagePublishingHistory.distroarchseriesID
                == DistroArchSeries.id,
            BinaryPackagePublishingHistory.archiveID.is_in(
                self.distribution.all_distro_archive_ids),
            ).order_by(BinaryPackagePublishingHistory.id)

    def getAllPublishedSources(self):
        """See `IDistroSeries`."""
        # Consider main archives only, and return all sources in
        # the PUBLISHED state.
        return self._getAllSources().find(
            status=PackagePublishingStatus.PUBLISHED)

    def getAllPublishedBinaries(self):
        """See `IDistroSeries`."""
        # Consider main archives only, and return all binaries in
        # the PUBLISHED state.
        return self._getAllBinaries().find(
            status=PackagePublishingStatus.PUBLISHED)

    def getAllUncondemnedSources(self):
        """See `IDistroSeries`."""
        return self._getAllSources().find(scheduleddeletiondate=None)

    def getAllUncondemnedBinaries(self):
        """See `IDistroSeries`."""
        return self._getAllBinaries().find(scheduleddeletiondate=None)

    def getSourcePackagePublishing(self, pocket, component, archive):
        """See `IDistroSeries`."""
        return Store.of(self).find(
            SourcePackagePublishingHistory,
            SourcePackagePublishingHistory.archive == archive,
            SourcePackagePublishingHistory.distroseries == self,
            SourcePackagePublishingHistory.pocket == pocket,
            SourcePackagePublishingHistory.component == component,
            SourcePackagePublishingHistory.status ==
                PackagePublishingStatus.PUBLISHED)

    def getBinaryPackagePublishing(self, archtag, pocket, component, archive):
        """See `IDistroSeries`."""
        return Store.of(self).find(
            BinaryPackagePublishingHistory,
            DistroArchSeries.distroseries == self,
            DistroArchSeries.architecturetag == archtag,
            BinaryPackagePublishingHistory.archive == archive,
            BinaryPackagePublishingHistory.distroarchseries ==
                DistroArchSeries.id,
            BinaryPackagePublishingHistory.pocket == pocket,
            BinaryPackagePublishingHistory.component == component,
            BinaryPackagePublishingHistory.status ==
                PackagePublishingStatus.PUBLISHED)

    def getBuildRecords(self, build_state=None, name=None, pocket=None,
                        arch_tag=None, user=None, binary_only=True):
        """See IHasBuildRecords"""
        # Ignore "user", since it would not make any difference to the
        # records returned here (private builds are only in PPA right
        # now). We also ignore binary_only and always return binaries.
        return getUtility(IBinaryPackageBuildSet).getBuildsForDistro(
            self, build_state, name, pocket, arch_tag)

    def createUploadedSourcePackageRelease(
        self, sourcepackagename, version, maintainer, builddepends,
        builddependsindep, architecturehintlist, component, creator,
        urgency, changelog, changelog_entry, dsc, dscsigningkey, section,
        dsc_maintainer_rfc822, dsc_standards_version, dsc_format,
        dsc_binaries, archive, copyright, build_conflicts,
        build_conflicts_indep, dateuploaded=DEFAULT,
        source_package_recipe_build=None, user_defined_fields=None,
        homepage=None):
        """See `IDistroSeries`."""
        return SourcePackageRelease(
            upload_distroseries=self, sourcepackagename=sourcepackagename,
            version=version, maintainer=maintainer, dateuploaded=dateuploaded,
            builddepends=builddepends, builddependsindep=builddependsindep,
            architecturehintlist=architecturehintlist, component=component,
            creator=creator, urgency=urgency, changelog=changelog,
            changelog_entry=changelog_entry, dsc=dsc,
            dscsigningkey=dscsigningkey, section=section, copyright=copyright,
            upload_archive=archive,
            dsc_maintainer_rfc822=dsc_maintainer_rfc822,
            dsc_standards_version=dsc_standards_version,
            dsc_format=dsc_format, dsc_binaries=dsc_binaries,
            build_conflicts=build_conflicts,
            build_conflicts_indep=build_conflicts_indep,
            source_package_recipe_build=source_package_recipe_build,
            user_defined_fields=user_defined_fields, homepage=homepage)

    def getComponentByName(self, name):
        """See `IDistroSeries`."""
        comp = Component.byName(name)
        if comp is None:
            raise NotFoundError(name)
        permitted = set(self.components)
        if comp in permitted:
            return comp
        raise NotFoundError(name)

    def getSectionByName(self, name):
        """See `IDistroSeries`."""
        section = Section.byName(name)
        if section is None:
            raise NotFoundError(name)
        permitted = set(self.sections)
        if section in permitted:
            return section
        raise NotFoundError(name)

    def searchPackages(self, text):
        """See `IDistroSeries`."""
        find_spec = (
            DistroSeriesPackageCache,
            BinaryPackageName,
            SQL('rank(fti, ftq(%s)) AS rank' % sqlvalues(text)))
        origin = [
            DistroSeriesPackageCache,
            Join(
                BinaryPackageName,
                DistroSeriesPackageCache.binarypackagename ==
                    BinaryPackageName.id),
            ]

        # Note: When attempting to convert the query below into straight
        # Storm expressions, a 'tuple index out-of-range' error was always
        # raised.
        package_caches = IStore(BinaryPackageName).using(*origin).find(
            find_spec,
            DistroSeriesPackageCache.distroseries == self,
            DistroSeriesPackageCache.archiveID.is_in(
                self.distribution.all_distro_archive_ids),
            Or(
                fti_search(DistroSeriesPackageCache, text),
                DistroSeriesPackageCache.name.contains_string(text.lower())),
            ).config(distinct=True)

        # Create a function that will decorate the results, converting
        # them from the find_spec above into a DSBP:
        def result_to_dsbp((cache, binary_package_name, rank)):
            return DistroSeriesBinaryPackage(
                distroseries=cache.distroseries,
                binarypackagename=binary_package_name,
                cache=cache)

        # Return the decorated result set so the consumer of these
        # results will only see DSBPs
        return DecoratedResultSet(package_caches, result_to_dsbp)

    def newArch(self, architecturetag, processor, official, owner,
                supports_virtualized=False, enabled=True):
        """See `IDistroSeries`."""
        return DistroArchSeries(
            architecturetag=architecturetag, processor=processor,
            official=official, distroseries=self, owner=owner,
            supports_virtualized=supports_virtualized, enabled=enabled)

    def newMilestone(self, name, dateexpected=None, summary=None,
                     code_name=None, tags=None):
        """See `IDistroSeries`."""
        milestone = Milestone(
            name=name, code_name=code_name,
            dateexpected=dateexpected, summary=summary,
            distribution=self.distribution, distroseries=self)
        if tags:
            milestone.setTags(tags.split())
        return milestone

    def getLatestUploads(self):
        """See `IDistroSeries`."""
        query = """
        sourcepackagerelease.id=packageuploadsource.sourcepackagerelease
        AND sourcepackagerelease.sourcepackagename=sourcepackagename.id
        AND packageuploadsource.packageupload=packageupload.id
        AND packageupload.status=%s
        AND packageupload.distroseries=%s
        AND packageupload.archive IN %s
        """ % sqlvalues(
                PackageUploadStatus.DONE,
                self,
                self.distribution.all_distro_archive_ids)

        last_uploads = SourcePackageRelease.select(
            query, limit=5, prejoins=['sourcepackagename'],
            clauseTables=['SourcePackageName', 'PackageUpload',
                          'PackageUploadSource'],
            orderBy=['-packageupload.id'])

        distro_sprs = [
            self.getSourcePackageRelease(spr) for spr in last_uploads]

        return distro_sprs

    @staticmethod
    def setNewerDistroSeriesVersions(spphs):
        """Set the newer_distroseries_version attribute on the spph entries.

        :param spphs: The SourcePackagePublishingHistory objects to set the
            newer_distroseries_version attribute on.
        """
        # Partition by distro series to use getCurrentSourceReleases
        distro_series = collections.defaultdict(list)
        for spph in spphs:
            distro_series[spph.distroseries].append(spph)
        for series, spphs in distro_series.items():
            packagenames = set()
            for spph in spphs:
                packagenames.add(spph.sourcepackagerelease.sourcepackagename)
            latest_releases = series.getCurrentSourceReleases(
                packagenames)
            for spph in spphs:
                latest_release = latest_releases.get(spph.meta_sourcepackage)
                if latest_release is not None and apt_pkg.version_compare(
                    latest_release.version, spph.source_package_version) > 0:
                    version = latest_release
                else:
                    version = None
                get_property_cache(spph).newer_distroseries_version = version

    def createQueueEntry(self, pocket, archive, changesfilename=None,
                         changesfilecontent=None, changes_file_alias=None,
                         signing_key=None, package_copy_job=None):
        """See `IDistroSeries`."""
        if (changesfilename is None) != (changesfilecontent is None):
            raise AssertionError(
                "Inconsistent changesfilename and changesfilecontent. "
                "Pass either both, or neither.")
        if changes_file_alias is not None and changesfilename is not None:
            raise AssertionError(
                "Conflicting options: "
                "Both changesfilename and changes_file_alias were given.")
        have_changes_file = not (
            changesfilename is None and changes_file_alias is None)
        if package_copy_job is None and not have_changes_file:
            raise AssertionError(
                "changesfilename and changesfilecontent must be supplied "
                "if there is no package_copy_job")

        if changesfilename is not None:
            # We store the changes file in the librarian to avoid having to
            # deal with broken encodings in these files; this will allow us
            # to regenerate these files as necessary.
            #
            # The use of StringIO here should be safe: we do not encoding of
            # the content in the changes file (as doing so would be guessing
            # at best, causing unpredictable corruption), and simply pass it
            # off to the librarian.

            # The PGP signature is stripped from all changesfiles
            # to avoid replay attacks (see bugs 159304 and 451396).
            signed_message = signed_message_from_string(changesfilecontent)
            if signed_message is not None:
                # Overwrite `changesfilecontent` with the text stripped
                # of the PGP signature.
                new_content = signed_message.signedContent
                if new_content is not None:
                    changesfilecontent = signed_message.signedContent

            changes_file_alias = getUtility(ILibraryFileAliasSet).create(
                changesfilename, len(changesfilecontent),
                StringIO(changesfilecontent), 'text/plain',
                restricted=archive.private)

        return PackageUpload(
            distroseries=self, status=PackageUploadStatus.NEW,
            pocket=pocket, archive=archive, changesfile=changes_file_alias,
            signing_key=signing_key, package_copy_job=package_copy_job)

    def getPackageUploadQueue(self, state):
        """See `IDistroSeries`."""
        return PackageUploadQueue(self, state)

    def getPackageUploads(self, status=None, created_since_date=None,
                          archive=None, pocket=None, custom_type=None,
                          name=None, version=None, exact_match=False):
        """See `IDistroSeries`."""
        return getUtility(IPackageUploadSet).getAll(
            self, created_since_date, status, archive, pocket, custom_type,
            name=name, version=version, exact_match=exact_match)

    def getBugSummaryContextWhereClause(self):
        """See BugTargetBase."""
        # Circular fail.
        from lp.bugs.model.bugsummary import BugSummary
        return And(
                BugSummary.distroseries_id == self.id,
                BugSummary.sourcepackagename_id == None
                )

    def copyTranslationsFromParent(self, transaction, logger=None):
        """See `IDistroSeries`."""
        if logger is None:
            logger = logging

        assert self.defer_translation_imports, (
            "defer_translation_imports not set!"
            " That would corrupt translation data mixing new imports"
            " with the information being copied.")

        assert self.hide_all_translations, (
            "hide_all_translations not set!"
            " That would allow users to see and modify incomplete"
            " translation state.")

        flush_database_updates()
        flush_database_caches()
        copy_active_translations(self, transaction, logger)

    def getPOFileContributorsByLanguage(self, language):
        """See `IDistroSeries`."""
        contributors = IStore(Person).find(
            Person,
            POFileTranslator.personID == Person.id,
            POFile.id == POFileTranslator.pofileID,
            POFile.language == language,
            POTemplate.id == POFile.potemplateID,
            POTemplate.distroseries == self,
            POTemplate.iscurrent == True)
        contributors = contributors.order_by(*Person._storm_sortingColumns)
        contributors = contributors.config(distinct=True)
        return contributors

    def getPendingPublications(self, archive, pocket, is_careful):
        """See ICanPublishPackages."""
        queries = ['distroseries = %s' % sqlvalues(self)]

        # Query main archive for this distroseries
        queries.append('archive=%s' % sqlvalues(archive))

        # Careful publishing should include all PUBLISHED rows, normal run
        # only includes PENDING ones.
        statuses = [PackagePublishingStatus.PENDING]
        if is_careful:
            statuses.append(PackagePublishingStatus.PUBLISHED)
        queries.append('status IN %s' % sqlvalues(statuses))

        # Restrict to a specific pocket.
        queries.append('pocket = %s' % sqlvalues(pocket))

        # Exclude RELEASE pocket if the distroseries was already released,
        # since it should not change for main archive.
        # We allow RELEASE publishing for PPAs.
        # We also allow RELEASE publishing for partner.
        if (not self.isUnstable() and
            not archive.allowUpdatesToReleasePocket()):
            queries.append(
            'pocket != %s' % sqlvalues(PackagePublishingPocket.RELEASE))

        publications = SourcePackagePublishingHistory.select(
            " AND ".join(queries), orderBy="-id")

        return publications

    def publish(self, diskpool, log, archive, pocket, is_careful=False):
        """See ICanPublishPackages."""
        log.debug("Publishing %s-%s" % (self.title, pocket.name))
        log.debug("Attempting to publish pending sources.")

        dirty_pockets = set()
        for spph in self.getPendingPublications(archive, pocket, is_careful):
            if not self.checkLegalPocket(spph, is_careful, log):
                continue
            spph.publish(diskpool, log)
            dirty_pockets.add((self.name, spph.pocket))

        # propagate publication request to each distroarchseries.
        for dar in self.architectures:
            more_dirt = dar.publish(
                diskpool, log, archive, pocket, is_careful)
            dirty_pockets.update(more_dirt)

        return dirty_pockets

    def checkLegalPocket(self, publication, is_careful, log):
        """Check if the publication can happen in the archive."""
        # 'careful' mode re-publishes everything:
        if is_careful:
            return True

        if not publication.archive.canModifySuite(self, publication.pocket):
            log.error(
                "Tried to publish %s (%s) into the %s pocket on series %s "
                "(%s), skipping" % (
                    publication.displayname, publication.id,
                    publication.pocket, self.displayname, self.status.name))
            return False

        return True

    @property
    def main_archive(self):
        return self.distribution.main_archive

    def getTemplatesCollection(self):
        """See `IHasTranslationTemplates`."""
        return TranslationTemplatesCollection().restrictDistroSeries(self)

    def getSharingPartner(self):
        """See `IHasTranslationTemplates`."""
        # No sharing partner is defined for DistroSeries.
        return None

    def getSuite(self, pocket):
        """See `IDistroSeries`."""
        if pocket == PackagePublishingPocket.RELEASE:
            return self.name
        else:
            return '%s%s' % (self.name, pocketsuffix[pocket])

    def isSourcePackageFormatPermitted(self, format):
        return getUtility(
            ISourcePackageFormatSelectionSet).getBySeriesAndFormat(
                self, format) is not None

    def initDerivedDistroSeries(self, user, parents, architectures=(),
                                archindep_archtag=None, packagesets=(),
                                rebuild=False, overlays=(),
                                overlay_pockets=(),
                                overlay_components=()):
        """See `IDistroSeries`."""
        from lp.soyuz.scripts.initialize_distroseries import (
            InitializationError,
            InitializeDistroSeries,
            )
        if self.isDerivedSeries():
            raise DerivationError(
                "DistroSeries %s already has parent series." % self.name)
        initialize_series = InitializeDistroSeries(
            self, parents, architectures, archindep_archtag, packagesets,
            rebuild, overlays, overlay_pockets, overlay_components)
        try:
            initialize_series.check()
        except InitializationError as e:
            raise DerivationError(e)
        getUtility(IInitializeDistroSeriesJobSource).create(
            self, parents, architectures, archindep_archtag, packagesets,
            rebuild, overlays, overlay_pockets, overlay_components)

    def getParentSeries(self):
        """See `IDistroSeriesPublic`."""
        # Circular imports.
        from lp.registry.interfaces.distroseriesparent import (
            IDistroSeriesParentSet,
            )
        dsp_set = getUtility(IDistroSeriesParentSet)
        dsps = dsp_set.getByDerivedSeries(self).order_by('ordering')
        return [dsp.parent_series for dsp in dsps]

    def getDerivedSeries(self):
        """See `IDistroSeriesPublic`."""
        # Circular imports.
        from lp.registry.interfaces.distroseriesparent import (
            IDistroSeriesParentSet,
            )
        dsps = getUtility(IDistroSeriesParentSet).getByParentSeries(self)
        return [dsp.derived_series for dsp in dsps]

    def getBugTaskWeightFunction(self):
        """Provide a weight function to determine optimal bug task.

        Full weight is given to tasks for this distro series.

        If the series isn't found, the distribution task is better than
        others.
        """
        seriesID = self.id
        distributionID = self.distributionID

        def weight_function(bugtask):
            if bugtask.distroseriesID == seriesID:
                return OrderedBugTask(1, bugtask.id, bugtask)
            elif bugtask.distributionID == distributionID:
                return OrderedBugTask(2, bugtask.id, bugtask)
            else:
                return OrderedBugTask(3, bugtask.id, bugtask)
        return weight_function

    def getDifferencesTo(self, parent_series=None, difference_type=None,
                         source_package_name_filter=None, status=None,
                         child_version_higher=False):
        """See `IDistroSeries`."""
        return getUtility(
            IDistroSeriesDifferenceSource).getForDistroSeries(
                self,
                difference_type=difference_type,
                name_filter=source_package_name_filter,
                status=status,
                child_version_higher=child_version_higher)

    def isDerivedSeries(self):
        """See `IDistroSeries`."""
        return not self.getParentSeries() == []

    def isInitializing(self):
        """See `IDistroSeries`."""
        job = self.getInitializationJob()
        return job is not None and job.is_pending

    def isInitialized(self):
        """See `IDistroSeries`."""
        published = self.main_archive.getPublishedSources(distroseries=self)
        return not published.is_empty()

    def getInitializationJob(self):
        """See `IDistroSeries`."""
        return getUtility(IInitializeDistroSeriesJobSource).get(self)

    def getDifferenceComments(self, since=None, source_package_name=None):
        """See `IDistroSeries`."""
        comment_source = getUtility(IDistroSeriesDifferenceCommentSource)
        return comment_source.getForDistroSeries(
            self, since=since, source_package_name=source_package_name)


class DistroSeriesSet:
    implements(IDistroSeriesSet)

    def get(self, distroseriesid):
        """See `IDistroSeriesSet`."""
        return DistroSeries.get(distroseriesid)

    def translatables(self):
        """See `IDistroSeriesSet`."""
        # Join POTemplate distinctly to only get entries with available
        # translations.
        return IStore(DistroSeries).using((DistroSeries, POTemplate)).find(
            DistroSeries,
            DistroSeries.hide_all_translations == False,
            DistroSeries.id == POTemplate.distroseriesID).config(distinct=True)

    def queryByName(self, distribution, name, follow_aliases=False):
        """See `IDistroSeriesSet`."""
        series = DistroSeries.selectOneBy(distribution=distribution, name=name)
        if series is not None:
            return series
        if follow_aliases:
            try:
                return distribution.resolveSeriesAlias(name)
            except NoSuchDistroSeries:
                pass
        return None

    def queryByVersion(self, distribution, version):
        """See `IDistroSeriesSet`."""
        return DistroSeries.selectOneBy(
            distribution=distribution, version=version)

    def _parseSuite(self, suite):
        """Parse 'suite' into a series name and a pocket."""
        tokens = suite.rsplit('-', 1)
        if len(tokens) == 1:
            return suite, PackagePublishingPocket.RELEASE
        series, pocket = tokens
        try:
            pocket = PackagePublishingPocket.items[pocket.upper()]
        except KeyError:
            # No such pocket. Probably trying to get a hyphenated series name.
            return suite, PackagePublishingPocket.RELEASE
        else:
            return series, pocket

    def fromSuite(self, distribution, suite):
        """See `IDistroSeriesSet`."""
        series_name, pocket = self._parseSuite(suite)
        series = distribution.getSeries(series_name)
        return series, pocket

    def getCurrentSourceReleases(self, distro_series_source_packagenames):
        """See `IDistroSeriesSet`."""
        releases = get_current_source_releases(
            distro_series_source_packagenames,
            lambda series: series.distribution.all_distro_archive_ids,
            (lambda series:
                SourcePackagePublishingHistory.distroseries == series),
            [], SourcePackagePublishingHistory.distroseriesID)
        result = {}
        for spr, series_id in releases:
            series = getUtility(IDistroSeriesSet).get(series_id)
            result[series.getSourcePackage(spr.sourcepackagename)] = (
                DistroSeriesSourcePackageRelease(series, spr))
        return result

    def search(self, distribution=None, isreleased=None, orderBy=None):
        """See `IDistroSeriesSet`."""
        where_clause = ""
        if distribution is not None:
            where_clause += "distribution = %s" % sqlvalues(distribution.id)
        if isreleased is not None:
            if where_clause:
                where_clause += " AND "
            if isreleased:
                # The query is filtered on released releases.
                where_clause += "releasestatus in (%s, %s)" % sqlvalues(
                    SeriesStatus.CURRENT,
                    SeriesStatus.SUPPORTED)
            else:
                # The query is filtered on unreleased releases.
                where_clause += "releasestatus in (%s, %s, %s)" % sqlvalues(
                    SeriesStatus.EXPERIMENTAL,
                    SeriesStatus.DEVELOPMENT,
                    SeriesStatus.FROZEN)
        if orderBy is not None:
            return DistroSeries.select(where_clause, orderBy=orderBy)
        else:

            return DistroSeries.select(where_clause)
