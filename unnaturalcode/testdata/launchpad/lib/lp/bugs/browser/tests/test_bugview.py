# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lazr.restful.interfaces import IJSONRequestCache
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.bugs.browser.bug import (
    BugInformationTypePortletView,
    BugView,
    )
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    login,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )


class TestBugView(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestBugView, self).setUp()
        login('test@canonical.com')
        self.bug = self.factory.makeBug()
        self.view = BugView(self.bug, LaunchpadTestRequest())

    def test_regular_attachments_dont_include_invalid_records(self):
        # As reported in bug 542274, rendering the link to bug
        # attchments that do not have a LibraryFileContent record,
        # leads to an OOPS. Ensure that such attachments do not appear
        # in BugViewMixin.regular_attachments and BugViewMixin.patches.
        self.factory.makeBugAttachment(
            bug=self.bug, description="regular attachment", is_patch=False)
        attachment = self.factory.makeBugAttachment(
            bug=self.bug, description="bad regular attachment",
            is_patch=False)
        removeSecurityProxy(attachment.libraryfile).content = None
        self.assertEqual(
            ['regular attachment'],
            [attachment['attachment'].title
             for attachment in self.view.regular_attachments])

    def test_patches_dont_include_invalid_records(self):
        # As reported in bug 542274, rendering the link to bug
        # attchments that do not have a LibraryFileContent record,
        # leads to an OOPS. Ensure that such attachments do not appear
        # in BugViewMixin.regular_attachments and BugViewMixin.patches.
        self.factory.makeBugAttachment(
            bug=self.bug, description="patch", is_patch=True)
        patch = self.factory.makeBugAttachment(
            bug=self.bug, description="bad patch", is_patch=True)
        removeSecurityProxy(patch.libraryfile).content = None
        self.assertEqual(
            ['patch'],
            [attachment['attachment'].title
             for attachment in self.view.patches])


class TestBugInformationTypePortletView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugInformationTypePortletView, self).setUp()
        login('test@canonical.com')
        self.bug = self.factory.makeBug()
        self.view = BugInformationTypePortletView(
            self.bug, LaunchpadTestRequest())

    def test_information_type(self):
        self.bug.transitionToInformationType(
            InformationType.USERDATA, self.bug.owner)
        self.assertEqual(
            self.bug.information_type.title, self.view.information_type)
        self.assertEqual(
            self.bug.information_type.description,
            self.view.information_type_description)

    def test_information_type_css_class(self):
        self.bug.transitionToInformationType(
            InformationType.USERDATA, self.bug.owner)
        self.assertEqual('sprite private', self.view.information_type_css)
        self.bug.transitionToInformationType(
            InformationType.PUBLICSECURITY, self.bug.owner)
        self.assertEqual('sprite public', self.view.information_type_css)

    def test_proprietary_excluded_for_normal_projects(self):
        # The Proprietary information type isn't in the JSON request cache for
        # normal projects without proprietary bugs configured.
        self.view.initialize()
        cache = IJSONRequestCache(self.view.request)
        expected = [
            InformationType.PUBLIC.name,
            InformationType.PUBLICSECURITY.name,
            InformationType.PRIVATESECURITY.name,
            InformationType.USERDATA.name]
        self.assertContentEqual(expected, [
            type['value']
            for type in cache.objects['information_type_data'].values()])
