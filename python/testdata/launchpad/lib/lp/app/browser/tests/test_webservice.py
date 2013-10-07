# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for webservice features across Launchpad."""

__metaclass__ = type


from lazr.restful.interfaces import IFieldHTMLRenderer
from lazr.restful.utils import get_current_web_service_request
from zope.component import getMultiAdapter

from lp.app.browser.tales import format_link
from lp.registry.interfaces.product import IProduct
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import LaunchpadWebServiceCaller


class TestXHTMLRepresentations(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_person(self):
        # Test the XHTML representation of a person.
        eric = self.factory.makePerson()
        # We need something that has an IPersonChoice, a project will do.
        product = self.factory.makeProduct(owner=eric)
        field = IProduct['owner']
        request = get_current_web_service_request()
        renderer = getMultiAdapter(
            (product, field, request), IFieldHTMLRenderer)
        # The representation of a person is the same as a tales
        # PersonFormatter.
        self.assertEqual(format_link(eric), renderer(eric))

    def test_text(self):
        # Test the XHTML representation of a text field.
        text = u'\N{SNOWMAN} snowman@example.com bug 1'
        # We need something that has an IPersonChoice, a project will do.
        product = self.factory.makeProduct()
        field = IProduct['description']
        request = get_current_web_service_request()
        renderer = getMultiAdapter(
            (product, field, request), IFieldHTMLRenderer)
        # The representation is linkified html.
        self.assertEqual(
            u'<p>\N{SNOWMAN} snowman@example.com '
            '<a href="/bugs/1" class="bug-link">bug 1</a></p>',
            renderer(text))


class BaseMissingObjectWebService:
    """Base test of NotFound errors for top-level webservice objects."""

    layer = DatabaseFunctionalLayer
    object_type = None

    def test_object_not_found(self):
        """Missing top-level objects generate 404s but not OOPS."""
        webservice = LaunchpadWebServiceCaller(
            'launchpad-library', 'salgado-change-anything')
        response = webservice.get('/%s/123456789' % self.object_type)
        self.assertEqual(response.status, 404)
        self.assertEqual(response.getheader('x-lazr-oopsid'), None)


class TestMissingBranches(BaseMissingObjectWebService, TestCaseWithFactory):
    """Test NotFound for webservice branches requests."""

    object_type = 'branches'


class TestMissingBugTrackers(
    BaseMissingObjectWebService, TestCaseWithFactory):
    """Test NotFound for webservice bug_trackers requests."""

    object_type = 'bug_trackers'


class TestMissingBugs(BaseMissingObjectWebService, TestCaseWithFactory):
    """Test NotFound for webservice bugs requests."""

    object_type = 'bugs'


class TestMissingBuilders(BaseMissingObjectWebService, TestCaseWithFactory):
    """Test NotFound for webservice builders requests."""

    object_type = 'builders'


class TestMissingCountries(BaseMissingObjectWebService, TestCaseWithFactory):
    """Test NotFound for webservice countries requests."""

    object_type = 'countries'


class TestMissingCves(BaseMissingObjectWebService, TestCaseWithFactory):
    """Test NotFound for webservice cves requests."""

    object_type = 'cves'


class TestMissingDistributions(
    BaseMissingObjectWebService, TestCaseWithFactory):
    """Test NotFound for webservice distributions requests."""

    object_type = 'distributions'


class TestMissingLanguages(BaseMissingObjectWebService, TestCaseWithFactory):
    """Test NotFound for webservice launguages requests."""

    object_type = 'languages'


class TestMissingPackagesets(
    BaseMissingObjectWebService, TestCaseWithFactory):
    """Test NotFound for webservice packagesets requests."""

    object_type = 'packagesets'


class TestMissingPeople(BaseMissingObjectWebService, TestCaseWithFactory):
    """Test NotFound for webservice branches requests."""

    object_type = 'people'


class TestMissingProjectGroups(
    BaseMissingObjectWebService, TestCaseWithFactory):
    """Test NotFound for webservice project_groups requests."""

    object_type = 'project_groups'


class TestMissingProjects(BaseMissingObjectWebService, TestCaseWithFactory):
    """Test NotFound for webservice projects requests."""

    object_type = 'projects'


class TestMissingQuestions(BaseMissingObjectWebService, TestCaseWithFactory):
    """Test NotFound for webservice questions requests."""

    object_type = 'questions'


class TestMissingTemporaryBlobs(
    BaseMissingObjectWebService, TestCaseWithFactory):
    """Test NotFound for webservice temporary_blobs requests."""

    object_type = 'temporary_blobs'


class TestMissingTranslationGroups(
    BaseMissingObjectWebService, TestCaseWithFactory):
    """Test NotFound for webservice translation_groups requests."""

    object_type = 'translation_groups'


class TestMissingTranslationImportQueueEntries(
    BaseMissingObjectWebService, TestCaseWithFactory):
    """Test NotFound for webservice translation_import_queue_entries requests.
    """

    object_type = 'translation_import_queue_entries'
