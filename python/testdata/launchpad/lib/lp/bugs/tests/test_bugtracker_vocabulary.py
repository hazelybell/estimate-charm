# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the bug tracker vocabularies."""

__metaclass__ = type

from zope.schema.vocabulary import getVocabularyRegistry

from lp.bugs.interfaces.bugtracker import BugTrackerType
from lp.testing import (
    login,
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestBugTrackerVocabulary(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugTrackerVocabulary, self).setUp()
        vocabulary_registry = getVocabularyRegistry()
        self.vocab = vocabulary_registry.get(None, 'BugTracker')

    def test_toTerm(self):
        # Verify the data in the term.
        bug_tracker = self.factory.makeBugTracker()
        login_person(bug_tracker.owner)
        bug_tracker.name = 'weasel'
        bug_tracker.title = 'The Weasel Bug Tracker'
        [term] = self.vocab.searchForTerms('weasel')
        self.assertEqual(bug_tracker, term.value)
        self.assertEqual(bug_tracker.name, term.token)
        self.assertEqual(bug_tracker.title, term.title)

    def test_getTermByToken_match(self):
        # Verify the token by lookup.
        bug_tracker = self.factory.makeBugTracker()
        login_person(bug_tracker.owner)
        bug_tracker.name = 'mink'
        term = self.vocab.getTermByToken('mink')
        self.assertEqual(bug_tracker, term.value)

    def test_getTermByToken_no_match(self):
        # Verify that a LookupError error is raised.
        self.assertRaises(
            LookupError, self.vocab.getTermByToken, 'does not exist')

    def searchForBugTrackers(self, query):
        terms = self.vocab.searchForTerms(query)
        return [term.value for term in terms]

    def test_search_name(self):
        # Verify that queries match name text.
        bug_tracker = self.factory.makeBugTracker()
        login_person(bug_tracker.owner)
        bug_tracker.name = 'skunkworks'
        bug_trackers = self.searchForBugTrackers('skunk')
        self.assertEqual([bug_tracker], bug_trackers)

    def test_search_title(self):
        # Verify that queries match title text.
        bug_tracker = self.factory.makeBugTracker()
        login_person(bug_tracker.owner)
        bug_tracker.title = 'A ferret in your pants'
        bug_trackers = self.searchForBugTrackers('ferret')
        self.assertEqual([bug_tracker], bug_trackers)

    def test_search_summary(self):
        # Verify that queries match summary text.
        bug_tracker = self.factory.makeBugTracker()
        login_person(bug_tracker.owner)
        bug_tracker.summary = 'A badger is a member of the weasel family.'
        bug_trackers = self.searchForBugTrackers('badger')
        self.assertEqual([bug_tracker], bug_trackers)

    def test_search_baseurl(self):
        # Verify that queries match baseurl text.
        bug_tracker = self.factory.makeBugTracker(
            base_url='http://bugs.otter.dom/')
        bug_trackers = self.searchForBugTrackers('otter')
        self.assertEqual([bug_tracker], bug_trackers)

    def test_search_inactive(self):
        # Verify that inactive bug trackers are not returned by search,
        # but are in the vocabulary.
        bug_tracker = self.factory.makeBugTracker()
        login('admin@canonical.com')
        bug_tracker.name = 'stoat'
        bug_tracker.active = False
        bug_trackers = self.searchForBugTrackers('stoat')
        self.assertEqual([], bug_trackers)
        term = self.vocab.getTermByToken('stoat')
        self.assertEqual(bug_tracker, term.value)


class TestWebBugTrackerVocabulary(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestWebBugTrackerVocabulary, self).setUp()
        vocabulary_registry = getVocabularyRegistry()
        self.vocab = vocabulary_registry.get(None, 'WebBugTracker')

    def test_search_no_email_type(self):
        # Verify that emailaddress bug trackers are not returned by search,
        # and are not in the vocabulary.
        bug_tracker = self.factory.makeBugTracker(
            bugtrackertype=BugTrackerType.EMAILADDRESS)
        login_person(bug_tracker.owner)
        bug_tracker.name = 'marten'
        terms = self.vocab.searchForTerms('marten')
        bug_trackers = [term.value for term in terms]
        self.assertEqual([], bug_trackers)
        self.assertRaises(
            LookupError, self.vocab.getTermByToken, 'marten')
