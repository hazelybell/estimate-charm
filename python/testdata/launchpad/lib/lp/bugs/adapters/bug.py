# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Resources having to do with Launchpad bugs."""

__metaclass__ = type
__all__ = [
    'bugcomment_to_entry',
    'bugtask_to_privacy',
    'convert_to_information_type',
    ]

from lazr.restful.interfaces import IEntry
from zope.component import getMultiAdapter

from lp.app.enums import InformationType


def bugcomment_to_entry(comment, version):
    """Will adapt to the bugcomment to the real IMessage.

    This is needed because navigation to comments doesn't return
    real IMessage instances but IBugComment.
    """
    return getMultiAdapter(
        (comment.bugtask.bug.messages[comment.index], version), IEntry)


def bugtask_to_privacy(bugtask):
    """Adapt the bugtask to the underlying bug (which implements IPrivacy).

    Needed because IBugTask does not implement IPrivacy.
    """
    return bugtask.bug


def convert_to_information_type(private, security_related):
    if private and security_related:
        return InformationType.PRIVATESECURITY
    elif security_related:
        return InformationType.PUBLICSECURITY
    elif private:
        return InformationType.USERDATA
    else:
        return InformationType.PUBLIC
