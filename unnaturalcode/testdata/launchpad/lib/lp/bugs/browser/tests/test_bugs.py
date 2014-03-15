# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version (see the file LICENSE).

"""Unit tests for bug set and bug application views."""

__metaclass__ = type

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.bugs.interfaces.bugtask import BugTaskStatus
from lp.bugs.interfaces.malone import IMaloneApplication
from lp.bugs.publisher import BugsLayer
from lp.registry.enums import BugSharingPolicy
from lp.registry.interfaces.product import License
from lp.services.webapp.publisher import canonical_url
from lp.testing import (
    celebrity_logged_in,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import find_tag_by_id
from lp.testing.views import create_initialized_view


class TestMaloneView(TestCaseWithFactory):
    """Test the MaloneView for the Bugs application."""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestMaloneView, self).setUp()
        self.application = getUtility(IMaloneApplication)

    def test_redirect_id_success(self):
        # The view redirects to the bug when it is found.
        bug = self.factory.makeBug()
        form = dict(id=str(bug.id))
        view = create_initialized_view(
            self.application, name='+index', layer=BugsLayer, form=form)
        self.assertEqual(None, view.error_message)
        self.assertEqual(
            canonical_url(bug), view.request.response.getHeader('Location'))

    def test_redirect_name_success(self):
        # The view redirects to the bug when it is found.
        bug = self.factory.makeBug()
        with celebrity_logged_in('admin'):
            bug.name = 'bingo'
        form = dict(id='bingo')
        view = create_initialized_view(
            self.application, name='+index', layer=BugsLayer, form=form)
        self.assertEqual(None, view.error_message)
        self.assertEqual(
            canonical_url(bug), view.request.response.getHeader('Location'))

    def test_redirect_unknown_bug_fail(self):
        # The view reports an error and does not redirect if the bug is not
        # found.
        form = dict(id='fnord')
        view = create_initialized_view(
            self.application, name='+index', layer=BugsLayer, form=form)
        self.assertEqual(
            "Bug 'fnord' is not registered.", view.error_message)
        self.assertEqual(None, view.request.response.getHeader('Location'))

    def test_redirect_list_of_bug_fail(self):
        # The view reports an error and does not redirect if list is provided
        # instead of a string.
        form = dict(id=['fnord', 'pting'])
        view = create_initialized_view(
            self.application, name='+index', layer=BugsLayer, form=form)
        self.assertEqual(
            "Bug ['fnord', 'pting'] is not registered.", view.error_message)
        self.assertEqual(None, view.request.response.getHeader('Location'))

    def test_search_bugs_form_rendering(self):
        # The view's template directly renders the form widgets.
        view = create_initialized_view(self.application, '+index')
        content = find_tag_by_id(view.render(), 'search-all-bugs')
        self.assertEqual('form', content.name)
        self.assertIsNot(
            None, content.find(True, id='field.searchtext'))
        self.assertIsNot(
            None, content.find(True, id='field.actions.search'))
        self.assertIsNot(
            None, content.find(True, id='field.scope.option.all'))
        self.assertIsNot(
            None, content.find(True, id='field.scope.option.project'))
        target_widget = view.widgets['scope'].target_widget
        self.assertIsNot(
            None, content.find(True, id=target_widget.show_widget_id))
        text = str(content)
        picker_vocab = "DistributionOrProductOrProjectGroup"
        self.assertIn(picker_vocab, text)
        focus_script = "setFocusByName('field.searchtext')"
        self.assertIn(focus_script, text)

    def test_search_all_bugs_rendering(self):
        view = create_initialized_view(
            self.application, '+bugs', rootsite='bugs')
        content = view.render()
        # we should get some valid content out of this
        self.assertIn('Search all bugs', content)

    def _assert_getBugData(self, related_bug=None):
        # The getBugData method works as expected.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct()
        bug = self.factory.makeBug(
            target=product,
            owner=owner,
            status=BugTaskStatus.INPROGRESS,
            title='title', description='description',
            information_type=InformationType.PRIVATESECURITY)
        with person_logged_in(owner):
            bug_data = getUtility(IMaloneApplication).getBugData(
                owner, bug.id, related_bug)
            expected_bug_data = {
                    'id': bug.id,
                    'information_type': 'Private Security',
                    'is_private': True,
                    'importance': 'Undecided',
                    'importance_class': 'importanceUNDECIDED',
                    'status': 'In Progress',
                    'status_class': 'statusINPROGRESS',
                    'bug_summary': 'title',
                    'description': 'description',
                    'bug_url': canonical_url(bug.default_bugtask),
                    'different_pillars': related_bug is not None
        }
        self.assertEqual([expected_bug_data], bug_data)

    def test_getBugData(self):
        # The getBugData method works as expected without a related_bug.
        self._assert_getBugData()

    def test_getBugData_with_related_bug(self):
        # The getBugData method works as expected if related bug is specified.
        related_bug = self.factory.makeBug()
        self._assert_getBugData(related_bug)

    def test_createBug_public_bug_sharing_policy_public(self):
        # createBug() does not adapt the default kwargs when they are none.
        product = self.factory.makeProduct()
        with person_logged_in(product.owner):
            product.setBugSharingPolicy(BugSharingPolicy.PUBLIC)
        bug = self.application.createBug(
            product.owner, 'title', 'description', product)
        self.assertEqual(InformationType.PUBLIC, bug.information_type)

    def test_createBug_default_sharing_policy_proprietary(self):
        # createBug() does not adapt the default kwargs when they are none.
        product = self.factory.makeProduct(
            licenses=[License.OTHER_PROPRIETARY])
        with person_logged_in(product.owner):
            product.setBugSharingPolicy(BugSharingPolicy.PROPRIETARY_OR_PUBLIC)
        bug = self.application.createBug(
            product.owner, 'title', 'description', product)
        self.assertEqual(InformationType.PROPRIETARY, bug.information_type)

    def test_createBug_public_bug_sharing_policy_proprietary(self):
        # createBug() adapts a kwarg to InformationType if one is is not None.
        product = self.factory.makeProduct(
            licenses=[License.OTHER_PROPRIETARY])
        with person_logged_in(product.owner):
            product.setBugSharingPolicy(BugSharingPolicy.PROPRIETARY_OR_PUBLIC)
        bug = self.application.createBug(
            product.owner, 'title', 'description', product, private=False)
        self.assertEqual(InformationType.PUBLIC, bug.information_type)
