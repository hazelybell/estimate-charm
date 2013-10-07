# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the POTemplate recipe view classes and templates."""

__metaclass__ = type

from lp.app.enums import ServiceUsage
from lp.services.features.testing import FeatureFixture
from lp.testing import (
    BrowserTestCase,
    celebrity_logged_in,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import (
    extract_text,
    find_tag_by_id,
    )
from lp.translations.interfaces.side import TranslationSide


def set_translations_usage(obj):
    """Set the translations_usage to LAUNCHPAD."""
    with celebrity_logged_in('admin'):
        obj.translations_usage = ServiceUsage.LAUNCHPAD


def enable_translations_on_distroseries(distroseries):
    with celebrity_logged_in('admin'):
        distroseries.hide_all_translations = False


class TestSharingInfoMixin:
    """Test display of sharing info."""

    def _makePackagingAndTemplates(self, side):
        """Create a packaging links and the templates on each side of it.

        Returns the template for the requested side.
        """
        upstream_template = self.factory.makePOTemplate()
        packaging = self.factory.makePackagingLink(
            productseries=upstream_template.productseries, in_ubuntu=True)
        ubuntu_template = self.factory.makePOTemplate(
            distroseries=packaging.distroseries,
            sourcepackagename=packaging.sourcepackagename,
            name=upstream_template.name)
        if side == TranslationSide.UPSTREAM:
            return upstream_template
        else:
            return ubuntu_template

    def makeNotSharingObject(self):
        """Create an object that is not sharing."""
        raise NotImplementedError

    NOT_SHARING_TEXT = None

    def makeSharingObject(self):
        """Create an object that is sharing."""
        raise NotImplementedError

    SHARING_TEXT = None

    def getAuthorizedUser(self, obj):
        """Get a user that is authorized to edit sharing details on obj."""
        raise NotImplementedError

    def getAuthorizedUserForProductseries(self, productseries):
        """Get a user that has Edit rights on productseries.

        If productseries is None, return an arbritrary user. Used by
        implementations of getAuthorizedUser.
        """
        logged_in_user = self.factory.makePerson()
        if productseries is not None:
            with celebrity_logged_in('admin'):
                productseries.product.owner = logged_in_user
        return logged_in_user

    def _test_sharing_information(self, obj,
                                  id_under_test, expected_text,
                                  authorized=False):
        if authorized:
            user = self.getAuthorizedUser(obj)
        else:
            user = None
        browser = self.getViewBrowser(
                obj, user=user, no_login=(not authorized),
                rootsite="translations")

        sharing_info = find_tag_by_id(browser.contents, id_under_test)
        if expected_text is None:
            self.assertIs(None, sharing_info)
        else:
            self.assertIsNot(None, sharing_info)
            self.assertTextMatchesExpressionIgnoreWhitespace(
                expected_text, extract_text(sharing_info))

    def test_not_sharing_info(self):
        self._test_sharing_information(
            self.makeNotSharingObject(),
            'sharing-information', self.NOT_SHARING_TEXT)

    def test_sharing_info(self):
        self._test_sharing_information(
            self.makeSharingObject(),
            'sharing-information', self.SHARING_TEXT)


class TestSharingDetailsLinkMixin:
    """Test that the link to the sharing details page is present.

    Requires TestSharingInfoMixin.
    """

    SHARING_DETAILS_INFO = "View sharing details"
    SHARING_DETAILS_SETUP = "Set up sharing"
    SHARING_DETAILS_EDIT = "Edit sharing details"

    def test_sharing_details_info(self):
        # For unauthorized users, the link to the sharing details page is
        # informational.
        self._test_sharing_information(
            self.makeSharingObject(),
            'sharing-details', self.SHARING_DETAILS_INFO)

    def test_sharing_details_setup(self):
        # For authorized users of not sharing objects, the link to the
        # sharing details page encourages action.
        self._test_sharing_information(
            self.makeNotSharingObject(),
            'sharing-details', self.SHARING_DETAILS_SETUP,
            authorized=True)

    def test_sharing_details_edit(self):
        # For authorized users, the link to the sharing details page is for
        # editing
        self._test_sharing_information(
            self.makeSharingObject(),
            'sharing-details', self.SHARING_DETAILS_EDIT,
            authorized=True)


class TestUpstreamPOTemplateSharingInfo(BrowserTestCase,
                                        TestSharingInfoMixin,
                                        TestSharingDetailsLinkMixin):
    """Test display of template sharing info."""

    layer = DatabaseFunctionalLayer

    def makeNotSharingObject(self):
        return self.factory.makePOTemplate()

    NOT_SHARING_TEXT = """
        This template is not sharing translations with a template in an
        Ubuntu source package."""

    def makeSharingObject(self):
        template = self._makePackagingAndTemplates(TranslationSide.UPSTREAM)
        return template

    SHARING_TEXT = """
        This template is sharing translations with .*"""

    SHARING_DETAILS_SETUP = None

    def getAuthorizedUser(self, potemplate):
        productseries = potemplate.productseries
        return self.getAuthorizedUserForProductseries(productseries)


class TestPOFileSharingInfo(BrowserTestCase, TestSharingInfoMixin):
    """Test display of POFile sharing info."""

    layer = DatabaseFunctionalLayer

    def makeNotSharingObject(self):
        return self.factory.makePOFile()

    NOT_SHARING_TEXT = None

    def makeSharingObject(self):
        template = self._makePackagingAndTemplates(TranslationSide.UPSTREAM)
        # This will also create a copy of pofile in the sharing template.
        pofile = self.factory.makePOFile(
            potemplate=template, create_sharing=True)
        return pofile

    SHARING_TEXT = """
        These translations are shared with .*"""

    def getAuthorizedUser(self, productseries):
        return None


class TestDummyPOFileSharingInfo(BrowserTestCase, TestSharingInfoMixin):
    """Test display of DummyPOFile sharing info."""

    layer = DatabaseFunctionalLayer

    def makeNotSharingObject(self):
        template = self.factory.makePOTemplate()
        return template.getDummyPOFile(self.factory.makeLanguage())

    NOT_SHARING_TEXT = None

    def makeSharingObject(self):
        template = self._makePackagingAndTemplates(TranslationSide.UPSTREAM)
        # This will also create a copy of pofile in the sharing template.
        return template.getDummyPOFile(self.factory.makeLanguage())

    SHARING_TEXT = """
        These translations are shared with .*"""


class TestUpstreamSharingInfo(BrowserTestCase,
                              TestSharingInfoMixin,
                              TestSharingDetailsLinkMixin):
    """Test display of product series sharing info."""

    layer = DatabaseFunctionalLayer

    def makeNotSharingObject(self):
        productseries = self.factory.makeProductSeries()
        set_translations_usage(productseries.product)
        return productseries

    NOT_SHARING_TEXT = """
        This project series is not sharing translations with an Ubuntu source
        package."""

    def makeSharingObject(self):
        packaging = self.factory.makePackagingLink(in_ubuntu=True)
        set_translations_usage(packaging.productseries.product)
        return packaging.productseries

    SHARING_TEXT = """
        This project series is sharing translations with .*"""

    SHARING_DETAILS_SETUP = None

    def getAuthorizedUser(self, productseries):
        return self.getAuthorizedUserForProductseries(productseries)


class TestUbuntuPOTemplateSharingInfo(BrowserTestCase,
                                      TestSharingInfoMixin,
                                      TestSharingDetailsLinkMixin):
    """Test display of template sharing info in an Ubuntu source package."""

    layer = DatabaseFunctionalLayer

    def makeNotSharingObject(self):
        template = self.factory.makePOTemplate(side=TranslationSide.UBUNTU)
        enable_translations_on_distroseries(template.distroseries)
        return template

    NOT_SHARING_TEXT = """
        This template is not sharing translations with a template in an
        upstream project."""

    def makeSharingObject(self):
        template = self._makePackagingAndTemplates(TranslationSide.UBUNTU)
        enable_translations_on_distroseries(template.distroseries)
        return template

    SHARING_TEXT = """
        This template is sharing translations with .*"""

    def getAuthorizedUser(self, potemplate):
        productseries = potemplate.sourcepackage.productseries
        return self.getAuthorizedUserForProductseries(productseries)


class TestUbuntuSharingInfo(BrowserTestCase,
                            TestSharingInfoMixin,
                            TestSharingDetailsLinkMixin):
    """Test display of source package sharing info."""

    layer = DatabaseFunctionalLayer

    def makeNotSharingObject(self):
        sourcepackage = self.factory.makeSourcePackage(
            distroseries=self.factory.makeUbuntuDistroSeries())
        enable_translations_on_distroseries(sourcepackage.distroseries)
        return sourcepackage

    NOT_SHARING_TEXT = """
        This source package is not sharing translations with an upstream
        project."""

    def makeSharingObject(self):
        packaging = self.factory.makePackagingLink(in_ubuntu=True)
        return packaging.sourcepackage

    SHARING_TEXT = """
        This source package is sharing translations with .*"""

    def getAuthorizedUser(self, sourcepackage):
        productseries = sourcepackage.productseries
        return self.getAuthorizedUserForProductseries(productseries)
