# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'AlreadyRegisteredError',
    'BranchPopupWidget',
    'NoProductError',
    ]

import sys

from lazr.uri import (
    InvalidURIError,
    URI,
    )
from zope.component import getUtility
from zope.formlib.interfaces import ConversionError

from lp.app.browser.tales import BranchFormatterAPI
from lp.app.validators import LaunchpadValidationError
from lp.app.widgets.popup import VocabularyPickerWidget
from lp.code.enums import BranchType
from lp.code.interfaces.branch import IBranch
from lp.code.interfaces.branchlookup import IBranchLookup
from lp.code.interfaces.branchnamespace import get_branch_namespace
from lp.services.webapp.escaping import structured
from lp.services.webapp.interfaces import ILaunchBag


class AlreadyRegisteredError(Exception):
    """Raised when we try to register an already-registered branch."""


class NoProductError(Exception):
    """Raised when we need a product and can't find one."""


class BranchPopupWidget(VocabularyPickerWidget):
    """Custom popup widget for choosing branches."""

    displayWidth = '35'

    def getBranchNameFromURL(self, url):
        """Return a branch name based on `url`.

        The name is based on the last path segment of the URL. If there is
        already another branch of that name on the product, then we'll try to
        find a unique name by appending numbers.
        """
        return URI(url).ensureNoSlash().path.split('/')[-1]

    def getPerson(self):
        """Return the person in the context, if any."""
        return getUtility(ILaunchBag).user

    def getProduct(self):
        """Return the product in the context, if there is one."""
        return getUtility(ILaunchBag).product

    def makeBranchFromURL(self, url):
        """Make a mirrored branch for `url`.

        The product and owner of the branch are derived from information in
        the launchbag. The name of the branch is derived from the last segment
        of the URL and is guaranteed to be unique for the product.

        :param url: The URL to mirror.
        :return: An `IBranch`.
        """
        # XXX: JonathanLange 2008-12-08 spec=package-branches: This method
        # needs to be rewritten to get the sourcepackage and distroseries out
        # of the launch bag.
        url = unicode(URI(url).ensureNoSlash())
        if getUtility(IBranchLookup).getByUrl(url) is not None:
            raise AlreadyRegisteredError('Already a branch for %r' % url)
        # Make sure the URL is valid.
        IBranch['url'].validate(url)
        product = self.getProduct()
        if product is None:
            raise NoProductError("Could not find product in LaunchBag.")
        owner = self.getPerson()
        name = self.getBranchNameFromURL(url)
        namespace = get_branch_namespace(person=owner, product=product)
        branch = namespace.createBranchWithPrefix(
            BranchType.MIRRORED, name, owner, url=url)
        branch.requestMirror()
        self.request.response.addNotification(
            structured('Registered %s' %
                       BranchFormatterAPI(branch).link(None)))
        return branch

    def _toFieldValue(self, form_input):
        try:
            return super(BranchPopupWidget, self)._toFieldValue(form_input)
        except ConversionError:
            # Save the initial error so we can re-raise it later.
            exc_class, exc_obj, exc_tb = sys.exc_info()

            # Try to register a branch, assuming form_input is a URL.
            try:
                return self.makeBranchFromURL(form_input)
            except (InvalidURIError, NoProductError, AlreadyRegisteredError,
                    LaunchpadValidationError):
                # If it's not a URL or we can't figure out a product, then we
                # re-raise the initial error.
                raise exc_class, exc_obj, exc_tb
