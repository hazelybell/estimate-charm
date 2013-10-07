# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type


from datetime import (
    datetime,
    timedelta,
    )
import doctest

from pytz import utc
from testtools.matchers import DocTestMatches
from zope.component import provideUtility
from zope.interface import implements
from zope.schema import Choice
from zope.schema.interfaces import IVocabularyFactory
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )

from lp.app.widgets.suggestion import (
    SuggestionWidget,
    TargetBranchWidget,
    )
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.services.webapp.vocabulary import (
    FilteredVocabularyBase,
    IHugeVocabulary,
    )
from lp.testing import (
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class Simple:
    """A simple class to test fields and widgets."""

    def __init__(self, name, displayname):
        self.name = name
        self.displayname = displayname


class SimpleHugeVocabulary(SimpleVocabulary, FilteredVocabularyBase):
    implements(IHugeVocabulary)
    displayname = "Simple objects"
    step_title = "Select something"

    def __call__(self, context):
        # Allow an instance to be used as a utility.
        return self


class TestSuggestionWidget(TestCaseWithFactory):
    """Test the SuggestionWidget class."""

    layer = DatabaseFunctionalLayer
    doctest_opts = (
        doctest.NORMALIZE_WHITESPACE | doctest.REPORT_NDIFF |
        doctest.ELLIPSIS)

    SAFE_OBJECT = Simple('token-1', 'Safe title')
    UNSAFE_OBJECT = Simple('token-2', '<unsafe> &nbsp; title')

    SAFE_TERM = SimpleTerm(
        SAFE_OBJECT, SAFE_OBJECT.name, SAFE_OBJECT.displayname)
    UNSAFE_TERM = SimpleTerm(
        UNSAFE_OBJECT, UNSAFE_OBJECT.name, UNSAFE_OBJECT.displayname)

    class ExampleSuggestionWidget(SuggestionWidget):

        @staticmethod
        def _getSuggestions(context):
            return SimpleVocabulary([TestSuggestionWidget.SAFE_TERM])

        def _autoselectOther(self):
            on_key_press = "selectWidget('%s', event);" % self._otherId()
            self.other_selection_widget.onKeyPress = on_key_press

    def setUp(self):
        super(TestSuggestionWidget, self).setUp()
        request = LaunchpadTestRequest()
        vocabulary = SimpleHugeVocabulary(
            [self.SAFE_TERM, self.UNSAFE_TERM])
        provideUtility(
            vocabulary, provides=IVocabularyFactory,
            name='SimpleHugeVocabulary')
        field = Choice(
            __name__='test_field', vocabulary="SimpleHugeVocabulary")
        field = field.bind(object())
        self.widget = self.ExampleSuggestionWidget(
            field, vocabulary, request)

    def test__renderLabel_unsafe_content(self):
        # Render label escapes unsafe markup.
        strutured_string = self.widget._renderLabel(self.UNSAFE_TERM.title, 2)
        expected_item_0 = (
            """<label for="field.test_field.2"
            ...>&lt;unsafe&gt; &amp;nbsp; title</label>""")
        self.assertThat(
            strutured_string.escapedtext,
            DocTestMatches(expected_item_0, self.doctest_opts))

    def test__renderSuggestionLabel_unsafe_content(self):
        # Render sugestion label escapes unsafe markup.
        strutured_string = self.widget._renderSuggestionLabel(
            self.UNSAFE_OBJECT, 2)
        expected_item_0 = (
            """<label for="field.test_field.2"
            ...>&lt;unsafe&gt; &amp;nbsp; title</label>""")
        self.assertThat(
            strutured_string.escapedtext,
            DocTestMatches(expected_item_0, self.doctest_opts))

    def test_renderItems(self):
        # Render all vocabulary and the other option as items.
        markups = self.widget.renderItems(None)
        self.assertEqual(2, len(markups))
        expected_item_0 = (
            """<input class="radioType" checked="checked" ...
            value="token-1" />&nbsp;<label ...>Safe title</label>""")
        self.assertThat(
            markups[0], DocTestMatches(expected_item_0, self.doctest_opts))
        expected_item_1 = (
            """<input class="radioType" ...
             onClick="this.form['field.test_field.test_field'].focus()" ...
             value="other" />&nbsp;<label ...>Other:</label>
             <input type="text" value="" ...
             onKeyPress="selectWidget(&#x27;field.test_field.1&#x27;, event);"
             .../>...""")

        # XXX wallyworld 2011-04-18 bug=764170: We cannot pass an unencoded
        # unicode string to the DocTestMatcher
        markup = markups[1].encode('utf-8')
        self.assertThat(
            markup, DocTestMatches(expected_item_1, self.doctest_opts))


def make_target_branch_widget(branch):
    """Given a branch, return a widget for selecting where to land it."""
    choice = Choice(vocabulary='Branch').bind(branch)
    request = LaunchpadTestRequest()
    return TargetBranchWidget(choice, None, request)


class TestTargetBranchWidget(TestCaseWithFactory):
    """Test the TargetBranchWidget class."""

    layer = DatabaseFunctionalLayer

    def makeBranchAndOldMergeProposal(self, timedelta):
        """Make an old  merge proposal and a branch with the same target."""
        bmp = self.factory.makeBranchMergeProposal(
            date_created=datetime.now(utc) - timedelta)
        login_person(bmp.registrant)
        target = bmp.target_branch
        return target, self.factory.makeBranchTargetBranch(target.target)

    def test_recent_target(self):
        """Targets for proposals newer than 90 days are included."""
        target, source = self.makeBranchAndOldMergeProposal(
            timedelta(days=89))
        widget = make_target_branch_widget(source)
        self.assertIn(target, widget.suggestion_vocab)

    def test_stale_target(self):
        """Targets for proposals older than 90 days are not considered."""
        target, source = self.makeBranchAndOldMergeProposal(
            timedelta(days=91))
        widget = make_target_branch_widget(source)
        self.assertNotIn(target, widget.suggestion_vocab)
