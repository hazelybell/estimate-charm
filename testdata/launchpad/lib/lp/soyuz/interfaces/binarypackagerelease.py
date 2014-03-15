# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Binary package release interfaces."""

__metaclass__ = type

__all__ = [
    'IBinaryPackageRelease',
    'IBinaryPackageReleaseDownloadCount',
    ]

from lazr.restful.declarations import (
    export_as_webservice_entry,
    exported,
    )
from lazr.restful.fields import (
    Reference,
    ReferenceChoice,
    )
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Date,
    Datetime,
    Dict,
    Int,
    List,
    Object,
    Text,
    TextLine,
    )

from lp import _
from lp.app.validators.version import valid_debian_version
from lp.services.worlddata.interfaces.country import ICountry
from lp.soyuz.interfaces.archive import IArchive


class IBinaryPackageRelease(Interface):
    id = Int(title=_('ID'), required=True)
    binarypackagename = Int(required=True)
    binarypackagenameID = Int(required=True)
    version = TextLine(required=True, constraint=valid_debian_version)
    summary = Text(required=True)
    description = Text(required=True)
    build = Int(required=True)
    binpackageformat = Int(required=True)
    component = Int(required=True)
    section = Int(required=True)
    priority = Int(required=False)
    shlibdeps = TextLine(required=False)
    depends = TextLine(required=False)
    recommends = TextLine(required=False)
    suggests = TextLine(required=False)
    conflicts = TextLine(required=False)
    replaces = TextLine(required=False)
    provides = TextLine(required=False)
    pre_depends = TextLine(required=False)
    enhances = TextLine(required=False)
    breaks = TextLine(required=False)
    essential = Bool(required=False)
    installedsize = Int(required=False)
    architecturespecific = Bool(required=True)
    datecreated = Datetime(required=True, readonly=True)
    debug_package = Object(
        title=_("Debug package"), schema=Interface, required=False,
        description=_("The corresponding package containing debug symbols "
                      "for this binary."))
    user_defined_fields = List(
        title=_("Sequence of user-defined fields as key-value pairs."))

    homepage = TextLine(
        title=_("Homepage"),
        description=_(
        "Upstream project homepage as set in the package. This URL is not "
        "sanitized."),
        required=False)

    files = Attribute("Related list of IBinaryPackageFile entries")

    title = TextLine(required=True, readonly=True)
    name = Attribute("Binary Package Name")
    sourcepackagename = Attribute(
        "The name of the source package from where this binary was built.")

    # Properties.
    distributionsourcepackagerelease = Attribute(
        "The sourcepackage release in this distribution from which this "
        "binary was built.")

    is_new = Bool(
        title=_("New Binary."),
        description=_("True if there binary version was never published for "
                      "the architeture it was built for. False otherwise."))

    # This is a dictionary for fast retrieval over the webservice.
    properties = Dict(title=_("The properties of this binary."))

    def addFile(file):
        """Create a BinaryPackageFile record referencing this build
        and attach the provided library file alias (file).
        """

    def override(component=None, section=None, priority=None):
        """Uniform method to override binarypackagerelease attribute.

        All arguments are optional and can be set individually. A non-passed
        argument remains untouched.
        """


class IBinaryPackageReleaseDownloadCount(Interface):
    """Daily download count of a binary package release in an archive."""
    export_as_webservice_entry()

    id = Int(title=_('ID'), required=True, readonly=True)
    archive = exported(Reference(
        title=_('Archive'), schema=IArchive, required=True,
        readonly=True))
    binary_package_release = Reference(
        title=_('The binary package release'), schema=IBinaryPackageRelease,
        required=True, readonly=True)
    binary_package_name = exported(
        TextLine(
            title=_("Binary package name"),
            required=False, readonly=True))
    binary_package_version = exported(
        TextLine(
            title=_("Binary package version"),
            required=False, readonly=True))
    day = exported(
        Date(title=_('Day of the downloads'), required=True, readonly=True))
    count = exported(
        Int(title=_('Number of downloads'), required=True, readonly=True))
    country = exported(
        ReferenceChoice(
            title=_('Country'), required=False, readonly=True,
            vocabulary='CountryName', schema=ICountry))
