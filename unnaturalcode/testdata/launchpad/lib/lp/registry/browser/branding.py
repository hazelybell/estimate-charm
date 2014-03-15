# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Browser views for items that can be displayed as images."""

__metaclass__ = type

__all__ = [
    'BrandingChangeView',
    ]

from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadEditFormView,
    )
from lp.app.widgets.image import ImageChangeWidget
from lp.services.webapp import canonical_url


class BrandingChangeView(LaunchpadEditFormView):
    """This is a base class that MUST be subclassed for each object, because
    each object will have a different description for its branding that is
    part of its own interface.

    For each subclass, specify the schema ("IPerson") and the field_names
    (some subset of icon, logo, mugshot).
    """

    @property
    def label(self):
        return ('Change the images used to represent %s in Launchpad'
                % self.context.displayname)

    page_title = "Change branding"

    custom_widget('icon', ImageChangeWidget, ImageChangeWidget.EDIT_STYLE)
    custom_widget('logo', ImageChangeWidget, ImageChangeWidget.EDIT_STYLE)
    custom_widget('mugshot', ImageChangeWidget, ImageChangeWidget.EDIT_STYLE)

    @action("Change Branding", name='change')
    def change_action(self, action, data):
        self.updateContextFromData(data)

    @property
    def next_url(self):
        return canonical_url(self.context)

    cancel_url = next_url
