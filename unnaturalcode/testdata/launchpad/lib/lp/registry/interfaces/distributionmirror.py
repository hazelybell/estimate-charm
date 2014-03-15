# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'IDistributionMirror',
    'IMirrorDistroArchSeries',
    'IMirrorDistroSeriesSource',
    'IMirrorProbeRecord',
    'IDistributionMirrorSet',
    'IMirrorCDImageDistroSeries',
    'PROBE_INTERVAL',
    'MirrorContent',
    'MirrorSpeed',
    'MirrorFreshness',
    'MirrorStatus',
    'UnableToFetchCDImageFileList',
    ]

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
from lazr.restful.declarations import (
    export_as_webservice_entry,
    export_read_operation,
    export_write_operation,
    exported,
    mutator_for,
    operation_parameters,
    )
from lazr.restful.fields import (
    Reference,
    ReferenceChoice,
    )
from lazr.restful.interface import copy_field
from zope.component import getUtility
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.interface.exceptions import Invalid
from zope.interface.interface import invariant
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    Int,
    TextLine,
    )

from lp import _
from lp.app.validators import LaunchpadValidationError
from lp.app.validators.name import name_validator
from lp.services.fields import (
    ContentNameField,
    PublicPersonChoice,
    URIField,
    Whiteboard,
    )
from lp.services.webapp.escaping import (
    html_escape,
    structured,
    )
from lp.services.worlddata.interfaces.country import ICountry

# The number of hours before we bother probing a mirror again
PROBE_INTERVAL = 23


class MirrorContent(DBEnumeratedType):
    """The content that is mirrored."""

    ARCHIVE = DBItem(1, """
        Archive

        This mirror contains source and binary packages for a given
        distribution. Mainly used for APT-based system.
        """)

    RELEASE = DBItem(2, """
        CD Image

        Mirror containing released installation images for a given
        distribution.
        """)


class MirrorSpeed(DBEnumeratedType):
    """The speed of a given mirror."""

    S128K = DBItem(10, """
        128 Kbps

        The upstream link of this mirror can make up to 128Kb per second.
        """)

    S256K = DBItem(20, """
        256 Kbps

        The upstream link of this mirror can make up to 256Kb per second.
        """)

    S512K = DBItem(30, """
        512 Kbps

        The upstream link of this mirror can make up to 512Kb per second.
        """)

    S1M = DBItem(40, """
        1 Mbps

        The upstream link of this mirror can make up to 1Mb per second.
        """)

    S2M = DBItem(50, """
        2 Mbps

        The upstream link of this mirror can make up to 2Mb per second.
        """)

    S10M = DBItem(60, """
        10 Mbps

        The upstream link of this mirror can make up to 10Mb per second.
        """)

    S45M = DBItem(65, """
        45 Mbps

        The upstream link of this mirror can make up to 45 Mb per second.
        """)

    S100M = DBItem(70, """
        100 Mbps

        The upstream link of this mirror can make up to 100Mb per second.
        """)

    S1G = DBItem(80, """
        1 Gbps

        The upstream link of this mirror can make up to 1 gigabit per second.
        """)

    S2G = DBItem(90, """
        2 Gbps

        The upstream link of this mirror can make up to 2 gigabits per second.
        """)

    S4G = DBItem(100, """
        4 Gbps

        The upstream link of this mirror can make up to 4 gigabits per second.
        """)

    S10G = DBItem(110, """
        10 Gbps

        The upstream link of this mirror can make up to 10 gigabits per second.
        """)

    S20G = DBItem(120, """
        20 Gbps

        The upstream link of this mirror can make up to 20 gigabits per second.
        """)


class MirrorFreshness(DBEnumeratedType):
    """The freshness of a given mirror's content."""

    UP = DBItem(1, """
        Up to date

        This mirror is up to date with the original content.
        """)

    ONEHOURBEHIND = DBItem(2, """
        One hour behind

        This mirror's content seems to have been last updated one hour ago.
        """)

    TWOHOURSBEHIND = DBItem(3, """
        Two hours behind

        This mirror's content seems to have been last updated two hours ago.
        """)

    SIXHOURSBEHIND = DBItem(4, """
        Six hours behind

        This mirror's content seems to have been last updated six hours ago.
        """)

    ONEDAYBEHIND = DBItem(5, """
        One day behind

        This mirror's content seems to have been last updated one day ago.
        """)

    TWODAYSBEHIND = DBItem(6, """
        Two days behind

        This mirror's content seems to have been last updated two days ago.
        """)

    ONEWEEKBEHIND = DBItem(7, """
        One week behind

        This mirror's content seems to have been last updated one week ago.
        """)

    UNKNOWN = DBItem(8, """
        Last update unknown

        We couldn't determine when this mirror's content was last updated.
        """)


class MirrorStatus(DBEnumeratedType):
    """The status of a mirror."""

    PENDING_REVIEW = DBItem(10, """
        Pending review

        This mirror hasn't been reviewed by a mirror admin.
        """)

    UNOFFICIAL = DBItem(20, """
        Unofficial

        This mirror has been reviewed by a mirror admin and is not one of
        the official mirrors for its distribution.
        """)

    OFFICIAL = DBItem(30, """
        Official

        This mirror has been reviewed by a mirror admin and is one of
        the official mirrors for its distribution.
        """)


class DistributionMirrorNameField(ContentNameField):
    errormessage = _("%s is already in use by another distribution mirror.")

    @property
    def _content_iface(self):
        return IDistributionMirror

    def _getByName(self, name):
        return getUtility(IDistributionMirrorSet).getByName(name)


class DistroMirrorURIField(URIField):
    """Base class for the DistributionMirror unique URI fields."""

    def getMirrorByURI(self, uri):
        """Return the mirror with the given URI."""
        raise NotImplementedError()

    def _validate(self, value):
        # import here to avoid circular import
        from lp.services.webapp import canonical_url
        from lazr.uri import URI

        super(DistroMirrorURIField, self)._validate(value)
        uri = URI(self.normalize(value))

        # This field is also used when creating new mirrors and in that case
        # self.context is not an IDistributionMirror so it doesn't make sense
        # to try to get the existing value of the attribute.
        if IDistributionMirror.providedBy(self.context):
            orig_value = self.get(self.context)
            if orig_value is not None and URI(orig_value) == uri:
                return # url was not changed

        mirror = self.getMirrorByURI(str(uri))
        if mirror is not None:
            message = _(
                'The distribution mirror <a href="${url}">${mirror}</a> '
                'is already registered with this URL.',
                mapping={'url': html_escape(canonical_url(mirror)),
                         'mirror': html_escape(mirror.title)})
            raise LaunchpadValidationError(structured(message))


class DistroMirrorHTTPURIField(DistroMirrorURIField):

    def getMirrorByURI(self, url):
        return getUtility(IDistributionMirrorSet).getByHttpUrl(url)


class DistroMirrorFTPURIField(DistroMirrorURIField):

    def getMirrorByURI(self, url):
        return getUtility(IDistributionMirrorSet).getByFtpUrl(url)


class DistroMirrorRsyncURIField(DistroMirrorURIField):

    def getMirrorByURI(self, url):
        return getUtility(IDistributionMirrorSet).getByRsyncUrl(url)


class IDistributionMirror(Interface):
    """A mirror of a given distribution."""
    export_as_webservice_entry()

    id = Int(title=_('The unique id'), required=True, readonly=True)
    owner = exported(PublicPersonChoice(
        title=_('Owner'), readonly=False, vocabulary='ValidOwner',
        required=True, description=_(
            "The person who is set as the current administrator of this"
            "mirror.")))
    distribution = exported(
        Reference(
            Interface,
            # Really IDistribution, circular import fixed in
            # _schema_circular_imports.
            title=_("Distribution"), required=True, readonly=True,
            description=_("The distribution that is mirrored")))
    name = exported(DistributionMirrorNameField(
        title=_('Name'), required=True, readonly=False,
        description=_('A short and unique name for this mirror.'),
        constraint=name_validator))
    displayname = exported(TextLine(
        title=_('Organisation'), required=False, readonly=False,
        description=_('The name of the organization hosting this mirror.')))
    description = exported(TextLine(
        title=_('Description'), required=False, readonly=False))
    http_base_url = exported(DistroMirrorHTTPURIField(
        title=_('HTTP URL'), required=False, readonly=False,
        allowed_schemes=['http'], allow_userinfo=False,
        allow_query=False, allow_fragment=False, trailing_slash=True,
        description=_('e.g.: http://archive.ubuntu.com/ubuntu/')))
    ftp_base_url = exported(DistroMirrorFTPURIField(
        title=_('FTP URL'), required=False, readonly=False,
        allowed_schemes=['ftp'], allow_userinfo=False,
        allow_query=False, allow_fragment=False, trailing_slash=True,
        description=_('e.g.: ftp://archive.ubuntu.com/ubuntu/')))
    rsync_base_url = exported(DistroMirrorRsyncURIField(
        title=_('Rsync URL'), required=False, readonly=False,
        allowed_schemes=['rsync'], allow_userinfo=False,
        allow_query=False, allow_fragment=False, trailing_slash=True,
        description=_('e.g.: rsync://archive.ubuntu.com/ubuntu/')))
    enabled = exported(Bool(
        title=_('This mirror was probed successfully.'),
        required=False, readonly=True, default=False))
    speed = exported(Choice(
        title=_('Link Speed'), required=True, readonly=False,
        vocabulary=MirrorSpeed))
    country = exported(ReferenceChoice(
        title=_('Location'), description=_(
            "The country in which this mirror is based."),
        required=True, readonly=False,
        vocabulary='CountryName', schema=ICountry))
    content = exported(Choice(
        title=_('Content'), required=True, readonly=False,
        description=_(
            'Choose "CD Image" if this mirror contains CD images of '
            'this distribution. Choose "Archive" if this is a '
            'mirror of packages for this distribution.'),
        vocabulary=MirrorContent))
    status = exported(Choice(
        title=_('Status'), required=True, readonly=False,
        vocabulary=MirrorStatus,
        description=_("The current status of a mirror's registration.")))

    title = Attribute('The title of this mirror')
    cdimage_series = Attribute(
        'All MirrorCDImageDistroSeries of this mirror')
    source_series = Attribute(
        'All MirrorDistroSeriesSources of this mirror')
    arch_series = Attribute('All MirrorDistroArchSeries of this mirror')
    last_probe_record = Attribute(
        'The last MirrorProbeRecord for this mirror.')
    all_probe_records = Attribute('All MirrorProbeRecords for this mirror.')
    has_ftp_or_rsync_base_url = Bool(
        title=_('Does this mirror have a FTP or Rsync base URL?'))
    arch_mirror_freshness = Attribute(
        'The freshness of this mirror\'s archive mirrors')
    source_mirror_freshness = Attribute(
        'The freshness of this mirror\'s source mirrors')
    base_url = Attribute('The HTTP or FTP base URL of this mirror')
    date_created = exported(Datetime(
        title=_('Date Created'), required=True, readonly=True,
        description=_("The date on which this mirror was registered.")))
    country_dns_mirror = exported(Bool(
        title=_('Country DNS Mirror'),
        description=_('Whether this is a country mirror in DNS.'),
        required=False, readonly=True, default=False))

    reviewer = exported(PublicPersonChoice(
        title=_('Reviewer'), required=False, readonly=True,
        vocabulary='ValidPersonOrTeam', description=_(
            "The person who last reviewed this mirror.")))
    date_reviewed = exported(Datetime(
        title=_('Date reviewed'), required=False, readonly=True,
        description=_(
            "The date on which this mirror was last reviewed by a mirror "
            "admin.")))

    official_candidate = exported(Bool(
        title=_('Apply to be an official mirror of this distribution'),
        required=False, readonly=False, default=True))
    whiteboard = exported(Whiteboard(
        title=_('Whiteboard'), required=False, readonly=False,
        description=_("Notes on the current status of the mirror (only "
                      "visible to admins and the mirror's registrant).")))

    @export_read_operation()
    def canTransitionToCountryMirror():
        """Verify if a mirror can be set as a country mirror or return
        False."""

    @mutator_for(country_dns_mirror)
    @operation_parameters(country_dns_mirror=copy_field(country_dns_mirror))
    @export_write_operation()
    def transitionToCountryMirror(country_dns_mirror):
        """Method run on changing country_dns_mirror."""

    @invariant
    def mirrorMustHaveHTTPOrFTPURL(mirror):
        if not (mirror.http_base_url or mirror.ftp_base_url):
            raise Invalid('A mirror must have at least an HTTP or FTP URL.')

    def getSummarizedMirroredSourceSeries():
        """Return a summarized list of this distribution_mirror's
        MirrorDistroSeriesSource objects.

        Summarized, in this case, means that it ignores pocket and components
        and returns the MirrorDistroSeriesSource with the worst freshness for
        each distroseries of this distribution mirror.
        """

    def getSummarizedMirroredArchSeries():
        """Return a summarized list of this distribution_mirror's
        MirrorDistroArchSeries objects.

        Summarized, in this case, means that it ignores pocket and components
        and returns the MirrorDistroArchSeries with the worst freshness for
        each distro_arch_series of this distribution mirror.
        """

    @export_read_operation()
    def getOverallFreshness():
        """Return this mirror's overall freshness.

        For ARCHIVE mirrors, the overall freshness is the worst freshness of
        all of this mirror's content objects (MirrorDistroArchSeries,
        MirrorDistroSeriesSource or MirrorCDImageDistroSeriess).

        For RELEASE mirrors, the overall freshness is either UPTODATE, if the
        mirror contains all ISO images that it should or UNKNOWN if it doesn't
        contain one or more ISO images.
        """

    @export_read_operation()
    def isOfficial():
        """Return True if this is an official mirror."""

    def shouldDisable(expected_file_count=None):
        """Should this mirror be marked disabled?

        If this is a RELEASE mirror then expected_file_count must not be None,
        and it should be disabled if the number of cdimage_series it
        contains is smaller than the given expected_file_count.

        If this is an ARCHIVE mirror, then it should be disabled only if it
        has no content at all.

        We could use len(get_expected_cdimage_paths()) to obtain the
        expected_file_count, but that's not a good idea because that method
        gets the expected paths from releases.ubuntu.com, which is something
        we don't have control over.
        """

    def disable(notify_owner, log):
        """Disable this mirror and notify the distro's mirror admins by email.

        :param notify_owner: If True, an identical notification is sent to the
        mirror owner.

        :param log: The log of requests/responses from the last time this
        mirror was probed.  This is only necessary because we want to include
        a snippet of the log in the email notification but the content can
        only be read back from the librarian after we commit the transaction
        (and we really don't want to do it here).

        This method can't be called before a probe record has been created
        because we'll link to the latest probe record in the email we send to
        notify the owner.

        The notification(s) are actually sent only if this mirror was
        previously enabled or if it was probed only once.
        """

    def newProbeRecord(log_file):
        """Create and return a new MirrorProbeRecord for this mirror."""

    def deleteMirrorDistroArchSeries(distro_arch_series, pocket, component):
        """Delete the MirrorDistroArchSeries with the given arch series and
        pocket, in case it exists.
        """

    def ensureMirrorDistroArchSeries(distro_arch_series, pocket, component):
        """Check if we have a MirrorDistroArchSeries with the given arch
        series and pocket, creating one if not.

        Return that MirrorDistroArchSeries.
        """

    def ensureMirrorDistroSeriesSource(distroseries, pocket, component):
        """Check if we have a MirrorDistroSeriesSource with the given distro
        series, creating one if not.

        Return that MirrorDistroSeriesSource.
        """

    def deleteMirrorDistroSeriesSource(distroseries, pocket, component):
        """Delete the MirrorDistroSeriesSource with the given distro series,
        in case it exists.
        """

    def ensureMirrorCDImageSeries(arch_series, flavour):
        """Check if we have a MirrorCDImageDistroSeries with the given
        arch series and flavour, creating one if not.

        Return that MirrorCDImageDistroSeries.
        """

    def deleteMirrorCDImageSeries(arch_series, flavour):
        """Delete the MirrorCDImageDistroSeries with the given arch
        series and flavour, in case it exists.
        """

    def deleteAllMirrorCDImageSeries():
        """Delete all MirrorCDImageDistroSeriess of this mirror."""

    def getExpectedPackagesPaths():
        """Get all paths where we can find Packages.gz files on this mirror.

        Return a list containing, for each path, the DistroArchSeries,
        the PackagePublishingPocket and the Component to which that given
        Packages.gz file refer to and the path to the file itself.
        """

    def getExpectedSourcesPaths():
        """Get all paths where we can find Sources.gz files on this mirror.

        Return a list containing, for each path, the DistroSeries, the
        PackagePublishingPocket and the Component to which that given
        Sources.gz file refer to and the path to the file itself.
        """


class UnableToFetchCDImageFileList(Exception):
    """Couldn't fetch the file list needed for probing cdimage mirrors."""


class IDistributionMirrorSet(Interface):
    """The set of DistributionMirrors"""

    def __getitem__(mirror_id):
        """Return the DistributionMirror with the given id."""

    def getMirrorsToProbe(content_type, ignore_last_probe=False, limit=None):
        """Return all official mirrors with the given content type that need
        to be probed.

        A mirror needs to be probed either if it was never probed before or if
        it wasn't probed in the last PROBE_INTERVAL hours.

        If ignore_last_probe is True, then all official mirrors of the given
        content type will be probed even if they were probed in the last
        PROBE_INTERVAL hours.

        If limit is not None, then return at most limit mirrors, giving
        precedence to never probed ones followed by the ones probed longest
        ago.
        """

    def getBestMirrorsForCountry(country, mirror_type):
        """Return the best mirrors to be used by someone in the given country.

        The list of mirrors is composed by the official mirrors located in
        the given country (or in the country's continent if the country
        doesn't have any) plus the main mirror of that type.
        """

    def getByName(name):
        """Return the mirror with the given name or None."""

    def getByHttpUrl(url):
        """Return the mirror with the given HTTP URL or None."""

    def getByFtpUrl(url):
        """Return the mirror with the given FTP URL or None."""

    def getByRsyncUrl(url):
        """Return the mirror with the given Rsync URL or None."""


class IMirrorDistroArchSeries(Interface):
    """The mirror of the packages of a given Distro Arch Series"""

    distribution_mirror = Attribute(_("The Distribution Mirror"))
    distro_arch_series = Choice(
        title=_('Version and Architecture'), required=True, readonly=True,
        vocabulary='FilteredDistroArchSeries')
    freshness = Choice(
        title=_('Freshness'), required=True, readonly=False,
        vocabulary=MirrorFreshness)
    # Is it possible to use a Choice here without specifying a vocabulary?
    component = Int(title=_('Component'), required=True, readonly=True)
    pocket = Choice(
        title=_('Pocket'), required=True, readonly=True,
        vocabulary='PackagePublishingPocket')

    def getURLsToCheckUpdateness():
        """Return a dict mapping each MirrorFreshness to a URL on this mirror.

        If there's not publishing records for this DistroArchSeries,
        Component and Pocket, an empty dictionary is returned.

        These URLs should be checked and, if they are accessible, we know
        that's the current freshness of this mirror.
        """


class IMirrorDistroSeriesSource(Interface):
    """The mirror of a given Distro Series"""

    distribution_mirror = Attribute(_("The Distribution Mirror"))
    distroseries = Choice(
        title=_('Series'), required=True, readonly=True,
        vocabulary='FilteredDistroSeries')
    freshness = Choice(
        title=_('Freshness'), required=True, readonly=False,
        vocabulary=MirrorFreshness)
    # Is it possible to use a Choice here without specifying a vocabulary?
    component = Int(title=_('Component'), required=True, readonly=True)
    pocket = Choice(
        title=_('Pocket'), required=True, readonly=True,
        vocabulary='PackagePublishingPocket')

    def getURLsToCheckUpdateness():
        """Return a dict mapping each MirrorFreshness to a URL on this mirror.

        If there's not publishing records for this DistroSeries, Component
        and Pocket, an empty dictionary is returned.

        These URLs should be checked and, if they are accessible, we know
        that's the current freshness of this mirror.
        """


class IMirrorCDImageDistroSeries(Interface):
    """The mirror of a given CD/DVD image"""

    distribution_mirror = Attribute(_("The Distribution Mirror"))
    distroseries = Attribute(_("The DistroSeries"))
    flavour = TextLine(
        title=_("The Flavour's name"), required=True, readonly=True)


class IMirrorProbeRecord(Interface):
    """A record stored when a mirror is probed.

    We store this in order to have a history of that mirror's probes.
    """

    distribution_mirror = Attribute(_("The Distribution Mirror"))
    date_created = Datetime(
        title=_('Date Created'), required=True, readonly=True)
    log_file = Attribute(_("The log of this probing."))
