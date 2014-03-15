# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for a Sprint (a meeting, conference or hack session).

A Sprint basically consists of a bunch of people getting together to discuss
some specific issues.
"""

__metaclass__ = type

__all__ = [
    'ISprint',
    'IHasSprints',
    'ISprintSet',
    ]

from zope.component import getUtility
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Choice,
    Datetime,
    Int,
    Text,
    TextLine,
    )

from lp import _
from lp.app.interfaces.headings import IRootContext
from lp.app.validators.name import name_validator
from lp.blueprints.interfaces.specificationtarget import IHasSpecifications
from lp.registry.interfaces.role import (
    IHasDrivers,
    IHasOwner,
    )
from lp.services.fields import (
    ContentNameField,
    IconImageUpload,
    LogoImageUpload,
    MugshotImageUpload,
    PublicPersonChoice,
    )


class SprintNameField(ContentNameField):

    errormessage = _("%s is already in use by another sprint.")

    @property
    def _content_iface(self):
        return ISprint

    def _getByName(self, name):
        return getUtility(ISprintSet)[name]


class ISprint(IHasOwner, IHasDrivers, IHasSpecifications, IRootContext):
    """A sprint, or conference, or meeting."""

    id = Int(title=_('The Sprint ID'))

    name = SprintNameField(
        title=_('Name'), required=True, description=_('A unique name '
        'for this sprint, or conference, or meeting. This will part of '
        'the URL so pick something short. A single word is all you get.'),
        constraint=name_validator)
    displayname = Attribute('A pseudonym for the title.')
    title = TextLine(
        title=_('Title'), required=True, description=_("Please provide "
        "a title for this meeting. This will be shown in listings of "
        "meetings."))
    summary = Text(
        title=_('Summary'), required=True, description=_("A one-paragraph "
        "summary of the meeting plans and goals. Put the rest in a web "
        "page and link to it using the field below."))
    driver = PublicPersonChoice(
        title=_('Meeting Driver'), required=False,
        description=_('The person or team that will manage the agenda of '
        'this meeting. Use this if you want to delegate the approval of '
        'agenda items to somebody else.'), vocabulary='ValidPersonOrTeam')
    address = Text(
        title=_('Meeting Address'), required=False,
        description=_("The address of the meeting venue."))
    home_page = TextLine(
        title=_('Home Page'), required=False, description=_("A web page "
        "with further information about the event."))
    icon = IconImageUpload(
        title=_("Icon"), required=False,
        default_image_resource='/@@/meeting',
        description=_(
            "A small image of exactly 14x14 pixels and at most 5kb in size, "
            "that can be used to identify this meeting. The icon will be "
            "displayed wherever we list and link to the meeting."))
    logo = LogoImageUpload(
        title=_("Logo"), required=False,
        default_image_resource='/@@/meeting-logo',
        description=_(
            "An image of exactly 64x64 pixels that will be displayed in "
            "the heading of all pages related to this meeting. It should be "
            "no bigger than 50kb in size."))
    mugshot = MugshotImageUpload(
        title=_("Brand"), required=False,
        default_image_resource='/@@/meeting-mugshot',
        description=_(
            "A large image of exactly 192x192 pixels, that will be displayed "
            "on this meeting's home page in Launchpad. It should be no "
            "bigger than 100kb in size. "))
    homepage_content = Text(
        title=_("Homepage Content"), required=False,
        description=_(
            "The content of this meeting's home page. Edit this and it "
            "will be displayed for all the world to see. It is NOT a wiki "
            "so you cannot undo changes."))
    owner = PublicPersonChoice(
        title=_('Owner'), required=True, readonly=True,
        vocabulary='ValidPersonOrTeam')
    time_zone = Choice(
        title=_('Timezone'), required=True, description=_('The time '
        'zone in which this sprint, or conference, takes place. '),
        vocabulary='TimezoneName')
    time_starts = Datetime(
        title=_('Starting Date and Time'), required=True)
    time_ends = Datetime(
        title=_('Finishing Date and Time'), required=True)
    datecreated = Datetime(
        title=_('Date Created'), required=True, readonly=True)

    # joins
    attendees = Attribute('The set of attendees at this sprint.')
    attendances = Attribute('The set of SprintAttendance records.')

    def specificationLinks(status=None):
        """Return the SprintSpecification records matching the filter,
        quantity and sort given. The rules for filtering and sorting etc are
        the same as those for IHasSpecifications.specifications()
        """

    def getSpecificationLink(id):
        """Return the specification link for this sprint that has the given
        ID. We use the naked ID because there is no unique name for a spec
        outside of a single product or distro, and a sprint can cover
        multiple products and distros.
        """

    def acceptSpecificationLinks(idlist, decider):
        """Accept the given sprintspec items, and return the number of
        sprintspec items that remain proposed.
        """

    def declineSpecificationLinks(idlist, decider):
        """Decline the given sprintspec items, and return the number of
        sprintspec items that remain proposed.
        """

    # subscription-related methods
    def attend(person, time_starts, time_ends, is_physical):
        """Record that this person will be attending the Sprint."""

    def removeAttendance(person):
        """Remove the person's attendance record."""

    # bug linking
    def linkSpecification(spec):
        """Link this sprint to the given specification."""

    def unlinkSpecification(spec):
        """Remove this specification from the sprint spec list."""

    def isDriver(user):
        """Returns True if and only if the specified user
        is a driver of this sprint.

        A driver for a sprint is either the person in the
        `driver` attribute, a person who is memeber of a team
        in the `driver` attribute or an administrator.
        """


class IHasSprints(Interface):
    """An interface for things that have lists of sprints associated with
    them. This is used for projects, products and distributions, for
    example, where we can generate a list of upcoming events relevant to
    them.
    """

    coming_sprints = Attribute(
        "A list of up to 5 events currently on, or soon to be on, that are "
        "relevant to this context.")

    sprints = Attribute("All sprints relevant to this context.")

    past_sprints = Attribute("Sprints that occured in the past.")


class ISprintSet(Interface):
    """A container for sprints."""

    title = Attribute('Title')

    all = Attribute('All sprints, in reverse order of starting')

    def __iter__():
        """Iterate over all Sprints, in reverse time_start order."""

    def __getitem__(name):
        """Get a specific Sprint."""

    def new(owner, name, title, time_zone, time_starts, time_ends,
            summary, address=None, driver=None, home_page=None,
            mugshot=None, logo=None, icon=None):
        """Create a new sprint."""
