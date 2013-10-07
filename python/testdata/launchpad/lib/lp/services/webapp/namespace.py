# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'FormNamespaceView',
    'JsonModelNamespaceView',
    ]


from z3c.ptcompat import (
    bind_template,
    ViewPageTemplateFile,
    )
from zope.component import getMultiAdapter
from zope.interface import implements
from zope.publisher.defaultview import getDefaultViewName
from zope.publisher.interfaces.browser import IBrowserPublisher
from zope.security.proxy import removeSecurityProxy
from zope.traversing.interfaces import TraversalError
from zope.traversing.namespace import view

from lp.app.browser.launchpadform import LaunchpadFormView


class FormNamespaceView(view):
    """A namespace view to handle traversals with ++form++."""

    # Use a class variable for the template so that it does not need
    # to be created during the traverse.
    template = ViewPageTemplateFile('templates/launchpad-form-body.pt')

    def traverse(self, name, ignored):
        """Form traversal adapter.

        This adapter allows any LaunchpadFormView to simply render the
        form body.
        """
        # Note: removeSecurityProxy seems necessary here as otherwise
        # isinstance below doesn't determine the type of the context.
        context = removeSecurityProxy(self.context)

        if isinstance(context, LaunchpadFormView):
            # Note: without explicitly creating the BoundPageTemplate here
            # the view fails to render.
            context.index = bind_template(FormNamespaceView.template, context)
        else:
            raise TraversalError("The URL does not correspond to a form.")

        return self.context


class JsonModelNamespaceView(view):
    """A namespace view to handle traversals with ++model++.

    Use of this namespace is only guaranteed to work if it is fully populated
    by a view's `initialize` method.  Any objects added after the call to
    initialize will not be presented by the namespace.
    """

    implements(IBrowserPublisher)

    def traverse(self, name, ignored):
        """Model traversal adapter.

        This adapter allows any LaunchpadView to render its JSON cache.
        """
        return self

    def browserDefault(self, request):
        # Tell traversal to stop, already.
        return self, None

    def __call__(self):
        """Return the JSON cache."""
        if IBrowserPublisher.providedBy(self.context):
            view = self.context
        else:
            defaultviewname = getDefaultViewName(
                self.context, self.request)
            view = getMultiAdapter(
                (self.context, self.request), name=defaultviewname)
        if view is None:
            return
        naked_view = removeSecurityProxy(view)
        naked_view.initialize()
        cache = naked_view.getCacheJSON()
        self.request.response.setHeader('content-type', 'application/json')
        return cache
