# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lp.bugs.publisher import BugsLayer
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.views import create_view


class TestBugTargetTags(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugTargetTags, self).setUp()
        self.project = self.factory.makeProject()
        self.target_product = self.factory.makeProduct(project=self.project)

    def test_no_tags(self):
        self.factory.makeBug(target=self.target_product)
        view = create_view(
            self.project,
            name="+bugtarget-portlet-tags-content",
            layer=BugsLayer)
        self.assertEqual([], [tag['tag'] for tag in view.tags_cloud_data])

    def test_tags(self):
        self.factory.makeBug(target=self.target_product, tags=['foo'])
        view = create_view(
            self.project,
            name="+bugtarget-portlet-tags-content",
            layer=BugsLayer)
        self.assertEqual(
            [u'foo'],
            [tag['tag'] for tag in view.tags_cloud_data])

    def test_tags_order(self):
        """Test that the tags are ordered by most used first"""
        self.factory.makeBug(target=self.target_product, tags=['tag-last'])
        for counter in range(0, 2):
            self.factory.makeBug(
                target=self.target_product, tags=['tag-middle'])
        for counter in range(0, 3):
            self.factory.makeBug(
                target=self.target_product, tags=['tag-first'])
        view = create_view(
            self.project,
            name="+bugtarget-portlet-tags-content",
            layer=BugsLayer)
        self.assertEqual(
            [u'tag-first', u'tag-middle', u'tag-last'],
            [tag['tag'] for tag in view.tags_cloud_data])
