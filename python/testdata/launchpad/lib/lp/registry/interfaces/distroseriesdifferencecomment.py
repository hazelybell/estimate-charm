# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Distribution series difference messages."""

__metaclass__ = type
__all__ = [
    'IDistroSeriesDifferenceComment',
    'IDistroSeriesDifferenceCommentSource',
    ]


from lazr.restful.declarations import (
    export_as_webservice_entry,
    exported,
    )
from lazr.restful.fields import Reference
from zope.interface import Interface
from zope.schema import (
    Datetime,
    Int,
    Text,
    TextLine,
    )

from lp import _
from lp.registry.interfaces.distroseriesdifference import (
    IDistroSeriesDifference,
    )
from lp.services.messages.interfaces.message import IMessage


class IDistroSeriesDifferenceComment(Interface):
    """A comment for a distroseries difference record."""
    export_as_webservice_entry()

    id = Int(title=_('ID'), required=True, readonly=True)

    distro_series_difference = Reference(
        IDistroSeriesDifference, title=_("Distro series difference"),
        required=True, readonly=True, description=_(
            "The distro series difference to which this message "
            "belongs."))
    message = Reference(
        IMessage, title=_("Message"), required=True, readonly=True,
        description=_("A comment about this difference."))

    body_text = exported(Text(
        title=_("Comment text"), readonly=True, description=_(
            "The comment text for the related distro series difference.")))

    comment_author = exported(Reference(
        # Really IPerson.
        Interface, title=_("The author of the comment."),
        readonly=True))

    comment_date = exported(Datetime(
        title=_('Comment date.'), readonly=True))

    source_package_name = exported(TextLine(
        title=_("Source package name"), required=True, readonly=True,
        description=_(
            "Name of the source package that this comment is for.")))


class IDistroSeriesDifferenceCommentSource(Interface):
    """A utility of this interface can be used to create comments."""

    def new(distro_series_difference, owner, comment):
        """Create a new comment on a distro series difference.

        :param distro_series_difference: The distribution series difference
            that is being commented on.
        :param owner: The person making the comment.
        :param comment: The comment.
        :return: A new `DistroSeriesDifferenceComment` object.
        """

    def getForDifference(distro_series_difference, id):
        """Return the `IDistroSeriesDifferenceComment` with the given id."""

    def getForDistroSeries(distroseries, since=None):
        """Get comments for `distroseries` (since `since` if given).

        :param distroseries: The `DistroSeries` to find comments for.
        :param since: A timestamp.  No comments older than this will be
            returned.
        :return: A result set of `DistroSeriesDifferenceComment`s, ordered
            from oldest to newest.
        """
