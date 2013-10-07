# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for feeds generation."""

__metaclass__ = type

__all__ = [
    'IFeed',
    'IFeedEntry',
    'IFeedPerson',
    'IFeedTypedData',
    'UnsupportedFeedFormat',
    ]

from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Datetime,
    Int,
    List,
    Text,
    TextLine,
    URI,
    )


class UnsupportedFeedFormat(Exception):
    """The requested feed format is not supported."""


class IFeed(Interface):
    """Interface for feeds.

    Feeds in Launchpad are published using the Atom syndication standard, as
    defined by the proposed standard RFC 4287[1] or as HTML snippets.

    An Atom feed is an XML document consisting of a feed and zero or more
    entries.  The feed section describes the feed as a whole while the entries
    are descriptions of the individual components of that feed.  For instance
    the feed for "feeds.launchpad.net/ubuntu/announcement.atom" has metadata
    referring to the Ubuntu project and each entry in the feed represents a
    specific announcement.

    The components of IFeed are those data specifically for the feed.  The
    entry data is found in IFeedEntry.

    [1] http://tools.ietf.org/html/rfc4287
    """

    # Given the polling nature of feed readers it is important that feed data
    # be cached to minimize load on the application servers.  Each feed can
    # give hints as to how long it should be cached.  'max_age' is the
    # duration in seconds the feed should be cached before being considered
    # stale.
    max_age = Int(
        title=u"Maximum age",
        description=u"Maximum age in seconds for a feed to be cached.")

    # A feed could contain an arbitrary large number of entries, so a quantity
    # may be specified to limit the number of entries returned.
    quantity = Int(
        title=u"Quantity",
        description=u"Number of items to be returned in a feed.")

    # The title of the feed is prominently displayed in readers and should
    # succinctly identify the feed, e.g. "Latest bugs in Kubuntu".
    title = TextLine(
        title=u"Title of the feed.")

    # The URL for a feed identifies it uniquely and it should never change.
    # The latest bugs in Kubuntu is:
    # http://feeds.launchpad.net/kubuntu/latest-bugs.atom
    link_self = TextLine(
        title=u"URL for the feed.",
        description=u"The link_self URL for the feed should be "
                     "unique and permanent.")

    # The site URL refers to the top-level page for the site serving the
    # feed.  For Launchpad the site_url should be the mainsite URL,
    # i.e. http://launchpad.net.
    site_url = TextLine(
        title=u"Site URL",
        description=u"The URL for the main site of Launchpad.")

    # Feeds are intended to be machine-readable -- XML to be processed by a
    # feed reader and then, possibly, displayed.  The alternate URL is the
    # location of the human-readable equivalent for the feed.  For Ubuntu
    # announcements the alternate location is
    # http://launchpad.net/ubuntu/+announcements.
    link_alternate = TextLine(
        title=u"Alternate URL for the feed.",
        description=u"The URL to a resource that is the human-readable "
                     "equivalent of the feed.  So for: "
                     "http://feeds.launchpad.net/ubuntu/announcements.atom "
                     "the link_alternate would be: "
                     "http://launchpad.net/ubuntu/+announcements")

    # The feed ID is a permanent ID for the feed and it must be unique across
    # all time and domains.  That sounds harder than it really is.  To make
    # our IDs unique we follow the Tag ID standard proposed in RFC 4151 which
    # composes an ID using 'tag:' + domain + creation date + unique URL path.
    # So an ID for a Jokosher announcment feed would look like:
    # tag:launchpad.net,2006-5-26:/jokosher/+announcements.
    feed_id = TextLine(
        title=u"ID for the feed.",
        description=u"The <id> for a feed is permanent and globally unique. "
                     "It is constructed following RFC 4151.")

    # The feed format is either 'atom' or 'html'.
    feed_format = TextLine(
        title=u"Feed format",
        description=u"Requested feed format.  "
                     "Raises UnsupportedFeed if not supported.")

    # The logo URL points to an image identifying the feed and will likely
    # vary from one Launchpad application to another.  For example the logo
    # for bugs is:
    # http://launchpad.net/@@/bug.
    logo = TextLine(
        title=u"Logo URL",
        description=u"The URL for the feed logo.")

    # The icon URL points to an image identifying the feed.  For Launchpad
    # feeds the icon is http://launchpad.net/@@/launchpad.
    icon = TextLine(
        title=u"Icon URL",
        description=u"The URL for the feed icon.")

    # The date updated represents the last date any information in the feed
    # changed.  For instance for feed for Launchpad announcements the date
    # updated is the most recent date any of the announcements presented in
    # the feed changed.  Feed readers use the date updated one criteria as to
    # whether to fetch the feed information anew.
    date_updated = Datetime(
        title=u"Date update",
        description=u"Date of last update for the feed.")

    def getItems():
        """Get the individual items for the feed.

        Individual items will provide `IFeedEntry`.
        """

    def renderAtom():
        """Render the object as an Atom feed.

        Override this as opposed to overriding render().
        """

    def renderHTML():
        """Render the object as an html feed.

        Override this as opposed to overriding render().
        """


class IFeedEntry(Interface):
    """Interface for an entry in a feed.

    """

    # The title of the entry is prominently displayed in readers and should
    # succinctly identify the entry, e.g. "Microsoft has a majority market
    # share."
    title = TextLine(
        title=u"Title",
        description=u"The title of the entry")

    # The link alternate is an URL specifying the location of the
    # human-readable equivalent for the entry.  For a Ubuntu announcements, an
    # example alternate location is
    # http://launchpad.net/ubuntu/+announcement/4.
    link_alternate = TextLine(
        title=u"Alternate URL for the entry.",
        description=u"The URL to a resource that is the human-readable "
                     "equivalent of the entry, e.g. "
                     "http://launchpad.net/ubuntu/+announcement/1")

    # The actual content for the entry that is to be displayed in the feed
    # reader.  It may be text or marked up HTML.  It should be an
    # IFeedTypedData.
    content = Attribute(
        u"Content for the entry.  Descriptive content for the entry.  "
        "For an announcement, for example, the content "
        "is the text of the announcement.  It may be "
        "plain text or formatted html, as is done for "
        "bugs.")

    # Date the entry was created in the system, without respect to the feed.
    date_created = Datetime(
        title=u"Date Created",
        description=u"Date the entry was originally created in Launchpad.")

    # Date any aspect of the entry was changed.
    date_updated = Datetime(
        title=u"Date Updated",
        description=u"Date the entry was last updated.")

    # Date the entry became published.
    date_published = Datetime(
        title=u"Date Published",
        description=u"Date the entry was published.  "
                     "For some content this date will be the same "
                     "as the creation date.  For others, like an "
                     "announcement, it will be the date the announcement "
                     "became public.")

    # The primary authors for the entry.
    authors= Attribute(
        "A list of IFeedPerson representing the authors for the entry.")

    # People who contributed to the entry.  The line between authors and
    # contributors is fuzzy.  For a bug, all comment writers could be
    # considered authors.  Another interpretation would have the original
    # filer as the author and all commenters as contributors.  Pick an
    # approach and be consistent.
    contributors = Attribute(
        "A list of IFeedPerson representing the contributors for the entry.")

    # The logo representing the entry.
    # Not used and ignored.
    logo  = TextLine(
        title=u"Logo URL",
        description=u"The URL for the entry logo."
                     "Currently not used.")

    # The icon representing the entry.
    # Not used and ignored.
    icon  = TextLine(
        title=u"Icon URL",
        description=u"The URL for the entry icon."
                     "Currently not used.")

    # The description of the program that generated the feed.  May include
    # versioning information.  Useful for debugging purposes only.
    # Not used and ignored.
    generator = TextLine(
        title=u"The generator of the feed.",
        description=u"A description of the program generating the feed.  "
                     "Analogous to a browser USER-AGENT string.  "
                     "Currently not used.")


class IFeedTypedData(Interface):
    """Interface for typed data in a feed."""

    content_types = List(
        title=u"Content types",
        description=u"List of supported content types",
        required=True)

    content = Text(
        title=u"Content",
        description=u"Data contents",
        required=True)

    content_type = Text(
        title=u"Content type",
        description=u"The actual content type for this object.  Must be"
                     "one of those listed in content_types.",
        required=False)

    root_url = Text(
        title=u"Root URL",
        description=u"URL for the root of the site that produced the content, "
                     "i.e. 'http://code.launchpad.net'",
        required=False)

class IFeedPerson(Interface):
    """Interface for a person in a feed."""

    name = TextLine(
        title=u"Name",
        description=u"The person's name.",
        required=True)

    email = TextLine(
        title=u"Email",
        description=u"The person's email address.",
        required=False)

    uri = URI(
        title=u"URI",
        description=u"The URI for the person.",
        required=True)
