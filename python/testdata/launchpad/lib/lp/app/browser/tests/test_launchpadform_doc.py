# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import doctest
import unittest

from zope.formlib.interfaces import (
    IDisplayWidget,
    IInputWidget,
    )
from zope.interface import (
    directlyProvides,
    implements,
    )

from lp.app.browser.launchpadform import LaunchpadFormView
from lp.services.webapp.interfaces import (
    ICheckBoxWidgetLayout,
    IMultiLineWidgetLayout,
    ISingleLineWidgetLayout,
    )
from lp.testing.layers import FunctionalLayer


class LaunchpadFormTest(unittest.TestCase):

    layer = FunctionalLayer

    def test_formLayout(self):
        # Verify that exactly one of isSingleLineLayout(), isMultiLineLayout()
        # and isCheckBoxLayout() return True for particular widget.
        #
        # If more than one returns True, then that widget may get included
        # in the form twice.
        form = LaunchpadFormView(None, None)
        class FakeWidget:
            pass
        widget = FakeWidget()
        form.widgets = {'widget': widget}
        # test every combination of the three interfaces:
        for use_single_line in [False, True]:
            for use_multi_line in [False, True]:
                for use_checkbox in [False, True]:
                    provides = []
                    if use_single_line:
                        provides.append(ISingleLineWidgetLayout)
                    if use_multi_line:
                        provides.append(IMultiLineWidgetLayout)
                    if use_checkbox:
                        provides.append(ICheckBoxWidgetLayout)
                    directlyProvides(widget, *provides)

                    # Now count how many of the is* functions return True:
                    count = 0
                    if form.isSingleLineLayout('widget'):
                        count += 1
                    if form.isMultiLineLayout('widget'):
                        count += 1
                    if form.isCheckBoxLayout('widget'):
                        count += 1

                    self.assertEqual(count, 1,
                                     'Expected count of 1 for %r.  Got %d'
                                     % (provides, count))

    def test_showOptionalMarker(self):
        """Verify a field marked .for_display has no (Optional) marker."""
        # IInputWidgets have an (Optional) marker if they are not required.
        form = LaunchpadFormView(None, None)
        class FakeInputWidget:
            implements(IInputWidget)
            def __init__(self, required):
                self.required = required
        form.widgets = {'widget': FakeInputWidget(required=False)}
        self.assertTrue(form.showOptionalMarker('widget'))
        # Required IInputWidgets have no (Optional) marker.
        form.widgets = {'widget': FakeInputWidget(required=True)}
        self.assertFalse(form.showOptionalMarker('widget'))
        # IDisplayWidgets have no (Optional) marker, regardless of whether
        # they are required or not, since they are read only.
        class FakeDisplayWidget:
            implements(IDisplayWidget)
            def __init__(self, required):
                self.required = required
        form.widgets = {'widget': FakeDisplayWidget(required=False)}
        self.assertFalse(form.showOptionalMarker('widget'))
        form.widgets = {'widget': FakeDisplayWidget(required=True)}
        self.assertFalse(form.showOptionalMarker('widget'))


def doctest_custom_widget_with_setUpFields_override():
    """As a regression test, it is important to note that the custom_widget
    class advisor should still work when setUpFields is overridden.  For
    instance, consider this custom widget and view:

        >>> from zope.formlib.interfaces import IDisplayWidget, IInputWidget
        >>> from zope.interface import directlyProvides, implements
        >>> from lp.app.browser.launchpadform import (
        ...     LaunchpadFormView, custom_widget)
        >>> from zope.schema import Bool
        >>> from zope.publisher.browser import TestRequest
        >>> from zope.formlib import form

        >>> class CustomStubWidget:
        ...     implements(IInputWidget)
        ...     # The methods below are the minimal necessary for widget
        ...     # initialization.
        ...     def __init__(self, field, request):
        ...         self.field, self.request = field, request
        ...     def setPrefix(self, prefix):
        ...         self.name = '.'.join((prefix, self.field.__name__))
        ...     def hasInput(self):
        ...         return False
        ...     def setRenderedValue(self, value):
        ...         self.value = value
        ...
        >>> class CustomView(LaunchpadFormView):
        ...     custom_widget('my_bool', CustomStubWidget)
        ...     def setUpFields(self):
        ...         self.form_fields = form.Fields(Bool(__name__='my_bool'))
        ...

    The custom setUpFields adds a field dynamically. Then setUpWidgets will
    use the custom widget for the field. We simply call setUpFields and
    setUpWidgets explicitly here for ease of testing, though normally they
    are called by LaunchpadFormView.initialize.

        >>> view = CustomView(None, TestRequest())
        >>> view.setUpFields()
        >>> view.setUpWidgets()
        >>> isinstance(view.widgets['my_bool'], CustomStubWidget)
        True
    """


def test_suite():
    return unittest.TestSuite((
        unittest.TestLoader().loadTestsFromName(__name__),
        doctest.DocTestSuite()
        ))
