# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Specification message interfaces."""

__metaclass__ = type
__all__ = [
    'ISpecificationMessage',
    'ISpecificationMessageSet',
    ]

from lazr.restful.fields import Reference
from zope.interface import Interface
from zope.schema import Bool

from lp.blueprints.interfaces.specification import ISpecification
from lp.services.messages.interfaces.message import IMessage


class ISpecificationMessage(Interface):
    """A link between a specification and a message."""

    specification = Reference(schema=ISpecification,
        title=u"The specification.")
    message = Reference(schema=IMessage, title=u"The message.")
    visible = Bool(title=u"Is this message visible?", required=False,
        default=True)


class ISpecificationMessageSet(Interface):
    """The set of all ISpecificationMessages."""

    def createMessage(subject, specification, owner, content=None):
        """Create an ISpecificationMessage.

        title -- a string
        specification -- an ISpecification
        owner -- an IPerson
        content -- a string

        The created message will have the specification's initial message as
        its parent.

        Returns the created ISpecificationMessage.
        """

    def get(specificationmessageid):
        """Retrieve an ISpecificationMessage by its ID."""

    def getBySpecificationAndMessage(specification, message):
        """Return the corresponding ISpecificationMesssage.

        Return None if no such ISpecificationMesssage exists.
        """
