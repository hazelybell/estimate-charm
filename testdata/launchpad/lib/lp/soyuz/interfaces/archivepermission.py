# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""ArchivePermission interface."""

__metaclass__ = type

__all__ = [
    'IArchivePermission',
    'IArchivePermissionSet',
    'IArchiveUploader',
    'IArchiveQueueAdmin',
    ]

from lazr.restful.declarations import (
    export_as_webservice_entry,
    exported,
    )
from lazr.restful.fields import Reference
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    TextLine,
    )

from lp import _
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.sourcepackagename import ISourcePackageName
from lp.services.fields import PublicPersonChoice
from lp.soyuz.enums import ArchivePermissionType
from lp.soyuz.interfaces.archive import IArchive
from lp.soyuz.interfaces.component import IComponent
from lp.soyuz.interfaces.packageset import IPackageset


class IArchivePermission(Interface):
    """The interface for `ArchivePermission`."""
    export_as_webservice_entry(publish_web_link=False)

    id = Attribute("The archive permission ID.")

    date_created = exported(
        Datetime(
            title=_('Date Created'), required=False, readonly=False,
            description=_("The timestamp when the permission was created.")))

    archive = exported(
        Reference(
            IArchive,
            title=_("Archive"),
            description=_("The archive that this permission is for.")))

    permission = exported(
        Choice(
            title=_("The permission type being granted."),
            values=ArchivePermissionType, readonly=False, required=True))

    personID = Attribute("DB ID for person.")
    person = exported(
        PublicPersonChoice(
            title=_("Person"),
            description=_("The person or team being granted the permission."),
            required=True, vocabulary="ValidPersonOrTeam"))

    component = Reference(
        IComponent,
        title=_("Component"),
        description=_("The component that this permission is related to."))

    sourcepackagename = Reference(
        ISourcePackageName,
        title=_("Source Package Name"),
        description=_("The source package name that this permission is "
                      "related to."))

    # This is the *text* component name, as opposed to `component` above
    # which is the `IComponent` and we don't want to export that.
    component_name = exported(
        TextLine(
            title=_("Component Name"),
            required=True))

    # This is the *text* package name, as opposed to `sourcepackagename`
    # which is the `ISourcePackageName` and we don't want to export
    # that.
    source_package_name = exported(
        TextLine(
            title=_("Source Package Name"),
            required=True))

    packageset = Reference(
            IPackageset,
            title=_("Packageset"),
            description=_("The package set that this permission is for."))

    explicit = exported(
        Bool(
            title=_("Explicit"),
            description=_(
                "Set this flag for package sets with high-profile packages "
                "requiring specialist skills for proper handling.")))

    package_set_name = exported(
        TextLine(
            title=_("Package set name"),
            required=True))

    distro_series_name = exported(
        TextLine(
            title=_(
                "The name of the distro series associated with the "
                "package set."),
            required=True))

    pocket = exported(
        Choice(
            title=_("Pocket"),
            description=_("The pocket that this permission is for."),
            vocabulary=PackagePublishingPocket,
            required=True))

    distroseries = exported(
        Reference(
            IDistroSeries,
            title=_("Distro series"),
            description=_(
                "The distro series that this permission is for (only for "
                "pocket permissions)."),
            required=False))


class IArchiveUploader(IArchivePermission):
    """Marker interface for URL traversal of uploader permissions."""


class IArchiveQueueAdmin(IArchivePermission):
    """Marker interface for URL traversal of queue admin permissions."""


class IArchivePermissionSet(Interface):
    """The interface for `ArchivePermissionSet`."""

    # Do not export this utility directly on the webservice.  There is
    # no reasonable security model we can implement for it because it
    # requires the archive context to be able to make an informed
    # security decision.
    #
    # For this reason, the security declaration in the zcml is
    # deliberately permissive.  We don't expect anything to access this
    # utility except the IArchive code, which is appropriately protected.

    def checkAuthenticated(person, archive, permission, item):
        """The `ArchivePermission` records that authenticate the person.

        :param person: An `IPerson` whom should be checked for authentication.
        :param archive: The context `IArchive` for the permission check.
        :param permission: The `ArchivePermissionType` to check.
        :param item: The context `IComponent` or `ISourcePackageName` for the
            permission check.

        :return: all the `ArchivePermission` records that match the parameters
        supplied.  If none are returned, it means the person is not
        authenticated in that context.
        """

    def permissionsForArchive(archive):
        """All `ArchivePermission` records for the archive.

        :param archive: An `IArchive`.
        """

    def permissionsForPerson(person, archive):
        """All `ArchivePermission` records for the person.

        :param person: An `IPerson`
        :param archive: An `IArchive`
        """

    def uploadersForComponent(archive, component=None):
        """The `ArchivePermission` records for authorised component uploaders.

        :param archive: The context `IArchive` for the permission check.
        :param component: Optional `IComponent`, if specified will only
            return records for uploaders to that component, otherwise
            all components are considered.  You can also supply a string
            component name instead.
        :raises ComponentNotFound: if the named component does not exist.

        :return: `ArchivePermission` records for all the uploaders who
            are authorised for the supplied component.
        """

    def componentsForUploader(archive, person):
        """The `ArchivePermission` records for the person's upload components.

        :param archive: The context `IArchive` for the permission check.
        :param person: An `IPerson` for whom you want to find out which
            components he has access to.

        :return: `ArchivePermission` records for all the components that
            'person' is allowed to upload to.
        """

    def packagesForUploader(archive, person):
        """The `ArchivePermission` records for the person's upload packages.

        :param archive: The context `IArchive` for the permission check.
        :param person: An `IPerson` for whom you want to find out which
            packages he has access to.

        :return: `ArchivePermission` records for all the packages that
            'person' is allowed to upload to.
        """

    def uploadersForPackage(archive, sourcepackagename):
        """The `ArchivePermission` records for authorised package uploaders.

        :param archive: The context `IArchive` for the permission check.
        :param sourcepackagename: An `ISourcePackageName` or a string
            package name.
        :raises SourceNotFound: if the string package name does not exist.

        :return: `ArchivePermission` records for all the uploaders who are
            authorised to upload the named source package.
        """

    def packagesetsForUploader(archive, person):
        """The `ArchivePermission` records for the person's package sets.

        :param archive: The archive the permission applies to.
        :param person: An `IPerson` for whom you want to find out which
            package sets he has access to.

        :return: `ArchivePermission` records for all the package sets that
            'person' is allowed to upload to.
        """

    def packagesetsForSourceUploader(archive, sourcepackagename, person):
        """The package set based permissions for a given source and uploader.

        Return the `IArchivePermission` records that
            * apply to the given `archive`
            * relate to
                - package sets that include the given source package name
                - the given `person`

        :param archive: The archive the permission applies to.
        :param sourcepackagename: the source package name; can be
            either a string or a `ISourcePackageName`.
        :param person: An `IPerson` for whom you want to find out which
            package sets he has access to.

        :raises SourceNotFound: if a source package with the given
            name could not be found.
        :return: `ArchivePermission` records for the package sets that
            include the given source package name and to which the given
            person may upload.
        """

    def packagesetsForSource(
        archive, sourcepackagename, direct_permissions=True):
        """All package set based permissions for the given archive and source.

        This method is meant to aid the process of "debugging" package set
        based archive permission since It allows the listing of permissions
        for the given source package irrespective of a person.

        :param archive: The archive the permission applies to.
        :param sourcepackagename: the source package name; can be
            either a string or a `ISourcePackageName`.
        :param direct_permissions: If set, only package sets that directly
            include the given source will be considered.

        :raises SourceNotFound: if a source package with the given
            name could not be found.
        :return: `ArchivePermission` records for the package sets that
            include the given source package name and apply to the
            archive in question.
        """

    def isSourceUploadAllowed(
        archive, sourcepackagename, person, distroseries=None):
        """True if the person is allowed to upload the given source package.

        Return True if there exists a permission that combines
            * the given `archive`
            * a package set that includes the given source package name
            * the given person or a team he is a member of

        If the source package name is included by *any* package set with
        an explicit permission then only such explicit permissions will
        be considered.

        :param archive: The archive the permission applies to.
        :param sourcepackagename: the source package name; can be
            either a string or a `ISourcePackageName`.
        :param person: An `IPerson` for whom you want to find out which
            package sets he has access to.
        :param distroseries: The `IDistroSeries` for which to check
            permissions. If none is supplied then `currentseries` in
            Ubuntu is assumed.

        :raises SourceNotFound: if a source package with the given
            name could not be found.
        :return: True if the person is allowed to upload the source package.
        """

    def uploadersForPackageset(archive, packageset, direct_permissions=True):
        """The `ArchivePermission` records for uploaders to the package set.

        Please note: if a package set *name* is passed the respective
                     package set in the current distro series will be used.

        :param archive: The archive the permission applies to.
        :param packageset: An `IPackageset` or a string package set name.
        :param direct_permissions: If True only consider permissions granted
            directly for the package set at hand. Otherwise, include any
            uploaders for package sets that include this one.
        :raises NotFoundError: if no package set exists with the given name.

        :return: `ArchivePermission` records for all the uploaders who are
            authorized to upload to the named source package set.
        """

    def uploadersForPocket(archive, pocket):
        """The `ArchivePermission` records for authorised pocket uploaders.

        :param archive: The context `IArchive` for the permission check.
        :param pocket: A `PackagePublishingPocket`.

        :return: `ArchivePermission` records for all the uploaders who
            are authorised for the supplied pocket.
        """

    def pocketsForUploader(archive, person):
        """The `ArchivePermission` records for the person's upload pockets.

        :param archive: The context `IArchive` for the permission check.
        :param person: An `IPerson` for whom you want to find out which
            pockets he has access to.

        :return: `ArchivePermission` records for all the pockets that
            'person' is allowed to upload to.
        """

    def queueAdminsForComponent(archive, component):
        """The `ArchivePermission` records for authorised queue admins.

        :param archive: The context `IArchive` for the permission check.
        :param component: The context `IComponent` for the permission check.
            You can also supply a string component name instead.

        :return: `ArchivePermission` records for all the person who are
            allowed to administer the distroseries upload queue.
        """

    def componentsForQueueAdmin(archive, person):
        """Return `ArchivePermission` for the person's queue admin components.

        :param archive: The context `IArchive` for the permission check, or
            an iterable of `IArchive`s.
        :param person: An `IPerson` for whom you want to find out which
            components he has access to.

        :return: `ArchivePermission` records for all the components that
            'person' is allowed to administer the queue for.
        """

    def queueAdminsForPocket(archive, pocket, distroseries=None):
        """The `ArchivePermission` records for authorised pocket queue admins.

        :param archive: The context `IArchive` for the permission check.
        :param pocket: A `PackagePublishingPocket`.
        :param distroseries: An optional `IDistroSeries`.

        :return: `ArchivePermission` records for all the persons who are
            allowed to administer the pocket upload queue.
        """

    def pocketsForQueueAdmin(archive, person):
        """Return `ArchivePermission` for the person's queue admin pockets.

        :param archive: The context `IArchive` for the permission check, or
            an iterable of `IArchive`s.
        :param person: An `IPerson` for whom you want to find out which
            pockets he has access to.

        :return: `ArchivePermission` records for all the pockets that
            'person' is allowed to administer the queue for.
        """

    def newPackageUploader(archive, person, sourcepackagename):
        """Create and return a new `ArchivePermission` for an uploader.

        :param archive: The context `IArchive` for the permission check.
        :param person: An `IPerson` for whom you want to add permission.
        :param sourcepackagename: An `ISourcePackageName` or a string
            package name.

        :return: The new `ArchivePermission`, or the existing one if it
            already exists.
        """

    def newPackagesetUploader(archive, person, packageset, explicit=False):
        """Create and return a new `ArchivePermission` for an uploader.

        Please note: if a package set *name* is passed the respective
                     package set in the current distro series will be used.

        :param archive: The archive the permission applies to.
        :param person: An `IPerson` for whom you want to add permission.
        :param packageset: An `IPackageset` or a string package set name.
        :param explicit: True if the permissions granted by this package set
            exclude permissions granted by non-explicit package sets.
        :raises ValueError: if an `ArchivePermission` record for this
            person and packageset already exists *but* with a different
            'explicit' flag value.

        :return: The new `ArchivePermission`, or the existing one if it
            already exists.
        """

    def newComponentUploader(archive, person, component):
        """Create and return a new `ArchivePermission` for an uploader.

        :param archive: The context `IArchive` for the permission check.
        :param person: An `IPerson` for whom you want to add permission.
        :param component: An `IComponent` or a string package name.

        :return: The new `ArchivePermission`, or the existing one if it
            already exists.
        """

    def newPocketUploader(archive, person, pocket):
        """Create and return a new `ArchivePermission` for an uploader.

        :param archive: The context `IArchive` for the permission check.
        :param person: An `IPerson` for whom you want to add permission.
        :param component: A `PackagePublishingPocket`.

        :return: The new `ArchivePermission`, or the existing one if it
            already exists.
        """

    def newQueueAdmin(archive, person, component):
        """Create and return a new `ArchivePermission` for a queue admin.

        :param archive: The context `IArchive` for the permission check.
        :param person: An `IPerson` for whom you want to add permission.
        :param component: An `IComponent` or a string package name.

        :return: The new `ArchivePermission`, or the existing one if it
            already exists.
        """

    def newPocketQueueAdmin(archive, person, pocket, distroseries=None):
        """Create and return a new `ArchivePermission` for a queue admin.

        :param archive: The context `IArchive` for the permission check.
        :param person: An `IPerson` for whom you want to add permission.
        :param pocket: A `PackagePublishingPocket`.
        :param distroseries: An optional `IDistroSeries`.

        :return: The new `ArchivePermission`, or the existing one if it
            already exists.
        """

    def deletePackageUploader(archive, person, sourcepackagename):
        """Revoke upload permissions for a person.

        :param archive: The context `IArchive` for the permission check.
        :param person: An `IPerson` for whom you want to revoke permission.
        :param sourcepackagename: An `ISourcePackageName` or a string
            package name.
        """

    def deletePackagesetUploader(archive, person, packageset, explicit=False):
        """Revoke upload permissions for a person.

        Please note: if a package set *name* is passed the respective
                     package set in the current distro series will be used.

        :param archive: The archive the permission applies to.
        :param person: An `IPerson` for whom you want to revoke permission.
        :param packageset: An `IPackageset` or a string package set name.
        :param explicit: The value of the 'explicit' flag for the permission
            to be revoked.
        """

    def deleteComponentUploader(archive, person, component):
        """Revoke upload permissions for a person.

        :param archive: The context `IArchive` for the permission check.
        :param person: An `IPerson` for whom you want to revoke permission.
        :param component: An `IComponent` or a string package name.
        """

    def deletePocketUploader(archive, person, pocket):
        """Revoke upload permissions for a person.

        :param archive: The context `IArchive` for the permission check.
        :param person: An `IPerson` for whom you want to revoke permission.
        :param pocket: A `PackagePublishingPocket`.
        """

    def deleteQueueAdmin(archive, person, component):
        """Revoke queue admin permissions for a person.

        :param archive: The context `IArchive` for the permission check.
        :param person: An `IPerson` for whom you want to revoke permission.
        :param component: An `IComponent` or a string package name.
        """

    def deletePocketQueueAdmin(archive, person, pocket, distroseries=None):
        """Revoke queue admin permissions for a person.

        :param archive: The context `IArchive` for the permission check.
        :param person: An `IPerson` for whom you want to revoke permission.
        :param pocket: A `PackagePublishingPocket`.
        :param distroseries: An optional `IDistroSeries`.
        """
