# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'BinaryPackageRelease',
    'BinaryPackageReleaseDownloadCount',
    ]


import simplejson
from sqlobject import (
    BoolCol,
    ForeignKey,
    IntCol,
    StringCol,
    )
from storm.locals import (
    Date,
    Int,
    Reference,
    Store,
    Storm,
    )
from zope.interface import implements

from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.sqlbase import SQLBase
from lp.services.propertycache import (
    cachedproperty,
    get_property_cache,
    )
from lp.soyuz.enums import (
    BinaryPackageFileType,
    BinaryPackageFormat,
    PackagePublishingPriority,
    )
from lp.soyuz.interfaces.binarypackagerelease import (
    IBinaryPackageRelease,
    IBinaryPackageReleaseDownloadCount,
    )
from lp.soyuz.model.files import BinaryPackageFile


class BinaryPackageRelease(SQLBase):
    implements(IBinaryPackageRelease)
    _table = 'BinaryPackageRelease'
    binarypackagename = ForeignKey(dbName='binarypackagename', notNull=True,
                                   foreignKey='BinaryPackageName')
    version = StringCol(dbName='version', notNull=True)
    summary = StringCol(dbName='summary', notNull=True, default="")
    description = StringCol(dbName='description', notNull=True)
    build = ForeignKey(
        dbName='build', foreignKey='BinaryPackageBuild', notNull=True)
    binpackageformat = EnumCol(dbName='binpackageformat', notNull=True,
                               schema=BinaryPackageFormat)
    component = ForeignKey(dbName='component', foreignKey='Component',
                           notNull=True)
    section = ForeignKey(dbName='section', foreignKey='Section', notNull=True)
    priority = EnumCol(dbName='priority', notNull=True,
                       schema=PackagePublishingPriority)
    shlibdeps = StringCol(dbName='shlibdeps')
    depends = StringCol(dbName='depends')
    recommends = StringCol(dbName='recommends')
    suggests = StringCol(dbName='suggests')
    conflicts = StringCol(dbName='conflicts')
    replaces = StringCol(dbName='replaces')
    provides = StringCol(dbName='provides')
    pre_depends = StringCol(dbName='pre_depends')
    enhances = StringCol(dbName='enhances')
    breaks = StringCol(dbName='breaks')
    essential = BoolCol(dbName='essential', default=False)
    installedsize = IntCol(dbName='installedsize')
    architecturespecific = BoolCol(dbName='architecturespecific',
                                   notNull=True)
    homepage = StringCol(dbName='homepage')
    datecreated = UtcDateTimeCol(notNull=True, default=UTC_NOW)
    debug_package = ForeignKey(dbName='debug_package',
                              foreignKey='BinaryPackageRelease')

    _user_defined_fields = StringCol(dbName='user_defined_fields')

    def __init__(self, *args, **kwargs):
        if 'user_defined_fields' in kwargs:
            kwargs['_user_defined_fields'] = simplejson.dumps(
                kwargs['user_defined_fields'])
            del kwargs['user_defined_fields']
        super(BinaryPackageRelease, self).__init__(*args, **kwargs)

    @property
    def user_defined_fields(self):
        """See `IBinaryPackageRelease`."""
        if self._user_defined_fields is None:
            return []
        return simplejson.loads(self._user_defined_fields)

    @property
    def title(self):
        """See `IBinaryPackageRelease`."""
        return '%s-%s' % (self.binarypackagename.name, self.version)

    @property
    def name(self):
        """See `IBinaryPackageRelease`."""
        return self.binarypackagename.name

    @property
    def distributionsourcepackagerelease(self):
        """See `IBinaryPackageRelease`."""
        # import here to avoid circular import problems
        from lp.soyuz.model.distributionsourcepackagerelease \
            import DistributionSourcePackageRelease
        return DistributionSourcePackageRelease(
            distribution=self.build.distribution,
            sourcepackagerelease=self.build.source_package_release)

    @property
    def sourcepackagename(self):
        """See `IBinaryPackageRelease`."""
        return self.build.source_package_release.sourcepackagename.name

    @property
    def is_new(self):
        """See `IBinaryPackageRelease`."""
        distroarchseries = self.build.distro_arch_series
        distroarchseries_binary_package = distroarchseries.getBinaryPackage(
            self.binarypackagename)
        return distroarchseries_binary_package.currentrelease is None

    @property
    def properties(self):
        """See `IBinaryPackageRelease`."""
        return {
            "name": self.name,
            "version": self.version,
            "is_new": self.is_new,
            "architecture": self.build.arch_tag,
            "component": self.component.name,
            "section": self.section.name,
            "priority": self.priority.name,
            }

    @cachedproperty
    def files(self):
        return list(
            Store.of(self).find(BinaryPackageFile, binarypackagerelease=self))

    def addFile(self, file):
        """See `IBinaryPackageRelease`."""
        determined_filetype = None
        if file.filename.endswith(".deb"):
            determined_filetype = BinaryPackageFileType.DEB
        elif file.filename.endswith(".rpm"):
            determined_filetype = BinaryPackageFileType.RPM
        elif file.filename.endswith(".udeb"):
            determined_filetype = BinaryPackageFileType.UDEB
        elif file.filename.endswith(".ddeb"):
            determined_filetype = BinaryPackageFileType.DDEB
        else:
            raise AssertionError(
                'Unsupported file type: %s' % file.filename)

        del get_property_cache(self).files
        return BinaryPackageFile(binarypackagerelease=self,
                                 filetype=determined_filetype,
                                 libraryfile=file)

    def override(self, component=None, section=None, priority=None):
        """See `IBinaryPackageRelease`."""
        if component is not None:
            self.component = component
        if section is not None:
            self.section = section
        if priority is not None:
            self.priority = priority


class BinaryPackageReleaseDownloadCount(Storm):
    """See `IBinaryPackageReleaseDownloadCount`."""

    implements(IBinaryPackageReleaseDownloadCount)
    __storm_table__ = 'BinaryPackageReleaseDownloadCount'

    id = Int(primary=True)
    archive_id = Int(name='archive', allow_none=False)
    archive = Reference(archive_id, 'Archive.id')
    binary_package_release_id = Int(
        name='binary_package_release', allow_none=False)
    binary_package_release = Reference(
        binary_package_release_id, 'BinaryPackageRelease.id')
    day = Date(allow_none=False)
    country_id = Int(name='country', allow_none=True)
    country = Reference(country_id, 'Country.id')
    count = Int(allow_none=False)

    def __init__(self, archive, binary_package_release, day, country, count):
        super(BinaryPackageReleaseDownloadCount, self).__init__()
        self.archive = archive
        self.binary_package_release = binary_package_release
        self.day = day
        self.country = country
        self.count = count

    @property
    def binary_package_name(self):
        """See `IBinaryPackageReleaseDownloadCount`."""
        return self.binary_package_release.name

    @property
    def binary_package_version(self):
        """See `IBinaryPackageReleaseDownloadCount`."""
        return self.binary_package_release.version
