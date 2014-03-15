# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""`IFAQTarget` browser views."""

__metaclass__ = type

__all__ = [
    'FAQTargetNavigationMixin',
    'FAQCreateView',
    ]

from lp import _
from lp.answers.interfaces.faq import IFAQ
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadFormView,
    )
from lp.app.errors import NotFoundError
from lp.app.widgets.textwidgets import TokensTextWidget
from lp.services.webapp import (
    canonical_url,
    stepthrough,
    )


class FAQTargetNavigationMixin:
    """Navigation mixin for `IFAQTarget`."""

    @stepthrough('+faq')
    def traverse_faq(self, name):
        """Return the FAQ by ID."""
        try:
            id_ = int(name)
        except ValueError:
            raise NotFoundError(name)
        return self.context.getFAQ(id_)


class FAQCreateView(LaunchpadFormView):
    """A view to create a new FAQ."""

    schema = IFAQ
    label = _('Create a new FAQ')
    field_names = ['title', 'keywords', 'content']

    custom_widget('keywords', TokensTextWidget)

    @property
    def page_title(self):
        return 'Create a FAQ for %s' % self.context.displayname

    @action(_('Create'), name='create')
    def create__action(self, action, data):
        """Creates the FAQ."""
        faq = self.context.newFAQ(
            self.user, data['title'], data['content'],
            keywords=data['keywords'])
        self.next_url = canonical_url(faq)
