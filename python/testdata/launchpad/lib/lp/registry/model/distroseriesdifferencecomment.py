# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""A comment/message for a difference between two distribution series."""

__metaclass__ = type

__all__ = [
    'DistroSeriesDifferenceComment',
    ]

from email.Utils import make_msgid

from storm.locals import (
    Desc,
    Int,
    Reference,
    Storm,
    )
from zope.interface import (
    classProvides,
    implements,
    )

from lp.registry.interfaces.distroseriesdifferencecomment import (
    IDistroSeriesDifferenceComment,
    IDistroSeriesDifferenceCommentSource,
    )
from lp.registry.model.sourcepackagename import SourcePackageName
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    )
from lp.services.messages.model.message import (
    Message,
    MessageChunk,
    )


class DistroSeriesDifferenceComment(Storm):
    """See `IDistroSeriesDifferenceComment`."""
    implements(IDistroSeriesDifferenceComment)
    classProvides(IDistroSeriesDifferenceCommentSource)
    __storm_table__ = 'DistroSeriesDifferenceMessage'

    id = Int(primary=True)

    distro_series_difference_id = Int(name='distro_series_difference',
                                      allow_none=False)
    distro_series_difference = Reference(
        distro_series_difference_id, 'DistroSeriesDifference.id')

    message_id = Int(name="message", allow_none=False)
    message = Reference(message_id, 'Message.id')

    @property
    def comment_author(self):
        """See `IDistroSeriesDifferenceComment`."""
        return self.message.owner

    @property
    def body_text(self):
        """See `IDistroSeriesDifferenceComment`."""
        return self.message.text_contents

    @property
    def comment_date(self):
        """See `IDistroSeriesDifferenceComment`."""
        return self.message.datecreated

    @property
    def source_package_name(self):
        """See `IDistroSeriesDifferenceCommentSource`."""
        return self.distro_series_difference.source_package_name.name

    @staticmethod
    def new(distro_series_difference, owner, comment):
        """See `IDistroSeriesDifferenceCommentSource`."""
        msgid = make_msgid('distroseriesdifference')
        message = Message(
            parent=None, owner=owner, rfc822msgid=msgid,
            subject=distro_series_difference.title)
        MessageChunk(message=message, content=comment, sequence=1)

        store = IMasterStore(DistroSeriesDifferenceComment)
        dsd_comment = DistroSeriesDifferenceComment()
        dsd_comment.distro_series_difference = distro_series_difference
        dsd_comment.message = message

        comment = store.add(dsd_comment)
        store.flush()
        return comment

    @staticmethod
    def getForDifference(distro_series_difference, id):
        """See `IDistroSeriesDifferenceCommentSource`."""
        store = IStore(DistroSeriesDifferenceComment)
        DSDComment = DistroSeriesDifferenceComment
        return store.find(
            DSDComment,
            DSDComment.distro_series_difference == distro_series_difference,
            DSDComment.id == id).one()

    @staticmethod
    def getForDistroSeries(distroseries, since=None,
                           source_package_name=None):
        """See `IDistroSeriesDifferenceCommentSource`."""
        # Avoid circular imports.
        from lp.registry.model.distroseriesdifference import (
            DistroSeriesDifference,
            )
        store = IStore(DistroSeriesDifferenceComment)
        DSD = DistroSeriesDifference
        DSDComment = DistroSeriesDifferenceComment
        conditions = [
            DSDComment.distro_series_difference_id == DSD.id,
            DSD.derived_series_id == distroseries.id,
            ]

        if source_package_name is not None:
            conditions += [
                SourcePackageName.id == DSD.source_package_name_id,
                SourcePackageName.name == source_package_name,
                ]

        if since is not None:
            older_messages = store.find(
                Message.id, Message.datecreated < since).order_by(
                    Desc(Message.datecreated))
            preceding_message = older_messages.first()
            if preceding_message is not None:
                conditions.append(DSDComment.message_id > preceding_message)

        return store.find(DSDComment, *conditions).order_by(
            DSDComment.message_id)
