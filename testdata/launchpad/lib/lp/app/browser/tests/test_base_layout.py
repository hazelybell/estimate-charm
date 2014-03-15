# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for base-layout.pt and its macros.

The base-layout master template defines macros that control the layout
of the page. Any page can use these layout options by including

    metal:use-macro='view/macro:page/<layout>"

in the root element. The template provides common layout to Launchpad.
"""

__metaclass__ = type

from BeautifulSoup import BeautifulSoup
from z3c.ptcompat import ViewPageTemplateFile

from lp.registry.interfaces.person import PersonVisibility
from lp.services.webapp.publisher import LaunchpadView
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import (
    extract_text,
    find_tag_by_id,
    )


class TestBaseLayout(TestCaseWithFactory):
    """Test the page parts provided by the base-layout.pt."""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBaseLayout, self).setUp()
        self.user = self.factory.makePerson(name='waffles')
        self.request = LaunchpadTestRequest(
            SERVER_URL='http://launchpad.dev',
            PATH_INFO='/~waffles/+layout')
        self.request.setPrincipal(self.user)
        self.context = None

    def makeTemplateView(self, layout, context=None):
        """Return a view that uses the specified layout."""

        class TemplateView(LaunchpadView):
            """A simple view to test base-layout."""
            __launchpad_facetname__ = 'overview'
            template = ViewPageTemplateFile(
                'testfiles/%s.pt' % layout.replace('_', '-'))
            page_title = 'Test base-layout: %s' % layout

        if context is None:
            self.context = self.user
        else:
            self.context = context
        return TemplateView(self.context, self.request)

    def test_base_layout_doctype(self):
        # Verify that the document is a html DOCTYPE.
        view = self.makeTemplateView('main_side')
        markup = view()
        self.assertTrue(markup.startswith('<!DOCTYPE html>'))

    def verify_base_layout_html_element(self, content):
        # The html element states the namespace and language information.
        self.assertEqual(
            'http://www.w3.org/1999/xhtml', content.html['xmlns'])
        html_tag = content.html
        self.assertEqual('en', html_tag['xml:lang'])
        self.assertEqual('en', html_tag['lang'])
        self.assertEqual('ltr', html_tag['dir'])

    def verify_base_layout_head_parts(self, view, content):
        # Verify the common head parts of every layout.
        head = content.head
        # The page's title starts with the view's page_title.
        self.assertTrue(head.title.string.startswith(view.page_title))
        # The shortcut icon for the browser chrome is provided.
        link_tag = head.link
        self.assertEqual('shortcut icon', link_tag['rel'])
        self.assertEqual('/@@/launchpad.png', link_tag['href'])
        # The template loads the common scripts.
        load_script = find_tag_by_id(head, 'base-layout-load-scripts').name
        self.assertEqual('script', load_script)

    def verify_base_layout_body_parts(self, document):
        # Verify the common body parts of every layout.
        self.assertEqual('body', document.name)
        yui_layout = document.find('div', 'yui-d0')
        self.assertTrue(yui_layout is not None)
        self.assertEqual(
            'login-logout', yui_layout.find(True, id='locationbar')['class'])
        self.assertEqual(
            'yui-main', yui_layout.find(True, id='maincontent')['class'])
        self.assertEqual(
            'invisible', document.find(True, id='help-pane')['class'])
        self.assertEqual(
            'footer', yui_layout.find(True, id='footer')['class'])

    def verify_watermark(self, document):
        # Verify the parts of a watermark.
        yui_layout = document.find('div', 'yui-d0')
        watermark = yui_layout.find(True, id='watermark')
        self.assertEqual('watermark-apps-portlet', watermark['class'])
        if self.context.is_team:
            self.assertEqual('/@@/team-logo', watermark.img['src'])
            self.assertEqual(u'\u201cWaffles\u201d team', watermark.h2.string)
        else:
            self.assertEqual('/@@/person-logo', watermark.img['src'])
            self.assertEqual('Waffles', watermark.h2.string)
        self.assertEqual('facetmenu', watermark.ul['class'])

    def test_main_side(self):
        # The main_side layout has everything.
        view = self.makeTemplateView('main_side')
        content = BeautifulSoup(view())
        self.assertIsNot(None, content.find(text=' Extra head content '))
        self.verify_base_layout_html_element(content)
        self.verify_base_layout_head_parts(view, content)
        document = find_tag_by_id(content, 'document')
        self.verify_base_layout_body_parts(document)
        classes = 'tab-overview main_side public yui3-skin-sam'.split()
        self.assertEqual(classes, document['class'].split())
        self.verify_watermark(document)
        self.assertEqual(
            'registering', document.find(True, id='registration')['class'])
        self.assertEqual(
            'Registered on 2005-09-16 by Illuminati',
            document.find(True, id='registration').string.strip(),
            )
        self.assertEndsWith(
            extract_text(document.find(True, id='maincontent')),
            'Main content of the page.')
        self.assertEqual(
            'yui-b side', document.find(True, id='side-portlets')['class'])
        self.assertEqual('form', document.find(True, id='globalsearch').name)

    def test_main_only(self):
        # The main_only layout has everything except side portlets.
        view = self.makeTemplateView('main_only')
        content = BeautifulSoup(view())
        self.verify_base_layout_html_element(content)
        self.verify_base_layout_head_parts(view, content)
        document = find_tag_by_id(content, 'document')
        self.verify_base_layout_body_parts(document)
        classes = 'tab-overview main_only public yui3-skin-sam'.split()
        self.assertEqual(classes, document['class'].split())
        self.verify_watermark(document)
        self.assertEqual(
            'registering', document.find(True, id='registration')['class'])
        self.assertEqual(None, document.find(True, id='side-portlets'))
        self.assertEqual('form', document.find(True, id='globalsearch').name)

    def test_searchless(self):
        # The searchless layout is missing side portlets and search.
        view = self.makeTemplateView('searchless')
        content = BeautifulSoup(view())
        self.verify_base_layout_html_element(content)
        self.verify_base_layout_head_parts(view, content)
        document = find_tag_by_id(content, 'document')
        self.verify_base_layout_body_parts(document)
        self.verify_watermark(document)
        classes = 'tab-overview searchless public yui3-skin-sam'.split()
        self.assertEqual(classes, document['class'].split())
        self.assertEqual(
            'registering', document.find(True, id='registration')['class'])
        self.assertEqual(None, document.find(True, id='side-portlets'))
        self.assertEqual(None, document.find(True, id='globalsearch'))

    def test_contact_support_logged_in(self):
        # The support link points to /support when the user is logged in.
        view = self.makeTemplateView('main_only')
        view._user = self.user
        content = BeautifulSoup(view())
        footer = find_tag_by_id(content, 'footer')
        link = footer.find('a', text='Contact Launchpad Support').parent
        self.assertEqual('/support', link['href'])

    def test_contact_support_anonymous(self):
        # The support link points to /feedback when the user is anonymous.
        view = self.makeTemplateView('main_only')
        view._user = None
        content = BeautifulSoup(view())
        footer = find_tag_by_id(content, 'footer')
        link = footer.find('a', text='Contact Launchpad Support').parent
        self.assertEqual('/feedback', link['href'])

    def test_user_without_launchpad_view(self):
        # When the user does not have launchpad.View on the context,
        # base-layout does not render the main slot and side slot.
        owner = self.factory.makePerson()
        with person_logged_in(owner):
            team = self.factory.makeTeam(
                displayname='Waffles', owner=owner,
                visibility=PersonVisibility.PRIVATE)
            archive = self.factory.makeArchive(private=True, owner=team)
            archive.newSubscription(self.user, registrant=owner)
        with person_logged_in(self.user):
            view = self.makeTemplateView('main_side', context=team)
            content = BeautifulSoup(view())
        self.assertIs(None, content.find(text=' Extra head content '))
        self.verify_base_layout_html_element(content)
        self.verify_base_layout_head_parts(view, content)
        document = find_tag_by_id(content, 'document')
        self.verify_base_layout_body_parts(document)
        self.verify_watermark(document)
        # These parts are unique to the case without launchpad.View.
        self.assertIsNone(document.find(True, id='side-portlets'))
        self.assertIsNone(document.find(True, id='registration'))
        self.assertEndsWith(
            extract_text(document.find(True, id='maincontent')),
            'The information in this page is not shared with you.')

    def test_user_with_launchpad_view(self):
        # Users with launchpad.View do not see the sharing explanation.
        # See the main_side, main_only, and searchless tests to know
        # what content is provides to the user who can view.
        view = self.makeTemplateView('main_side')
        content = extract_text(find_tag_by_id(view(), 'maincontent'))
        self.assertNotIn(
            'The information in this page is not shared with you.', content)
