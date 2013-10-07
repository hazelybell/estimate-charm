# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""A simple display widget that renders like the tal expression fmt:link."""

__metaclass__ = type
__all__ = [
    'LinkWidget',
    ]

from zope.component import queryAdapter
from zope.formlib.widget import DisplayWidget
from zope.traversing.interfaces import IPathAdapter


class LinkWidget(DisplayWidget):
    """Renders using the tal formatter for fmt:link.

    Used by specifying `custom_widget('fieldname', LinkWidget)`.
    """

    def __init__(self, context, request, *ignored):
        """Ignores extra params such as vocabularies."""
        super(DisplayWidget, self).__init__(context, request)

    def __call__(self):
        adapter = queryAdapter(self._data, IPathAdapter, 'fmt')
        return adapter.link('')
