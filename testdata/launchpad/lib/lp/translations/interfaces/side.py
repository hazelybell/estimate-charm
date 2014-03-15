# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Traits of the two "sides" of translation: Ubuntu and upstream."""

__metaclass__ = type
__all__ = [
    'ITranslationSideTraits',
    'ITranslationSideTraitsSet',
    'TranslationSide',
    ]

from lazr.restful.fields import Reference
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import TextLine


class TranslationSide:
    """The two "sides" of software that can be translated in Launchpad.

    These are "upstream" and "Ubuntu."
    """
    UPSTREAM = 1
    UBUNTU = 2


class ITranslationSideTraits(Interface):
    """Traits describing a "side": upstream or Ubuntu.

    Encapsulates primitives that depend on translation side: finding the
    message that is current on the given side, checking the flag that
    says whether a message is current on this side, setting or clearing
    the flag, and providing the same capabilities for the other side.

    For an introduction to the Traits pattern, see
    http://www.cantrip.org/traits.html
    """
    side = Attribute("This TranslationSide")
    other_side_traits = Reference(
        Interface, title=u"Traits for other side.", required=True,
        readonly=True)
    flag_name = TextLine(
        title=u"The TranslationMessage flag for this side",
        required=True, readonly=True)
    displayname = TextLine(
        title=u"Display name for this side", required=True, readonly=True)

    def getCurrentMessage(potemplate, potmsgset, language):
        """Find the current message on this side, if any."""

    def getFlag(translationmessage):
        """Retrieve a message's "current" flag for this side."""

    def setFlag(translationmessage, value):
        """Set a message's "current" flag for this side.

        This is a dumb operation.  It does not worry about conflicting
        other messages.
        """


class ITranslationSideTraitsSet(Interface):
    """Utility for `TranslationSideTraits`."""

    def getTraits(side):
        """Retrieve the `TranslationSideTraits` for `side`."""

    def getForTemplate(potemplate):
        """Get the `TranslationSideTraits` for `potemplate`s side."""

    def getAllTraits():
        """Return dict mapping `TranslationSide` to traits objects."""
