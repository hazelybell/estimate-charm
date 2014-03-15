# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for BranchView."""

__metaclass__ = type

from datetime import datetime
from textwrap import dedent

from BeautifulSoup import BeautifulSoup
import pytz
from storm.store import Store
from testtools.matchers import Equals
from zope.component import getUtility
from zope.publisher.interfaces import NotFound
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.app.interfaces.headings import IRootContext
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.app.interfaces.services import IService
from lp.bugs.interfaces.bugtask import (
    BugTaskStatus,
    UNRESOLVED_BUGTASK_STATUSES,
    )
from lp.code.browser.branch import BranchMirrorStatusView
from lp.code.bzr import (
    BranchFormat,
    ControlFormat,
    RepositoryFormat,
    )
from lp.code.enums import BranchType
from lp.registry.enums import BranchSharingPolicy
from lp.registry.interfaces.accesspolicy import IAccessPolicySource
from lp.registry.interfaces.person import PersonVisibility
from lp.services.config import config
from lp.services.database.constants import UTC_NOW
from lp.services.helpers import truncate_text
from lp.services.webapp.publisher import canonical_url
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    BrowserTestCase,
    login,
    login_person,
    logout,
    person_logged_in,
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.matchers import (
    BrowsesWithQueryLimit,
    Contains,
    HasQueryCount,
    )
from lp.testing.pages import (
    extract_text,
    find_tag_by_id,
    setupBrowser,
    setupBrowserForUser,
    )
from lp.testing.views import (
    create_initialized_view,
    create_view,
    )


class TestBranchMirrorHidden(TestCaseWithFactory):
    """Make sure that the appropriate mirror locations are hidden."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestBranchMirrorHidden, self).setUp()
        config.push(
            "test", dedent("""\
                [codehosting]
                private_mirror_hosts: private.example.com
                """))

    def tearDown(self):
        config.pop("test")
        super(TestBranchMirrorHidden, self).tearDown()

    def testNormalBranch(self):
        # A branch from a normal location is fine.
        branch = self.factory.makeAnyBranch(
            branch_type=BranchType.MIRRORED,
            url="http://example.com/good/mirror")
        view = create_initialized_view(branch, '+index')
        self.assertTrue(view.user is None)
        self.assertEqual(
            "http://example.com/good/mirror", view.mirror_location)

    def testLocationlessRemoteBranch(self):
        # A branch from a normal location is fine.
        branch = self.factory.makeAnyBranch(
            branch_type=BranchType.REMOTE, url=None)
        view = create_initialized_view(branch, '+index')
        self.assertTrue(view.user is None)
        self.assertIs(None, view.mirror_location)

    def testHiddenBranchAsAnonymous(self):
        # A branch location with a defined private host is hidden from
        # anonymous browsers.
        branch = self.factory.makeAnyBranch(
            branch_type=BranchType.MIRRORED,
            url="http://private.example.com/bzr-mysql/mysql-5.0")
        view = create_initialized_view(branch, '+index')
        self.assertTrue(view.user is None)
        self.assertEqual("<private server>", view.mirror_location)

    def testHiddenBranchAsBranchOwner(self):
        # A branch location with a defined private host is visible to the
        # owner.
        owner = self.factory.makePerson(email="eric@example.com")
        branch = self.factory.makeAnyBranch(
            branch_type=BranchType.MIRRORED,
            owner=owner, url="http://private.example.com/bzr-mysql/mysql-5.0")
        # Now log in the owner.
        login('eric@example.com')
        view = create_initialized_view(branch, '+index')
        self.assertEqual(view.user, owner)
        self.assertEqual(
            "http://private.example.com/bzr-mysql/mysql-5.0",
            view.mirror_location)

    def testHiddenBranchAsOtherLoggedInUser(self):
        # A branch location with a defined private host is hidden from other
        # users.
        owner = self.factory.makePerson(email="eric@example.com")
        other = self.factory.makePerson(email="other@example.com")
        branch = self.factory.makeAnyBranch(
            branch_type=BranchType.MIRRORED, owner=owner,
            url="http://private.example.com/bzr-mysql/mysql-5.0")
        # Now log in the other person.
        login('other@example.com')
        view = create_initialized_view(branch, '+index')
        self.assertEqual(view.user, other)
        self.assertEqual("<private server>", view.mirror_location)


class TestBranchView(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def testMirrorStatusMessageIsTruncated(self):
        """mirror_status_message is truncated if the text is overly long."""
        branch = self.factory.makeBranch(branch_type=BranchType.MIRRORED)
        branch.mirrorFailed(
            "on quick brown fox the dog jumps to" *
            BranchMirrorStatusView.MAXIMUM_STATUS_MESSAGE_LENGTH)
        branch_view = create_view(branch, '+mirror-status')
        self.assertEqual(
            truncate_text(branch.mirror_status_message,
                          branch_view.MAXIMUM_STATUS_MESSAGE_LENGTH) + ' ...',
            branch_view.mirror_status_message)

    def testMirrorStatusMessage(self):
        """mirror_status_message on the view is the same as on the branch."""
        branch = self.factory.makeBranch(branch_type=BranchType.MIRRORED)
        branch.mirrorFailed("This is a short error message.")
        branch_view = create_view(branch, '+mirror-status')
        self.assertTrue(
            len(branch.mirror_status_message)
            <= branch_view.MAXIMUM_STATUS_MESSAGE_LENGTH,
            "branch.mirror_status_message longer than expected: %r"
            % (branch.mirror_status_message, ))
        self.assertEqual(
            branch.mirror_status_message, branch_view.mirror_status_message)
        self.assertEqual(
            "This is a short error message.",
            branch_view.mirror_status_message)

    def testShowMergeLinksOnManyBranchProject(self):
        # The merge links are shown on projects that have multiple branches.
        product = self.factory.makeProduct(name='super-awesome-project')
        branch = self.factory.makeAnyBranch(product=product)
        self.factory.makeAnyBranch(product=product)
        view = create_initialized_view(branch, '+index')
        self.assertTrue(view.show_merge_links)

    def testShowMergeLinksOnJunkBranch(self):
        # The merge links are not shown on junk branches because they do not
        # support merge proposals.
        junk_branch = self.factory.makeBranch(product=None)
        view = create_initialized_view(junk_branch, '+index')
        self.assertFalse(view.show_merge_links)

    def testShowMergeLinksOnSingleBranchProject(self):
        # The merge links are not shown on branches attached to a project that
        # only has one branch because it's pointless to propose it for merging
        # if there's nothing to merge into.
        branch = self.factory.makeAnyBranch()
        view = create_initialized_view(branch, '+index')
        self.assertFalse(view.show_merge_links)

    def testNoProductSeriesPushingTranslations(self):
        # By default, a branch view shows no product series pushing
        # translations to the branch.
        branch = self.factory.makeBranch()
        view = create_initialized_view(branch, '+index')
        self.assertEqual(list(view.translations_sources()), [])

    def testProductSeriesPushingTranslations(self):
        # If a product series exports its translations to the branch,
        # the view shows it.
        product = self.factory.makeProduct()
        trunk = product.getSeries('trunk')
        branch = self.factory.makeBranch(owner=product.owner)
        removeSecurityProxy(trunk).translations_branch = branch
        view = create_initialized_view(branch, '+index')
        self.assertEqual(list(view.translations_sources()), [trunk])

    def test_is_empty_directory(self):
        # Branches are considered empty until they get a control format.
        branch = self.factory.makeBranch()
        view = create_initialized_view(branch, '+index')
        self.assertTrue(view.is_empty_directory)
        with person_logged_in(branch.owner):
            # Make it look as though the branch has been pushed.
            branch.branchChanged(
                None, None, ControlFormat.BZR_METADIR_1, None, None)
        self.assertFalse(view.is_empty_directory)

    def test_empty_directories_use_existing(self):
        # Push example should include --use-existing-dir for empty directories.
        branch = self.factory.makeBranch(owner=self.user)
        text = self.getMainText(branch)
        self.assertIn('push\n--use-existing-dir', text)
        with person_logged_in(self.user):
            # Make it look as though the branch has been pushed.
            branch.branchChanged(
                None, None, ControlFormat.BZR_METADIR_1, None, None)
        text = self.getMainText(branch)
        self.assertNotIn('push\n--use-existing-dir', text)

    def test_user_can_upload(self):
        # A user can upload if they have edit permissions.
        branch = self.factory.makeAnyBranch()
        view = create_initialized_view(branch, '+index')
        login_person(branch.owner)
        self.assertTrue(view.user_can_upload)

    def test_user_can_upload_admins_can(self):
        # Admins can upload to any hosted branch.
        branch = self.factory.makeAnyBranch()
        view = create_initialized_view(branch, '+index')
        login('admin@canonical.com')
        self.assertTrue(view.user_can_upload)

    def test_user_can_upload_non_owner(self):
        # Someone not associated with the branch cannot upload
        branch = self.factory.makeAnyBranch()
        view = create_initialized_view(branch, '+index')
        login_person(self.factory.makePerson())
        self.assertFalse(view.user_can_upload)

    def test_user_can_upload_mirrored(self):
        # Even the owner of a mirrored branch can't upload.
        branch = self.factory.makeAnyBranch(branch_type=BranchType.MIRRORED)
        view = create_initialized_view(branch, '+index')
        login_person(branch.owner)
        self.assertFalse(view.user_can_upload)

    def _addBugLinks(self, branch):
        for status in BugTaskStatus.items:
            bug = self.factory.makeBug(status=status)
            branch.linkBug(bug, branch.owner)

    def test_linked_bugtasks(self):
        # The linked bugs for a non series branch shows all linked bugs.
        branch = self.factory.makeAnyBranch()
        with person_logged_in(branch.owner):
            self._addBugLinks(branch)
        view = create_initialized_view(branch, '+index')
        self.assertEqual(len(BugTaskStatus), len(view.linked_bugtasks))
        self.assertFalse(view.context.is_series_branch)

    def test_linked_bugtasks_privacy(self):
        # If a linked bug is private, it is not in the linked bugs if the user
        # can't see any of the tasks.
        branch = self.factory.makeAnyBranch()
        reporter = self.factory.makePerson()
        bug = self.factory.makeBug(
            owner=reporter, information_type=InformationType.USERDATA)
        with person_logged_in(reporter):
            branch.linkBug(bug, reporter)
            view = create_initialized_view(branch, '+index')
            self.assertEqual([bug.id],
                [task.bug.id for task in view.linked_bugtasks])
        with person_logged_in(branch.owner):
            view = create_initialized_view(branch, '+index')
            self.assertEqual([], view.linked_bugtasks)

    def test_linked_bugtasks_series_branch(self):
        # The linked bugtasks for a series branch shows only unresolved bugs.
        product = self.factory.makeProduct()
        branch = self.factory.makeProductBranch(product=product)
        with person_logged_in(product.owner):
            product.development_focus.branch = branch
        with person_logged_in(branch.owner):
            self._addBugLinks(branch)
        view = create_initialized_view(branch, '+index')
        for bugtask in view.linked_bugtasks:
            self.assertTrue(
                bugtask.status in UNRESOLVED_BUGTASK_STATUSES)

    def test_linked_bugs_nonseries_branch_query_scaling(self):
        # As we add linked bugs, the query count for a branch index page stays
        # constant.
        branch = self.factory.makeAnyBranch()
        browses_under_limit = BrowsesWithQueryLimit(54, branch.owner)
        # Start with some bugs, otherwise we might see a spurious increase
        # depending on optimisations in eager loaders.
        with person_logged_in(branch.owner):
            self._addBugLinks(branch)
            self.assertThat(branch, browses_under_limit)
        with person_logged_in(branch.owner):
            # Add plenty of bugs.
            for _ in range(5):
                self._addBugLinks(branch)
            self.assertThat(branch, browses_under_limit)

    def test_linked_bugs_series_branch_query_scaling(self):
        # As we add linked bugs, the query count for a branch index page stays
        # constant.
        product = self.factory.makeProduct(
            branch_sharing_policy=BranchSharingPolicy.PUBLIC)
        branch = self.factory.makeProductBranch(product=product)
        browses_under_limit = BrowsesWithQueryLimit(54, branch.owner)
        with person_logged_in(product.owner):
            product.development_focus.branch = branch
        # Start with some bugs, otherwise we might see a spurious increase
        # depending on optimisations in eager loaders.
        with person_logged_in(branch.owner):
            self._addBugLinks(branch)
            self.assertThat(branch, browses_under_limit)
        with person_logged_in(branch.owner):
            # Add plenty of bugs.
            for _ in range(5):
                self._addBugLinks(branch)
            self.assertThat(branch, browses_under_limit)

    def _add_revisions(self, branch, nr_revisions=1):
        revisions = []
        for seq in range(1, nr_revisions + 1):
            revision = self.factory.makeRevision(
                author="Eric the Viking <eric@vikings-r-us.example.com>",
                log_body=(
                    "Testing the email address in revisions\n"
                    "email Bob (bob@example.com) for details."))

            branch_revision = branch.createBranchRevision(seq, revision)
            branch.updateScannedDetails(revision, seq)
            revisions.append(branch_revision)
        return revisions

    def test_recent_revisions(self):
        # There is a heading for the recent revisions.
        branch = self.factory.makeAnyBranch()
        with person_logged_in(branch.owner):
            self._add_revisions(branch)
        browser = self.getUserBrowser(canonical_url(branch))
        tag = find_tag_by_id(browser.contents, 'recent-revisions')
        text = extract_text(tag)
        expected_text = """
            Recent revisions
            .*
            1. By Eric the Viking &lt;eric@vikings-r-us.example.com&gt;
            .*
            Testing the email address in revisions\n
            email Bob \(bob@example.com\) for details.
            """

        self.assertTextMatchesExpressionIgnoreWhitespace(expected_text, text)

    def test_recent_revisions_email_hidden_with_no_login(self):
        # If the user is not logged in, the email addresses are hidden in both
        # the revision author and the commit message.
        branch = self.factory.makeAnyBranch()
        with person_logged_in(branch.owner):
            self._add_revisions(branch)
            branch_url = canonical_url(branch)
        browser = setupBrowser()
        logout()
        browser.open(branch_url)
        tag = find_tag_by_id(browser.contents, 'recent-revisions')
        text = extract_text(tag)
        expected_text = """
            Recent revisions
            .*
            1. By Eric the Viking &lt;email address hidden&gt;
            .*
            Testing the email address in revisions\n
            email Bob \(&lt;email address hidden&gt;\) for details.
            """
        self.assertTextMatchesExpressionIgnoreWhitespace(expected_text, text)

    def test_recent_revisions_with_merge_proposals(self):
        # Revisions which result from merging in a branch with a merge
        # proposal show the merge proposal details.

        branch = self.factory.makeAnyBranch()
        with person_logged_in(branch.owner):
            revisions = self._add_revisions(branch, 2)
            mp = self.factory.makeBranchMergeProposal(
                target_branch=branch, registrant=branch.owner)
            mp.markAsMerged(merged_revno=revisions[0].sequence)

            # These values are extracted here and used below.
            mp_url = canonical_url(mp, rootsite='code', force_local_path=True)
            branch_display_name = mp.source_branch.displayname

        browser = self.getUserBrowser(canonical_url(branch))

        revision_content = find_tag_by_id(
            browser.contents, 'recent-revisions')

        text = extract_text(revision_content)
        expected_text = """
            Recent revisions
            .*
            2. By Eric the Viking &lt;eric@vikings-r-us.example.com&gt;
            .*
            Testing the email address in revisions\n
            email Bob \(bob@example.com\) for details.\n
            1. By Eric the Viking &lt;eric@vikings-r-us.example.com&gt;
            .*
            Testing the email address in revisions\n
            email Bob \(bob@example.com\) for details.
            Merged branch %s
            """ % branch_display_name

        self.assertTextMatchesExpressionIgnoreWhitespace(expected_text, text)

        links = revision_content.findAll('a')
        self.assertEqual(mp_url, links[2]['href'])

    def test_recent_revisions_with_merge_proposals_and_bug_links(self):
        # Revisions which result from merging in a branch with a merge
        # proposal show the merge proposal details. If the source branch of
        # the merge proposal has linked bugs, these should also be shown.

        branch = self.factory.makeAnyBranch()
        with person_logged_in(branch.owner):
            revisions = self._add_revisions(branch, 2)
            mp = self.factory.makeBranchMergeProposal(
                target_branch=branch, registrant=branch.owner)
            mp.markAsMerged(merged_revno=revisions[0].sequence)

            # record linked bug info for use below
            linked_bug_urls = []
            linked_bug_text = []
            for x in range(0, 2):
                bug = self.factory.makeBug()
                mp.source_branch.linkBug(bug, branch.owner)
                linked_bug_urls.append(
                    canonical_url(bug.default_bugtask, rootsite='bugs'))
                bug_text = "Bug #%s: %s" % (bug.id, bug.title)
                linked_bug_text.append(bug_text)

            # These values are extracted here and used below.
            linked_bug_rendered_text = "\n".join(linked_bug_text)
            mp_url = canonical_url(mp, force_local_path=True)
            branch_display_name = mp.source_branch.displayname

        browser = self.getUserBrowser(canonical_url(branch))

        revision_content = find_tag_by_id(
            browser.contents, 'recent-revisions')

        text = extract_text(revision_content)
        expected_text = """
            Recent revisions
            .*
            2. By Eric the Viking &lt;eric@vikings-r-us.example.com&gt;
            .*
            Testing the email address in revisions\n
            email Bob \(bob@example.com\) for details.\n
            1. By Eric the Viking &lt;eric@vikings-r-us.example.com&gt;
            .*
            Testing the email address in revisions\n
            email Bob \(bob@example.com\) for details.
            Merged branch %s
            %s
            """ % (branch_display_name, linked_bug_rendered_text)

        self.assertTextMatchesExpressionIgnoreWhitespace(expected_text, text)

        links = revision_content.findAll('a')
        self.assertEqual(mp_url, links[2]['href'])
        self.assertEqual(linked_bug_urls[0], links[3]['href'])
        self.assertEqual(linked_bug_urls[1], links[4]['href'])

    def test_view_for_user_with_artifact_grant(self):
        # Users with an artifact grant for a branch related to a private
        # product can view the main branch page.
        owner = self.factory.makePerson()
        user = self.factory.makePerson()
        product = self.factory.makeProduct(
            owner=owner,
            information_type=InformationType.PROPRIETARY)
        with person_logged_in(owner):
            product_name = product.name
            branch = self.factory.makeBranch(
                product=product, owner=owner,
                information_type=InformationType.PROPRIETARY)
            getUtility(IService, 'sharing').ensureAccessGrants(
                [user], owner, branches=[branch])
        with person_logged_in(user):
            url = canonical_url(branch)
        # The main check: No Unauthorized error should be raised.
        browser = self.getUserBrowser(url, user=user)
        self.assertIn(product_name, browser.contents)

    def test_query_count_landing_candidates(self):
        product = self.factory.makeProduct()
        branch = self.factory.makeBranch(product=product)
        for i in range(10):
            self.factory.makeBranchMergeProposal(target_branch=branch)
        stacked = self.factory.makeBranch(product=product)
        source = self.factory.makeBranch(stacked_on=stacked, product=product)
        prereq = self.factory.makeBranch(product=product)
        self.factory.makeBranchMergeProposal(
            source_branch=source, target_branch=branch,
            prerequisite_branch=prereq)
        Store.of(branch).flush()
        Store.of(branch).invalidate()
        view = create_view(branch, '+index')
        with StormStatementRecorder() as recorder:
            view.landing_candidates
        self.assertThat(recorder, HasQueryCount(Equals(5)))

    def test_query_count_subscriber_content(self):
        branch = self.factory.makeBranch()
        for i in range(10):
            self.factory.makeBranchSubscription(branch=branch)
        Store.of(branch).flush()
        Store.of(branch).invalidate()
        view = create_initialized_view(
            branch, '+branch-portlet-subscriber-content')
        with StormStatementRecorder() as recorder:
            view.render()
        self.assertThat(recorder, HasQueryCount(Equals(9)))

    def test_query_count_index_with_subscribers(self):
        branch = self.factory.makeBranch()
        for i in range(10):
            self.factory.makeBranchSubscription(branch=branch)
        Store.of(branch).flush()
        Store.of(branch).invalidate()
        branch_url = canonical_url(branch, view_name='+index', rootsite='code')
        browser = setupBrowser()
        logout()
        with StormStatementRecorder() as recorder:
            browser.open(branch_url)
        self.assertThat(recorder, HasQueryCount(Equals(26)))


class TestBranchViewPrivateArtifacts(BrowserTestCase):
    """ Tests that branches with private team artifacts can be viewed.

    A Branch may be associated with a private team as follows:
    - the owner is a private team
    - a subscriber is a private team
    - a reviewer is a private team

    A logged in user who is not authorised to see the private team(s) still
    needs to be able to view the branch. The private team will be rendered in
    the normal way, displaying the team name and Launchpad URL.
    """

    layer = DatabaseFunctionalLayer

    def _getBrowser(self, user=None):
        if user is None:
            browser = setupBrowser()
            logout()
            return browser
        else:
            login_person(user)
            return setupBrowserForUser(user=user)

    def test_view_branch_with_private_owner(self):
        # A branch with a private owner is rendered.
        private_owner = self.factory.makeTeam(
            displayname="PrivateTeam", visibility=PersonVisibility.PRIVATE)
        with person_logged_in(private_owner):
            branch = self.factory.makeAnyBranch(owner=private_owner)
        # Ensure the branch owner is rendered.
        url = canonical_url(branch, rootsite='code')
        user = self.factory.makePerson()
        browser = self._getBrowser(user)
        browser.open(url)
        soup = BeautifulSoup(browser.contents)
        self.assertIsNotNone(soup.find('a', text="PrivateTeam"))

    def test_view_private_branch_with_private_owner(self):
        # A private branch with a private owner is rendered.
        private_owner = self.factory.makeTeam(
            displayname="PrivateTeam", visibility=PersonVisibility.PRIVATE)
        with person_logged_in(private_owner):
            branch = self.factory.makeAnyBranch(owner=private_owner)
        # Ensure the branch owner is rendered.
        url = canonical_url(branch, rootsite='code')
        user = self.factory.makePerson()
        # Subscribe the user so they can see the branch.
        with person_logged_in(private_owner):
            self.factory.makeBranchSubscription(branch, user, private_owner)
        browser = self._getBrowser(user)
        browser.open(url)
        soup = BeautifulSoup(browser.contents)
        self.assertIsNotNone(soup.find('a', text="PrivateTeam"))

    def test_anonymous_view_branch_with_private_owner(self):
        # A branch with a private owner is not rendered for anon users.
        private_owner = self.factory.makeTeam(
            visibility=PersonVisibility.PRIVATE)
        with person_logged_in(private_owner):
            branch = self.factory.makeAnyBranch(owner=private_owner)
        # Viewing the branch results in an error.
        url = canonical_url(branch, rootsite='code')
        browser = self._getBrowser()
        self.assertRaises(NotFound, browser.open, url)

    def test_view_branch_with_private_subscriber(self):
        # A branch with a private subscriber is rendered.
        private_subscriber = self.factory.makeTeam(
            name="privateteam", visibility=PersonVisibility.PRIVATE)
        branch = self.factory.makeAnyBranch()
        with person_logged_in(branch.owner):
            self.factory.makeBranchSubscription(
                branch, private_subscriber, branch.owner)
        # Ensure the branch subscriber is rendered.
        url = canonical_url(branch, rootsite='code')
        user = self.factory.makePerson()
        browser = self._getBrowser(user)
        browser.open(url)
        soup = BeautifulSoup(browser.contents)
        self.assertIsNotNone(
            soup.find('div', attrs={'id': 'subscriber-privateteam'}))

    def test_anonymous_view_branch_with_private_subscriber(self):
        # Private branch subscribers are not rendered for anon users.
        private_subscriber = self.factory.makeTeam(
            name="privateteam", visibility=PersonVisibility.PRIVATE)
        branch = self.factory.makeAnyBranch()
        with person_logged_in(private_subscriber):
            self.factory.makeBranchSubscription(
                branch, private_subscriber, branch.owner)
        # Viewing the branch doesn't show the private subscriber.
        url = canonical_url(branch, rootsite='code')
        browser = self._getBrowser()
        browser.open(url)
        soup = BeautifulSoup(browser.contents)
        self.assertIsNone(
            soup.find('div', attrs={'id': 'subscriber-privateteam'}))

    def _createPrivateMergeProposalVotes(self):
        private_reviewer = self.factory.makeTeam(
            name="privateteam", visibility=PersonVisibility.PRIVATE)
        product = self.factory.makeProduct()
        branch = self.factory.makeProductBranch(product=product)
        target_branch = self.factory.makeProductBranch(product=product)
        with person_logged_in(branch.owner):
            self.factory.makeBranchMergeProposal(
                source_branch=branch, target_branch=target_branch,
                reviewer=removeSecurityProxy(private_reviewer))
        return branch

    def test_view_branch_with_private_reviewer(self):
        # A branch with a private reviewer is rendered.
        branch = self._createPrivateMergeProposalVotes()
        # Ensure the branch reviewers are rendered.
        url = canonical_url(branch, rootsite='code')
        user = self.factory.makePerson()
        browser = self._getBrowser(user)
        browser.open(url)
        soup = BeautifulSoup(browser.contents)
        reviews_list = soup.find('dl', attrs={'class': 'reviews'})
        self.assertIsNotNone(reviews_list.find('a', text='Privateteam'))

    def test_anonymous_view_branch_with_private_reviewer(self):
        # A branch with a private reviewer is rendered.
        branch = self._createPrivateMergeProposalVotes()
        # Viewing the branch doesn't show the private reviewers.
        url = canonical_url(branch, rootsite='code')
        browser = self._getBrowser()
        browser.open(url)
        soup = BeautifulSoup(browser.contents)
        reviews_list = soup.find('dl', attrs={'class': 'reviews'})
        self.assertIsNone(reviews_list.find('a', text='Privateteam'))

    def test_unsubscribe_private_branch(self):
        # Unsubscribing from a branch with a policy grant still allows the
        # branch to be seen.
        product = self.factory.makeProduct()
        owner = self.factory.makePerson()
        subscriber = self.factory.makePerson()
        [ap] = getUtility(IAccessPolicySource).find(
            [(product, InformationType.USERDATA)])
        self.factory.makeAccessPolicyGrant(
            policy=ap, grantee=subscriber, grantor=product.owner)
        branch = self.factory.makeBranch(
            product=product, owner=owner,
            information_type=InformationType.USERDATA)
        with person_logged_in(owner):
            self.factory.makeBranchSubscription(branch, subscriber, owner)
            base_url = canonical_url(branch, rootsite='code')
            expected_title = '%s : Code : %s' % (
                branch.name, product.displayname)
        url = '%s/+subscription/%s' % (base_url, subscriber.name)
        browser = self._getBrowser(user=subscriber)
        browser.open(url)
        browser.getControl('Unsubscribe').click()
        self.assertEqual(base_url, browser.url)
        self.assertEqual(expected_title, browser.title)

    def test_unsubscribe_private_branch_no_access(self):
        # Unsubscribing from a branch with no access will redirect to the
        # context of the branch.
        product = self.factory.makeProduct()
        owner = self.factory.makePerson()
        subscriber = self.factory.makePerson()
        branch = self.factory.makeBranch(
            product=product, owner=owner,
            information_type=InformationType.USERDATA)
        with person_logged_in(owner):
            self.factory.makeBranchSubscription(branch, subscriber, owner)
            base_url = canonical_url(branch, rootsite='code')
            product_url = canonical_url(product, rootsite='code')
        url = '%s/+subscription/%s' % (base_url, subscriber.name)
        expected_title = "Code : %s" % product.displayname
        browser = self._getBrowser(user=subscriber)
        browser.open(url)
        browser.getControl('Unsubscribe').click()
        self.assertEqual(product_url, browser.url)
        self.assertEqual(expected_title, browser.title)


class TestBranchReviewerEditView(TestCaseWithFactory):
    """Test the BranchReviewerEditView view."""

    layer = DatabaseFunctionalLayer

    def test_initial_reviewer_not_set(self):
        # If the reviewer is not set, the field is populated with the owner of
        # the branch.
        branch = self.factory.makeAnyBranch()
        self.assertIs(None, branch.reviewer)
        view = create_view(branch, '+reviewer')
        self.assertEqual(branch.owner, view.initial_values['reviewer'])

    def test_initial_reviewer_set(self):
        # If the reviewer has been set, it is shown as the initial value.
        branch = self.factory.makeAnyBranch()
        login_person(branch.owner)
        branch.reviewer = self.factory.makePerson()
        view = create_view(branch, '+reviewer')
        self.assertEqual(branch.reviewer, view.initial_values['reviewer'])

    def test_set_reviewer(self):
        # Test setting the reviewer.
        branch = self.factory.makeAnyBranch()
        reviewer = self.factory.makePerson()
        login_person(branch.owner)
        view = create_initialized_view(branch, '+reviewer')
        view.change_action.success({'reviewer': reviewer})
        self.assertEqual(reviewer, branch.reviewer)
        # Last modified has been updated.
        self.assertSqlAttributeEqualsDate(
            branch, 'date_last_modified', UTC_NOW)

    def test_set_reviewer_as_owner_clears_reviewer(self):
        # If the reviewer is set to be the branch owner, the review field is
        # cleared in the database.
        branch = self.factory.makeAnyBranch()
        login_person(branch.owner)
        branch.reviewer = self.factory.makePerson()
        view = create_initialized_view(branch, '+reviewer')
        view.change_action.success({'reviewer': branch.owner})
        self.assertIs(None, branch.reviewer)
        # Last modified has been updated.
        self.assertSqlAttributeEqualsDate(
            branch, 'date_last_modified', UTC_NOW)

    def test_set_reviewer_to_same_does_not_update_last_modified(self):
        # If the user has set the reviewer to be same and clicked on save,
        # then the underlying object hasn't really been changed, so the last
        # modified is not updated.
        modified_date = datetime(2007, 1, 1, tzinfo=pytz.UTC)
        branch = self.factory.makeAnyBranch(date_created=modified_date)
        view = create_initialized_view(branch, '+reviewer')
        view.change_action.success({'reviewer': branch.owner})
        self.assertIs(None, branch.reviewer)
        # Last modified has not been updated.
        self.assertEqual(modified_date, branch.date_last_modified)


class TestBranchBzrIdentity(TestCaseWithFactory):
    """Test the bzr_identity on the PersonOwnedBranchesView."""

    layer = DatabaseFunctionalLayer

    def test_dev_focus_identity(self):
        # A branch that is a development focus branch, should show using the
        # short name on the listing.
        product = self.factory.makeProduct(name="fooix")
        branch = self.factory.makeProductBranch(product=product)
        # To avoid dealing with admins, just log in the product owner to set
        # the development focus branch.
        login_person(product.owner)
        product.development_focus.branch = branch
        view = create_initialized_view(
            branch.owner, '+ownedbranches', rootsite='code')
        navigator = view.branches()
        [decorated_branch] = navigator.branches
        self.assertEqual("lp://dev/fooix", decorated_branch.bzr_identity)


class TestBranchProposalsVisible(TestCaseWithFactory):
    """Test that the BranchView filters out proposals the user cannot see."""

    layer = DatabaseFunctionalLayer

    def test_public_target(self):
        # If the user can see the target, then there are merges, and the
        # landing_target is available for the template rendering.
        bmp = self.factory.makeBranchMergeProposal()
        branch = bmp.source_branch
        view = create_view(branch, '+index')
        self.assertFalse(view.no_merges)
        [target] = view.landing_targets
        # Check the ids as the target is a DecoratedMergeProposal.
        self.assertEqual(bmp.id, target.id)

    def test_private_target(self):
        # If the target is private, the landing targets should not include it.
        bmp = self.factory.makeBranchMergeProposal()
        branch = bmp.source_branch
        removeSecurityProxy(bmp.target_branch).information_type = (
            InformationType.USERDATA)
        view = create_view(branch, '+index')
        self.assertTrue(view.no_merges)
        self.assertEqual([], view.landing_targets)

    def test_public_source(self):
        # If the user can see the source, then there are merges, and the
        # landing_candidate is available for the template rendering.
        bmp = self.factory.makeBranchMergeProposal()
        branch = bmp.target_branch
        view = create_view(branch, '+index')
        self.assertFalse(view.no_merges)
        [candidate] = view.landing_candidates
        # Check the ids as the target is a DecoratedMergeProposal.
        self.assertEqual(bmp.id, candidate.id)

    def test_private_source(self):
        # If the source is private, the landing candidates should not include
        # it.
        bmp = self.factory.makeBranchMergeProposal()
        branch = bmp.target_branch
        removeSecurityProxy(bmp.source_branch).information_type = (
            InformationType.USERDATA)
        view = create_view(branch, '+index')
        self.assertTrue(view.no_merges)
        self.assertEqual([], view.landing_candidates)

    def test_prerequisite_public(self):
        # If the branch is a prerequisite branch for a public proposals, then
        # there are merges.
        branch = self.factory.makeProductBranch()
        bmp = self.factory.makeBranchMergeProposal(prerequisite_branch=branch)
        view = create_view(branch, '+index')
        self.assertFalse(view.no_merges)
        [proposal] = view.dependent_branches
        self.assertEqual(bmp, proposal)

    def test_prerequisite_private(self):
        # If the branch is a prerequisite branch where either the source or
        # the target is private, then the dependent_branches are not shown.
        branch = self.factory.makeProductBranch()
        bmp = self.factory.makeBranchMergeProposal(prerequisite_branch=branch)
        removeSecurityProxy(bmp.source_branch).information_type = (
            InformationType.USERDATA)
        view = create_view(branch, '+index')
        self.assertTrue(view.no_merges)
        self.assertEqual([], view.dependent_branches)


class TestBranchRootContext(TestCaseWithFactory):
    """Test the adaptation of IBranch to IRootContext."""

    layer = DatabaseFunctionalLayer

    def test_personal_branch(self):
        # The root context of a personal branch is the person.
        branch = self.factory.makePersonalBranch()
        root_context = IRootContext(branch)
        self.assertEqual(branch.owner, root_context)

    def test_package_branch(self):
        # The root context of a package branch is the distribution.
        branch = self.factory.makePackageBranch()
        root_context = IRootContext(branch)
        self.assertEqual(branch.distroseries.distribution, root_context)

    def test_product_branch(self):
        # The root context of a product branch is the product.
        branch = self.factory.makeProductBranch()
        root_context = IRootContext(branch)
        self.assertEqual(branch.product, root_context)


class TestBranchEditView(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_branch_target_widget_renders_junk(self):
        # The branch target widget renders correctly for a junk branch.
        person = self.factory.makePerson()
        branch = self.factory.makePersonalBranch(owner=person)
        login_person(person)
        view = create_initialized_view(branch, name='+edit')
        self.assertEqual('personal', view.widgets['target'].default_option)

    def test_branch_target_widget_renders_product(self):
        # The branch target widget renders correctly for a product branch.
        person = self.factory.makePerson()
        product = self.factory.makeProduct()
        branch = self.factory.makeProductBranch(product=product, owner=person)
        login_person(person)
        view = create_initialized_view(branch, name='+edit')
        self.assertEqual('product', view.widgets['target'].default_option)
        self.assertEqual(
            product.name, view.widgets['target'].product_widget.selected_value)

    def test_no_branch_target_widget_for_source_package_branch(self):
        # The branch target widget is not rendered for a package branch.
        person = self.factory.makePerson()
        branch = self.factory.makePackageBranch(owner=person)
        login_person(person)
        view = create_initialized_view(branch, name='+edit')
        self.assertIsNone(view.widgets.get('target'))

    def test_branch_target_widget_saves_junk(self):
        # The branch target widget can retarget to a junk branch.
        person = self.factory.makePerson()
        product = self.factory.makeProduct()
        branch = self.factory.makeProductBranch(product=product, owner=person)
        login_person(person)
        form = {
            'field.target': 'personal',
            'field.actions.change': 'Change Branch',
        }
        view = create_initialized_view(branch, name='+edit', form=form)
        self.assertEqual(person, branch.target.context)
        self.assertEqual(1, len(view.request.response.notifications))
        self.assertEqual(
            'This branch is now a personal branch for %s (%s)'
                % (person.displayname, person.name),
            view.request.response.notifications[0].message)

    def test_save_to_different_junk(self):
        # The branch target widget can retarget to a junk branch.
        person = self.factory.makePerson()
        branch = self.factory.makePersonalBranch(owner=person)
        new_owner = self.factory.makeTeam(name='newowner', members=[person])
        login_person(person)
        form = {
            'field.target': 'personal',
            'field.owner': 'newowner',
            'field.actions.change': 'Change Branch',
        }
        view = create_initialized_view(branch, name='+edit', form=form)
        self.assertEqual(new_owner, branch.target.context)
        self.assertEqual(1, len(view.request.response.notifications))
        self.assertEqual(
            'The branch owner has been changed to Newowner (newowner)',
            view.request.response.notifications[0].message)

    def test_branch_target_widget_saves_product(self):
        # The branch target widget can retarget to a product branch.
        person = self.factory.makePerson()
        branch = self.factory.makePersonalBranch(owner=person)
        product = self.factory.makeProduct()
        login_person(person)
        form = {
            'field.target': 'product',
            'field.target.product': product.name,
            'field.actions.change': 'Change Branch',
        }
        view = create_initialized_view(branch, name='+edit', form=form)
        self.assertEqual(product, branch.target.context)
        self.assertEqual(
            'The branch target has been changed to %s (%s)'
                % (product.displayname, product.name),
            view.request.response.notifications[0].message)

    def test_forbidden_target_is_error(self):
        # An error is displayed if a branch is saved with a target that is not
        # allowed by the sharing policy.
        owner = self.factory.makePerson()
        initial_target = self.factory.makeProduct()
        self.factory.makeProduct(
            name="commercial", owner=owner,
            branch_sharing_policy=BranchSharingPolicy.PROPRIETARY)
        branch = self.factory.makeProductBranch(
            owner=owner, product=initial_target,
            information_type=InformationType.PUBLIC)
        browser = self.getUserBrowser(
            canonical_url(branch) + '/+edit', user=owner)
        browser.getControl(name="field.target.product").value = "commercial"
        browser.getControl("Change Branch").click()
        self.assertThat(
            browser.contents,
            Contains('Public branches are not allowed for target Commercial.'))
        with person_logged_in(owner):
            self.assertEquals(initial_target, branch.target.context)

    def test_information_type_in_ui(self):
        # The information_type of a branch can be changed via the UI by an
        # authorised user.
        person = self.factory.makePerson()
        branch = self.factory.makeProductBranch(owner=person)
        admins = getUtility(ILaunchpadCelebrities).admin
        admin = admins.teamowner
        browser = self.getUserBrowser(
            canonical_url(branch) + '/+edit', user=admin)
        browser.getControl("Private", index=1).click()
        browser.getControl("Change Branch").click()
        with person_logged_in(person):
            self.assertEqual(InformationType.USERDATA, branch.information_type)

    def test_can_not_change_privacy_of_stacked_on_private(self):
        # The privacy field is not shown if the branch is stacked on a
        # private branch.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        stacked_on = self.factory.makeBranch(
            product=product, owner=owner,
            information_type=InformationType.USERDATA)
        branch = self.factory.makeBranch(
            product=product, owner=owner, stacked_on=stacked_on)
        with person_logged_in(owner):
            browser = self.getUserBrowser(
                canonical_url(branch) + '/+edit', user=owner)
        self.assertRaises(LookupError, browser.getControl, "Information Type")

    def test_edit_view_ajax_render(self):
        # An information type change request is processed as expected when an
        # XHR request is made to the view.
        person = self.factory.makePerson()
        branch = self.factory.makeProductBranch(owner=person)

        extra = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        request = LaunchpadTestRequest(
            method='POST', form={
                'field.actions.change': 'Change Branch',
                'field.information_type': 'PUBLICSECURITY'},
            **extra)
        with person_logged_in(person):
            view = create_initialized_view(
                branch, name='+edit-information-type',
                request=request, principal=person)
            request.traversed_objects = [person, branch.product, branch, view]
            result = view.render()
            self.assertEqual('', result)
            self.assertEqual(
                branch.information_type, InformationType.PUBLICSECURITY)


class TestBranchEditViewInformationTypes(TestCaseWithFactory):
    """Tests for BranchEditView.getInformationTypesToShow."""

    layer = DatabaseFunctionalLayer

    def assertShownTypes(self, types, branch, user=None):
        if user is None:
            user = removeSecurityProxy(branch).owner
        with person_logged_in(user):
            view = create_initialized_view(branch, '+edit', user=user)
            self.assertContentEqual(types, view.getInformationTypesToShow())

    def test_public_branch(self):
        # A normal public branch on a public project can be any information
        # type except embargoed and proprietary.
        # The model doesn't enforce this, so it's just a UI thing.
        branch = self.factory.makeBranch(
            information_type=InformationType.PUBLIC)
        self.assertShownTypes(
            [InformationType.PUBLIC, InformationType.PUBLICSECURITY,
             InformationType.PRIVATESECURITY, InformationType.USERDATA],
            branch)

    def test_branch_with_disallowed_type(self):
        # We don't force branches with a disallowed type (eg. Proprietary on a
        # non-commercial project) to change, so the current type is
        # shown.
        product = self.factory.makeProduct()
        self.factory.makeAccessPolicy(pillar=product)
        branch = self.factory.makeBranch(
            product=product, information_type=InformationType.PROPRIETARY)
        self.assertShownTypes(
            [InformationType.PUBLIC, InformationType.PUBLICSECURITY,
             InformationType.PRIVATESECURITY, InformationType.USERDATA,
             InformationType.PROPRIETARY], branch)

    def test_stacked_on_private(self):
        # A branch stacked on a private branch has its choices limited
        # to the current type and the stacked-on type.
        product = self.factory.makeProduct()
        stacked_on_branch = self.factory.makeBranch(
            product=product, information_type=InformationType.USERDATA)
        branch = self.factory.makeBranch(
            product=product, stacked_on=stacked_on_branch,
            owner=product.owner,
            information_type=InformationType.PRIVATESECURITY)
        self.assertShownTypes(
            [InformationType.PRIVATESECURITY, InformationType.USERDATA],
            branch)

    def test_branch_for_project_with_embargoed_and_proprietary(self):
        # Branches for commercial projects which have a policy of embargoed or
        # proprietary allow only embargoed and proprietary types.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        self.factory.makeCommercialSubscription(product=product)
        with person_logged_in(owner):
            product.setBranchSharingPolicy(
                BranchSharingPolicy.EMBARGOED_OR_PROPRIETARY)
            branch = self.factory.makeBranch(
                product=product, owner=owner,
                information_type=InformationType.PROPRIETARY)
        self.assertShownTypes(
            [InformationType.EMBARGOED, InformationType.PROPRIETARY], branch)

    def test_branch_for_project_with_proprietary(self):
        # Branches for commercial projects which have a policy of proprietary
        # allow only the proprietary type.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(owner=owner)
        self.factory.makeCommercialSubscription(product=product)
        with person_logged_in(owner):
            product.setBranchSharingPolicy(BranchSharingPolicy.PROPRIETARY)
            branch = self.factory.makeBranch(
                product=product, owner=owner,
                information_type=InformationType.PROPRIETARY)
        self.assertShownTypes([InformationType.PROPRIETARY], branch)


class TestBranchUpgradeView(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def test_upgrade_branch_action_cannot_upgrade(self):
        # A nice error is displayed if a branch cannot be upgraded.
        branch = self.factory.makePersonalBranch(
        branch_format=BranchFormat.BZR_BRANCH_6,
        repository_format=RepositoryFormat.BZR_CHK_2A)
        login_person(branch.owner)
        self.addCleanup(logout)
        branch.requestUpgrade(branch.owner)
        view = create_initialized_view(branch, '+upgrade')
        view.upgrade_branch_action.success({})
        self.assertEqual(1, len(view.request.notifications))
        self.assertEqual(
            'An upgrade is already in progress for branch %s.' %
            branch.bzr_identity, view.request.notifications[0].message)


class TestBranchPrivacyPortlet(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def test_information_type_in_ui(self):
        # The privacy portlet shows the information_type.
        owner = self.factory.makePerson()
        branch = self.factory.makeBranch(
            owner=owner, information_type=InformationType.USERDATA)
        with person_logged_in(owner):
            view = create_initialized_view(branch, '+portlet-privacy')
            edit_url = '/' + branch.unique_name + '/+edit-information-type'
            soup = BeautifulSoup(view.render())
        information_type = soup.find('strong')
        description = soup.find('div', id='information-type-description')
        self.assertEqual(
            InformationType.USERDATA.title, information_type.renderContents())
        self.assertTextMatchesExpressionIgnoreWhitespace(
            InformationType.USERDATA.description, description.renderContents())
        self.assertIsNotNone(
            soup.find('a', id='privacy-link', attrs={'href': edit_url}))
