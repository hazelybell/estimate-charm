# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Source package name interfaces."""

__metaclass__ = type

__all__ = [
    'ISourcePackageName',
    'ISourcePackageNameSet',
    ]

from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Int,
    TextLine,
    )

from lp import _
from lp.app.validators.name import name_validator


class ISourcePackageName(Interface):
    """Interface provied by a SourcePackageName.

    This is a tiny table that allows multiple SourcePackage entities to share
    a single name.
    """
    id = Int(title=_("ID"), required=True)
    name = TextLine(title=_("Valid Source package name"),
                    required=True, constraint=name_validator)
    potemplates = Attribute("The list of PO templates that this object has.")
    packagings = Attribute("Everything we know about the packaging of "
        "packages with this source package name.")

    def __unicode__():
        """Return the name"""


class ISourcePackageNameSet(Interface):
    """A set of SourcePackageName."""

    def __getitem__(name):
        """Retrieve a sourcepackagename by name."""

    def get(sourcepackagenameid):
        """Return a sourcepackagename by its id.

        If the sourcepackagename can't be found a NotFoundError will be
        raised.
        """

    def getAll():
        """return an iselectresults representing all package names"""

    def queryByName(name):
        """Get a sourcepackagename by its name atttribute.

        Returns the matching ISourcePackageName or None.
        """

    def new(name):
        """Create a new source package name."""

    def getOrCreateByName(name):
        """Get a source package name by name, creating it if necessary."""
