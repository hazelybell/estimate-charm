# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Module docstring goes here."""

__metaclass__ = type
__all__ = [
    'DistributionMirror',
    'MirrorDistroArchSeries',
    'MirrorDistroSeriesSource',
    'MirrorProbeRecord',
    'DistributionMirrorSet',
    'MirrorCDImageDistroSeries',
    ]

from datetime import (
    datetime,
    MINYEAR,
    timedelta,
    )

import pytz
from sqlobject import (
    BoolCol,
    ForeignKey,
    StringCol,
    )
from storm.expr import (
    And,
    Desc,
    Func,
    )
from storm.store import Store
from zope.component import getUtility
from zope.interface import implements

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.archivepublisher.diskpool import poolify
from lp.registry.errors import (
    CannotTransitionToCountryMirror,
    CountryMirrorAlreadySet,
    MirrorHasNoHTTPURL,
    MirrorNotOfficial,
    MirrorNotProbed,
    )
from lp.registry.interfaces.distributionmirror import (
    IDistributionMirror,
    IDistributionMirrorSet,
    IMirrorCDImageDistroSeries,
    IMirrorDistroArchSeries,
    IMirrorDistroSeriesSource,
    IMirrorProbeRecord,
    MirrorContent,
    MirrorFreshness,
    MirrorSpeed,
    MirrorStatus,
    PROBE_INTERVAL,
    )
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.person import validate_public_person
from lp.registry.interfaces.pocket import (
    PackagePublishingPocket,
    pocketsuffix,
    )
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.interfaces.sourcepackage import SourcePackageFileType
from lp.services.config import config
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from lp.services.helpers import shortlist
from lp.services.mail.helpers import (
    get_contact_email_addresses,
    get_email_template,
    )
from lp.services.mail.sendmail import (
    format_address,
    simple_sendmail,
    )
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    urlappend,
    )
from lp.services.worlddata.model.country import Country
from lp.soyuz.enums import (
    BinaryPackageFileType,
    PackagePublishingStatus,
    )
from lp.soyuz.interfaces.distroarchseries import IDistroArchSeries
from lp.soyuz.model.files import (
    BinaryPackageFile,
    SourcePackageReleaseFile,
    )
from lp.soyuz.model.publishing import (
    BinaryPackagePublishingHistory,
    SourcePackagePublishingHistory,
    )


class DistributionMirror(SQLBase):
    """See IDistributionMirror"""

    implements(IDistributionMirror)
    _table = 'DistributionMirror'
    _defaultOrder = ('-speed', 'name', 'id')

    owner = ForeignKey(
        dbName='owner', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)
    reviewer = ForeignKey(
        dbName='reviewer', foreignKey='Person',
        storm_validator=validate_public_person, default=None)
    distribution = ForeignKey(
        dbName='distribution', foreignKey='Distribution', notNull=True)
    name = StringCol(
        alternateID=True, notNull=True)
    displayname = StringCol(
        notNull=False, default=None)
    description = StringCol(
        notNull=False, default=None)
    http_base_url = StringCol(
        notNull=False, default=None, unique=True)
    ftp_base_url = StringCol(
        notNull=False, default=None, unique=True)
    rsync_base_url = StringCol(
        notNull=False, default=None, unique=True)
    enabled = BoolCol(
        notNull=True, default=False)
    speed = EnumCol(
        notNull=True, enum=MirrorSpeed)
    country = ForeignKey(
        dbName='country', foreignKey='Country', notNull=True)
    content = EnumCol(
        notNull=True, enum=MirrorContent)
    official_candidate = BoolCol(
        notNull=True, default=False)
    status = EnumCol(
        notNull=True, default=MirrorStatus.PENDING_REVIEW, enum=MirrorStatus)
    date_created = UtcDateTimeCol(notNull=True, default=UTC_NOW)
    date_reviewed = UtcDateTimeCol(default=None)
    whiteboard = StringCol(
        notNull=False, default=None)
    country_dns_mirror = BoolCol(
        notNull=True, default=False)

    @property
    def base_url(self):
        """See IDistributionMirror"""
        if self.http_base_url is not None:
            return self.http_base_url
        else:
            return self.ftp_base_url

    @property
    def last_probe_record(self):
        """See IDistributionMirror"""
        return MirrorProbeRecord.selectFirst(
            MirrorProbeRecord.q.distribution_mirrorID == self.id,
            orderBy='-date_created')

    @property
    def all_probe_records(self):
        """See IDistributionMirror"""
        return MirrorProbeRecord.selectBy(
            distribution_mirror=self, orderBy='-date_created')

    @property
    def title(self):
        """See IDistributionMirror"""
        if self.displayname:
            return self.displayname
        else:
            return self.name.capitalize()

    @property
    def has_ftp_or_rsync_base_url(self):
        """See IDistributionMirror"""
        return (self.ftp_base_url is not None
                or self.rsync_base_url is not None)

    @cachedproperty
    def arch_mirror_freshness(self):
        """See IDistributionMirror"""
        store = Store.of(self)
        mirror = store.find(
            MirrorDistroArchSeries,
            And(
                MirrorDistroArchSeries.distribution_mirror == self,
                MirrorDistroArchSeries.freshness != MirrorFreshness.UNKNOWN)
                ).order_by(Desc(MirrorDistroArchSeries.freshness)).first()
        if not mirror:
            return None
        else:
            return mirror.freshness

    @cachedproperty
    def source_mirror_freshness(self):
        """See IDistributionMirror"""
        store = Store.of(self)
        mirror = store.find(
            MirrorDistroSeriesSource,
            And(
                MirrorDistroSeriesSource.distribution_mirror == self,
                MirrorDistroSeriesSource.freshness != MirrorFreshness.UNKNOWN)
                ).order_by(Desc(MirrorDistroSeriesSource.freshness)).first()
        if not mirror:
            return None
        else:
            return mirror.freshness

    def destroySelf(self):
        """Delete this mirror from the database.

        Only mirrors which have never been probed can be deleted.
        """
        assert self.last_probe_record is None, (
            "This mirror has been probed and thus can't be removed.")
        SQLBase.destroySelf(self)

    def verifyTransitionToCountryMirror(self):
        """Verify that a mirror can be set as a country mirror.

        Return True if valid, otherwise raise a subclass of
        CannotTransitionToCountryMirror.
        """

        current_country_mirror = self.distribution.getCountryMirror(
            self.country, self.content)

        if current_country_mirror is not None:
            # Country already has a country mirror.
            raise CountryMirrorAlreadySet(
                "%s already has a country %s mirror set." % (
                    self.country.name, self.content))

        if not self.isOfficial():
            # Only official mirrors may be set as country mirrors.
            raise MirrorNotOfficial(
                "This mirror may not be set as a country mirror as it is not "
                "an official mirror.")

        if self.http_base_url is None:
            # Country mirrors must have HTTP URLs set.
            raise MirrorHasNoHTTPURL(
                "This mirror may not be set as a country mirror as it does "
                "not have an HTTP URL set.")

        if not self.last_probe_record:
            # Only mirrors which have been probed may be set as country
            # mirrors.
            raise MirrorNotProbed(
                "This mirror may not be set as a country mirror as it has "
                "not been probed.")

        # Verification done.
        return True

    def canTransitionToCountryMirror(self):
        """See `IDistributionMirror`."""
        try:
            return self.verifyTransitionToCountryMirror()
        except CannotTransitionToCountryMirror:
            return False

    def transitionToCountryMirror(self, country_dns_mirror):
        """See `IDistributionMirror`."""

        # country_dns_mirror has not been changed, do nothing.
        if self.country_dns_mirror == country_dns_mirror:
            return

        # Environment sanity checks.
        if country_dns_mirror:
            self.verifyTransitionToCountryMirror()

        self.country_dns_mirror = country_dns_mirror

    def getOverallFreshness(self):
        """See IDistributionMirror"""
        # XXX Guilherme Salgado 2006-08-16:
        # We shouldn't be using MirrorFreshness to represent the overall
        # freshness of a mirror, but for now it'll do the job and we'll use
        # the UNKNOWN freshness to represent a mirror without any content
        # (which may mean the mirror was never verified or it was verified
        # and no content was found).
        if self.content == MirrorContent.RELEASE:
            if self.cdimage_series:
                return MirrorFreshness.UP
            else:
                return MirrorFreshness.UNKNOWN

        elif self.content == MirrorContent.ARCHIVE:
            # Return the worst (i.e. highest valued) mirror freshness out of
            # all mirrors (binary and source) for this distribution mirror.
            arch_mirror_freshness = self.arch_mirror_freshness
            source_mirror_freshness = self.source_mirror_freshness

            # Return unknown if no content
            if (arch_mirror_freshness is None and
                source_mirror_freshness is None):
                return MirrorFreshness.UNKNOWN

            # Return arch_mirror freshness if we have no source mirror.
            if  (arch_mirror_freshness is not None and
                  source_mirror_freshness is None):
                return arch_mirror_freshness

            # Return source_mirror freshness if we have no arch mirror.
            if (arch_mirror_freshness is None and
                source_mirror_freshness is not None):
                return source_mirror_freshness

            # Return the freshest data if we have data for both.
            if source_mirror_freshness > arch_mirror_freshness:
                return source_mirror_freshness
            else:
                return arch_mirror_freshness
        else:
            raise AssertionError(
                'DistributionMirror.content is not ARCHIVE nor RELEASE: %r'
                % self.content)

    def isOfficial(self):
        """See IDistributionMirror"""
        return (self.official_candidate
                and self.status == MirrorStatus.OFFICIAL)

    def shouldDisable(self, expected_file_count=None):
        """See IDistributionMirror"""
        if self.content == MirrorContent.RELEASE:
            if expected_file_count is None:
                raise AssertionError(
                    'For series mirrors we need to know the '
                    'expected_file_count in order to tell if it should '
                    'be disabled or not.')
            if expected_file_count > self.cdimage_series.count():
                return True
        else:
            if not (self.source_series or self.arch_series):
                return True
        return False

    def disable(self, notify_owner, log):
        """See IDistributionMirror"""
        assert self.last_probe_record is not None, (
            "This method can't be called on a mirror that has never been "
            "probed.")
        if self.enabled or self.all_probe_records.count() == 1:
            self._sendFailureNotification(notify_owner, log)
        self.enabled = False

    def _sendFailureNotification(self, notify_owner, log):
        """Send a failure notification to the distribution's mirror admins and
        to the mirror owner, in case notify_owner is True.
        """
        template = get_email_template(
            'notify-mirror-owner.txt', app='registry')
        fromaddress = format_address(
            "Launchpad Mirror Prober", config.canonical.noreply_from_address)

        replacements = {
            'distro': self.distribution.title,
            'mirror_name': self.name,
            'mirror_url': canonical_url(self),
            'log_snippet': "\n".join(log.split('\n')[:20]),
            'logfile_url': self.last_probe_record.log_file.http_url}
        message = template % replacements
        subject = "Launchpad: Verification of %s failed" % self.name

        mirror_admin_address = get_contact_email_addresses(
            self.distribution.mirror_admin)
        simple_sendmail(fromaddress, mirror_admin_address, subject, message)

        if notify_owner:
            owner_address = get_contact_email_addresses(self.owner)
            if len(owner_address) > 0:
                simple_sendmail(fromaddress, owner_address, subject, message)

    def newProbeRecord(self, log_file):
        """See IDistributionMirror"""
        return MirrorProbeRecord(distribution_mirror=self, log_file=log_file)

    def deleteMirrorDistroArchSeries(self, distro_arch_series, pocket,
                                     component):
        """See IDistributionMirror"""
        mirror = MirrorDistroArchSeries.selectOneBy(
            distribution_mirror=self, distro_arch_series=distro_arch_series,
            pocket=pocket, component=component)
        if mirror is not None:
            mirror.destroySelf()

    def _getMirrorDistroArchSeries(
        self, distro_arch_series, pocket, component):
        """Return MirrorDistroArchSeries given a arch series and pocket."""

        return IStore(MirrorDistroArchSeries).find(
            MirrorDistroArchSeries,
            distribution_mirror=self,
            distro_arch_series=distro_arch_series,
            pocket=pocket,
            component=component).one()

    def ensureMirrorDistroArchSeries(self, distro_arch_series, pocket,
                                     component):
        """See `IDistributionMirror`."""
        assert IDistroArchSeries.providedBy(distro_arch_series)
        mirror = self._getMirrorDistroArchSeries(
                distro_arch_series=distro_arch_series,
                pocket=pocket, component=component)
        if mirror is None:
            mirror = MirrorDistroArchSeries(
                pocket=pocket, distribution_mirror=self,
                distro_arch_series=distro_arch_series,
                component=component)
        return mirror

    def _getMirrorDistroSeriesSource(self, distroseries, pocket, component):
        """Return MirrorDistroSeriesSource given a arch series and pocket."""

        return IStore(MirrorDistroSeriesSource).find(
            MirrorDistroSeriesSource,
            distribution_mirror=self,
            distroseries=distroseries,
            pocket=pocket,
            component=component).one()

    def ensureMirrorDistroSeriesSource(self, distroseries, pocket, component):
        """See `IDistributionMirror`."""
        assert IDistroSeries.providedBy(distroseries)
        mirror = self._getMirrorDistroSeriesSource(
            distroseries=distroseries, pocket=pocket, component=component)
        if mirror is None:
            mirror = MirrorDistroSeriesSource(
                distribution_mirror=self, distroseries=distroseries,
                pocket=pocket, component=component)
        return mirror

    def deleteMirrorDistroSeriesSource(self, distroseries, pocket, component):
        """See IDistributionMirror"""
        mirror = MirrorDistroSeriesSource.selectOneBy(
            distribution_mirror=self, distroseries=distroseries,
            pocket=pocket, component=component)
        if mirror is not None:
            mirror.destroySelf()

    def ensureMirrorCDImageSeries(self, distroseries, flavour):
        """See IDistributionMirror"""
        mirror = MirrorCDImageDistroSeries.selectOneBy(
            distribution_mirror=self, distroseries=distroseries,
            flavour=flavour)
        if mirror is None:
            mirror = MirrorCDImageDistroSeries(
                distribution_mirror=self, distroseries=distroseries,
                flavour=flavour)
        return mirror

    def deleteMirrorCDImageSeries(self, distroseries, flavour):
        """See IDistributionMirror"""
        mirror = MirrorCDImageDistroSeries.selectOneBy(
            distribution_mirror=self, distroseries=distroseries,
            flavour=flavour)
        if mirror is not None:
            mirror.destroySelf()

    def deleteAllMirrorCDImageSeries(self):
        """See IDistributionMirror"""
        for mirror in self.cdimage_series:
            mirror.destroySelf()

    @property
    def arch_series(self):
        """See IDistributionMirror"""
        return MirrorDistroArchSeries.selectBy(distribution_mirror=self)

    @property
    def cdimage_series(self):
        """See IDistributionMirror"""
        return MirrorCDImageDistroSeries.selectBy(distribution_mirror=self)

    @property
    def source_series(self):
        """See IDistributionMirror"""
        return MirrorDistroSeriesSource.selectBy(distribution_mirror=self)

    def getSummarizedMirroredSourceSeries(self):
        """See IDistributionMirror"""
        query = """
            MirrorDistroSeriesSource.id IN (
              SELECT DISTINCT ON (
                        MirrorDistroSeriesSource.distribution_mirror,
                        MirrorDistroSeriesSource.distroseries)
                     MirrorDistroSeriesSource.id
              FROM MirrorDistroSeriesSource, DistributionMirror
              WHERE DistributionMirror.id =
                         MirrorDistroSeriesSource.distribution_mirror
                    AND DistributionMirror.id = %(mirrorid)s
                    AND DistributionMirror.distribution = %(distribution)s
              ORDER BY MirrorDistroSeriesSource.distribution_mirror,
                       MirrorDistroSeriesSource.distroseries,
                       MirrorDistroSeriesSource.freshness DESC)
            """ % sqlvalues(distribution=self.distribution, mirrorid=self)
        return MirrorDistroSeriesSource.select(query)

    def getSummarizedMirroredArchSeries(self):
        """See IDistributionMirror"""
        query = """
            MirrorDistroArchSeries.id IN (
                SELECT DISTINCT ON (
                        MirrorDistroArchSeries.distribution_mirror,
                        MirrorDistroArchSeries.distroarchseries)
                       MirrorDistroArchSeries.id
                FROM MirrorDistroArchSeries, DistributionMirror
                WHERE DistributionMirror.id =
                            MirrorDistroArchSeries.distribution_mirror
                      AND DistributionMirror.id = %(mirrorid)s
                      AND DistributionMirror.distribution = %(distribution)s
                ORDER BY MirrorDistroArchSeries.distribution_mirror,
                         MirrorDistroArchSeries.distroarchseries,
                         MirrorDistroArchSeries.freshness DESC)
            """ % sqlvalues(distribution=self.distribution, mirrorid=self)
        return MirrorDistroArchSeries.select(query)

    def getExpectedPackagesPaths(self):
        """See IDistributionMirror"""
        paths = []
        for series in self.distribution.series:
            for pocket, suffix in pocketsuffix.items():
                for component in series.components:
                    for arch_series in series.architectures:
                        # Skip unsupported series and unofficial architectures
                        # for official series and ones which were not on the
                        # mirror on its last probe.
                        if ((series.status == SeriesStatus.OBSOLETE or
                                not arch_series.official) and
                                not self._getMirrorDistroArchSeries(
                                    arch_series, pocket, component)):
                            continue

                        path = ('dists/%s%s/%s/binary-%s/Packages.gz'
                                % (series.name, suffix, component.name,
                                   arch_series.architecturetag))
                        paths.append((arch_series, pocket, component, path))
        return paths

    def getExpectedSourcesPaths(self):
        """See IDistributionMirror"""
        paths = []
        for series in self.distribution.series:
            for pocket, suffix in pocketsuffix.items():
                for component in series.components:
                    # Skip sources for series which are obsolete and ones
                    # which were not on the mirror on its last probe.
                    if (series.status == SeriesStatus.OBSOLETE and
                        not self._getMirrorDistroSeriesSource(
                            series, pocket, component)):
                        continue

                    path = ('dists/%s%s/%s/source/Sources.gz'
                            % (series.name, suffix, component.name))
                    paths.append((series, pocket, component, path))
        return paths


class DistributionMirrorSet:
    """See IDistributionMirrorSet"""

    implements(IDistributionMirrorSet)

    def __getitem__(self, mirror_id):
        """See IDistributionMirrorSet"""
        return DistributionMirror.get(mirror_id)

    def getBestMirrorsForCountry(self, country, mirror_type):
        """See IDistributionMirrorSet"""
        # As per mvo's request we only return mirrors which have an
        # http_base_url.
        country_id = None
        if country is not None:
            country_id = country.id
        base_query = And(
            DistributionMirror.content == mirror_type,
            DistributionMirror.enabled == True,
            DistributionMirror.http_base_url != None,
            DistributionMirror.official_candidate == True,
            DistributionMirror.status == MirrorStatus.OFFICIAL)
        query = And(DistributionMirror.countryID == country_id, base_query)
        # The list of mirrors returned by this method is fed to apt through
        # launchpad.net, so we order the results randomly in a lame attempt to
        # balance the load on the mirrors.
        order_by = [Func('random')]
        mirrors = shortlist(
            DistributionMirror.select(query, orderBy=order_by),
            longest_expected=200)

        if not mirrors and country is not None:
            continent = country.continent
            query = And(
                Country.q.continentID == continent.id,
                DistributionMirror.countryID == Country.q.id,
                base_query)
            mirrors.extend(shortlist(
                DistributionMirror.select(query, orderBy=order_by),
                longest_expected=300))

        if mirror_type == MirrorContent.ARCHIVE:
            main_mirror = getUtility(
                ILaunchpadCelebrities).ubuntu_archive_mirror
        elif mirror_type == MirrorContent.RELEASE:
            main_mirror = getUtility(
                ILaunchpadCelebrities).ubuntu_cdimage_mirror
        else:
            raise AssertionError("Unknown mirror type: %s" % mirror_type)
        assert main_mirror is not None, 'Main mirror was not found'
        if main_mirror not in mirrors:
            mirrors.append(main_mirror)
        return mirrors

    def getMirrorsToProbe(
            self, content_type, ignore_last_probe=False, limit=None):
        """See IDistributionMirrorSet"""
        query = """
            SELECT distributionmirror.id, MAX(mirrorproberecord.date_created)
            FROM distributionmirror
            LEFT OUTER JOIN mirrorproberecord
                ON mirrorproberecord.distribution_mirror =
                    distributionmirror.id
            WHERE distributionmirror.content = %s
                AND distributionmirror.official_candidate IS TRUE
                AND distributionmirror.status = %s
            GROUP BY distributionmirror.id
            """ % sqlvalues(content_type, MirrorStatus.OFFICIAL)

        if not ignore_last_probe:
            query += """
                HAVING MAX(mirrorproberecord.date_created) IS NULL
                    OR MAX(mirrorproberecord.date_created)
                        < %s - '%s hours'::interval
                """ % sqlvalues(UTC_NOW, PROBE_INTERVAL)

        query += """
            ORDER BY MAX(COALESCE(
                mirrorproberecord.date_created, '1970-01-01')) ASC, id"""

        if limit is not None:
            query += " LIMIT %d" % limit

        store = IStore(MirrorDistroArchSeries)
        ids = ", ".join(str(id)
                        for (id, date_created) in store.execute(query))
        query = '1 = 2'
        if ids:
            query = 'id IN (%s)' % ids
        return DistributionMirror.select(query)

    def getByName(self, name):
        """See IDistributionMirrorSet"""
        return DistributionMirror.selectOneBy(name=name)

    def getByHttpUrl(self, url):
        """See IDistributionMirrorSet"""
        return DistributionMirror.selectOneBy(http_base_url=url)

    def getByFtpUrl(self, url):
        """See IDistributionMirrorSet"""
        return DistributionMirror.selectOneBy(ftp_base_url=url)

    def getByRsyncUrl(self, url):
        """See IDistributionMirrorSet"""
        return DistributionMirror.selectOneBy(rsync_base_url=url)


class _MirrorSeriesMixIn:
    """A class containing some commonalities between MirrorDistroArchSeries
    and MirrorDistroSeriesSource.

    This class is not meant to be used alone. Instead, both
    MirrorDistroSeriesSource and MirrorDistroArchSeries should inherit from
    it and override the methods and attributes that say so.
    """

    # The freshness_times map defines levels for specifying how up to date a
    # mirror is; we use published files to assess whether a certain level is
    # fulfilled by a mirror. The map is used in combination with a special
    # freshness UP that maps to the latest published file for that
    # distribution series, component and pocket: if that file is found, we
    # consider the distribution to be up to date; if it is not found we then
    # look through the rest of the map to try and determine at what level
    # the mirror is.
    freshness_times = [
        (MirrorFreshness.ONEHOURBEHIND, 1.5),
        (MirrorFreshness.TWOHOURSBEHIND, 2.5),
        (MirrorFreshness.SIXHOURSBEHIND, 6.5),
        (MirrorFreshness.ONEDAYBEHIND, 24.5),
        (MirrorFreshness.TWODAYSBEHIND, 48.5),
        (MirrorFreshness.ONEWEEKBEHIND, 168.5),
        ]

    def _getPackageReleaseURLFromPublishingRecord(self, publishing_record):
        """Given a publishing record, return a dictionary mapping
        MirrorFreshness items to URLs of files on this mirror.

        Must be overwritten on subclasses.
        """
        raise NotImplementedError

    def getLatestPublishingEntry(self, time_interval):
        """Return the publishing entry with the most recent datepublished.

        Time interval must be a tuple of the form (start, end), and only
        records whose datepublished is between start and end are considered.
        """
        raise NotImplementedError

    def getURLsToCheckUpdateness(self, when=None):
        """See IMirrorDistroSeriesSource or IMirrorDistroArchSeries."""
        if when is None:
            when = datetime.now(pytz.timezone('UTC'))

        start = datetime(MINYEAR, 1, 1, tzinfo=pytz.timezone('UTC'))
        time_interval = (start, when)
        latest_upload = self.getLatestPublishingEntry(time_interval)
        if latest_upload is None:
            return {}

        url = self._getPackageReleaseURLFromPublishingRecord(latest_upload)
        urls = {MirrorFreshness.UP: url}

        # For each freshness in self.freshness_times, do:
        #   1) if latest_upload was published before the start of this
        #      freshness' time interval, skip it and move to the next item.
        #   2) if latest_upload was published between this freshness' time
        #      interval, adjust the end of the time interval to be identical
        #      to latest_upload.datepublished. We do this because even if the
        #      mirror doesn't have the latest upload, we can't skip that whole
        #      time interval: the mirror might have other packages published
        #      in that interval.
        #      This happens in pathological cases where two publications were
        #      done successively after a long period of time with no
        #      publication: if the mirror lacks the latest published package,
        #      we still need to check the corresponding interval or we will
        #      misreport the mirror as being very out of date.
        #   3) search for publishing records whose datepublished is between
        #      the specified time interval, and if one is found, append an
        #      item to the urls dictionary containing this freshness and the
        #      url on this mirror from where the file correspondent to that
        #      publishing record can be downloaded.
        last_threshold = 0
        for freshness, threshold in self.freshness_times:
            start = when - timedelta(hours=threshold)
            end = when - timedelta(hours=last_threshold)
            last_threshold = threshold
            if latest_upload.datepublished < start:
                continue
            if latest_upload.datepublished < end:
                end = latest_upload.datepublished

            time_interval = (start, end)
            upload = self.getLatestPublishingEntry(time_interval)

            if upload is None:
                # No uploads that would allow us to know the mirror was in
                # this freshness, so we better skip it.
                continue

            url = self._getPackageReleaseURLFromPublishingRecord(upload)
            urls.update({freshness: url})

        return urls


class MirrorCDImageDistroSeries(SQLBase):
    """See IMirrorCDImageDistroSeries"""

    implements(IMirrorCDImageDistroSeries)
    _table = 'MirrorCDImageDistroSeries'
    _defaultOrder = 'id'

    distribution_mirror = ForeignKey(
        dbName='distribution_mirror', foreignKey='DistributionMirror',
        notNull=True)
    distroseries = ForeignKey(
        dbName='distroseries', foreignKey='DistroSeries', notNull=True)
    flavour = StringCol(notNull=True)


class MirrorDistroArchSeries(SQLBase, _MirrorSeriesMixIn):
    """See IMirrorDistroArchSeries"""

    implements(IMirrorDistroArchSeries)
    _table = 'MirrorDistroArchSeries'
    _defaultOrder = [
        'distroarchseries', 'component', 'pocket', 'freshness', 'id']

    distribution_mirror = ForeignKey(
        dbName='distribution_mirror', foreignKey='DistributionMirror',
        notNull=True)
    distro_arch_series = ForeignKey(
        dbName='distroarchseries', foreignKey='DistroArchSeries',
        notNull=True)
    component = ForeignKey(
        dbName='component', foreignKey='Component', notNull=True)
    freshness = EnumCol(
        notNull=True, default=MirrorFreshness.UNKNOWN, enum=MirrorFreshness)
    pocket = EnumCol(
        notNull=True, schema=PackagePublishingPocket)

    def getLatestPublishingEntry(self, time_interval, deb_only=True):
        """Return the BinaryPackagePublishingHistory record with the
        most recent datepublished.

        :deb_only: If True, return only publishing records whose
                   binarypackagerelease's binarypackagefile.filetype is
                   BinaryPackageFileType.DEB.
        """
        query = """
            BinaryPackagePublishingHistory.pocket = %s
            AND BinaryPackagePublishingHistory.component = %s
            AND BinaryPackagePublishingHistory.distroarchseries = %s
            AND BinaryPackagePublishingHistory.archive = %s
            AND BinaryPackagePublishingHistory.status = %s
            """ % sqlvalues(self.pocket, self.component,
                            self.distro_arch_series,
                            self.distro_arch_series.main_archive,
                            PackagePublishingStatus.PUBLISHED)

        if deb_only:
            query += """
                AND BinaryPackagePublishingHistory.binarypackagerelease =
                    BinaryPackageFile.binarypackagerelease
                AND BinaryPackageFile.filetype = %s
                """ % sqlvalues(BinaryPackageFileType.DEB)

        if time_interval is not None:
            start, end = time_interval
            assert end > start, '%s is not more recent than %s' % (end, start)
            query = (query + " AND datepublished >= %s AND datepublished < %s"
                     % sqlvalues(start, end))
        return BinaryPackagePublishingHistory.selectFirst(
            query, clauseTables=['BinaryPackageFile'],
            orderBy='-datepublished')

    def _getPackageReleaseURLFromPublishingRecord(self, publishing_record):
        """Return the URL on this mirror from where the BinaryPackageRelease.

        Given a BinaryPackagePublishingHistory, return the URL on
        this mirror from where the BinaryPackageRelease file can be
        downloaded.
        """
        bpr = publishing_record.binarypackagerelease
        base_url = self.distribution_mirror.base_url
        path = poolify(bpr.sourcepackagename, self.component.name)
        file = BinaryPackageFile.selectOneBy(
            binarypackagerelease=bpr, filetype=BinaryPackageFileType.DEB)
        full_path = 'pool/%s/%s' % (path, file.libraryfile.filename)
        return urlappend(base_url, full_path)


class MirrorDistroSeriesSource(SQLBase, _MirrorSeriesMixIn):
    """See IMirrorDistroSeriesSource"""

    implements(IMirrorDistroSeriesSource)
    _table = 'MirrorDistroSeriesSource'
    _defaultOrder = ['distroseries', 'component', 'pocket', 'freshness', 'id']

    distribution_mirror = ForeignKey(
        dbName='distribution_mirror', foreignKey='DistributionMirror',
        notNull=True)
    distroseries = ForeignKey(
        dbName='distroseries', foreignKey='DistroSeries',
        notNull=True)
    component = ForeignKey(
        dbName='component', foreignKey='Component', notNull=True)
    freshness = EnumCol(
        notNull=True, default=MirrorFreshness.UNKNOWN, enum=MirrorFreshness)
    pocket = EnumCol(
        notNull=True, schema=PackagePublishingPocket)

    def getLatestPublishingEntry(self, time_interval):
        query = """
            SourcePackagePublishingHistory.pocket = %s
            AND SourcePackagePublishingHistory.component = %s
            AND SourcePackagePublishingHistory.distroseries = %s
            AND SourcePackagePublishingHistory.archive = %s
            AND SourcePackagePublishingHistory.status = %s
            """ % sqlvalues(self.pocket, self.component,
                            self.distroseries,
                            self.distroseries.main_archive,
                            PackagePublishingStatus.PUBLISHED)

        if time_interval is not None:
            start, end = time_interval
            assert end > start
            query = (query + " AND datepublished >= %s AND datepublished < %s"
                     % sqlvalues(start, end))
        return SourcePackagePublishingHistory.selectFirst(
            query, orderBy='-datepublished')

    def _getPackageReleaseURLFromPublishingRecord(self, publishing_record):
        """return the URL on this mirror from where the SourcePackageRelease.

        Given a SourcePackagePublishingHistory, return the URL on
        this mirror from where the SourcePackageRelease file can be
        downloaded.
        """
        spr = publishing_record.sourcepackagerelease
        base_url = self.distribution_mirror.base_url
        sourcename = spr.name
        path = poolify(sourcename, self.component.name)
        file = SourcePackageReleaseFile.selectOneBy(
            sourcepackagerelease=spr, filetype=SourcePackageFileType.DSC)
        full_path = 'pool/%s/%s' % (path, file.libraryfile.filename)
        return urlappend(base_url, full_path)


class MirrorProbeRecord(SQLBase):
    """See IMirrorProbeRecord"""

    implements(IMirrorProbeRecord)
    _table = 'MirrorProbeRecord'
    _defaultOrder = 'id'

    distribution_mirror = ForeignKey(
        dbName='distribution_mirror', foreignKey='DistributionMirror',
        notNull=True)
    log_file = ForeignKey(
        dbName='log_file', foreignKey='LibraryFileAlias', notNull=True)
    date_created = UtcDateTimeCol(notNull=True, default=UTC_NOW)
