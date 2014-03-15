# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'CustomLanguageCodeAddView',
    'CustomLanguageCodeBreadcrumb',
    'CustomLanguageCodesIndexView',
    'CustomLanguageCodeRemoveView',
    'CustomLanguageCodeView',
    'HasCustomLanguageCodesNavigation',
    'HasCustomLanguageCodesTraversalMixin',
    ]


import re

from lazr.restful.utils import smartquote

from lp.app.browser.launchpadform import (
    action,
    LaunchpadFormView,
    )
from lp.app.errors import NotFoundError
from lp.services.webapp import (
    canonical_url,
    LaunchpadView,
    Navigation,
    stepthrough,
    )
from lp.services.webapp.breadcrumb import Breadcrumb
from lp.services.webapp.escaping import structured
from lp.translations.interfaces.customlanguagecode import (
    ICustomLanguageCode,
    IHasCustomLanguageCodes,
    )

# Regex for allowable custom language codes.
CODE_PATTERN = "[a-zA-Z0-9_-]+$"


def check_code(custom_code):
    """Is this custom language code well-formed?"""
    return re.match(CODE_PATTERN, custom_code) is not None


class CustomLanguageCodeBreadcrumb(Breadcrumb):
    """Breadcrumb for a `CustomLanguageCode`."""

    @property
    def text(self):
        return smartquote(
            'Custom language code "%s"' % self.context.language_code)


class CustomLanguageCodesIndexView(LaunchpadView):
    """Listing of `CustomLanguageCode`s for a given context."""

    page_title = "Custom language codes"

    @property
    def label(self):
        return "Custom language codes for %s" % self.context.displayname


class CustomLanguageCodeAddView(LaunchpadFormView):
    """Create a new custom language code."""
    schema = ICustomLanguageCode
    field_names = ['language_code', 'language']
    page_title = "Add new code"

    create = False

    @property
    def label(self):
        return (
            "Add a custom language code for %s" % self.context.displayname)

    def validate(self, data):
        self.language_code = data.get('language_code')
        self.language = data.get('language')
        if self.language_code is not None:
            self.language_code = self.language_code.strip()

        if not self.language_code:
            self.setFieldError('language_code', "No code was entered.")
            return

        if not check_code(self.language_code):
            self.setFieldError('language_code', "Invalid language code.")
            return

        existing_code = self.context.getCustomLanguageCode(self.language_code)
        if existing_code is not None:
            if existing_code.language != self.language:
                self.setFieldError(
                    'language_code',
                    structured(
                        "There already is a custom language code '%s'.",
                            self.language_code))
                return
        else:
            self.create = True

    @action('Add', name='add')
    def add_action(self, action, data):
        if self.create:
            self.context.createCustomLanguageCode(
                self.language_code, self.language)

    @property
    def action_url(self):
        return canonical_url(
            self.context, rootsite='translations',
            view_name='+add-custom-language-code')

    @property
    def next_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(
            self.context, rootsite='translations',
            view_name='+custom-language-codes')

    cancel_url = next_url


class CustomLanguageCodeView(LaunchpadView):
    schema = ICustomLanguageCode

    @property
    def label(self):
        target_displayname = self.context.translation_target.displayname
        return smartquote(
            'Custom language code "%s" for %s' % (
                self.context.language_code, target_displayname))


class CustomLanguageCodeRemoveView(LaunchpadFormView):
    """View for removing a `CustomLanguageCode`."""
    schema = ICustomLanguageCode
    field_names = []

    page_title = "Remove"

    @property
    def code(self):
        """The custom code."""
        return self.context.language_code

    @property
    def label(self):
        return "Remove custom language code '%s'" % self.code

    @action("Remove")
    def remove(self, action, data):
        """Remove this `CustomLanguageCode`."""
        code = self.code
        self.context.translation_target.removeCustomLanguageCode(self.context)
        self.request.response.addInfoNotification(
            "Removed custom language code '%s'." % code)

    @property
    def next_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(
            self.context.translation_target, rootsite='translations',
            view_name='+custom-language-codes')

    cancel_url = next_url


class HasCustomLanguageCodesTraversalMixin:
    """Navigate from an `IHasCustomLanguageCodes` to a `CustomLanguageCode`.
    """

    @stepthrough('+customcode')
    def traverseCustomCode(self, name):
        """Traverse +customcode URLs."""
        if not check_code(name):
            raise NotFoundError("Invalid custom language code.")

        return self.context.getCustomLanguageCode(name)


class HasCustomLanguageCodesNavigation(Navigation,
                                       HasCustomLanguageCodesTraversalMixin):
    """Generic navigation for `IHasCustomLanguageCodes`."""
    usedfor = IHasCustomLanguageCodes
