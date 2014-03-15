# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for launchpad classes."""

__metaclass__ = type

from zope.security.interfaces import (
    Forbidden,
    ForbiddenAttribute,
    Unauthorized,
    )

from lp.app.interfaces.launchpad import IPrivacy
from lp.app.model.launchpad import Privacy
from lp.testing import TestCase
from lp.testing.layers import FunctionalLayer


class PrivacyTestCase(TestCase):

    layer = FunctionalLayer

    def test_init(self):
        thing = ['any', 'thing']
        privacy = Privacy(thing, True)
        self.assertIs(True, IPrivacy.providedBy(privacy))
        self.assertIs(True, privacy.private)
        privacy = Privacy(thing, False)
        self.assertIs(False, privacy.private)


class ExceptionPrivacyTestCase(TestCase):

    layer = FunctionalLayer

    def test_exception(self):
        privacy = IPrivacy(IndexError('test'))
        self.assertIs(True, IPrivacy.providedBy(privacy))
        self.assertIs(False, privacy.private)

    def test_unauthorized(self):
        privacy = IPrivacy(Unauthorized('test'))
        self.assertIs(True, IPrivacy.providedBy(privacy))
        self.assertIs(True, privacy.private)

    def test_forbidden(self):
        privacy = IPrivacy(Forbidden('test'))
        self.assertIs(True, IPrivacy.providedBy(privacy))
        self.assertIs(True, privacy.private)

    def test_forbidden_attribute(self):
        privacy = IPrivacy(ForbiddenAttribute('test'))
        self.assertIs(True, IPrivacy.providedBy(privacy))
        self.assertIs(True, privacy.private)
