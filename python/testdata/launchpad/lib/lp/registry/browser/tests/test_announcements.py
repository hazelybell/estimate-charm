# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for +announcement views."""

__metaclass__ = type

from datetime import datetime

from lxml import html
from pytz import utc

from lp.testing import (
    normalize_whitespace,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.views import create_initialized_view


class TestAnnouncement(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def test_announcement_info(self):
        product = self.factory.makeProduct(displayname=u"Foo")
        announcer = self.factory.makePerson(displayname=u"Bar Baz")
        announcement = product.announce(announcer, "Hello World")
        view = create_initialized_view(announcement, "+index")
        root = html.fromstring(view())
        [reg_para] = root.cssselect("p.registered")
        self.assertEqual(
            "Written for Foo by Bar Baz",
            normalize_whitespace(reg_para.text_content()))

    def test_announcement_info_with_publication_date(self):
        product = self.factory.makeProduct(displayname=u"Foo")
        announcer = self.factory.makePerson(displayname=u"Bar Baz")
        announced = datetime(2007, 01, 12, tzinfo=utc)
        announcement = product.announce(
            announcer, "Hello World", publication_date=announced)
        view = create_initialized_view(announcement, "+index")
        root = html.fromstring(view())
        [reg_para] = root.cssselect("p.registered")
        self.assertEqual(
            "Written for Foo by Bar Baz on 2007-01-12",
            normalize_whitespace(reg_para.text_content()))
