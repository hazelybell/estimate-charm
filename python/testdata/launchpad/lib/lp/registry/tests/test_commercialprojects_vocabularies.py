# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the commercial projects vocabularies."""

__metaclass__ = type

from lp.registry.interfaces.product import License
from lp.registry.vocabularies import CommercialProjectsVocabulary
from lp.services.identity.interfaces.emailaddress import EmailAddressStatus
from lp.testing import (
    celebrity_logged_in,
    login_celebrity,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestCommProjVocabulary(TestCaseWithFactory):
    """Test that the CommercialProjectsVocabulary behaves as expected."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestCommProjVocabulary, self).setUp()
        self.owner = self.factory.makePerson(
            email_address_status=EmailAddressStatus.VALIDATED)
        self._createProjects()
        self.vocab = CommercialProjectsVocabulary(context=self.owner)

    def _createProjects(self):
        """Create maintained projects."""
        # Create 5 proprietary projects.
        self.num_proprietary = 5
        for i in range(self.num_proprietary):
            self.factory.makeProduct(
                name='widget%d' % i, owner=self.owner,
                 licenses=[License.OTHER_PROPRIETARY])
        # Create an open source project.
        self.num_commercial = self.num_proprietary + 1
        self.maintained_project = self.factory.makeProduct(
            name='open-widget', owner=self.owner,
            licenses=[License.GNU_GPL_V3])
        # Create a deactivated open source project.
        with celebrity_logged_in('admin'):
            self.deactivated_project = self.factory.makeProduct(
                name='norwegian-blue-widget', owner=self.owner,
                licenses=[License.GNU_GPL_V3])
            self.deactivated_project.active = False

    def test_attributes(self):
        self.assertEqual('Select a commercial project', self.vocab.displayname)
        self.assertEqual('Search', self.vocab.step_title)
        self.assertEqual('displayname', self.vocab._orderBy)

    def test_searchForTerms_empty(self):
        # An empty search will return all active maintained projects.
        results = self.vocab.searchForTerms('')
        self.assertEqual(
            self.num_commercial, len(results),
            "Expected %d results but got %d." % (self.num_commercial,
                                                 len(results)))

    def test_searchForTerms_success(self):
        # Search for active maintained projects success.
        results = self.vocab.searchForTerms(u'widget')
        self.assertEqual(
            self.num_commercial, len(results),
            "Expected %d results but got %d." % (self.num_commercial,
                                                 len(results)))
        # Ensure we get only those that match by searching for a single
        # widget, using 't1', a subset of the name 'widget1'.
        results = self.vocab.searchForTerms(u't1')
        self.assertEqual(1, len(results),
                         "Expected %d result but got %d." % (1, len(results)))

    def test_searchForTerms_fail(self):
        # Search for deactivated or non-maintained projects fails.
        results = self.vocab.searchForTerms(u'norwegian-blue-widget')
        self.assertEqual(0, len(results),
                         "Expected %d results but got %d." %
                         (0, len(results)))

        results = self.vocab.searchForTerms(u'firefox')
        self.assertEqual(0, len(results),
                         "Expected %d results but got %d." %
                         (0, len(results)))

    def test_searchForTerms_commercial_admin(self):
        # Users with launchpad.Commercial can search for any active project.
        expert = login_celebrity('commercial_admin')
        self.vocab = CommercialProjectsVocabulary(context=expert)
        self.assertEqual(
            1, len(self.vocab.searchForTerms(u'open-widget')))
        self.assertEqual(
            0, len(self.vocab.searchForTerms(u'norwegian-blue-widget')))

    def test_toTerm(self):
        # Commercial project terms contain subscription information.
        term = self.vocab.toTerm(self.maintained_project)
        self.assertEqual(self.maintained_project, term.value)
        self.assertEqual('open-widget', term.token)
        self.assertEqual('Open-widget', term.title)

    def test_getTermByToken_user(self):
        # The term for a token in the vocabulary is returned for maintained
        # projects.
        token = self.vocab.getTermByToken(u'open-widget')
        self.assertEqual(self.maintained_project, token.value)

    def test_getTermByToken_commercial_admin(self):
        # The term for a token in the vocabulary is returned for any
        # active project.
        login_celebrity('commercial_admin')
        token = self.vocab.getTermByToken(u'open-widget')
        self.assertEqual(self.maintained_project, token.value)

    def test_getTermByToken_error_user(self):
        # A LookupError is raised if the token is not in the vocabulary.
        self.assertRaises(
            LookupError, self.vocab.getTermByToken, u'norwegian-blue-widget')

    def test_getTermByToken_error_commercial_admin(self):
        # The term for a token in the vocabulary is returned for any
        # active project.
        login_celebrity('commercial_admin')
        self.assertRaises(
            LookupError, self.vocab.getTermByToken, u'norwegian-blue-widget')

    def test_iter(self):
        # The vocabulary can be iterated and the order is by displayname.
        displaynames = [p.value.displayname for p in self.vocab]
        self.assertEqual(
            ['Open-widget', 'Widget0', 'Widget1', 'Widget2', 'Widget3',
             'Widget4'],
            displaynames)

    def test_contains_maintainer(self):
        # The vocabulary only contains active projects the user maintains.
        other_project = self.factory.makeProduct()
        self.assertIs(False, other_project in self.vocab)
        self.assertIs(False, self.deactivated_project in self.vocab)
        self.assertIs(True, self.maintained_project in self.vocab)

    def test_contains_commercial_admin(self):
        # The vocabulary contains all active projects for commercial.
        other_project = self.factory.makeProduct()
        expert = login_celebrity('commercial_admin')
        self.vocab = CommercialProjectsVocabulary(context=expert)
        self.assertIs(True, other_project in self.vocab)
        self.assertIs(False, self.deactivated_project in self.vocab)
        self.assertIs(True, self.maintained_project in self.vocab)
