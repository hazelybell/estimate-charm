# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Product release interfaces."""

__metaclass__ = type

__all__ = [
    'IProductRelease',
    'IProductReleaseEditRestricted',
    'IProductReleaseFile',
    'IProductReleaseFileAddForm',
    'IProductReleaseFileEditRestricted',
    'IProductReleaseFilePublic',
    'IProductReleasePublic',
    'IProductReleaseSet',
    'UpstreamFileType',
    ]

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
from lazr.restful.declarations import (
    call_with,
    export_as_webservice_entry,
    export_factory_operation,
    export_operation_as,
    export_write_operation,
    exported,
    operation_parameters,
    REQUEST_USER,
    )
from lazr.restful.fields import (
    CollectionField,
    Reference,
    ReferenceChoice,
    )
from lazr.restful.interface import copy_field
from zope.component import getUtility
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bytes,
    Choice,
    Datetime,
    Int,
    Text,
    TextLine,
    )

from lp import _
from lp.app.validators import LaunchpadValidationError
from lp.app.validators.version import sane_version
from lp.services.config import config
from lp.services.fields import (
    ContentNameField,
    PersonChoice,
    )


def file_size_constraint(value, max_size):
    """Check constraints.

    The file cannot be empty and must be <= max_size.
    """
    size = len(value)
    if size == 0:
        raise LaunchpadValidationError(u'Cannot upload empty file.')
    elif max_size > 0 and size > max_size:
        raise LaunchpadValidationError(
            u'Cannot upload files larger than %i bytes' % max_size)
    else:
        return True


def productrelease_file_size_constraint(value):
    """Constraint for a product release file's size."""
    max_size = config.launchpad.max_productrelease_file_size
    return file_size_constraint(value, max_size)


def productrelease_signature_size_constraint(value):
    """Constraint for a product release signature's size."""
    max_size = config.launchpad.max_productrelease_signature_size
    return file_size_constraint(value, max_size)


class UpstreamFileType(DBEnumeratedType):
    """Upstream File Type

    When upstream open source project release a product they will
    include several files in the release. All of these files are
    stored in Launchpad (we throw nothing away ;-). This schema
    gives the type of files that we know about.
    """

    CODETARBALL = DBItem(1, """
        Code Release Tarball

        This file contains code in a compressed package like
        a tar.gz or tar.bz or .zip file.
        """)

    README = DBItem(2, """
        README File

        This is a README associated with the upstream
        release. It might be in .txt or .html format, the
        filename would be an indicator.
        """)

    RELEASENOTES = DBItem(3, """
        Release Notes

        This file contains the release notes of the new
        upstream release. Again this could be in .txt or
        in .html format.
        """)

    CHANGELOG = DBItem(4, """
        ChangeLog File

        This file contains information about changes in this
        release from the previous release in the series. This
        is usually not a detailed changelog, but a high-level
        summary of major new features and fixes.
        """)

    INSTALLER = DBItem(5, """
        Installer file

        This file contains an installer for a product.  It may
        be a Debian package, an RPM file, an OS X disk image, a
        Windows installer, or some other type of installer.
        """)


class ProductReleaseVersionField(ContentNameField):

    errormessage = _(
        "%s is already in use by another version in this release series.")

    @property
    def _content_iface(self):
        return IProductRelease

    def _getByName(self, version):
        """Return the content object for the specified version.

        The version is specified either by the context directly or by the
        context's referenced productseries.  Overridden from
        `ContentFieldName`.
        """
        # Import locally to avoid circular imports.
        from lp.registry.interfaces.productseries import (
            IProductSeries)
        if IProductSeries.providedBy(self.context):
            productseries = self.context
        else:
            productseries = self.context.productseries
        releaseset = getUtility(IProductReleaseSet)
        release = releaseset.getBySeriesAndVersion(productseries, version)
        if release == self.context:
            # A ProductRelease may edit itself; do not report that another
            # ProductRelease exists with the same version.
            return None
        return release


class IProductReleaseFileEditRestricted(Interface):
    """`IProductReleaseFile` properties which require `launchpad.Edit`."""

    @export_write_operation()
    @export_operation_as('delete')
    def destroySelf():
        """Delete the product release file."""


class IProductReleaseFilePublic(Interface):
    """Public properties for `IProductReleaseFile`."""

    id = Int(title=_('ID'), required=True, readonly=True)
    productrelease = exported(
        ReferenceChoice(title=_('Project release'),
                        description=_("The parent product release."),
                        schema=Interface,  # Defined later.
                        required=True,
                        vocabulary='ProductRelease'),
        exported_as='project_release')
    libraryfile = exported(
        Bytes(title=_("File"),
              description=_("The file contents."),
              readonly=True,
              required=True),
        exported_as='file')
    signature = exported(
        Bytes(title=_("File signature"),
              description=_("The file signature."),
              readonly=True,
              required=False))
    filetype = exported(
        Choice(title=_("Upstream file type"), required=True,
               vocabulary=UpstreamFileType,
               default=UpstreamFileType.CODETARBALL),
        exported_as='file_type')
    description = exported(
        Text(title=_("Description"), required=False,
             description=_('A detailed description of the file contents')))
    date_uploaded = exported(
        Datetime(title=_('Upload date'),
                 description=_('The date this file was uploaded'),
                 required=True, readonly=True))


class IProductReleaseFile(IProductReleaseFileEditRestricted,
                          IProductReleaseFilePublic):
    """A file associated with a ProductRelease."""
    export_as_webservice_entry("project_release_file", publish_web_link=False)


class IProductReleaseEditRestricted(Interface):
    """`IProductRelease` properties which require `launchpad.Edit`."""

    @call_with(uploader=REQUEST_USER, from_api=True)
    @operation_parameters(
        filename=TextLine(),
        signature_filename=TextLine(),
        content_type=TextLine(),
        file_content=Bytes(constraint=productrelease_file_size_constraint),
        signature_content=Bytes(
            constraint=productrelease_signature_size_constraint),
        file_type=copy_field(IProductReleaseFile['filetype'], required=False))
    @export_factory_operation(IProductReleaseFile, ['description'])
    @export_operation_as('add_file')
    def addReleaseFile(filename, file_content, content_type,
                       uploader, signature_filename=None,
                       signature_content=None,
                       file_type=UpstreamFileType.CODETARBALL,
                       description=None, from_api=False):
        """Add file to the library and link to this `IProductRelease`.

        The signature file will also be added if available.

        :param filename: Name of the file being uploaded.
        :param file_content: StringIO or file object.
        :param content_type: A MIME content type string.
        :param uploader: The person who uploaded the file.
        :param signature_filename: Name of the uploaded gpg signature file.
        :param signature_content: StringIO or file object.
        :param file_type: An `UpstreamFileType` enum value.
        :param description: Info about the file.
        :returns: `IProductReleaseFile` object.
        :raises: InvalidFilename if the filename is invalid or a duplicate
            of a file previously added to the release.
        """

    @export_write_operation()
    @export_operation_as('delete')
    def destroySelf():
        """Delete this release.

        This method must not be used if this release has any
        release files associated with it.
        """


class IProductReleasePublic(Interface):
    """Public `IProductRelease` properties."""

    id = Int(title=_('ID'), required=True, readonly=True)


class IProductReleaseView(Interface):
    """launchpad.View-restricted `IProductRelease` properties."""

    datereleased = exported(
        Datetime(
            title=_('Date released'), required=True,
            readonly=False,
            description=_('The date this release was published. Before '
                          'release, this should have an estimated '
                          'release date.')),
        exported_as="date_released"
        )

    version = exported(
        ProductReleaseVersionField(
            title=_('Version'),
            description=u'The specific version number assigned to this '
            'release. Letters and numbers are acceptable, for releases like '
            '"1.2rc3".',
            constraint=sane_version, readonly=True)
        )

    owner = exported(
        PersonChoice(
            title=u"The registrant of this release.",
            required=True,
            vocabulary='ValidOwner',
            description=_("The person or who registered this release.")
            )
        )

    productseries = Attribute("This release's parent series.")

    release_notes = exported(
        Text(
            title=_("Release notes"), required=False,
            description=_('A description of important new features '
                          '(though the changelog below might repeat some of '
                          'this information).'))
        )

    changelog = exported(
        Text(
            title=_('Changelog'), required=False,
            description=_('A description of every change in the release.'))
        )

    datecreated = exported(
        Datetime(title=_('Date Created'),
                 description=_("The date this project release was created in "
                               "Launchpad."),
                 required=True, readonly=True),
        exported_as="date_created")

    displayname = exported(
        Text(title=u'Constructed display name for a project release.',
             readonly=True),
        exported_as="display_name")

    title = exported(
        Text(title=u'Constructed title for a project release.', readonly=True)
        )

    can_have_release_files = Attribute("Whether release files can be added.")

    product = exported(
        Reference(title=u'The project that made this release.',
                  schema=Interface, readonly=True),
         exported_as="project")

    files = exported(
        CollectionField(
            title=_('Project release files'),
            description=_('A list of files for this release.'),
            readonly=True,
            value_type=Reference(schema=IProductReleaseFile)))

    milestone = exported(
        ReferenceChoice(
            title=u"Milestone for this release",
            description=_("A release requires a corresponding milestone "
                          "that is not attached to another release."),
            # Schema is set to IMilestone in interfaces/milestone.py.
            schema=Interface,
            vocabulary='Milestone',
            required=True))

    def getFileAliasByName(name):
        """Return the `LibraryFileAlias` by file name.

        Raises a NotFoundError if no matching ProductReleaseFile exists.
        """

    def getProductReleaseFileByName(name):
        """Return the `ProductReleaseFile` by file name.

        Raises a NotFoundError if no matching ProductReleaseFile exists.
        """
    def hasReleaseFile(name):
        """Does the release have a file that matches the name?"""


class IProductRelease(IProductReleaseEditRestricted, IProductReleaseView,
                      IProductReleasePublic):
    """A specific release (i.e. version) of a product.

    For example: Mozilla 1.7.2 or Apache 2.0.48.
    """

    export_as_webservice_entry('project_release')


# Set the schema for IProductReleaseFile now that IProductRelease is defined.
IProductReleaseFile['productrelease'].schema = IProductRelease


class IProductReleaseFileAddForm(Interface):
    """Schema for adding ProductReleaseFiles to a project."""
    description = Text(title=_("Description"), required=True,
        description=_('A short description of the file contents'))

    filecontent = Bytes(
        title=u"File", required=True,
        constraint=productrelease_file_size_constraint)

    signature = Bytes(
        title=u"GPG signature (recommended)", required=False,
        constraint=productrelease_signature_size_constraint)

    contenttype = Choice(title=_("File content type"), required=True,
                         vocabulary=UpstreamFileType,
                         default=UpstreamFileType.CODETARBALL)


class IProductReleaseSet(Interface):
    """Auxiliary class for ProductRelease handling."""

    def getBySeriesAndVersion(productseries, version, default=None):
        """Get a release by its version and productseries.

        If no release is found, default will be returned.
        """

    def getReleasesForSeries(series):
        """Get all releases for the series."""

    def getFilesForReleases(releases):
        """Get all files for the releases."""
