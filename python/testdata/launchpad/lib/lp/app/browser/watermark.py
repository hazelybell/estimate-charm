# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""The watermark TALES path adapter."""

__metaclass__ = type
__all__ = [
    'WatermarkTalesAdapter',
    ]


from zope.component import queryAdapter
from zope.interface import implements
from zope.traversing.interfaces import (
    IPathAdapter,
    ITraversable,
    TraversalError,
    )

from lp.app.interfaces.headings import (
    IEditableContextTitle,
    IMajorHeadingView,
    IRootContext,
    )
from lp.services.webapp.canonicalurl import nearest_provides_or_adapted
from lp.services.webapp.escaping import structured
from lp.services.webapp.publisher import canonical_url


class WatermarkTalesAdapter:
    """Adapter for any object to get the watermark heading and image."""

    implements(ITraversable)

    def __init__(self, view):
        self._view = view
        self._context = view.context

    @property
    def root_context(self):
        return nearest_provides_or_adapted(self._context, IRootContext)

    def heading(self):
        """Return the heading text for the page.

        If the view provides `IEditableContextTitle` then the top heading is
        rendered from the view's `title_edit_widget` and is generally
        editable.

        Otherwise, if the context provides `IRootContext` then we return an
        H1, else an H2.
        """
        # Check the view; is the title editable?
        if IEditableContextTitle.providedBy(self._view):
            return self._view.title_edit_widget()
        # The title is static, but only the context's index view gets an H1.
        if IMajorHeadingView.providedBy(self._view):
            heading = structured('h1')
        else:
            heading = structured('h2')
        # If there is actually no root context, then it's a top-level
        # context-less page so Launchpad.net is shown as the branding.
        if self.root_context is None:
            title = 'Launchpad.net'
        else:
            title = self.root_context.title
        # For non-editable titles, generate the static heading.
        return structured(
            "<%(heading)s>%(title)s</%(heading)s>",
            heading=heading,
            title=title).escapedtext

    def logo(self):
        """Return the logo image for the root context."""
        adapter = queryAdapter(self.root_context, IPathAdapter, 'image')
        if (self.root_context != self._context
            and self.root_context is not None):
            return '<a href="%s">%s</a>' % (
                canonical_url(self.root_context, rootsite='mainsite'),
                adapter.logo())
        else:
            return adapter.logo()

    def traverse(self, name, furtherPath):
        if name == "heading":
            return self.heading()
        elif name == "logo":
            return self.logo()
        else:
            raise TraversalError(name)
