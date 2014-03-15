# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""News item interfaces."""

__metaclass__ = type

__all__ = [
    'IAnnouncement',
    'IHasAnnouncements',
    'IMakesAnnouncements',
    'IAnnouncementSet',
    ]

from zope.interface import (
    Attribute,
    Interface,
    )


class IHasAnnouncements(Interface):
    """A mixin class for pillars that have announcements."""

    def getAnnouncement(id):
        """Return the requested announcement."""

    def getAnnouncements(limit=5, published_only=True):
        """Return a list of announcements visible to this user.

            :param limit: restrict the results to `limit` announcements.  If
                None is used as the limit then a full list is returned.

            :param published_only: when True the list will include only
                published announcements.
        """


class IMakesAnnouncements(IHasAnnouncements):
    """An interface for pillars that can make announcements."""

    def announce(user, title, summary=None, url=None,
                 publication_date=None):
        """Create a Announcement for this project.

        The user is the person making the announcement. The publication date
        is either None (a future date), or a specified datetime.
        """


class IAnnouncement(Interface):
    """An Announcement.

    An announcement is a piece of news which has a headline, summary, and
    possibly a URL where further information can be found. It also has
    attributes that determine its publishing state.
    """

    # Attributes relating to the lifecycle of the Announcement.
    id = Attribute("The unique ID of this announcement")
    date_created = Attribute("The date this announcement was registered")
    registrant = Attribute("The person who registered this announcement")
    date_last_modified = Attribute(
        "The date this announcement was last modified, if ever.")
    date_updated = Attribute(
        "The date created, or the date last modified, if ever")

    # The potential pillars to which the Announcement could belong, of which
    # only 1 should not be None.
    product = Attribute("The product for this announcement.")
    project = Attribute("The project for this announcement.")
    distribution = Attribute("The distribution for this announcement.")

    target = Attribute("The pillar to which this announcement belongs.")

    # The core details of the announcement.
    title = Attribute("The headline of your announcement.")
    summary = Attribute("A single-paragraph summary of the announcement.")
    url = Attribute("The web location of your announcement.")
    date_announced = Attribute(
        "The date the announcement will be published, or the date it was "
        "published if it is in the past. The announcement will only be "
        "published on that date if the 'active' flag is True.")
    active = Attribute("Whether or not this announcement can be published.")

    # Emergent properties of the announcement.
    future = Attribute("Whether or not this announcement is yet public.")
    published = Attribute(
        "Whether or not this announcement is published. This is different "
        "to IAnnouncement.future because it factors in retraction, while "
        "IAnnouncement.future looks only at the date_announced.")

    def modify(title, summary, url):
        """Update the details of the announcement. This will record the
        date_last_modified."""

    def retarget(target):
        """Retarget the announcement to a new project."""

    def retract():
        """Take this announcement off any public web pages and RSS feeds."""

    def setPublicationDate(publication_date):
        """Set the publication date. The value passed is either:

          None: publish it at some future date,
          A datetime: publish it on the date given.
        """

    def destroySelf():
        """Remove this announcement permanently."""


class IAnnouncementSet(IHasAnnouncements):
    """The set of all public announcements."""

    displayname = Attribute("Launchpad")
    title = Attribute("Launchpad title")


