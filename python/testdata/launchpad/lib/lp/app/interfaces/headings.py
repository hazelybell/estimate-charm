# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Marker interfaces that define how to generate headings for a view."""

__metaclass__ = type
__all__ = [
    'IEditableContextTitle',
    'IMajorHeadingView',
    'IRootContext',
    ]


from zope.interface import (
    Attribute,
    Interface,
    )


class IRootContext(Interface):
    """Something that is an object off the Launchpad root."""

    title = Attribute('The title of the root context object.')


class IMajorHeadingView(Interface):
    """This view's page should get a major heading (i.e. H1)."""


class IEditableContextTitle(Interface):
    """Interface specifying that the context has an editable title."""

    def title_edit_widget():
        """Return the HTML of the editable title widget."""
