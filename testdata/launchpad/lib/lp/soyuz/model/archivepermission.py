# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database class for table ArchivePermission."""

__metaclass__ = type

__all__ = [
    'ArchivePermission',
    'ArchivePermissionSet',
    ]

from operator import attrgetter

from lazr.enum import DBItem
from sqlobject import (
    BoolCol,
    ForeignKey,
    )
from storm.expr import SQL
from storm.locals import (
    Int,
    Reference,
    )
from storm.store import Store
from zope.component import getUtility
from zope.interface import (
    alsoProvides,
    implements,
    )
from zope.security.proxy import isinstance as zope_isinstance

from lp.app.errors import NotFoundError
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.sourcepackagename import (
    ISourcePackageName,
    ISourcePackageNameSet,
    )
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    )
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from lp.soyuz.enums import ArchivePermissionType
from lp.soyuz.interfaces.archive import (
    ComponentNotFound,
    IArchive,
    )
from lp.soyuz.interfaces.archivepermission import (
    IArchivePermission,
    IArchivePermissionSet,
    IArchiveQueueAdmin,
    IArchiveUploader,
    )
from lp.soyuz.interfaces.component import (
    IComponent,
    IComponentSet,
    )
from lp.soyuz.interfaces.packageset import IPackageset
from lp.soyuz.model.packageset import Packageset


def _extract_type_name(value):
    """Extract the type name of the given value."""
    return str(type(value)).split("'")[-2]


class ArchivePermission(SQLBase):
    """See `IArchivePermission`."""
    implements(IArchivePermission)
    _table = 'ArchivePermission'
    _defaultOrder = 'id'

    date_created = UtcDateTimeCol(
        dbName='date_created', notNull=True, default=UTC_NOW)

    archive = ForeignKey(foreignKey='Archive', dbName='archive', notNull=True)

    permission = EnumCol(
        dbName='permission', unique=False, notNull=True,
        schema=ArchivePermissionType)

    person = ForeignKey(foreignKey='Person', dbName='person', notNull=True)

    component = ForeignKey(
        foreignKey='Component', dbName='component', notNull=False)

    sourcepackagename = ForeignKey(
        foreignKey='SourcePackageName', dbName='sourcepackagename',
        notNull=False)

    packageset_id = Int(name='packageset', allow_none=True)
    packageset = Reference(packageset_id, 'Packageset.id')

    explicit = BoolCol(dbName='explicit', notNull=True, default=False)

    pocket = EnumCol(dbName="pocket", schema=PackagePublishingPocket)

    distroseries = ForeignKey(
        foreignKey='DistroSeries', dbName='distroseries', notNull=False)

    def _init(self, *args, **kw):
        """Provide the right interface for URL traversal."""
        SQLBase._init(self, *args, **kw)

        # Provide the additional marker interface depending on what type
        # of archive this is.  See also the browser:url declarations in
        # zcml/archivepermission.zcml.
        if self.permission == ArchivePermissionType.UPLOAD:
            alsoProvides(self, IArchiveUploader)
        elif self.permission == ArchivePermissionType.QUEUE_ADMIN:
            alsoProvides(self, IArchiveQueueAdmin)
        else:
            raise AssertionError(
                "Unknown permission type %s" % self.permission)

    @property
    def component_name(self):
        """See `IArchivePermission`"""
        if self.component:
            return self.component.name
        else:
            return None

    @property
    def source_package_name(self):
        """See `IArchivePermission`"""
        if self.sourcepackagename:
            return self.sourcepackagename.name
        else:
            return None

    @property
    def package_set_name(self):
        """See `IArchivePermission`"""
        if self.packageset:
            return self.packageset.name
        else:
            return None

    @property
    def distro_series_name(self):
        """See `IArchivePermission`"""
        if self.packageset:
            return self.packageset.distroseries.name
        elif self.distroseries:
            return self.distroseries.name
        else:
            return None


class ArchivePermissionSet:
    """See `IArchivePermissionSet`."""
    implements(IArchivePermissionSet)

    def checkAuthenticated(self, person, archive, permission, item,
                           distroseries=None):
        """See `IArchivePermissionSet`."""
        clauses = ["""
            ArchivePermission.archive = %s AND
            ArchivePermission.permission = %s AND
            ArchivePermission.person = TeamParticipation.team AND
            TeamParticipation.person = %s
            """ % sqlvalues(archive, permission, person)]

        prejoins = []

        if IComponent.providedBy(item):
            clauses.append(
                "ArchivePermission.component = %s" % sqlvalues(item))
            prejoins.append("component")
        elif ISourcePackageName.providedBy(item):
            clauses.append(
                "ArchivePermission.sourcepackagename = %s" % sqlvalues(item))
            prejoins.append("sourcepackagename")
        elif IPackageset.providedBy(item):
            clauses.append(
                "ArchivePermission.packageset = %s" % sqlvalues(item.id))
            prejoins.append("packageset")
        elif (zope_isinstance(item, DBItem) and
              item.enum.name == "PackagePublishingPocket"):
            clauses.append("ArchivePermission.pocket = %s" % sqlvalues(item))
            if distroseries is not None:
                clauses.append(
                    "(ArchivePermission.distroseries IS NULL OR "
                     "ArchivePermission.distroseries = %s)" %
                    sqlvalues(distroseries))
                prejoins.append("distroseries")
        else:
            raise AssertionError(
                "'item' %r is not an IComponent, IPackageset, "
                "ISourcePackageName or PackagePublishingPocket" % item)

        query = " AND ".join(clauses)
        auth = ArchivePermission.select(
            query, clauseTables=["TeamParticipation"],
            prejoins=prejoins)

        return auth

    def _nameToComponent(self, component):
        """Helper to convert a possible string component to IComponent"""
        try:
            if isinstance(component, basestring):
                component = getUtility(IComponentSet)[component]
            return component
        except NotFoundError:
            raise ComponentNotFound(component)

    def _nameToSourcePackageName(self, sourcepackagename):
        """Helper to convert a possible string name to ISourcePackageName."""
        if isinstance(sourcepackagename, basestring):
            sourcepackagename = getUtility(
                ISourcePackageNameSet)[sourcepackagename]
        return sourcepackagename

    def _precachePersonsForPermissions(self, permissions):
        list(getUtility(IPersonSet).getPrecachedPersonsFromIDs(
            set(map(attrgetter("personID"), permissions))))
        return permissions

    def permissionsForArchive(self, archive):
        """See `IArchivePermissionSet`."""
        return self._precachePersonsForPermissions(
            ArchivePermission.selectBy(archive=archive))

    def permissionsForPerson(self, archive, person):
        """See `IArchivePermissionSet`."""
        return IStore(ArchivePermission).find(
            ArchivePermission, """
            ArchivePermission.archive = %s AND
            EXISTS (SELECT TeamParticipation.person
                    FROM TeamParticipation
                    WHERE TeamParticipation.person = %s AND
                          TeamParticipation.team = ArchivePermission.person)
            """ % sqlvalues(archive, person))

    def _componentsFor(self, archives, person, permission_type):
        """Helper function to get ArchivePermission objects."""
        if IArchive.providedBy(archives):
            archive_ids = [archives.id]
        else:
            archive_ids = [archive.id for archive in archives]

        return ArchivePermission.select("""
            ArchivePermission.archive IN %s AND
            ArchivePermission.permission = %s AND
            ArchivePermission.component IS NOT NULL AND
            EXISTS (SELECT TeamParticipation.person
                    FROM TeamParticipation
                    WHERE TeamParticipation.person = %s AND
                          TeamParticipation.team = ArchivePermission.person)
            """ % sqlvalues(archive_ids, permission_type, person),
            prejoins=["component"])

    def componentsForUploader(self, archive, person):
        """See `IArchivePermissionSet`."""
        return self._componentsFor(
            archive, person, ArchivePermissionType.UPLOAD)

    def uploadersForComponent(self, archive, component=None):
        """See `IArchivePermissionSet`."""
        clauses = ["""
            ArchivePermission.archive = %s AND
            ArchivePermission.permission = %s
            """ % sqlvalues(archive, ArchivePermissionType.UPLOAD)]

        if component is not None:
            component = self._nameToComponent(component)
            clauses.append(
                "ArchivePermission.component = %s" % sqlvalues(component))
        else:
            clauses.append("ArchivePermission.component IS NOT NULL")

        query = " AND ".join(clauses)
        return ArchivePermission.select(query, prejoins=["component"])

    def packagesForUploader(self, archive, person):
        """See `IArchive`."""
        return ArchivePermission.select("""
            ArchivePermission.archive = %s AND
            ArchivePermission.permission = %s AND
            ArchivePermission.sourcepackagename IS NOT NULL AND
            EXISTS (SELECT TeamParticipation.person
                    FROM TeamParticipation
                    WHERE TeamParticipation.person = %s AND
                    TeamParticipation.team = ArchivePermission.person)
            """ % sqlvalues(archive, ArchivePermissionType.UPLOAD, person),
            prejoins=["sourcepackagename"])

    def uploadersForPackage(self, archive, sourcepackagename):
        """See `IArchivePermissionSet`."""
        sourcepackagename = self._nameToSourcePackageName(sourcepackagename)
        results = ArchivePermission.selectBy(
            archive=archive, permission=ArchivePermissionType.UPLOAD,
            sourcepackagename=sourcepackagename)
        return results.prejoin(["sourcepackagename"])

    def _pocketsFor(self, archives, person, permission_type):
        """Helper function to get ArchivePermission objects."""
        if IArchive.providedBy(archives):
            archive_ids = [archives.id]
        else:
            archive_ids = [archive.id for archive in archives]

        return ArchivePermission.select("""
            ArchivePermission.archive IN %s AND
            ArchivePermission.permission = %s AND
            ArchivePermission.pocket IS NOT NULL AND
            EXISTS (SELECT TeamParticipation.person
                    FROM TeamParticipation
                    WHERE TeamParticipation.person = %s AND
                          TeamParticipation.team = ArchivePermission.person)
            """ % sqlvalues(archive_ids, permission_type, person))

    def pocketsForUploader(self, archive, person):
        """See `IArchivePermissionSet`."""
        return self._pocketsFor(archive, person, ArchivePermissionType.UPLOAD)

    def uploadersForPocket(self, archive, pocket):
        """See `IArchivePermissionSet`."""
        return ArchivePermission.selectBy(
            archive=archive, permission=ArchivePermissionType.UPLOAD,
            pocket=pocket)

    def queueAdminsForComponent(self, archive, component):
        """See `IArchivePermissionSet`."""
        component = self._nameToComponent(component)
        results = ArchivePermission.selectBy(
            archive=archive, permission=ArchivePermissionType.QUEUE_ADMIN,
            component=component)
        return results.prejoin(["component"])

    def componentsForQueueAdmin(self, archive, person):
        """See `IArchivePermissionSet`."""
        return self._componentsFor(
            archive, person, ArchivePermissionType.QUEUE_ADMIN)

    def queueAdminsForPocket(self, archive, pocket, distroseries=None):
        """See `IArchivePermissionSet`."""
        kwargs = {}
        if distroseries is not None:
            kwargs["distroseries"] = distroseries
        return ArchivePermission.selectBy(
            archive=archive, permission=ArchivePermissionType.QUEUE_ADMIN,
            pocket=pocket, **kwargs)

    def pocketsForQueueAdmin(self, archive, person):
        """See `IArchivePermissionSet`."""
        return self._pocketsFor(
            archive, person, ArchivePermissionType.QUEUE_ADMIN)

    def newPackageUploader(self, archive, person, sourcepackagename):
        """See `IArchivePermissionSet`."""
        sourcepackagename = self._nameToSourcePackageName(sourcepackagename)
        existing = self.checkAuthenticated(
            person, archive, ArchivePermissionType.UPLOAD, sourcepackagename)
        try:
            return existing[0]
        except IndexError:
            return ArchivePermission(
                archive=archive, person=person,
                sourcepackagename=sourcepackagename,
                permission=ArchivePermissionType.UPLOAD)

    def newComponentUploader(self, archive, person, component):
        """See `IArchivePermissionSet`."""
        component = self._nameToComponent(component)
        existing = self.checkAuthenticated(
            person, archive, ArchivePermissionType.UPLOAD, component)
        try:
            return existing[0]
        except IndexError:
            return ArchivePermission(
                archive=archive, person=person, component=component,
                permission=ArchivePermissionType.UPLOAD)

    def newPocketUploader(self, archive, person, pocket):
        """See `IArchivePermissionSet`."""
        existing = self.checkAuthenticated(
            person, archive, ArchivePermissionType.UPLOAD, pocket)
        try:
            return existing[0]
        except IndexError:
            return ArchivePermission(
                archive=archive, person=person, pocket=pocket,
                permission=ArchivePermissionType.UPLOAD)

    def newQueueAdmin(self, archive, person, component):
        """See `IArchivePermissionSet`."""
        component = self._nameToComponent(component)
        existing = self.checkAuthenticated(
            person, archive, ArchivePermissionType.QUEUE_ADMIN, component)
        try:
            return existing[0]
        except IndexError:
            return ArchivePermission(
                archive=archive, person=person, component=component,
                permission=ArchivePermissionType.QUEUE_ADMIN)

    def newPocketQueueAdmin(self, archive, person, pocket, distroseries=None):
        """See `IArchivePermissionSet`."""
        existing = self.checkAuthenticated(
            person, archive, ArchivePermissionType.QUEUE_ADMIN, pocket,
            distroseries=distroseries)
        try:
            return existing[0]
        except IndexError:
            return ArchivePermission(
                archive=archive, person=person, pocket=pocket,
                distroseries=distroseries,
                permission=ArchivePermissionType.QUEUE_ADMIN)

    @staticmethod
    def _remove_permission(permission):
        if permission is None:
            # The permission has already been removed, so there's nothing more
            # to do here.
            return
        else:
            Store.of(permission).remove(permission)

    def deletePackageUploader(self, archive, person, sourcepackagename):
        """See `IArchivePermissionSet`."""
        sourcepackagename = self._nameToSourcePackageName(sourcepackagename)
        permission = ArchivePermission.selectOneBy(
            archive=archive, person=person,
            sourcepackagename=sourcepackagename,
            permission=ArchivePermissionType.UPLOAD)
        self._remove_permission(permission)

    def deleteComponentUploader(self, archive, person, component):
        """See `IArchivePermissionSet`."""
        component = self._nameToComponent(component)
        permission = ArchivePermission.selectOneBy(
            archive=archive, person=person, component=component,
            permission=ArchivePermissionType.UPLOAD)
        self._remove_permission(permission)

    def deletePocketUploader(self, archive, person, pocket):
        permission = ArchivePermission.selectOneBy(
            archive=archive, person=person, pocket=pocket,
            permission=ArchivePermissionType.UPLOAD)
        self._remove_permission(permission)

    def deleteQueueAdmin(self, archive, person, component):
        """See `IArchivePermissionSet`."""
        component = self._nameToComponent(component)
        permission = ArchivePermission.selectOneBy(
            archive=archive, person=person, component=component,
            permission=ArchivePermissionType.QUEUE_ADMIN)
        self._remove_permission(permission)

    def deletePocketQueueAdmin(self, archive, person, pocket,
                               distroseries=None):
        """See `IArchivePermissionSet`."""
        kwargs = {}
        if distroseries is not None:
            kwargs["distroseries"] = distroseries
        permission = ArchivePermission.selectOneBy(
            archive=archive, person=person, pocket=pocket,
            permission=ArchivePermissionType.QUEUE_ADMIN, **kwargs)
        self._remove_permission(permission)

    def _nameToPackageset(self, packageset):
        """Helper to convert a possible string name to IPackageset."""
        if isinstance(packageset, basestring):
            # A package set name was passed, assume the current distro series.
            ubuntu = getUtility(IDistributionSet).getByName('ubuntu')
            name = packageset
            store = IStore(Packageset)
            packageset = store.find(
                Packageset, name=name,
                distroseries=ubuntu.currentseries).one()
            if packageset is not None:
                return packageset
            else:
                raise NotFoundError("No such package set '%s'" % name)
        elif IPackageset.providedBy(packageset):
            return packageset
        else:
            raise ValueError(
                'Not a package set: %s' % _extract_type_name(packageset))

    def packagesetsForUploader(self, archive, person):
        """See `IArchivePermissionSet`."""
        store = IStore(ArchivePermission)
        query = '''
            SELECT ap.id
            FROM archivepermission ap, teamparticipation tp
            WHERE
                ap.person = tp.team AND tp.person = ?
                AND ap.archive = ?
                AND ap.packageset IS NOT NULL
        '''
        query = SQL(query, (person.id, archive.id))
        return store.find(
            ArchivePermission, ArchivePermission.id.is_in(query))

    def uploadersForPackageset(
        self, archive, packageset, direct_permissions=True):
        """See `IArchivePermissionSet`."""
        packageset = self._nameToPackageset(packageset)
        store = IStore(ArchivePermission)
        if direct_permissions == True:
            query = '''
                SELECT ap.id FROM archivepermission ap WHERE ap.packageset = ?
            '''
        else:
            query = '''
                SELECT ap.id
                FROM archivepermission ap, flatpackagesetinclusion fpsi
                WHERE fpsi.child = ? AND ap.packageset = fpsi.parent
            '''
        query += " AND ap.archive = ?"
        query = SQL(query, (packageset.id, archive.id))
        return store.find(
            ArchivePermission, ArchivePermission.id.is_in(query))

    def newPackagesetUploader(
        self, archive, person, packageset, explicit=False):
        """See `IArchivePermissionSet`."""
        packageset = self._nameToPackageset(packageset)
        store = IMasterStore(ArchivePermission)

        # First see whether we have a matching permission in the database
        # already.
        query = '''
            SELECT ap.id
            FROM archivepermission ap, teamparticipation tp
            WHERE
                ap.person = tp.team AND tp.person = ?
                AND ap.packageset = ? AND ap.archive = ?
        '''
        query = SQL(query, (person.id, packageset.id, archive.id))
        permissions = list(
            store.find(
                ArchivePermission, ArchivePermission.id.is_in(query)))
        if len(permissions) > 0:
            # Found permissions in the database, does the 'explicit' flag
            # have the requested value?
            conflicting = [permission for permission in permissions
                           if permission.explicit != explicit]
            if len(conflicting) > 0:
                # At least one permission with conflicting 'explicit' flag
                # value exists already.
                cperm = conflicting[0]
                raise ValueError(
                    "Permission for package set '%s' already exists for %s "
                    "but with a different 'explicit' flag value (%s)." %
                    (packageset.name, cperm.person.name, cperm.explicit))
            else:
                # No conflicts, does the requested permission exist already?
                existing = [permission for permission in permissions
                            if (permission.explicit == explicit and
                                permission.person == person and
                                permission.packageset == packageset)]
                assert len(existing) <= 1, (
                    "Too many permissions for %s and %s" %
                    (person.name, packageset.name))
                if len(existing) == 1:
                    # The existing permission matches, just return it.
                    return existing[0]

        # The requested permission does not exist yet. Insert it into the
        # database.
        permission = ArchivePermission(
            archive=archive,
            person=person, packageset=packageset,
            permission=ArchivePermissionType.UPLOAD, explicit=explicit)
        store.add(permission)

        return permission

    def deletePackagesetUploader(
        self, archive, person, packageset, explicit=False):
        """See `IArchivePermissionSet`."""
        packageset = self._nameToPackageset(packageset)
        store = IMasterStore(ArchivePermission)

        # Do we have the permission the user wants removed in the database?
        permission = store.find(
            ArchivePermission, archive=archive, person=person,
            packageset=packageset, permission=ArchivePermissionType.UPLOAD,
            explicit=explicit).one()
        self._remove_permission(permission)

    def packagesetsForSourceUploader(
        self, archive, sourcepackagename, person):
        """See `IArchivePermissionSet`."""
        sourcepackagename = self._nameToSourcePackageName(sourcepackagename)
        store = IStore(ArchivePermission)
        query = '''
            SELECT ap.id
            FROM
                archivepermission ap, teamparticipation tp,
                packagesetsources pss, flatpackagesetinclusion fpsi
            WHERE
                ap.person = tp.team AND tp.person = ?
                AND ap.packageset = fpsi.parent
                AND pss.packageset = fpsi.child
                AND pss.sourcepackagename = ?
                AND ap.archive = ?
        '''
        query = SQL(
            query, (person.id, sourcepackagename.id, archive.id))
        return store.find(
            ArchivePermission, ArchivePermission.id.is_in(query))

    def packagesetsForSource(
        self, archive, sourcepackagename, direct_permissions=True):
        """See `IArchivePermissionSet`."""
        sourcepackagename = self._nameToSourcePackageName(sourcepackagename)
        store = IStore(ArchivePermission)

        if direct_permissions:
            origin = SQL('ArchivePermission, PackagesetSources')
            rset = store.using(origin).find(ArchivePermission, SQL('''
                ArchivePermission.packageset = PackagesetSources.packageset
                AND PackagesetSources.sourcepackagename = ?
                AND ArchivePermission.archive = ?
                ''', (sourcepackagename.id, archive.id)))
        else:
            origin = SQL(
                'ArchivePermission, PackagesetSources, '
                'FlatPackagesetInclusion')
            rset = store.using(origin).find(ArchivePermission, SQL('''
                ArchivePermission.packageset = FlatPackagesetInclusion.parent
                AND PackagesetSources.packageset =
                    FlatPackagesetInclusion.child
                AND PackagesetSources.sourcepackagename = ?
                AND ArchivePermission.archive = ?
                ''', (sourcepackagename.id, archive.id)))
        return rset

    def isSourceUploadAllowed(
        self, archive, sourcepackagename, person, distroseries=None):
        """See `IArchivePermissionSet`."""
        sourcepackagename = self._nameToSourcePackageName(sourcepackagename)
        store = IStore(ArchivePermission)
        if distroseries is None:
            ubuntu = getUtility(IDistributionSet).getByName('ubuntu')
            distroseries = ubuntu.currentseries

        # Put together the parameters for the query that follows.
        archive_params = (ArchivePermissionType.UPLOAD, archive.id)
        permission_params = (sourcepackagename.id, person.id, distroseries.id)
        query_params = (
            # Query parameters for the first WHERE clause.
            (archive.id, distroseries.id, sourcepackagename.id) +
            # Query parameters for the second WHERE clause.
            permission_params + archive_params +
            # Query parameters for the third WHERE clause.
            permission_params + archive_params)

        query = '''
        SELECT CASE
          WHEN (
            SELECT COUNT(ap.id)
            FROM packagesetsources pss, archivepermission ap, packageset ps
            WHERE
              ap.archive = %s AND ap.explicit = TRUE
              AND ap.packageset = ps.id AND ps.distroseries = %s
              AND pss.sourcepackagename = %s
              AND pss.packageset = ap.packageset) > 0
          THEN (
            SELECT COUNT(ap.id)
            FROM
              packagesetsources pss, archivepermission ap, packageset ps,
              teamparticipation tp
            WHERE
              pss.sourcepackagename = %s
              AND ap.person = tp.team AND tp.person = %s
              AND ap.packageset = ps.id AND ps.distroseries = %s
              AND pss.packageset = ap.packageset AND ap.explicit = TRUE
              AND ap.permission = %s AND ap.archive = %s)
          ELSE (
            SELECT COUNT(ap.id)
            FROM
              packagesetsources pss, archivepermission ap, packageset ps,
              teamparticipation tp, flatpackagesetinclusion fpsi
            WHERE
              pss.sourcepackagename = %s
              AND ap.person = tp.team AND tp.person = %s
              AND ap.packageset = ps.id AND ps.distroseries = %s
              AND pss.packageset = fpsi.child AND fpsi.parent = ap.packageset
              AND ap.permission = %s AND ap.archive = %s)
        END AS number_of_permitted_package_sets;

        ''' % sqlvalues(*query_params)
        return store.execute(query).get_one()[0] > 0
