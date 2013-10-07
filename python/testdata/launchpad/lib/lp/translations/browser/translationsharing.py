# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Views and mixins to use for translation sharing."""

__metaclass__ = type

__all__ = [
    'TranslationSharingDetailsMixin',
    ]


from lp.services.webapp import canonical_url
from lp.services.webapp.authorization import check_permission


class TranslationSharingDetailsMixin:
    """Mixin for views that need to display translation details link.

    View using this need to implement is_sharing, can_edit_sharing_details
    and getTranslationTarget().
    """

    def is_sharing(self):
        """Whether this object is sharing translations or not."""
        raise NotImplementedError

    def getTranslationSourcePackage(self):
        """Return the sourcepackage or None."""
        raise NotImplementedError

    def sharing_details(self):
        """Construct the link to the sharing details page."""
        tag_template = (
            '<a class="sprite %(icon)s" id="sharing-details"'
            ' href="%(href)s">%(text)s</a>')

        sourcepackage = self.getTranslationSourcePackage()
        if sourcepackage is None:
            return ""
        productseries = sourcepackage.productseries
        can_edit_upstream = (
            productseries is None or
            check_permission('launchpad.Edit', productseries))
        if can_edit_upstream:
            icon = 'edit'
            if self.is_sharing():
                text = "Edit sharing details"
            else:
                text = "Set up sharing"
        else:
            icon = 'info'
            text = "View sharing details"
        href = canonical_url(
            sourcepackage,
            rootsite='translations',
            view_name='+sharing-details')
        return tag_template % dict(icon=icon, text=text, href=href)
