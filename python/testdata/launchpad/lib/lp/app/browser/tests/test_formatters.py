# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the TALES formatters."""

__metaclass__ = type

from lp.app.browser.tales import (
    ObjectFormatterAPI,
    PillarFormatterAPI,
    )
from lp.services.webapp.publisher import canonical_url
from lp.testing import (
    FakeAdapterMixin,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.views import create_view


class ObjectFormatterAPITestCase(TestCaseWithFactory, FakeAdapterMixin):

    layer = DatabaseFunctionalLayer

    def test_pagetitle_top_level(self):
        project = self.factory.makeProduct(name='fnord')
        view = create_view(project, name='+index', current_request=True)
        view.request.traversed_objects = [project, view]
        formatter = ObjectFormatterAPI(view)
        self.assertEqual('Fnord in Launchpad', formatter.pagetitle())

    def test_pagetitle_vhost(self):
        project = self.factory.makeProduct(name='fnord')
        view = create_view(project, name='+bugs', rootsite='bugs',
            current_request=True, server_url='https://bugs.launchpad.dev/')
        view.request.traversed_objects = [project, view]
        formatter = ObjectFormatterAPI(view)
        self.assertEqual('Bugs : Fnord', formatter.pagetitle())

    def test_pagetitle_lower_level_default_view(self):
        project = self.factory.makeProduct(name='fnord')
        view = create_view(
            project.development_focus, name='+index', current_request=True)
        view.request.traversed_objects = [
            project, project.development_focus, view]
        formatter = ObjectFormatterAPI(view)
        self.assertEqual('Series trunk : Fnord', formatter.pagetitle())

    def test_pagetitle_lower_level_named_view(self):
        project = self.factory.makeProduct(name='fnord')
        view = create_view(
            project.development_focus, name='+edit', current_request=True)
        view.request.traversed_objects = [
            project, project.development_focus, view]
        formatter = ObjectFormatterAPI(view)
        self.assertEqual(
            'Edit Fnord trunk series : Series trunk : Fnord',
            formatter.pagetitle())

    def test_pagetitle_last_breadcrumb_detail(self):
        project = self.factory.makeProduct(name='fnord')
        bug = self.factory.makeBug(target=project, title='bang')
        view = create_view(
            bug.bugtasks[0], name='+index', rootsite='bugs',
            current_request=True, server_url='https://bugs.launchpad.dev/')
        view.request.traversed_objects = [project, bug.bugtasks[0], view]
        formatter = ObjectFormatterAPI(view)
        self.assertEqual(
            u'%s \u201cbang\u201d : Bugs : Fnord' % bug.displayname,
            formatter.pagetitle())

    def test_pagetitle_last_breadcrumb_detail_too_long(self):
        project = self.factory.makeProduct(name='fnord')
        title = 'Bang out go the lights ' * 4
        bug = self.factory.makeBug(target=project, title=title)
        view = create_view(
            bug.bugtasks[0], name='+index', rootsite='bugs',
            current_request=True, server_url='https://bugs.launchpad.dev/')
        view.request.traversed_objects = [project, bug.bugtasks[0], view]
        formatter = ObjectFormatterAPI(view)
        detail = u'%s \u201c%s\u201d' % (bug.displayname, title)
        expected_title = u'%s...\u201d : Bugs : Fnord' % detail[0:64]
        self.assertEqual(expected_title, formatter.pagetitle())

    def test_global_css(self):
        person = self.factory.makePerson()
        view = create_view(person, name="+index")
        formatter = ObjectFormatterAPI(view)
        self.assertEqual('public', formatter.global_css())

        view = create_view(person, name="+archivesubscriptions")
        formatter = ObjectFormatterAPI(view)
        self.assertEqual(
            'private',
            formatter.global_css())

class TestPillarFormatterAPI(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    FORMATTER_CSS_CLASS = u'sprite product'

    def setUp(self):
        super(TestPillarFormatterAPI, self).setUp()
        self.product = self.factory.makeProduct()
        self.formatter = PillarFormatterAPI(self.product)
        self.product_url = canonical_url(
            self.product, path_only_if_possible=True)

    def test_link(self):
        # Calling PillarFormatterAPI.link() will return a link to the
        # current context, formatted to include a custom icon if the
        # context has one, and to display the context summary.
        link = self.formatter.link(None)
        template = u'<a href="%(url)s" class="%(css_class)s">%(summary)s</a>'
        mapping = {
            'url': self.product_url,
            'summary': self.product.displayname,
            'css_class': self.FORMATTER_CSS_CLASS,
            }
        self.assertEqual(link, template % mapping)

    def test_link_with_displayname(self):
        # Calling PillarFormatterAPI.link_with_displayname() will return
        # a link to the current context, formatted to include a custom icon
        # if the context has one, and to display a descriptive summary
        # (displayname and name of the context).
        link = self.formatter.link_with_displayname(None)
        template = (
            u'<a href="%(url)s" class="%(css_class)s">%(summary)s</a>'
            u'&nbsp;(<a href="%(url)s">%(name)s</a>)'
            )
        mapping = {
            'url': self.product_url,
            'summary': self.product.displayname,
            'name': self.product.name,
            'css_class': self.FORMATTER_CSS_CLASS,
            }
        self.assertEqual(link, template % mapping)
