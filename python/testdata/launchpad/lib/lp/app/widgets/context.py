# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

#
# Code to create a widget that encodes the value of the request context into
# the form.
#

__metaclass__ = type

from zope.interface import (
    implements,
    Interface,
    )

from lp.app.widgets.owner import RequestWidget


class IContextWidget(Interface):
    """The interface for a ContextWidget. A ContextWidget provides a hidden
    field that equates to the context object. So, for example, say you are
    creating a form to add a new CVE reference on a bug, you can provide the
    bug to the form using a contextWidget. It's similar to the OwnerWidget,
    which provides the user to the form as a field. This just provides the
    context object that the form was rendered off."""
    pass


class ContextWidget(RequestWidget):

    implements(IContextWidget)
    def __init__(self, context, vocabulary, request):
        RequestWidget.__init__(self, context, request)

    def getInputValue(self):
        return self.context.context.id

