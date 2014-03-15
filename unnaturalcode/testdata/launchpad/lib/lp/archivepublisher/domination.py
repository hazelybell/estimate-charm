# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Archive Domination class.

We call 'domination' the procedure used to identify and supersede all
old versions for a given publication, source or binary, inside a suite
(distroseries + pocket, for instance, gutsy or gutsy-updates).

It also processes the superseded publications and makes the ones with
unnecessary files 'eligible for removal', which will then be considered
for archive removal.  See deathrow.py.

In order to judge if a source is 'eligible for removal' it also checks
if its resulting binaries are not necessary any more in the archive, i.e.,
old binary publications can (and should) hold sources in the archive.

Source version life-cycle example:

  * foo_2.1: currently published, source and binary files live in the archive
             pool and it is listed in the archive indexes.

  * foo_2.0: superseded, it's not listed in archive indexes but one of its
             files is used for foo_2.1 (the orig.tar.gz) or foo_2.1 could
             not build for one or more architectures that foo_2.0 could;

  * foo_1.8: eligible for removal, none of its files are required in the
             archive since foo_2.0 was published (new orig.tar.gz) and none
             of its binaries are published (foo_2.0 was completely built)

  * foo_1.0: removed, it already passed through the quarantine period and its
             files got removed from the archive.

Note that:

  * PUBLISHED and SUPERSEDED are publishing statuses.

  * 'eligible for removal' is a combination of SUPERSEDED or DELETED
    publishing status and a defined (non-empty) 'scheduleddeletiondate'.

  * 'removed' is a combination of 'eligible for removal' and a defined
    (non-empy) 'dateremoved'.

The 'domination' procedure is the 2nd step of the publication pipeline and
it is performed for each suite using:

  * judgeAndDominate(distroseries, pocket)

"""

__metaclass__ = type

__all__ = ['Dominator']

from collections import defaultdict
from datetime import timedelta
from itertools import (
    ifilter,
    ifilterfalse,
    )
from operator import (
    attrgetter,
    itemgetter,
    )

import apt_pkg
from storm.expr import (
    And,
    Count,
    Desc,
    Select,
    )

from lp.registry.model.sourcepackagename import SourcePackageName
from lp.services.database.bulk import load_related
from lp.services.database.constants import UTC_NOW
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import (
    flush_database_updates,
    sqlvalues,
    )
from lp.services.orderingcheck import OrderingCheck
from lp.soyuz.enums import (
    BinaryPackageFormat,
    PackagePublishingStatus,
    )
from lp.soyuz.interfaces.publishing import inactive_publishing_status
from lp.soyuz.model.binarypackagebuild import BinaryPackageBuild
from lp.soyuz.model.binarypackagename import BinaryPackageName
from lp.soyuz.model.binarypackagerelease import BinaryPackageRelease
from lp.soyuz.model.publishing import (
    BinaryPackagePublishingHistory,
    SourcePackagePublishingHistory,
    )
from lp.soyuz.model.sourcepackagerelease import SourcePackageRelease

# Days before a package will be removed from disk.
STAY_OF_EXECUTION = 1


# Ugly, but works
apt_pkg.init_system()


def join_spph_spn():
    """Join condition: SourcePackagePublishingHistory/SourcePackageName."""
    SPPH = SourcePackagePublishingHistory
    SPN = SourcePackageName

    return SPN.id == SPPH.sourcepackagenameID


def join_spph_spr():
    """Join condition: SourcePackageRelease/SourcePackagePublishingHistory.
    """
    SPPH = SourcePackagePublishingHistory
    SPR = SourcePackageRelease

    return SPR.id == SPPH.sourcepackagereleaseID


class SourcePublicationTraits:
    """Basic generalized attributes for `SourcePackagePublishingHistory`.

    Used by `GeneralizedPublication` to hide the differences from
    `BinaryPackagePublishingHistory`.
    """
    release_class = SourcePackageRelease
    release_reference_name = 'sourcepackagereleaseID'

    @staticmethod
    def getPackageName(spph):
        """Return the name of this publication's source package."""
        return spph.sourcepackagename.name

    @staticmethod
    def getPackageRelease(spph):
        """Return this publication's `SourcePackageRelease`."""
        return spph.sourcepackagerelease


class BinaryPublicationTraits:
    """Basic generalized attributes for `BinaryPackagePublishingHistory`.

    Used by `GeneralizedPublication` to hide the differences from
    `SourcePackagePublishingHistory`.
    """
    release_class = BinaryPackageRelease
    release_reference_name = 'binarypackagereleaseID'

    @staticmethod
    def getPackageName(bpph):
        """Return the name of this publication's binary package."""
        return bpph.binarypackagename.name

    @staticmethod
    def getPackageRelease(bpph):
        """Return this publication's `BinaryPackageRelease`."""
        return bpph.binarypackagerelease


class GeneralizedPublication:
    """Generalize handling of publication records.

    This allows us to write code that can be dealing with either
    `SourcePackagePublishingHistory`s or `BinaryPackagePublishingHistory`s
    without caring which.  Differences are abstracted away in a traits
    class.
    """
    def __init__(self, is_source=True):
        self.is_source = is_source
        if is_source:
            self.traits = SourcePublicationTraits
        else:
            self.traits = BinaryPublicationTraits

    def getPackageName(self, pub):
        """Get the package's name."""
        return self.traits.getPackageName(pub)

    def getPackageVersion(self, pub):
        """Obtain the version string for a publication record."""
        return self.traits.getPackageRelease(pub).version

    def compare(self, pub1, pub2):
        """Compare publications by version.

        If both publications are for the same version, their creation dates
        break the tie.
        """
        version_comparison = apt_pkg.version_compare(
            self.getPackageVersion(pub1), self.getPackageVersion(pub2))

        if version_comparison == 0:
            # Use dates as tie breaker.
            return cmp(pub1.datecreated, pub2.datecreated)
        else:
            return version_comparison

    def sortPublications(self, publications):
        """Sort publications from most to least current versions."""
        return sorted(publications, cmp=self.compare, reverse=True)


def find_live_source_versions(sorted_pubs):
    """Find versions out of Published publications that should stay live.

    This particular notion of liveness applies to source domination: the
    latest version stays live, and that's it.

    :param sorted_pubs: An iterable of `SourcePackagePublishingHistory`
        sorted by descending package version.
    :return: A list of live versions.
    """
    # Given the required sort order, the latest version is at the head
    # of the list.
    return [sorted_pubs[0].sourcepackagerelease.version]


def get_binary_versions(binary_publications):
    """List versions for sequence of `BinaryPackagePublishingHistory`.

    :param binary_publications: An iterable of
        `BinaryPackagePublishingHistory`.
    :return: A list of the publications' respective versions.
    """
    return [pub.binarypackagerelease.version for pub in binary_publications]


def find_live_binary_versions_pass_1(sorted_pubs):
    """Find versions out of Published `publications` that should stay live.

    This particular notion of liveness applies to first-pass binary
    domination: the latest version stays live, and so do publications of
    binary packages for the "all" architecture.

    :param sorted_pubs: An iterable of `BinaryPackagePublishingHistory`,
        sorted by descending package version.
    :return: A list of live versions.
    """
    sorted_pubs = list(sorted_pubs)
    latest = sorted_pubs.pop(0)
    return get_binary_versions(
        [latest] + [
            pub for pub in sorted_pubs if not pub.architecture_specific])


class ArchSpecificPublicationsCache:
    """Cache to track which releases have arch-specific publications.

    This is used for second-pass binary domination:
    architecture-independent binary publications cannot be superseded as long
    as any architecture-dependent binary publications built from the same
    source package release are still active.  Thus such arch-indep
    publications are reprieved from domination.

    This class looks up whether publications for a release need that
    reprieve.  That only needs to be looked up in the database once per
    (source package release, archive, distroseries, pocket).  Hence this
    cache.
    """
    def __init__(self):
        self.cache = {}

    @staticmethod
    def getKey(bpph):
        """Extract just the relevant bits of information from a bpph."""
        return (
            bpph.binarypackagerelease.build.source_package_release,
            bpph.archive,
            bpph.distroseries,
            bpph.pocket,
            )

    def hasArchSpecificPublications(self, bpph):
        """Does bpph have active, arch-specific publications?

        If so, the dominator will want to reprieve `bpph`.
        """
        assert not bpph.architecture_specific, (
            "Wrongly dominating arch-specific binary pub in pass 2.")

        key = self.getKey(bpph)
        if key not in self.cache:
            self.cache[key] = self._lookUp(*key)
        return self.cache[key]

    @staticmethod
    def _lookUp(spr, archive, distroseries, pocket):
        """Look up an answer in the database."""
        query = spr.getActiveArchSpecificPublications(
            archive, distroseries, pocket)
        return not query.is_empty()


def find_live_binary_versions_pass_2(sorted_pubs, cache):
    """Find versions out of Published publications that should stay live.

    This particular notion of liveness applies to second-pass binary
    domination: the latest version stays live, and architecture-specific
    publications stay live (i.e, ones that are not for the "all"
    architecture).

    More importantly, any publication for binary packages of the "all"
    architecture stay live if any of the non-"all" binary packages from
    the same source package release are still active -- even if they are
    for other architectures.

    This is the raison d'etre for the two-pass binary domination algorithm:
    to let us see which architecture-independent binary publications can be
    superseded without rendering any architecture-specific binaries from the
    same source package release uninstallable.

    (Note that here, "active" includes Published publications but also
    Pending ones.  This is standard nomenclature in Soyuz.  Some of the
    domination code confuses matters by using the term "active" to mean only
    Published publications).

    :param sorted_pubs: An iterable of `BinaryPackagePublishingHistory`,
        sorted by descending package version.
    :param cache: An `ArchSpecificPublicationsCache` to reduce the number of
        times we need to look up whether an spr/archive/distroseries/pocket
        has active arch-specific publications.
    :return: A list of live versions.
    """
    sorted_pubs = list(sorted_pubs)
    latest = sorted_pubs.pop(0)
    is_arch_specific = attrgetter('architecture_specific')
    arch_specific_pubs = list(ifilter(is_arch_specific, sorted_pubs))
    arch_indep_pubs = list(ifilterfalse(is_arch_specific, sorted_pubs))

    bpbs = load_related(
        BinaryPackageBuild,
        [pub.binarypackagerelease for pub in arch_indep_pubs], ['buildID'])
    load_related(SourcePackageRelease, bpbs, ['source_package_release_id'])

    reprieved_pubs = [
        pub
        for pub in arch_indep_pubs
            if cache.hasArchSpecificPublications(pub)]

    return get_binary_versions([latest] + arch_specific_pubs + reprieved_pubs)


def contains_arch_indep(bpphs):
    """Are any of the publications among `bpphs` architecture-independent?"""
    return any(not bpph.architecture_specific for bpph in bpphs)


class Dominator:
    """Manage the process of marking packages as superseded.

    Packages are marked as superseded when they become obsolete.
    """

    def __init__(self, logger, archive):
        """Initialize the dominator.

        This process should be run after the publisher has published
        new stuff into the distribution but before the publisher
        creates the file lists for apt-ftparchive.
        """
        self.logger = logger
        self.archive = archive

    def dominatePackage(self, sorted_pubs, live_versions, generalization):
        """Dominate publications for a single package.

        The latest publication for any version in `live_versions` stays
        active.  Any older publications (including older publications for
        live versions with multiple publications) are marked as superseded by
        the respective oldest live releases that are newer than the superseded
        ones.

        Any versions that are newer than anything in `live_versions` are
        marked as deleted.  This should not be possible in Soyuz-native
        archives, but it can happen during archive imports when the
        previous latest version of a package has disappeared from the Sources
        list we import.

        :param sorted_pubs: A list of publications for the same package,
            in the same archive, series, and pocket, all with status
            `PackagePublishingStatus.PUBLISHED`.  They must be sorted from
            most current to least current, as would be the result of
            `generalization.sortPublications`.
        :param live_versions: Iterable of versions that are still considered
            "live" for this package.  For any of these, the latest publication
            among `publications` will remain Published.  Publications for
            older releases, as well as older publications of live versions,
            will be marked as Superseded.  Publications of newer versions than
            are listed in `live_versions` are marked as Deleted.
        :param generalization: A `GeneralizedPublication` helper representing
            the kind of publications these are: source or binary.
        """
        live_versions = frozenset(live_versions)

        self.logger.debug(
            "Package has %d live publication(s).  Live versions: %s",
            len(sorted_pubs), live_versions)

        # Verify that the publications are really sorted properly.
        check_order = OrderingCheck(cmp=generalization.compare, reverse=True)

        current_dominant = None
        dominant_version = None

        for pub in sorted_pubs:
            check_order.check(pub)

            version = generalization.getPackageVersion(pub)
            # There should never be two published releases with the same
            # version.  So it doesn't matter whether this comparison is
            # really a string comparison or a version comparison: if the
            # versions are equal by either measure, they're from the same
            # release.
            if version == dominant_version:
                # This publication is for a live version, but has been
                # superseded by a newer publication of the same version.
                # Supersede it.
                pub.supersede(current_dominant, logger=self.logger)
                self.logger.debug2(
                    "Superseding older publication for version %s.", version)
            elif version in live_versions:
                # This publication stays active; if any publications
                # that follow right after this are to be superseded,
                # this is the release that they are superseded by.
                current_dominant = pub
                dominant_version = version
                self.logger.debug2("Keeping version %s.", version)
            elif current_dominant is None:
                # This publication is no longer live, but there is no
                # newer version to supersede it either.  Therefore it
                # must be deleted.
                pub.requestDeletion(None)
                self.logger.debug2("Deleting version %s.", version)
            else:
                # This publication is superseded.  This is what we're
                # here to do.
                pub.supersede(current_dominant, logger=self.logger)
                self.logger.debug2("Superseding version %s.", version)

    def _sortPackages(self, publications, generalization):
        """Partition publications by package name, and sort them.

        The publications are sorted from most current to least current,
        as required by `dominatePackage` etc.

        :param publications: An iterable of `SourcePackagePublishingHistory`
            or of `BinaryPackagePublishingHistory`.
        :param generalization: A `GeneralizedPublication` helper representing
            the kind of publications these are: source or binary.
        :return: A dict mapping each package name to a sorted list of
            publications from `publications`.
        """
        pubs_by_package = defaultdict(list)
        for pub in publications:
            pubs_by_package[generalization.getPackageName(pub)].append(pub)

        # Sort the publication lists.  This is not an in-place sort, so
        # it involves altering the dict while we iterate it.  Listify
        # the keys so that we can be sure that we're not altering the
        # iteration order while iteration is underway.
        for package in list(pubs_by_package.keys()):
            pubs_by_package[package] = generalization.sortPublications(
                pubs_by_package[package])

        return pubs_by_package

    def _setScheduledDeletionDate(self, pub_record):
        """Set the scheduleddeletiondate on a publishing record.

        If the status is DELETED we set the date to UTC_NOW, otherwise
        it gets the configured stay of execution period.
        """
        if pub_record.status == PackagePublishingStatus.DELETED:
            pub_record.scheduleddeletiondate = UTC_NOW
        else:
            pub_record.scheduleddeletiondate = (
                UTC_NOW + timedelta(days=STAY_OF_EXECUTION))

    def _judgeSuperseded(self, source_records, binary_records):
        """Determine whether the superseded packages supplied should
        be moved to death row or not.

        Currently this is done by assuming that any superseded binary
        package should be removed. In the future this should attempt
        to supersede binaries in build-sized chunks only, bug 55030.

        Superseded source packages are considered removable when they
        have no binaries in this distroseries which are published or
        superseded

        When a package is considered for death row it is given a
        'scheduled deletion date' of now plus the defined 'stay of execution'
        time provided in the configuration parameter.
        """
        self.logger.debug("Beginning superseded processing...")

        for pub_record in binary_records:
            binpkg_release = pub_record.binarypackagerelease
            self.logger.debug(
                "%s/%s (%s) has been judged eligible for removal",
                binpkg_release.binarypackagename.name, binpkg_release.version,
                pub_record.distroarchseries.architecturetag)
            self._setScheduledDeletionDate(pub_record)
            # XXX cprov 20070820: 'datemadepending' is useless, since it's
            # always equals to "scheduleddeletiondate - quarantine".
            pub_record.datemadepending = UTC_NOW

        for pub_record in source_records:
            srcpkg_release = pub_record.sourcepackagerelease
            # Attempt to find all binaries of this
            # SourcePackageRelease which are/have been in this
            # distroseries...
            considered_binaries = BinaryPackagePublishingHistory.select("""
            binarypackagepublishinghistory.distroarchseries =
                distroarchseries.id AND
            binarypackagepublishinghistory.scheduleddeletiondate IS NULL AND
            binarypackagepublishinghistory.dateremoved IS NULL AND
            binarypackagepublishinghistory.archive = %s AND
            binarypackagebuild.source_package_release = %s AND
            distroarchseries.distroseries = %s AND
            binarypackagepublishinghistory.binarypackagerelease =
            binarypackagerelease.id AND
            binarypackagerelease.build = binarypackagebuild.id AND
            binarypackagepublishinghistory.pocket = %s
            """ % sqlvalues(self.archive, srcpkg_release,
                            pub_record.distroseries, pub_record.pocket),
            clauseTables=['DistroArchSeries', 'BinaryPackageRelease',
                          'BinaryPackageBuild'])

            # There is at least one non-removed binary to consider
            if not considered_binaries.is_empty():
                # However we can still remove *this* record if there's
                # at least one other PUBLISHED for the spr. This happens
                # when a package is moved between components.
                published = SourcePackagePublishingHistory.selectBy(
                    distroseries=pub_record.distroseries,
                    pocket=pub_record.pocket,
                    status=PackagePublishingStatus.PUBLISHED,
                    archive=self.archive,
                    sourcepackagereleaseID=srcpkg_release.id)
                # Zero PUBLISHED for this spr, so nothing to take over
                # for us, so leave it for consideration next time.
                if published.is_empty():
                    continue

            # Okay, so there's no unremoved binaries, let's go for it...
            self.logger.debug(
                "%s/%s (%s) source has been judged eligible for removal",
                srcpkg_release.sourcepackagename.name, srcpkg_release.version,
                pub_record.id)
            self._setScheduledDeletionDate(pub_record)
            # XXX cprov 20070820: 'datemadepending' is pointless, since it's
            # always equals to "scheduleddeletiondate - quarantine".
            pub_record.datemadepending = UTC_NOW

    def findBinariesForDomination(self, distroarchseries, pocket):
        """Find binary publications that need dominating.

        This is only for traditional domination, where the latest published
        publication is always kept published.  It will ignore publications
        that have no other publications competing for the same binary package.
        """
        BPPH = BinaryPackagePublishingHistory
        BPR = BinaryPackageRelease

        bpph_location_clauses = [
            BPPH.status == PackagePublishingStatus.PUBLISHED,
            BPPH.distroarchseries == distroarchseries,
            BPPH.archive == self.archive,
            BPPH.pocket == pocket,
            ]
        candidate_binary_names = Select(
            BPPH.binarypackagenameID, And(*bpph_location_clauses),
            group_by=BPPH.binarypackagenameID, having=(Count() > 1))
        main_clauses = bpph_location_clauses + [
            BPR.id == BPPH.binarypackagereleaseID,
            BPR.binarypackagenameID.is_in(candidate_binary_names),
            BPR.binpackageformat != BinaryPackageFormat.DDEB,
            ]

        # We're going to access the BPRs as well.  Since we make the
        # database look them up anyway, and since there won't be many
        # duplications among them, load them alongside the publications.
        # We'll also want their BinaryPackageNames, but adding those to
        # the join would complicate the query.
        query = IStore(BPPH).find((BPPH, BPR), *main_clauses)
        bpphs = list(DecoratedResultSet(query, itemgetter(0)))
        load_related(BinaryPackageName, bpphs, ['binarypackagenameID'])
        return bpphs

    def dominateBinaries(self, distroseries, pocket):
        """Perform domination on binary package publications.

        Dominates binaries, restricted to `distroseries`, `pocket`, and
        `self.archive`.
        """
        generalization = GeneralizedPublication(is_source=False)

        # Domination happens in two passes.  The first tries to
        # supersede architecture-dependent publications; the second
        # tries to supersede architecture-independent ones.  An
        # architecture-independent pub is kept alive as long as any
        # architecture-dependent pubs from the same source package build
        # are still live for any architecture, because they may depend
        # on the architecture-independent package.
        # Thus we limit the second pass to those packages that have
        # published, architecture-independent publications; anything
        # else will have completed domination in the first pass.
        packages_w_arch_indep = set()

        for distroarchseries in distroseries.architectures:
            self.logger.info(
                "Performing domination across %s/%s (%s)",
                distroarchseries.distroseries.name, pocket.title,
                distroarchseries.architecturetag)

            self.logger.info("Finding binaries...")
            bins = self.findBinariesForDomination(distroarchseries, pocket)
            sorted_packages = self._sortPackages(bins, generalization)
            self.logger.info("Dominating binaries...")
            for name, pubs in sorted_packages.iteritems():
                self.logger.debug("Dominating %s" % name)
                assert len(pubs) > 0, "Dominating zero binaries!"
                live_versions = find_live_binary_versions_pass_1(pubs)
                self.dominatePackage(pubs, live_versions, generalization)
                if contains_arch_indep(pubs):
                    packages_w_arch_indep.add(name)

        packages_w_arch_indep = frozenset(packages_w_arch_indep)

        # The second pass attempts to supersede arch-all publications of
        # older versions, from source package releases that no longer
        # have any active arch-specific publications that might depend
        # on the arch-indep ones.
        # (In maintaining this code, bear in mind that some or all of a
        # source package's binary packages may switch between
        # arch-specific and arch-indep between releases.)
        reprieve_cache = ArchSpecificPublicationsCache()
        for distroarchseries in distroseries.architectures:
            self.logger.info("Finding binaries...(2nd pass)")
            bins = self.findBinariesForDomination(distroarchseries, pocket)
            sorted_packages = self._sortPackages(bins, generalization)
            self.logger.info("Dominating binaries...(2nd pass)")
            for name in packages_w_arch_indep.intersection(sorted_packages):
                pubs = sorted_packages[name]
                self.logger.debug("Dominating %s" % name)
                assert len(pubs) > 0, "Dominating zero binaries in 2nd pass!"
                live_versions = find_live_binary_versions_pass_2(
                    pubs, reprieve_cache)
                self.dominatePackage(pubs, live_versions, generalization)

    def _composeActiveSourcePubsCondition(self, distroseries, pocket):
        """Compose ORM condition for restricting relevant source pubs."""
        SPPH = SourcePackagePublishingHistory

        return And(
            SPPH.status == PackagePublishingStatus.PUBLISHED,
            SPPH.distroseries == distroseries,
            SPPH.archive == self.archive,
            SPPH.pocket == pocket,
            )

    def findSourcesForDomination(self, distroseries, pocket):
        """Find binary publications that need dominating.

        This is only for traditional domination, where the latest published
        publication is always kept published.  See `find_live_source_versions`
        for this logic.

        To optimize for that logic, `findSourcesForDomination` will ignore
        publications that have no other publications competing for the same
        binary package.  There'd be nothing to do for those cases.
        """
        SPPH = SourcePackagePublishingHistory
        SPR = SourcePackageRelease

        spph_location_clauses = self._composeActiveSourcePubsCondition(
            distroseries, pocket)
        candidate_source_names = Select(
            SPPH.sourcepackagenameID,
            And(join_spph_spr(), spph_location_clauses),
            group_by=SPPH.sourcepackagenameID,
            having=(Count() > 1))

        # We'll also access the SourcePackageReleases associated with
        # the publications we find.  Since they're in the join anyway,
        # load them alongside the publications.
        # Actually we'll also want the SourcePackageNames, but adding
        # those to the (outer) query would complicate it, and
        # potentially slow it down.
        query = IStore(SPPH).find(
            (SPPH, SPR),
            join_spph_spr(),
            SPPH.sourcepackagenameID.is_in(candidate_source_names),
            spph_location_clauses)
        spphs = DecoratedResultSet(query, itemgetter(0))
        load_related(SourcePackageName, spphs, ['sourcepackagenameID'])
        return spphs

    def dominateSources(self, distroseries, pocket):
        """Perform domination on source package publications.

        Dominates sources, restricted to `distroseries`, `pocket`, and
        `self.archive`.
        """
        self.logger.debug(
            "Performing domination across %s/%s (Source)",
            distroseries.name, pocket.title)

        generalization = GeneralizedPublication(is_source=True)

        self.logger.debug("Finding sources...")
        sources = self.findSourcesForDomination(distroseries, pocket)
        sorted_packages = self._sortPackages(sources, generalization)

        self.logger.debug("Dominating sources...")
        for name, pubs in sorted_packages.iteritems():
            self.logger.debug("Dominating %s" % name)
            assert len(pubs) > 0, "Dominating zero sources!"
            live_versions = find_live_source_versions(pubs)
            self.dominatePackage(pubs, live_versions, generalization)

        flush_database_updates()

    def findPublishedSourcePackageNames(self, distroseries, pocket):
        """Find currently published source packages.

        Returns an iterable of tuples: (name of source package, number of
        publications in Published state).
        """
        looking_for = (
            SourcePackageName.name,
            Count(SourcePackagePublishingHistory.id),
            )
        result = IStore(SourcePackageName).find(
            looking_for,
            join_spph_spr(),
            join_spph_spn(),
            self._composeActiveSourcePubsCondition(distroseries, pocket))
        return result.group_by(SourcePackageName.name)

    def findPublishedSPPHs(self, distroseries, pocket, package_name):
        """Find currently published source publications for given package."""
        SPPH = SourcePackagePublishingHistory
        SPR = SourcePackageRelease

        query = IStore(SourcePackagePublishingHistory).find(
            SPPH,
            join_spph_spr(),
            join_spph_spn(),
            SourcePackageName.name == package_name,
            self._composeActiveSourcePubsCondition(distroseries, pocket))
        # Sort by descending version (SPR.version has type debversion in
        # the database, so this should be a real proper comparison) so
        # that _sortPackage will have slightly less work to do later.
        return query.order_by(Desc(SPR.version), Desc(SPPH.datecreated))

    def dominateSourceVersions(self, distroseries, pocket, package_name,
                               live_versions):
        """Dominate source publications based on a set of "live" versions.

        Active publications for the "live" versions will remain active.  All
        other active publications for the same package (and the same archive,
        distroseries, and pocket) are marked superseded.

        Unlike traditional domination, this allows multiple versions of a
        package to stay active in the same distroseries, archive, and pocket.

        :param distroseries: `DistroSeries` to dominate.
        :param pocket: `PackagePublishingPocket` to dominate.
        :param package_name: Source package name, as text.
        :param live_versions: Iterable of all version strings that are to
            remain active.
        """
        generalization = GeneralizedPublication(is_source=True)
        pubs = self.findPublishedSPPHs(distroseries, pocket, package_name)
        pubs = generalization.sortPublications(pubs)
        self.dominatePackage(pubs, live_versions, generalization)

    def judge(self, distroseries, pocket):
        """Judge superseded sources and binaries."""
        sources = SourcePackagePublishingHistory.select("""
            sourcepackagepublishinghistory.distroseries = %s AND
            sourcepackagepublishinghistory.archive = %s AND
            sourcepackagepublishinghistory.pocket = %s AND
            sourcepackagepublishinghistory.status IN %s AND
            sourcepackagepublishinghistory.scheduleddeletiondate is NULL AND
            sourcepackagepublishinghistory.dateremoved is NULL
            """ % sqlvalues(
                distroseries, self.archive, pocket,
                inactive_publishing_status))

        binaries = BinaryPackagePublishingHistory.select("""
            binarypackagepublishinghistory.distroarchseries =
                distroarchseries.id AND
            distroarchseries.distroseries = %s AND
            binarypackagepublishinghistory.archive = %s AND
            binarypackagepublishinghistory.pocket = %s AND
            binarypackagepublishinghistory.status IN %s AND
            binarypackagepublishinghistory.scheduleddeletiondate is NULL AND
            binarypackagepublishinghistory.dateremoved is NULL
            """ % sqlvalues(
                distroseries, self.archive, pocket,
                inactive_publishing_status),
            clauseTables=['DistroArchSeries'])

        self._judgeSuperseded(sources, binaries)

    def judgeAndDominate(self, distroseries, pocket):
        """Perform the domination and superseding calculations

        It only works across the distroseries and pocket specified.
        """

        self.dominateBinaries(distroseries, pocket)
        self.dominateSources(distroseries, pocket)
        self.judge(distroseries, pocket)

        self.logger.debug(
            "Domination for %s/%s finished", distroseries.name, pocket.title)
