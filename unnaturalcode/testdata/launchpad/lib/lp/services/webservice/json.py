# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Additional JSON serializer for the web service."""

__metaclass__ = type
__all__ = [
    'StrJSONSerializer',
    ]


from lazr.restful.interfaces import IJSONPublishable
from zope.interface import implements


class StrJSONSerializer:
    """Simple JSON serializer that simply str() it's context. """
    implements(IJSONPublishable)

    def __init__(self, context):
        self.context = context

    def toDataForJSON(self, media_type):
        return str(self.context)
