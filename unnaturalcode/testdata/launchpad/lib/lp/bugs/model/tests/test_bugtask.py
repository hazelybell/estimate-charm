# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from collections import namedtuple
from datetime import datetime
from operator import attrgetter
import subprocess
import unittest

from lazr.lifecycle.event import ObjectModifiedEvent
from lazr.lifecycle.snapshot import Snapshot
from lazr.restfulclient.errors import Unauthorized
from storm.store import Store
from testtools.matchers import Equals
from testtools.testcase import ExpectedException
import transaction
from zope.component import getUtility
from zope.event import notify
from zope.interface import providedBy
from zope.security.interfaces import Unauthorized as ZopeUnAuthorized
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import (
    InformationType,
    ServiceUsage,
    )
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.bugs.interfaces.bug import (
    CreateBugParams,
    IBug,
    IBugSet,
    )
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    BugTaskStatusSearch,
    CannotDeleteBugtask,
    DB_UNRESOLVED_BUGTASK_STATUSES,
    IBugTaskSet,
    RESOLVED_BUGTASK_STATUSES,
    UNRESOLVED_BUGTASK_STATUSES,
    UserCannotEditBugTaskMilestone,
    )
from lp.bugs.interfaces.bugtasksearch import BugTaskSearchParams
from lp.bugs.interfaces.bugwatch import IBugWatchSet
from lp.bugs.model.bugtask import (
    bug_target_from_key,
    bug_target_to_key,
    BugTask,
    IllegalTarget,
    validate_new_target,
    validate_target,
    )
from lp.bugs.scripts.bugtasktargetnamecaches import (
    BugTaskTargetNameCacheUpdater,
    )
from lp.bugs.tests.bug import create_old_bug
from lp.registry.enums import (
    BugSharingPolicy,
    TeamMembershipPolicy,
    )
from lp.registry.interfaces.accesspolicy import (
    IAccessArtifactGrantSource,
    IAccessArtifactSource,
    IAccessPolicyGrantSource,
    IAccessPolicySource,
    )
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.distributionsourcepackage import (
    IDistributionSourcePackage,
    )
from lp.registry.interfaces.distroseries import IDistroSeriesSet
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.product import IProductSet
from lp.registry.interfaces.projectgroup import IProjectGroupSet
from lp.registry.interfaces.sourcepackage import ISourcePackage
from lp.registry.model.sourcepackage import SourcePackage
from lp.registry.tests.test_accesspolicy import get_policies_for_artifact
from lp.services.database.sqlbase import (
    flush_database_caches,
    flush_database_updates,
    )
from lp.services.features.testing import FeatureFixture
from lp.services.job.tests import block_on_job
from lp.services.log.logger import FakeLogger
from lp.services.propertycache import get_property_cache
from lp.services.searchbuilder import any
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.interfaces import ILaunchBag
from lp.soyuz.interfaces.archive import ArchivePurpose
from lp.testing import (
    admin_logged_in,
    ANONYMOUS,
    EventRecorder,
    feature_flags,
    login,
    login_celebrity,
    login_person,
    logout,
    person_logged_in,
    set_feature_flag,
    StormStatementRecorder,
    TestCase,
    TestCaseWithFactory,
    ws_object,
    )
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import (
    AppServerLayer,
    CeleryJobLayer,
    DatabaseFunctionalLayer,
    )
from lp.testing.matchers import HasQueryCount


BugData = namedtuple("BugData", ['owner', 'distro', 'distro_release',
'source_package', 'bug', 'generic_task', 'series_task', ])

ConjoinedData = namedtuple("ConjoinedData", ['alsa_utils', 'generic_task',
    'devel_focus_task'])


class TestBugTaskAdaptation(TestCase):
    """Verify bugtask adaptation."""

    layer = DatabaseFunctionalLayer

    def test_bugtask_adaptation(self):
        """An IBugTask can be adapted to an IBug"""
        login('foo.bar@canonical.com')
        bugtask_four = getUtility(IBugTaskSet).get(4)
        bug = IBug(bugtask_four)
        self.assertEqual(bug.title,
                         u'Firefox does not support SVG')


class TestBugTaskCreation(TestCaseWithFactory):
    """Test BugTaskSet creation methods."""

    layer = DatabaseFunctionalLayer

    def test_upstream_task(self):
        """A bug that has to be fixed in an upstream product."""
        bugtaskset = getUtility(IBugTaskSet)
        bug_one = getUtility(IBugSet).get(1)
        mark = getUtility(IPersonSet).getByEmail('mark@example.com')
        evolution = getUtility(IProductSet).get(5)

        upstream_task = bugtaskset.createTask(
            bug_one, mark, evolution,
            status=BugTaskStatus.NEW,
            importance=BugTaskImportance.MEDIUM)

        self.assertEqual(upstream_task.product, evolution)
        self.assertEqual(upstream_task.target, evolution)

    def test_distro_specific_bug(self):
        """A bug that needs to be fixed in a specific distro."""
        bugtaskset = getUtility(IBugTaskSet)
        bug_one = getUtility(IBugSet).get(1)
        mark = getUtility(IPersonSet).getByEmail('mark@example.com')

        a_distro = self.factory.makeDistribution(name='tubuntu')
        distro_task = bugtaskset.createTask(
            bug_one, mark, a_distro,
            status=BugTaskStatus.NEW,
            importance=BugTaskImportance.MEDIUM)

        self.assertEqual(distro_task.distribution, a_distro)
        self.assertEqual(distro_task.target, a_distro)

    def test_distroseries_specific_bug(self):
        """A bug that needs to be fixed in a specific distro series

        These tasks are used for release management and backporting
        """
        bugtaskset = getUtility(IBugTaskSet)
        bug_one = getUtility(IBugSet).get(1)
        mark = getUtility(IPersonSet).getByEmail('mark@example.com')
        warty = getUtility(IDistroSeriesSet).get(1)

        distro_series_task = bugtaskset.createTask(
            bug_one, mark, warty,
            status=BugTaskStatus.NEW, importance=BugTaskImportance.MEDIUM)

        self.assertEqual(distro_series_task.distroseries, warty)
        self.assertEqual(distro_series_task.target, warty)

    def test_createmany_bugtasks(self):
        """We can create a set of bugtasks around different targets"""
        bugtaskset = getUtility(IBugTaskSet)
        mark = getUtility(IPersonSet).getByEmail('mark@example.com')
        evolution = getUtility(IProductSet).get(5)
        warty = getUtility(IDistroSeriesSet).get(1)
        bug_many = getUtility(IBugSet).get(4)

        a_distro = self.factory.makeDistribution(name='tubuntu')
        taskset = bugtaskset.createManyTasks(
            bug_many, mark,
            [evolution, a_distro, warty],
            status=BugTaskStatus.FIXRELEASED)
        tasks = [(t.product, t.distribution, t.distroseries) for t in taskset]
        tasks.sort()

        self.assertEqual(tasks[0][2], warty)
        self.assertEqual(tasks[1][1], a_distro)
        self.assertEqual(tasks[2][0], evolution)

    def test_accesspolicyartifacts_updated(self):
        # createManyTasks updates the AccessPolicyArtifacts related
        # to the bug.
        new_product = self.factory.makeProduct()
        bug = self.factory.makeBug(
            information_type=InformationType.USERDATA)

        with admin_logged_in():
            old_product = bug.default_bugtask.product
            getUtility(IBugTaskSet).createManyTasks(
                bug, bug.owner, [new_product])

        expected_policies = getUtility(IAccessPolicySource).find([
            (new_product, InformationType.USERDATA),
            (old_product, InformationType.USERDATA),
            ])
        self.assertContentEqual(
            expected_policies, get_policies_for_artifact(bug))


class TestBugTaskCreationPackageComponent(TestCaseWithFactory):
    """IBugTask contains a convenience method to look up archive component

    Obviously, it only applies to tasks that specify package information.
    """

    layer = DatabaseFunctionalLayer

    def test_doesnot_apply(self):
        """Tasks without package information should return None"""
        login('foo.bar@canonical.com')
        bug_one = getUtility(IBugSet).get(1)
        bugtaskset = getUtility(IBugTaskSet)
        evolution = getUtility(IProductSet).get(5)
        mark = getUtility(IPersonSet).getByEmail('mark@example.com')
        productset = getUtility(IProductSet)
        warty = getUtility(IDistroSeriesSet).get(1)

        upstream_task = bugtaskset.createTask(
            bug_one, mark, evolution,
            status=BugTaskStatus.NEW,
            importance=BugTaskImportance.MEDIUM)
        self.assertEqual(upstream_task.getPackageComponent(), None)

        a_distro = self.factory.makeDistribution(name='tubuntu')
        distro_task = bugtaskset.createTask(
            bug_one, mark, a_distro,
            status=BugTaskStatus.NEW,
            importance=BugTaskImportance.MEDIUM)
        self.assertEqual(distro_task.getPackageComponent(), None)

        distro_series_task = bugtaskset.createTask(
            bug_one, mark, warty,
            status=BugTaskStatus.NEW, importance=BugTaskImportance.MEDIUM)
        self.assertEqual(distro_series_task.getPackageComponent(), None)

        firefox = productset['firefox']
        firefox_1_0 = firefox.getSeries("1.0")
        productseries_task = bugtaskset.createTask(bug_one, mark, firefox_1_0)
        self.assertEqual(productseries_task.getPackageComponent(), None)

        debian_ff_task = bugtaskset.get(4)
        self.assertEqual(debian_ff_task.getPackageComponent(), None)

    def test_does_apply(self):
        """Tasks with package information return the archive component.

        And it only applies to tasks whose packages which are published in
        IDistribution.currentseries (for bugtasks on IDistributions) or the
        bugtask's series (for bugtasks on IDistroSeries)
        """
        login('foo.bar@canonical.com')
        bugtaskset = getUtility(IBugTaskSet)
        ubuntu_linux_task = bugtaskset.get(25)
        self.assertTrue(
            IDistributionSourcePackage.providedBy(ubuntu_linux_task.target))
        self.assertEqual(ubuntu_linux_task.getPackageComponent().name, 'main')

        distro_series_sp_task = bugtaskset.get(16)
        self.assertEqual(distro_series_sp_task.getPackageComponent().name,
                         'main')


class TestBugTaskTargets(TestCase):
    """Verify we handle various bugtask targets correctly"""

    layer = DatabaseFunctionalLayer

    def test_bugtask_target_productseries(self):
        """The 'target' of a task can be a product series"""
        login('foo.bar@canonical.com')
        bugtaskset = getUtility(IBugTaskSet)
        productset = getUtility(IProductSet)
        bug_one = getUtility(IBugSet).get(1)
        mark = getUtility(IPersonSet).getByEmail('mark@example.com')

        firefox = productset['firefox']
        firefox_1_0 = firefox.getSeries("1.0")
        productseries_task = bugtaskset.createTask(bug_one, mark, firefox_1_0)

        self.assertEqual(productseries_task.target, firefox_1_0)
        # getPackageComponent only applies to tasks that specify package info.
        self.assertEqual(productseries_task.getPackageComponent(), None)

    def test_bugtask_target_distro_sourcepackage(self):
        """The 'target' of a task can be a distro sourcepackage"""
        login('foo.bar@canonical.com')
        bugtaskset = getUtility(IBugTaskSet)

        debian_ff_task = bugtaskset.get(4)
        self.assertTrue(
            IDistributionSourcePackage.providedBy(debian_ff_task.target))

        target = debian_ff_task.target
        self.assertEqual(target.distribution.name, u'debian')
        self.assertEqual(target.sourcepackagename.name, u'mozilla-firefox')

        ubuntu_linux_task = bugtaskset.get(25)
        self.assertTrue(
            IDistributionSourcePackage.providedBy(ubuntu_linux_task.target))

        target = ubuntu_linux_task.target
        self.assertEqual(target.distribution.name, u'ubuntu')
        self.assertEqual(target.sourcepackagename.name, u'linux-source-2.6.15')

    def test_bugtask_target_distroseries_sourcepackage(self):
        """The 'target' of a task can be a distroseries sourcepackage"""
        login('foo.bar@canonical.com')
        bugtaskset = getUtility(IBugTaskSet)
        distro_series_sp_task = bugtaskset.get(16)

        expected_target = SourcePackage(
            distroseries=distro_series_sp_task.distroseries,
            sourcepackagename=distro_series_sp_task.sourcepackagename)
        got_target = distro_series_sp_task.target
        self.assertTrue(
            ISourcePackage.providedBy(distro_series_sp_task.target))
        self.assertEqual(got_target.distroseries,
                         expected_target.distroseries)
        self.assertEqual(got_target.sourcepackagename,
                         expected_target.sourcepackagename)


class TestBugTaskTargetName(TestCase):
    """Verify our targetdisplayname and targetname are correct."""

    layer = DatabaseFunctionalLayer

    def test_targetname_distribution(self):
        """The distribution name will be concat'd"""
        login('foo.bar@canonical.com')
        bugtaskset = getUtility(IBugTaskSet)
        bugtask = bugtaskset.get(17)

        self.assertEqual(bugtask.bugtargetdisplayname,
            u'mozilla-firefox (Ubuntu)')
        self.assertEqual(bugtask.bugtargetname,
            u'mozilla-firefox (Ubuntu)')

    def test_targetname_series_product(self):
        """The targetname for distro series/product versions will be name of
        source package or binary package. """
        login('foo.bar@canonical.com')
        bugtaskset = getUtility(IBugTaskSet)
        bugtask = bugtaskset.get(2)

        self.assertEqual(bugtask.bugtargetdisplayname, u'Mozilla Firefox')
        self.assertEqual(bugtask.bugtargetname, u'firefox')


class TestEditingBugTask(TestCase):
    """Verify out editing functionality of bugtasks."""

    layer = DatabaseFunctionalLayer

    def test_edit_upstream(self):
        """You cannot edit upstream tasks as ANONYMOUS"""
        login('foo.bar@canonical.com')
        bugtaskset = getUtility(IBugTaskSet)
        bug_one = getUtility(IBugSet).get(1)
        mark = getUtility(IPersonSet).getByEmail('mark@example.com')

        evolution = getUtility(IProductSet).get(5)
        upstream_task = bugtaskset.createTask(
            bug_one, mark, evolution,
            status=BugTaskStatus.NEW,
            importance=BugTaskImportance.MEDIUM)

        # An anonymous user cannot edit the bugtask.
        login(ANONYMOUS)
        with ExpectedException(ZopeUnAuthorized, ''):
            upstream_task.transitionToStatus(BugTaskStatus.CONFIRMED,
                                             getUtility(ILaunchBag.user))

        # A logged in user can edit the upstream bugtask.
        login('jeff.waugh@ubuntulinux.com')
        upstream_task.transitionToStatus(BugTaskStatus.FIXRELEASED,
                                         getUtility(ILaunchBag).user)

    def test_edit_distro_bugtasks(self):
        """Any logged-in user can edit tasks filed on distros

        However not if the bug is not marked private.
        So, as an anonymous user, we cannot edit anything:
        """
        login(ANONYMOUS)

        bugtaskset = getUtility(IBugTaskSet)
        distro_task = bugtaskset.get(25)

        # Anonymous cannot change the status.
        with ExpectedException(ZopeUnAuthorized):
            distro_task.transitionToStatus(BugTaskStatus.FIXRELEASED,
                                           getUtility(ILaunchBag).user)

        # Anonymous cannot change the assignee.
        sample_person = getUtility(IPersonSet).getByEmail('test@canonical.com')
        with ExpectedException(ZopeUnAuthorized):
            distro_task.transitionToAssignee(sample_person)

        login('test@canonical.com')

        distro_task.transitionToStatus(BugTaskStatus.FIXRELEASED,
                                       getUtility(ILaunchBag).user)
        distro_task.transitionToAssignee(sample_person)


class TestBugTaskTags(TestCase):
    """List of bugtasks often need to display related tasks."""

    layer = DatabaseFunctionalLayer

    def test_getting_tags_from_bugs(self):
        """Tags are related to bugtasks via bugs.

        BugTaskSet has a method getBugTaskTags that can calculate the tags in
        one query.
        """
        login('foo.bar@canonical.com')
        bug_two = getUtility(IBugSet).get(2)
        some_bugtask = bug_two.bugtasks[0]
        bug_three = getUtility(IBugSet).get(3)
        another_bugtask = bug_three.bugtasks[0]

        some_bugtask.bug.tags = [u'foo', u'bar']
        another_bugtask.bug.tags = [u'baz', u'bop']
        tags_by_task = getUtility(IBugTaskSet).getBugTaskTags([
            some_bugtask, another_bugtask])

        self.assertEqual(
            tags_by_task,
            {3: [u'bar', u'foo'], 6: [u'baz', u'bop']})


class TestBugTaskBadges(TestCaseWithFactory):

    """Verify getBugTaskBadgeProperties"""

    layer = DatabaseFunctionalLayer

    def test_butask_badges_populated(self):
        """getBugTaskBadgeProperties(), calcs properties for multiple tasks.

        A bug can have certain properties, which results in a badge being
        displayed in bug listings.
        """
        login('foo.bar@canonical.com')

        def get_badge_properties(badge_properties):
            bugtasks = sorted(badge_properties.keys(), key=attrgetter('id'))
            res = []
            for bugtask in bugtasks:
                res.append("Properties for bug %s:" % (bugtask.bug.id))
                for key, value in sorted(badge_properties[bugtask].items()):
                    res.append(" %s: %s" % (key, value))
            return res

        bug_two = getUtility(IBugSet).get(2)
        some_bugtask = bug_two.bugtasks[0]
        bug_three = getUtility(IBugSet).get(3)
        another_bugtask = bug_three.bugtasks[0]
        badge_properties = getUtility(IBugTaskSet).getBugTaskBadgeProperties(
            [some_bugtask, another_bugtask])

        self.assertEqual(get_badge_properties(badge_properties),
           ['Properties for bug 2:',
            ' has_branch: False',
            ' has_patch: False',
            ' has_specification: False',
            'Properties for bug 3:',
            ' has_branch: False',
            ' has_patch: False',
            ' has_specification: False'])

        # a specification gets linked...
        spec = self.factory.makeSpecification()
        spec.linkBug(bug_two)

        # or a branch gets linked to the bug...
        no_priv = getUtility(IPersonSet).getByEmail('no-priv@canonical.com')
        branch = self.factory.makeAnyBranch()
        bug_three.linkBranch(branch, no_priv)

        # the properties for the bugtasks reflect this.
        badge_properties = getUtility(IBugTaskSet).getBugTaskBadgeProperties(
            [some_bugtask, another_bugtask])
        self.assertEqual(get_badge_properties(badge_properties), [
            'Properties for bug 2:',
            ' has_branch: False',
            ' has_patch: False',
            ' has_specification: True',
            'Properties for bug 3:',
            ' has_branch: True',
            ' has_patch: False',
            ' has_specification: False',
        ])


class TestBugTaskPrivacy(TestCaseWithFactory):
    """Verify that the bug is either private or public.

    XXX: rharding 2012-05-14 bug=999298: These tests are ported from doctests
    and do too much work. They should be split into simpler and better unit
    tests.
    """

    layer = DatabaseFunctionalLayer

    def test_bugtask_privacy(self):
        # Let's log in as the user Foo Bar (to be allowed to edit bugs):
        launchbag = getUtility(ILaunchBag)
        login('foo.bar@canonical.com')
        foobar = launchbag.user

        # Mark one of the Firefox bugs private. While we do this, we're also
        # going to subscribe the Ubuntu team to the bug report to help
        # demonstrate later on the interaction between privacy and teams (see
        # the section entitled _Privacy and Team Awareness_):
        bug_upstream_firefox_crashes = getUtility(IBugTaskSet).get(15)

        ubuntu_team = getUtility(IPersonSet).getByEmail('support@ubuntu.com')
        bug_upstream_firefox_crashes.bug.subscribe(ubuntu_team, ubuntu_team)

        old_state = Snapshot(
            bug_upstream_firefox_crashes.bug, providing=IBug)
        self.assertTrue(
            bug_upstream_firefox_crashes.bug.setPrivate(True, foobar))

        bug_set_private = ObjectModifiedEvent(
            bug_upstream_firefox_crashes.bug, old_state,
            ["id", "title", "private"])

        notify(bug_set_private)
        flush_database_updates()

        # If we now login as someone who was neither implicitly nor explicitly
        # subscribed to this bug, e.g. No Privileges Person, they will not be
        # able to access or set properties of the bugtask.
        launchbag = getUtility(ILaunchBag)
        login("no-priv@canonical.com")
        mr_no_privs = launchbag.user

        with ExpectedException(ZopeUnAuthorized):
            bug_upstream_firefox_crashes.status

        with ExpectedException(ZopeUnAuthorized):
            bug_upstream_firefox_crashes.transitionToStatus(
                BugTaskStatus.FIXCOMMITTED, getUtility(ILaunchBag).user)

        # The private bugs will be invisible to No Privileges Person in the
        # search results:
        params = BugTaskSearchParams(
            status=any(BugTaskStatus.NEW, BugTaskStatus.CONFIRMED),
            orderby="id", user=mr_no_privs)
        upstream_mozilla = getUtility(IProductSet).getByName('firefox')
        bugtasks = upstream_mozilla.searchTasks(params)
        self.assertEqual(bugtasks.count(), 3)

        bug_ids = [bt.bug.id for bt in bugtasks]
        self.assertEqual(sorted(bug_ids), [1, 4, 5])

        # We can create an access policy grant on the pillar to which the bug
        # is targeted and No Privileges Person will have access to the private
        # bug
        aps = getUtility(IAccessPolicySource)
        [policy] = aps.find([(upstream_mozilla, InformationType.USERDATA)])
        apgs = getUtility(IAccessPolicyGrantSource)
        apgs.grant([(policy, mr_no_privs, ubuntu_team)])
        bugtasks = upstream_mozilla.searchTasks(params)
        self.assertEqual(bugtasks.count(), 4)

        bug_ids = [bt.bug.id for bt in bugtasks]
        self.assertEqual(sorted(bug_ids), [1, 4, 5, 6])
        apgs.revoke([(policy, mr_no_privs)])

        # Privacy and Priviledged Users
        # Now, we'll log in as Mark Shuttleworth, who was assigned to this bug
        # when it was marked private:
        login("mark@example.com")

        # And note that he can access and set the bugtask attributes:
        self.assertEqual(bug_upstream_firefox_crashes.status.title, 'New')
        bug_upstream_firefox_crashes.transitionToStatus(
            BugTaskStatus.NEW, getUtility(ILaunchBag).user)

        # Privacy and Team Awareness
        # No Privileges Person can't see the private bug, because he's not a
        # subscriber:
        no_priv = getUtility(IPersonSet).getByEmail('no-priv@canonical.com')
        params = BugTaskSearchParams(
            status=any(BugTaskStatus.NEW, BugTaskStatus.CONFIRMED),
            user=no_priv)

        firefox = getUtility(IProductSet)['firefox']
        firefox_bugtasks = firefox.searchTasks(params)
        self.assertEqual(
            [bugtask.bug.id for bugtask in firefox_bugtasks], [1, 4, 5])

        # But if we add No Privileges Person to the Ubuntu Team, and because
        # the Ubuntu Team *is* subscribed to the bug, No Privileges Person
        # will see the private bug.

        login("mark@example.com")
        ubuntu_team.addMember(no_priv, reviewer=ubuntu_team.teamowner)

        login("no-priv@canonical.com")
        params = BugTaskSearchParams(
            status=any(BugTaskStatus.NEW, BugTaskStatus.CONFIRMED),
            user=foobar)

        firefox_bugtasks = firefox.searchTasks(params)
        self.assertEqual(
            [bugtask.bug.id for bugtask in firefox_bugtasks], [1, 4, 5, 6])

        # Privacy and Launchpad Admins
        # ----------------------------
        # Let's log in as Daniel Henrique Debonzi:
        launchbag = getUtility(ILaunchBag)
        login("daniel.debonzi@canonical.com")
        debonzi = launchbag.user

        # The same search as above yields the same result, because Daniel
        # Debonzi is an administrator.
        firefox = getUtility(IProductSet).get(4)
        params = BugTaskSearchParams(status=any(BugTaskStatus.NEW,
                                                BugTaskStatus.CONFIRMED),
                                     user=debonzi)
        firefox_bugtasks = firefox.searchTasks(params)
        self.assertEqual(
            [bugtask.bug.id for bugtask in firefox_bugtasks], [1, 4, 5, 6])

        # Trying to retrieve the bug directly will work fine:
        bug_upstream_firefox_crashes = getUtility(IBugTaskSet).get(15)
        # As will attribute access:
        self.assertEqual(bug_upstream_firefox_crashes.status.title, 'New')

        # And attribute setting:
        bug_upstream_firefox_crashes.transitionToStatus(
            BugTaskStatus.CONFIRMED, getUtility(ILaunchBag).user)
        bug_upstream_firefox_crashes.transitionToStatus(
            BugTaskStatus.NEW, getUtility(ILaunchBag).user)

    def _createBugAndSpecification(self):
        bug = self.factory.makeBug()
        spec = self.factory.makeSpecification(
            information_type=InformationType.PROPRIETARY)
        with person_logged_in(spec.product.owner):
            spec.linkBug(bug)
        return spec, bug     

    def test_bug_specifications_is_filtered_for_anonymous(self):
        spec, bug = self._createBugAndSpecification()
        self.assertContentEqual([], bug.getSpecifications(None))

    def test_bug_specifications_is_filtered_for_unknown_user(self):
        spec, bug = self._createBugAndSpecification()
        self.assertContentEqual(
            [], bug.getSpecifications(self.factory.makePerson()))

    def test_bug_specifications_for_authorised_user(self):
        spec, bug = self._createBugAndSpecification()
        self.assertContentEqual(
            [spec], bug.getSpecifications(spec.product.owner))


class TestBugTaskDelta(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugTaskDelta, self).setUp()
        login('foo.bar@canonical.com')

    def test_get_empty_delta(self):
        # getDelta() should return None when no change has been made.
        bug_task = self.factory.makeBugTask()
        self.assertEqual(bug_task.getDelta(bug_task), None)

    def check_delta(self, bug_task_before, bug_task_after, **expected_delta):
        # Get a delta between one bug task and another, then compare
        # the contents of the delta with expected_delta (a dict, or
        # something that can be dictified). Anything not mentioned in
        # expected_delta is assumed to be None in the delta.
        delta = bug_task_after.getDelta(bug_task_before)
        expected_delta.setdefault('bugtask', bug_task_after)
        names = set(
            name for interface in providedBy(delta) for name in interface)
        for name in names:
            self.assertEquals(getattr(delta, name), expected_delta.get(name))

    def test_get_bugwatch_delta(self):
        # Exercise getDelta() with a change to bugwatch.
        bug_task = self.factory.makeBugTask()
        bug_task_before_modification = Snapshot(
            bug_task, providing=providedBy(bug_task))

        bug_watch = self.factory.makeBugWatch(bug=bug_task.bug)
        bug_task.bugwatch = bug_watch

        self.check_delta(
            bug_task_before_modification, bug_task,
            bugwatch=dict(old=None, new=bug_watch))

    def test_get_target_delta(self):
        # Exercise getDelta() with a change to target.
        user = self.factory.makePerson()
        product = self.factory.makeProduct(owner=user)
        bug_task = self.factory.makeBugTask(target=product)
        bug_task_before_modification = Snapshot(
            bug_task, providing=providedBy(bug_task))

        new_product = self.factory.makeProduct(owner=user)
        bug_task.transitionToTarget(new_product, user)

        self.check_delta(bug_task_before_modification, bug_task,
                         target=dict(old=product, new=new_product))

    def test_get_milestone_delta(self):
        # Exercise getDelta() with a change to milestone.
        user = self.factory.makePerson()
        product = self.factory.makeProduct(owner=user)
        bug_task = self.factory.makeBugTask(target=product)
        bug_task_before_modification = Snapshot(bug_task,
                                                providing=providedBy(bug_task))

        milestone = self.factory.makeMilestone(product=product)
        bug_task.milestone = milestone

        self.check_delta(
            bug_task_before_modification, bug_task,
            milestone=dict(old=None, new=milestone))

    def test_get_assignee_delta(self):
        # Exercise getDelta() with a change to assignee.
        user = self.factory.makePerson()
        product = self.factory.makeProduct(owner=user)
        bug_task = self.factory.makeBugTask(target=product)
        bug_task_before_modification = Snapshot(
            bug_task, providing=providedBy(bug_task))

        bug_task.transitionToAssignee(user)

        self.check_delta(
            bug_task_before_modification, bug_task,
            assignee=dict(old=None, new=user))

    def test_get_status_delta(self):
        # Exercise getDelta() with a change to status.
        user = self.factory.makePerson()
        product = self.factory.makeProduct(owner=user)
        bug_task = self.factory.makeBugTask(target=product)
        bug_task_before_modification = Snapshot(
            bug_task, providing=providedBy(bug_task))

        bug_task.transitionToStatus(BugTaskStatus.FIXRELEASED, user)

        self.check_delta(
            bug_task_before_modification, bug_task,
            status=dict(old=bug_task_before_modification.status,
                        new=bug_task.status))

    def test_get_importance_delta(self):
        # Exercise getDelta() with a change to importance.
        user = self.factory.makePerson()
        product = self.factory.makeProduct(owner=user)
        bug_task = self.factory.makeBugTask(target=product)
        bug_task_before_modification = Snapshot(
            bug_task, providing=providedBy(bug_task))

        bug_task.transitionToImportance(BugTaskImportance.HIGH, user)

        self.check_delta(
            bug_task_before_modification, bug_task,
            importance=dict(old=bug_task_before_modification.importance,
                            new=bug_task.importance))


class TestSimilarBugs(TestCaseWithFactory):
    """It's possible to get a list of similar bugs."""

    layer = DatabaseFunctionalLayer

    def _setupFirefoxBugTask(self):
        """Helper to init the firefox bugtask bits."""
        login('foo.bar@canonical.com')
        firefox = getUtility(IProductSet).getByName("firefox")
        new_ff_bug = self.factory.makeBug(target=firefox, title="Firefox")
        ff_bugtask = new_ff_bug.bugtasks[0]
        return firefox, new_ff_bug, ff_bugtask

    def test_access_similar_bugs(self):
        """The similar bugs property returns a list of similar bugs."""
        firefox, new_ff_bug, ff_bugtask = self._setupFirefoxBugTask()
        sample_person = getUtility(IPersonSet).getByEmail('test@canonical.com')
        similar_bugs = ff_bugtask.findSimilarBugs(user=sample_person)
        similar_bugs = sorted(similar_bugs, key=attrgetter('id'))

        self.assertEqual(similar_bugs[0].id, 1)
        self.assertEqual(similar_bugs[0].title, 'Firefox does not support SVG')
        self.assertEqual(similar_bugs[1].id, 5)
        self.assertEqual(
            similar_bugs[1].title,
            'Firefox install instructions should be complete')

    def test_similar_bugs_for_distribution(self):
        """This also works for distributions."""
        firefox, new_ff_bug, ff_bugtask = self._setupFirefoxBugTask()
        sample_person = getUtility(IPersonSet).getByEmail('test@canonical.com')
        ubuntu = getUtility(IDistributionSet).getByName('ubuntu')
        ubuntu_bugtask = self.factory.makeBugTask(bug=new_ff_bug,
                                                  target=ubuntu)
        similar_bugs = ubuntu_bugtask.findSimilarBugs(user=sample_person)
        similar_bugs = sorted(similar_bugs, key=attrgetter('id'))

        self.assertEqual(similar_bugs[0].id, 1)
        self.assertEqual(similar_bugs[0].title, 'Firefox does not support SVG')

    def test_with_sourcepackages(self):
        """This also works for SourcePackages."""
        firefox, new_ff_bug, ff_bugtask = self._setupFirefoxBugTask()
        sample_person = getUtility(IPersonSet).getByEmail('test@canonical.com')
        ubuntu = getUtility(IDistributionSet).getByName('ubuntu')
        a_ff_bug = self.factory.makeBug(target=firefox, title="a Firefox")
        firefox_package = ubuntu.getSourcePackage('mozilla-firefox')
        firefox_package_bugtask = self.factory.makeBugTask(
            bug=a_ff_bug, target=firefox_package)

        similar_bugs = firefox_package_bugtask.findSimilarBugs(
            user=sample_person)
        similar_bugs = sorted(similar_bugs, key=attrgetter('id'))
        self.assertEqual(similar_bugs[0].id, 1)
        self.assertEqual(similar_bugs[0].title,
                         'Firefox does not support SVG')

    def test_private_bugs_do_not_show(self):
        """Private bugs won't show up in the list of similar bugs.

        Exception: the user is a direct subscriber. We'll demonstrate this by
        creating a new bug against Firefox.
        """
        firefox, new_ff_bug, ff_bugtask = self._setupFirefoxBugTask()
        second_ff_bug = self.factory.makeBug(
            target=firefox, title="Yet another Firefox bug")
        no_priv = getUtility(IPersonSet).getByEmail('no-priv@canonical.com')
        similar_bugs = ff_bugtask.findSimilarBugs(user=no_priv)
        similar_bugs = sorted(similar_bugs, key=attrgetter('id'))

        self.assertEqual(len(similar_bugs), 3)

        # If we mark the new bug as private, it won't appear in the similar
        # bugs list for no_priv any more, since they're not a direct
        # subscriber.
        launchbag = getUtility(ILaunchBag)
        login('foo.bar@canonical.com')
        foobar = launchbag.user
        second_ff_bug.setPrivate(True, foobar)
        similar_bugs = ff_bugtask.findSimilarBugs(user=no_priv)
        similar_bugs = sorted(similar_bugs, key=attrgetter('id'))

        self.assertEqual(len(similar_bugs), 2)


class TestBugTaskPermissionsToSetAssigneeMixin:

    layer = DatabaseFunctionalLayer

    def setUp(self):
        """Create the test setup.

        We need
        - bug task targets (a product and a product series, or
          a distribution and distoseries, see classes derived from
          this one)
        - persons and team with special roles: product and distribution,
          owners, bug supervisors, drivers
        - bug tasks for the targets
        """
        super(TestBugTaskPermissionsToSetAssigneeMixin, self).setUp()
        self.target_owner_member = self.factory.makePerson()
        self.target_owner_team = self.factory.makeTeam(
            owner=self.target_owner_member,
            membership_policy=TeamMembershipPolicy.RESTRICTED)
        self.regular_user = self.factory.makePerson()

        login_person(self.target_owner_member)
        # Target and bug supervisor creation are deferred to sub-classes.
        self.makeTarget()
        self.setBugSupervisor()

        self.driver_team = self.factory.makeTeam(
            owner=self.target_owner_member)
        self.driver_member = self.factory.makePerson()
        self.driver_team.addMember(
            self.driver_member, self.target_owner_member)
        self.target.driver = self.driver_team

        self.series_driver_team = self.factory.makeTeam(
            owner=self.target_owner_member)
        self.series_driver_member = self.factory.makePerson()
        self.series_driver_team.addMember(
            self.series_driver_member, self.target_owner_member)
        self.series.driver = self.series_driver_team

        self.series_bugtask = self.factory.makeBugTask(target=self.series)
        self.series_bugtask.transitionToAssignee(self.regular_user)
        bug = self.series_bugtask.bug
        # If factory.makeBugTask() is called with a series target, it
        # creates automatically another bug task for the main target.
        self.target_bugtask = bug.getBugTask(self.target)
        self.target_bugtask.transitionToAssignee(self.regular_user)
        logout()

    def makeTarget(self):
        """Create a target and a series.

        The target and series must be assigned as attributes of self:
        'self.target' and 'self.series'.
        """
        raise NotImplementedError(self.makeTarget)

    def setBugSupervisor(self):
        """Set bug supervisor variables.

        This is the standard interface for sub-classes, but this
        method should return _setBugSupervisorData or
        _setBugSupervisorDataNone depending on what is required.
        """
        raise NotImplementedError(self.setBugSupervisor)

    def _setBugSupervisorData(self):
        """Helper function used by sub-classes to setup bug supervisors."""
        self.supervisor_member = self.factory.makePerson()
        self.supervisor_team = self.factory.makeTeam(
            owner=self.target_owner_member, members=[self.supervisor_member])
        self.target.bug_supervisor = self.supervisor_team

    def _setBugSupervisorDataNone(self):
        """Helper for sub-classes to work around setting a bug supervisor."""
        self.supervisor_member = None

    def test_userCanSetAnyAssignee_anonymous_user(self):
        # Anonymous users cannot set anybody as an assignee.
        login(ANONYMOUS)
        self.assertFalse(self.target_bugtask.userCanSetAnyAssignee(None))
        self.assertFalse(self.series_bugtask.userCanSetAnyAssignee(None))

    def test_userCanUnassign_anonymous_user(self):
        # Anonymous users cannot unassign anyone.
        login(ANONYMOUS)
        self.assertFalse(self.target_bugtask.userCanUnassign(None))
        self.assertFalse(self.series_bugtask.userCanUnassign(None))

    def test_userCanSetAnyAssignee_regular_user(self):
        # If we have a bug supervisor, check that regular user cannot
        # assign to someone else.  Otherwise, the regular user should
        # be able to assign to anyone.
        login_person(self.regular_user)
        if self.supervisor_member is not None:
            self.assertFalse(
                self.target_bugtask.userCanSetAnyAssignee(self.regular_user))
            self.assertFalse(
                self.series_bugtask.userCanSetAnyAssignee(self.regular_user))
        else:
            self.assertTrue(
                self.target_bugtask.userCanSetAnyAssignee(self.regular_user))
            self.assertTrue(
                self.series_bugtask.userCanSetAnyAssignee(self.regular_user))

    def test_userCanUnassign_logged_in_user(self):
        # Ordinary users can unassign any user or team.
        login_person(self.target_owner_member)
        other_user = self.factory.makePerson()
        self.series_bugtask.transitionToAssignee(other_user)
        self.target_bugtask.transitionToAssignee(other_user)
        login_person(self.regular_user)
        self.assertTrue(
            self.target_bugtask.userCanUnassign(self.regular_user))
        self.assertTrue(
            self.series_bugtask.userCanUnassign(self.regular_user))

    def test_userCanSetAnyAssignee_target_owner(self):
        # The bug task target owner can assign anybody.
        login_person(self.target_owner_member)
        self.assertTrue(
            self.target_bugtask.userCanSetAnyAssignee(self.target.owner))
        self.assertTrue(
            self.series_bugtask.userCanSetAnyAssignee(self.target.owner))

    def test_userCanSetAnyAssignee_bug_supervisor(self):
        # A bug supervisor can assign anybody.
        if self.supervisor_member is not None:
            login_person(self.supervisor_member)
            self.assertTrue(
                self.target_bugtask.userCanSetAnyAssignee(
                    self.supervisor_member))
            self.assertTrue(
                self.series_bugtask.userCanSetAnyAssignee(
                    self.supervisor_member))

    def test_userCanSetAnyAssignee_driver(self):
        # A project driver can assign anybody.
        login_person(self.driver_member)
        self.assertTrue(
            self.target_bugtask.userCanSetAnyAssignee(self.driver_member))
        self.assertTrue(
            self.series_bugtask.userCanSetAnyAssignee(self.driver_member))

    def test_userCanSetAnyAssignee_series_driver(self):
        # A series driver can assign anybody to series bug tasks.
        login_person(self.driver_member)
        self.assertTrue(
            self.series_bugtask.userCanSetAnyAssignee(
                self.series_driver_member))
        if self.supervisor_member is not None:
            # But he cannot assign anybody to bug tasks of the main target...
            self.assertFalse(
                self.target_bugtask.userCanSetAnyAssignee(
                    self.series_driver_member))
        else:
            # ...unless a bug supervisor is not set.
            self.assertTrue(
                self.target_bugtask.userCanSetAnyAssignee(
                    self.series_driver_member))

    def test_userCanSetAnyAssignee_launchpad_admins(self):
        # Launchpad admins can assign anybody.
        login_person(self.target_owner_member)
        foo_bar = getUtility(IPersonSet).getByEmail('foo.bar@canonical.com')
        login_person(foo_bar)
        self.assertTrue(self.target_bugtask.userCanSetAnyAssignee(foo_bar))
        self.assertTrue(self.series_bugtask.userCanSetAnyAssignee(foo_bar))

    def test_userCanSetAnyAssignee_bug_importer(self):
        # The bug importer celebrity can assign anybody.
        login_person(self.target_owner_member)
        bug_importer = getUtility(ILaunchpadCelebrities).bug_importer
        login_person(bug_importer)
        self.assertTrue(
            self.target_bugtask.userCanSetAnyAssignee(bug_importer))
        self.assertTrue(
            self.series_bugtask.userCanSetAnyAssignee(bug_importer))


class TestProductBugTaskPermissionsToSetAssignee(
    TestBugTaskPermissionsToSetAssigneeMixin, TestCaseWithFactory):

    def makeTarget(self):
        """Create a product and a product series."""
        self.target = self.factory.makeProduct(owner=self.target_owner_team)
        self.series = self.factory.makeProductSeries(self.target)

    def setBugSupervisor(self):
        """Establish a bug supervisor for this target."""
        self._setBugSupervisorData()


class TestProductNoBugSupervisorBugTaskPermissionsToSetAssignee(
    TestBugTaskPermissionsToSetAssigneeMixin, TestCaseWithFactory):

    def makeTarget(self):
        """Create a product and a product series without a bug supervisor."""
        self.target = self.factory.makeProduct(owner=self.target_owner_team)
        self.series = self.factory.makeProductSeries(self.target)

    def setBugSupervisor(self):
        """Set bug supervisor to None."""
        self._setBugSupervisorDataNone()


class TestDistributionBugTaskPermissionsToSetAssignee(
    TestBugTaskPermissionsToSetAssigneeMixin, TestCaseWithFactory):

    def makeTarget(self):
        """Create a distribution and a distroseries."""
        self.target = self.factory.makeDistribution(
            owner=self.target_owner_team)
        self.series = self.factory.makeDistroSeries(self.target)

    def setBugSupervisor(self):
        """Set bug supervisor to None."""
        self._setBugSupervisorData()


class TestDistributionNoBugSupervisorBugTaskPermissionsToSetAssignee(
    TestBugTaskPermissionsToSetAssigneeMixin, TestCaseWithFactory):

    def makeTarget(self):
        """Create a distribution and a distroseries."""
        self.target = self.factory.makeDistribution(
            owner=self.target_owner_team)
        self.series = self.factory.makeDistroSeries(self.target)

    def setBugSupervisor(self):
        """Establish a bug supervisor for this target."""
        self._setBugSupervisorDataNone()


class BugTaskSearchBugsElsewhereTest(unittest.TestCase):
    """Tests for searching bugs filtering on related bug tasks.

    It also acts as a helper class, which makes related doctests more
    readable, since they can use methods from this class.
    """
    layer = DatabaseFunctionalLayer

    def __init__(self, methodName='runTest', helper_only=False):
        """If helper_only is True, set up it only as a helper class."""
        if not helper_only:
            unittest.TestCase.__init__(self, methodName=methodName)

    def setUp(self):
        login(ANONYMOUS)

    def tearDown(self):
        logout()

    def _getBugTaskByTarget(self, bug, target):
        """Return a bug's bugtask for the given target."""
        for bugtask in bug.bugtasks:
            if bugtask.target == target:
                return bugtask
        else:
            raise AssertionError(
                "Didn't find a %s task on bug %s." % (
                    target.bugtargetname, bug.id))

    def setUpBugsResolvedUpstreamTests(self):
        """Modify some bugtasks to match the resolved upstream filter."""
        bugset = getUtility(IBugSet)
        productset = getUtility(IProductSet)
        firefox = productset.getByName("firefox")
        thunderbird = productset.getByName("thunderbird")

        # Mark an upstream task on bug #1 "Fix Released"
        bug_one = bugset.get(1)
        firefox_upstream = self._getBugTaskByTarget(bug_one, firefox)
        self.assertEqual(ServiceUsage.LAUNCHPAD,
                         firefox_upstream.product.bug_tracking_usage)
        self.old_firefox_status = firefox_upstream.status
        firefox_upstream.transitionToStatus(
            BugTaskStatus.FIXRELEASED, getUtility(ILaunchBag).user)
        self.firefox_upstream = firefox_upstream

        # Mark an upstream task on bug #9 "Fix Committed"
        bug_nine = bugset.get(9)
        thunderbird_upstream = self._getBugTaskByTarget(bug_nine, thunderbird)
        self.old_thunderbird_status = thunderbird_upstream.status
        thunderbird_upstream.transitionToStatus(BugTaskStatus.FIXCOMMITTED,
                                                getUtility(ILaunchBag).user)
        self.thunderbird_upstream = thunderbird_upstream

        # Add a watch to a Debian bug for bug #2, and mark the task Fix
        # Released.
        bug_two = bugset.get(2)
        bugwatchset = getUtility(IBugWatchSet)

        # Get a debbugs watch.
        watch_debbugs_327452 = bugwatchset.get(9)
        self.assertEquals(watch_debbugs_327452.bugtracker.name, "debbugs")
        self.assertEquals(watch_debbugs_327452.remotebug, "327452")

        # Associate the watch to a Fix Released task.
        debian = getUtility(IDistributionSet).getByName("debian")
        debian_firefox = debian.getSourcePackage("mozilla-firefox")
        bug_two_in_debian_firefox = self._getBugTaskByTarget(bug_two,
                                                            debian_firefox)
        bug_two_in_debian_firefox.bugwatch = watch_debbugs_327452
        bug_two_in_debian_firefox.transitionToStatus(
            BugTaskStatus.FIXRELEASED, getUtility(ILaunchBag).user)

        flush_database_updates()

    def tearDownBugsElsewhereTests(self):
        """Resets the modified bugtasks to their original statuses."""
        self.firefox_upstream.transitionToStatus(
            self.old_firefox_status,
            self.firefox_upstream.target.bug_supervisor)
        self.thunderbird_upstream.transitionToStatus(
            self.old_thunderbird_status,
            self.firefox_upstream.target.bug_supervisor)
        flush_database_updates()

    def assertBugTaskIsPendingBugWatchElsewhere(self, bugtask):
        """Assert the bugtask is pending a bug watch elsewhere.

        Pending a bugwatch elsewhere means that at least one of the bugtask's
        related task's target isn't using Malone, and that
        related_bugtask.bugwatch is None.
        """
        non_malone_using_bugtasks = [
            related_task for related_task in bugtask.related_tasks
            if not related_task.pillar.official_malone]
        pending_bugwatch_bugtasks = [
            related_bugtask for related_bugtask in non_malone_using_bugtasks
            if related_bugtask.bugwatch is None]
        self.assert_(
            len(pending_bugwatch_bugtasks) > 0,
            'Bugtask %s on %s has no related bug watches elsewhere.' % (
                bugtask.id, bugtask.target.displayname))

    def assertBugTaskIsResolvedUpstream(self, bugtask):
        """Make sure at least one of the related upstream tasks is resolved.

        "Resolved", for our purposes, means either that one of the related
        tasks is an upstream task in FIXCOMMITTED or FIXRELEASED state, or
        it is a task with a bugwatch, and in FIXCOMMITTED, FIXRELEASED, or
        INVALID state.
        """
        resolved_upstream_states = [
            BugTaskStatus.FIXCOMMITTED, BugTaskStatus.FIXRELEASED]
        resolved_bugwatch_states = [
            BugTaskStatus.FIXCOMMITTED, BugTaskStatus.FIXRELEASED,
            BugTaskStatus.INVALID]

        # Helper functions for the list comprehension below.
        def _is_resolved_upstream_task(bugtask):
            return (
                bugtask.product is not None and
                bugtask.status in resolved_upstream_states)

        def _is_resolved_bugwatch_task(bugtask):
            return (
                bugtask.bugwatch and bugtask.status in
                resolved_bugwatch_states)

        resolved_related_tasks = [
            related_task for related_task in bugtask.related_tasks
            if (_is_resolved_upstream_task(related_task) or
                _is_resolved_bugwatch_task(related_task))]

        self.assert_(len(resolved_related_tasks) > 0)
        self.assert_(
            len(resolved_related_tasks) > 0,
            'Bugtask %s on %s has no resolved related tasks.' % (
                bugtask.id, bugtask.target.displayname))

    def assertBugTaskIsOpenUpstream(self, bugtask):
        """Make sure at least one of the related upstream tasks is open.

        "Open", for our purposes, means either that one of the related
        tasks is an upstream task or a task with a bugwatch which has
        one of the states listed in open_states.
        """
        open_states = [
            BugTaskStatus.NEW,
            BugTaskStatus.INCOMPLETE,
            BugTaskStatus.CONFIRMED,
            BugTaskStatus.INPROGRESS,
            BugTaskStatus.UNKNOWN]

        # Helper functions for the list comprehension below.
        def _is_open_upstream_task(bugtask):
            return (
                bugtask.product is not None and
                bugtask.status in open_states)

        def _is_open_bugwatch_task(bugtask):
            return (
                bugtask.bugwatch and bugtask.status in
                open_states)

        open_related_tasks = [
            related_task for related_task in bugtask.related_tasks
            if (_is_open_upstream_task(related_task) or
                _is_open_bugwatch_task(related_task))]

        self.assert_(
            len(open_related_tasks) > 0,
            'Bugtask %s on %s has no open related tasks.' % (
                bugtask.id, bugtask.target.displayname))

    def _hasUpstreamTask(self, bug):
        """Does this bug have an upstream task associated with it?

        Returns True if yes, otherwise False.
        """
        for bugtask in bug.bugtasks:
            if bugtask.product is not None:
                return True
        return False

    def assertShouldBeShownOnNoUpstreamTaskSearch(self, bugtask):
        """Should the bugtask be shown in the search no upstream task search?

        Returns True if yes, otherwise False.
        """
        self.assert_(
            not self._hasUpstreamTask(bugtask.bug),
            'Bugtask %s on %s has upstream tasks.' % (
                bugtask.id, bugtask.target.displayname))


class BugTaskSetFindExpirableBugTasksTest(unittest.TestCase):
    """Test `BugTaskSet.findExpirableBugTasks()` behaviour."""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        """Setup the zope interaction and create expirable bugtasks."""
        login('test@canonical.com')
        self.user = getUtility(ILaunchBag).user
        self.distribution = getUtility(IDistributionSet).getByName('ubuntu')
        self.distroseries = self.distribution.getSeries('hoary')
        self.product = getUtility(IProductSet).getByName('jokosher')
        self.productseries = self.product.getSeries('trunk')
        self.bugtaskset = getUtility(IBugTaskSet)
        bugtasks = []
        bugtasks.append(
            create_old_bug("90 days old", 90, self.distribution))
        bugtasks.append(
            self.bugtaskset.createTask(
                bugtasks[-1].bug, self.user, self.distroseries))
        bugtasks.append(
            create_old_bug("90 days old", 90, self.product))
        bugtasks.append(
            self.bugtaskset.createTask(
                bugtasks[-1].bug, self.user, self.productseries))

    def tearDown(self):
        logout()

    def testSupportedTargetParam(self):
        """The target param supports a limited set of BugTargets.

        Four BugTarget types may passed as the target argument:
        Distribution, DistroSeries, Product, ProductSeries.
        """
        supported_targets_and_task_count = [
            (self.distribution, 2), (self.distroseries, 1), (self.product, 2),
            (self.productseries, 1), (None, 4)]
        for target, expected_count in supported_targets_and_task_count:
            expirable_bugtasks = self.bugtaskset.findExpirableBugTasks(
                0, self.user, target=target)
            self.assertEqual(expected_count, expirable_bugtasks.count(),
                 "%s has %d expirable bugtasks, expected %d." %
                 (self.distroseries, expirable_bugtasks.count(),
                  expected_count))

    def testUnsupportedBugTargetParam(self):
        """Test that unsupported targets raise errors.

        Three BugTarget types are not supported because the UI does not
        provide bug-index to link to the 'bugs that can expire' page.
        ProjectGroup, SourcePackage, and DistributionSourcePackage will
        raise an NotImplementedError.

        Passing an unknown bugtarget type will raise an AssertionError.
        """
        project = getUtility(IProjectGroupSet).getByName('mozilla')
        distributionsourcepackage = self.distribution.getSourcePackage(
            'mozilla-firefox')
        sourcepackage = self.distroseries.getSourcePackage(
            'mozilla-firefox')
        unsupported_targets = [project, distributionsourcepackage,
                               sourcepackage]
        for target in unsupported_targets:
            self.assertRaises(
                NotImplementedError, self.bugtaskset.findExpirableBugTasks,
                0, self.user, target=target)

        # Objects that are not a known BugTarget type raise an AssertionError.
        self.assertRaises(
            AssertionError, self.bugtaskset.findExpirableBugTasks,
            0, self.user, target=[])


class TestBugTaskStatuses(TestCase):

    def test_open_and_resolved_statuses(self):
        """
        There are constants that are used to define which statuses are for
        resolved bugs (`RESOLVED_BUGTASK_STATUSES`), and which are for
        unresolved bugs (`UNRESOLVED_BUGTASK_STATUSES`). The two constants
        include all statuses defined in BugTaskStatus, except for Unknown.
        """
        self.assertNotIn(BugTaskStatus.UNKNOWN, RESOLVED_BUGTASK_STATUSES)
        self.assertNotIn(BugTaskStatus.UNKNOWN, UNRESOLVED_BUGTASK_STATUSES)
        self.assertNotIn(
            BugTaskStatus.UNKNOWN, DB_UNRESOLVED_BUGTASK_STATUSES)


class TestBugTaskContributor(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_non_contributor(self):
        owner = self.factory.makePerson()
        bug = self.factory.makeBug(owner=owner)
        # Create a person who has not contributed
        person = self.factory.makePerson()
        result = bug.default_bugtask.getContributorInfo(owner, person)
        self.assertFalse(result['is_contributor'])
        self.assertEqual(person.displayname, result['person_name'])
        self.assertEqual(
            bug.default_bugtask.pillar.displayname, result['pillar_name'])

    def test_contributor(self):
        owner = self.factory.makePerson()
        product = self.factory.makeProduct()
        bug = self.factory.makeBug(target=product, owner=owner)
        bug1 = self.factory.makeBug(target=product, owner=owner)
        # Create a person who has contributed
        person = self.factory.makePerson()
        login('foo.bar@canonical.com')
        bug1.default_bugtask.transitionToAssignee(person)
        result = bug.default_bugtask.getContributorInfo(owner, person)
        self.assertTrue(result['is_contributor'])
        self.assertEqual(person.displayname, result['person_name'])
        self.assertEqual(
            bug.default_bugtask.pillar.displayname, result['pillar_name'])


class TestBugTaskDeletion(TestCaseWithFactory):
    """Test the different cases that makes a bugtask deletable or not."""

    layer = DatabaseFunctionalLayer

    def test_cannot_delete_if_not_logged_in(self):
        # You cannot delete a bug task if not logged in.
        bug = self.factory.makeBug()
        self.assertFalse(
            check_permission('launchpad.Delete', bug.default_bugtask))

    def test_unauthorised_cannot_delete(self):
        # Unauthorised users cannot delete a bug task.
        bug = self.factory.makeBug()
        unauthorised = self.factory.makePerson()
        login_person(unauthorised)
        self.assertFalse(
            check_permission('launchpad.Delete', bug.default_bugtask))

    def test_admin_can_delete(self):
        # With the feature flag on, an admin can delete a bug task.
        bug = self.factory.makeBug()
        login_celebrity('admin')
        self.assertTrue(
            check_permission('launchpad.Delete', bug.default_bugtask))

    def test_pillar_owner_can_delete(self):
        # With the feature flag on, the pillar owner can delete a bug task.
        bug = self.factory.makeBug()
        login_person(bug.default_bugtask.pillar.owner)
        self.assertTrue(
            check_permission('launchpad.Delete', bug.default_bugtask))

    def test_bug_supervisor_can_delete(self):
        # With the feature flag on, the bug supervisor can delete a bug task.
        bug_supervisor = self.factory.makePerson()
        product = self.factory.makeProduct(bug_supervisor=bug_supervisor)
        bug = self.factory.makeBug(target=product)
        login_person(bug_supervisor)
        self.assertTrue(
            check_permission('launchpad.Delete', bug.default_bugtask))

    def test_task_reporter_can_delete(self):
        # With the feature flag on, the bug task reporter can delete bug task.
        bug = self.factory.makeBug()
        login_person(bug.default_bugtask.owner)
        self.assertTrue(
            check_permission('launchpad.Delete', bug.default_bugtask))

    def test_cannot_delete_only_bugtask(self):
        # The only bugtask cannot be deleted.
        bug = self.factory.makeBug()
        bugtask = bug.default_bugtask
        login_person(bugtask.owner)
        self.assertRaises(CannotDeleteBugtask, bugtask.delete)

    def test_canBeDeleted_is_free(self):
        # BugTask.canBeDeleted uses cached data, so repeated execution
        # on a single bug is free.
        bug = self.factory.makeBug()
        task1 = self.factory.makeBugTask(bug=bug)
        task2 = self.factory.makeBugTask(bug=bug)
        self.assertEqual(True, bug.default_bugtask.canBeDeleted())
        with StormStatementRecorder() as recorder:
            self.assertEqual(True, task1.canBeDeleted())
            self.assertEqual(True, task2.canBeDeleted())
        self.assertThat(recorder, HasQueryCount(Equals(0)))

    def test_delete_bugtask(self):
        # A bugtask can be deleted and after deletion, re-nominated.
        owner = self.factory.makePerson()
        product = self.factory.makeProduct(driver=owner, bug_supervisor=owner)
        bug = self.factory.makeBug(target=product, owner=owner)
        target = self.factory.makeProductSeries(product=product)
        login_person(bug.owner)
        nomination = bug.addNomination(bug.owner, target)
        nomination.approve(bug.owner)
        bugtask = bug.getBugTask(target)
        bugtask.delete()
        self.assertEqual([bug.default_bugtask], bug.bugtasks)
        self.assertTrue(bug.canBeNominatedFor(target))

    def test_delete_default_bugtask(self):
        # The default bugtask can be deleted.
        bug = self.factory.makeBug()
        bugtask = self.factory.makeBugTask(bug=bug)
        bug = bugtask.bug
        login_person(bug.default_bugtask.owner)
        bug.default_bugtask.delete()
        self.assertEqual([bugtask], bug.bugtasks)
        self.assertEqual(bugtask, bug.default_bugtask)

    def test_accesspolicyartifacts_updated(self):
        # delete() updates the AccessPolicyArtifacts related
        # to the bug.
        new_product = self.factory.makeProduct()
        bug = self.factory.makeBug(information_type=InformationType.USERDATA)
        with admin_logged_in():
            old_product = bug.default_bugtask.product
            task = getUtility(IBugTaskSet).createTask(
                bug, bug.owner, new_product)

        expected_policies = getUtility(IAccessPolicySource).find([
            (old_product, InformationType.USERDATA),
            (new_product, InformationType.USERDATA),
            ])
        self.assertContentEqual(
            expected_policies, get_policies_for_artifact(bug))

        with admin_logged_in():
            task.delete()

        expected_policies = getUtility(IAccessPolicySource).find([
            (old_product, InformationType.USERDATA),
            ])
        self.assertContentEqual(
            expected_policies, get_policies_for_artifact(bug))


class TestStatusCountsForProductSeries(TestCaseWithFactory):
    """Test BugTaskSet.getStatusCountsForProductSeries()."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestStatusCountsForProductSeries, self).setUp()
        self.bugtask_set = getUtility(IBugTaskSet)
        self.owner = self.factory.makePerson()
        login_person(self.owner)
        self.product = self.factory.makeProduct(owner=self.owner)
        self.series = self.factory.makeProductSeries(product=self.product)
        self.milestone = self.factory.makeMilestone(productseries=self.series)

    def get_counts(self, user):
        return self.bugtask_set.getStatusCountsForProductSeries(
            user, self.series)

    def createBugs(self):
        self.factory.makeBug(milestone=self.milestone)
        self.factory.makeBug(
            milestone=self.milestone,
            information_type=InformationType.USERDATA)
        self.factory.makeBug(series=self.series)
        self.factory.makeBug(
            series=self.series, information_type=InformationType.USERDATA)

    def test_privacy_and_counts_for_unauthenticated_user(self):
        # An unauthenticated user should see bug counts for each status
        # that do not include private bugs.
        self.createBugs()
        self.assertEqual(
            {BugTaskStatus.NEW: 2},
            self.get_counts(None))

    def test_privacy_and_counts_for_owner(self):
        # The owner should see bug counts for each status that do
        # include all private bugs.
        self.createBugs()
        self.assertEqual(
            {BugTaskStatus.NEW: 4},
            self.get_counts(self.owner))

    def test_privacy_and_counts_for_other_user(self):
        # A random authenticated user should see bug counts for each
        # status that do include all private bugs, since it is costly to
        # query just the private bugs that the user has access to view,
        # and this query may be run many times on a single page.
        self.createBugs()
        other = self.factory.makePerson()
        self.assertEqual(
            {BugTaskStatus.NEW: 4},
            self.get_counts(other))

    def test_multiple_statuses(self):
        # Test that separate counts are provided for each status that
        # bugs are found in.
        statuses = [
            BugTaskStatus.INVALID,
            BugTaskStatus.OPINION,
            ]
        for status in statuses:
            self.factory.makeBug(milestone=self.milestone, status=status)
            self.factory.makeBug(series=self.series, status=status)
        for i in range(3):
            self.factory.makeBug(series=self.series)
        expected = {
            BugTaskStatus.INVALID: 2,
            BugTaskStatus.OPINION: 2,
            BugTaskStatus.NEW: 3,
            }
        self.assertEqual(expected, self.get_counts(None))

    def test_incomplete_status(self):
        # INCOMPLETE is stored as either INCOMPLETE_WITH_RESPONSE or
        # INCOMPLETE_WITHOUT_RESPONSE so the stats do not include a count of
        # INCOMPLETE tasks.
        statuses = [
            BugTaskStatusSearch.INCOMPLETE_WITH_RESPONSE,
            BugTaskStatusSearch.INCOMPLETE_WITHOUT_RESPONSE,
            BugTaskStatus.INCOMPLETE,
            ]
        for status in statuses:
            self.factory.makeBug(series=self.series, status=status)
        flush_database_updates()
        expected = {
            BugTaskStatusSearch.INCOMPLETE_WITH_RESPONSE: 1,
            BugTaskStatusSearch.INCOMPLETE_WITHOUT_RESPONSE: 2,
            }
        self.assertEqual(expected, self.get_counts(None))


class TestStatusCountsForProductSeries(TestCaseWithFactory):
    """Test BugTaskSet.getStatusCountsForProductSeries()."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestStatusCountsForProductSeries, self).setUp()
        self.bugtask_set = getUtility(IBugTaskSet)
        self.owner = self.factory.makePerson()
        login_person(self.owner)
        self.product = self.factory.makeProduct(owner=self.owner)
        self.series = self.factory.makeProductSeries(product=self.product)
        self.milestone = self.factory.makeMilestone(productseries=self.series)

    def get_counts(self, user):
        return self.bugtask_set.getStatusCountsForProductSeries(
            user, self.series)

    def createBugs(self):
        self.factory.makeBug(milestone=self.milestone)
        self.factory.makeBug(
            milestone=self.milestone,
            information_type=InformationType.USERDATA)
        self.factory.makeBug(series=self.series)
        self.factory.makeBug(
            series=self.series, information_type=InformationType.USERDATA)

    def test_privacy_and_counts_for_unauthenticated_user(self):
        # An unauthenticated user should see bug counts for each status
        # that do not include private bugs.
        self.createBugs()
        self.assertEqual(
            {BugTaskStatus.NEW: 2},
            self.get_counts(None))

    def test_privacy_and_counts_for_owner(self):
        # The owner should see bug counts for each status that do
        # include all private bugs.
        self.createBugs()
        self.assertEqual(
            {BugTaskStatus.NEW: 4},
            self.get_counts(self.owner))

    def test_privacy_and_counts_for_other_user(self):
        # A random authenticated user should see bug counts for each
        # status that do include all private bugs, since it is costly to
        # query just the private bugs that the user has access to view,
        # and this query may be run many times on a single page.
        self.createBugs()
        other = self.factory.makePerson()
        self.assertEqual(
            {BugTaskStatus.NEW: 4},
            self.get_counts(other))

    def test_multiple_statuses(self):
        # Test that separate counts are provided for each status that
        # bugs are found in.
        statuses = [
            BugTaskStatus.INVALID,
            BugTaskStatus.OPINION,
            ]
        for status in statuses:
            self.factory.makeBug(milestone=self.milestone, status=status)
            self.factory.makeBug(series=self.series, status=status)
        for i in range(3):
            self.factory.makeBug(series=self.series)
        expected = {
            BugTaskStatus.INVALID: 2,
            BugTaskStatus.OPINION: 2,
            BugTaskStatus.NEW: 3,
            }
        self.assertEqual(expected, self.get_counts(None))

    def test_incomplete_status(self):
        # INCOMPLETE is stored as either INCOMPLETE_WITH_RESPONSE or
        # INCOMPLETE_WITHOUT_RESPONSE so the stats do not include a count of
        # INCOMPLETE tasks.
        statuses = [
            BugTaskStatusSearch.INCOMPLETE_WITH_RESPONSE,
            BugTaskStatusSearch.INCOMPLETE_WITHOUT_RESPONSE,
            BugTaskStatus.INCOMPLETE,
            ]
        for status in statuses:
            self.factory.makeBug(series=self.series, status=status)
        flush_database_updates()
        expected = {
            BugTaskStatusSearch.INCOMPLETE_WITH_RESPONSE: 1,
            BugTaskStatusSearch.INCOMPLETE_WITHOUT_RESPONSE: 2,
            }
        self.assertEqual(expected, self.get_counts(None))


class TestBugTaskMilestones(TestCaseWithFactory):
    """Tests that appropriate milestones are returned for bugtasks."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugTaskMilestones, self).setUp()
        self.product = self.factory.makeProduct()
        self.product_bug = self.factory.makeBug(target=self.product)
        self.product_milestone = self.factory.makeMilestone(
            product=self.product)
        self.distribution = self.factory.makeDistribution()
        self.distribution_bug = self.factory.makeBug(target=self.distribution)
        self.distribution_milestone = self.factory.makeMilestone(
            distribution=self.distribution)
        self.bugtaskset = getUtility(IBugTaskSet)

    def test_get_target_milestones_with_one_task(self):
        milestones = list(self.bugtaskset.getBugTaskTargetMilestones(
            [self.product_bug.default_bugtask]))
        self.assertEqual(
            [self.product_milestone],
            milestones)

    def test_get_target_milestones_multiple_tasks(self):
        tasks = [
            self.product_bug.default_bugtask,
            self.distribution_bug.default_bugtask,
            ]
        milestones = sorted(
            self.bugtaskset.getBugTaskTargetMilestones(tasks))
        self.assertEqual(
            sorted([self.product_milestone, self.distribution_milestone]),
            milestones)


class TestConjoinedBugTasks(TestCaseWithFactory):
    """Tests for conjoined bug task functionality.

    They represent the same piece of work. The same is true for product and
    productseries tasks, when the productseries task is targeted to the
    IProduct.developmentfocus. The following attributes are synced:

    * status
    * assignee
    * importance
    * milestone
    * sourcepackagename
    * date_confirmed
    * date_inprogress
    * date_assigned
    * date_closed
    * date_left_new
    * date_triaged
    * date_fix_committed
    * date_fix_released


    XXX: rharding 2012-05-14 bug=999298: These tests are ported from doctests
    and do too much work. They should be split into simpler and better unit
    tests.
    """

    layer = DatabaseFunctionalLayer

    def _setupBugData(self):
        super(TestConjoinedBugTasks, self).setUp()
        owner = self.factory.makePerson()
        distro = self.factory.makeDistribution(name="eggs", owner=owner,
                                               bug_supervisor=owner)
        distro_release = self.factory.makeDistroSeries(distribution=distro,
                                                       registrant=owner)
        source_package = self.factory.makeSourcePackage(
            sourcepackagename="spam", distroseries=distro_release)
        bug = self.factory.makeBug(
            target=source_package.distribution_sourcepackage,
            owner=owner)
        with person_logged_in(owner):
            nomination = bug.addNomination(owner, distro_release)
            nomination.approve(owner)
            generic_task, series_task = bug.bugtasks
        return BugData(owner, distro, distro_release, source_package, bug,
                       generic_task, series_task)

    def test_editing_generic_status_reflects_upon_conjoined_master(self):
        # If a change is made to the status of a conjoined slave
        # (generic) task, that change is reflected upon the conjoined
        # master.
        data = self._setupBugData()
        with person_logged_in(data.owner):
            # Both the generic task and the series task start off with the
            # status of NEW.
            self.assertEqual(BugTaskStatus.NEW,
                             data.generic_task.status)
            self.assertEqual(BugTaskStatus.NEW,
                             data.series_task.status)
            # Transitioning the generic task to CONFIRMED.
            data.generic_task.transitionToStatus(BugTaskStatus.CONFIRMED,
                                                 data.owner)
            # Also transitions the series_task.
            self.assertEqual(BugTaskStatus.CONFIRMED,
                             data.series_task.status)

    def test_editing_generic_importance_reflects_upon_conjoined_master(self):
        # If a change is made to the importance of a conjoined slave
        # (generic) task, that change is reflected upon the conjoined
        # master.
        data = self._setupBugData()
        with person_logged_in(data.owner):
            data.generic_task.transitionToImportance(BugTaskImportance.HIGH,
                                                     data.owner)
            self.assertEqual(BugTaskImportance.HIGH,
                             data.series_task.importance)

    def test_editing_generic_assignee_reflects_upon_conjoined_master(self):
        # If a change is made to the assignee of a conjoined slave
        # (generic) task, that change is reflected upon the conjoined
        # master.
        data = self._setupBugData()
        with person_logged_in(data.owner):
            data.generic_task.transitionToAssignee(data.owner)
            self.assertEqual(data.owner, data.series_task.assignee)

    def test_editing_generic_package_reflects_upon_conjoined_master(self):
        # If a change is made to the source package of a conjoined slave
        # (generic) task, that change is reflected upon the conjoined
        # master.
        data = self._setupBugData()
        source_package_name = self.factory.makeSourcePackageName("ham")
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=data.distro.currentseries,
            sourcepackagename=source_package_name)
        with person_logged_in(data.owner):
            data.generic_task.transitionToTarget(
                data.distro.getSourcePackage(source_package_name), data.owner)
            self.assertEqual(source_package_name,
                             data.series_task.sourcepackagename)

    def test_conjoined_milestone(self):
        """Milestone attribute will sync across conjoined tasks."""
        data = self._setupBugData()
        login('foo.bar@canonical.com')
        launchbag = getUtility(ILaunchBag)
        conjoined = getUtility(IProductSet)['alsa-utils']
        con_generic_task = getUtility(IBugTaskSet).createTask(data.bug,
                                                              launchbag.user,
                                                              conjoined)
        con_devel_task = getUtility(IBugTaskSet).createTask(
            data.bug, launchbag.user, conjoined.getSeries("trunk"))

        test_milestone = conjoined.development_focus.newMilestone("test")
        noway_milestone = conjoined.development_focus.newMilestone("noway")

        Store.of(test_milestone).flush()

        self.assertIsNone(con_generic_task.milestone)
        self.assertIsNone(con_devel_task.milestone)

        con_devel_task.transitionToMilestone(test_milestone,
                                             conjoined.owner)

        self.assertEqual(con_generic_task.milestone.name, 'test')
        self.assertEqual(con_devel_task.milestone.name, 'test')

        # But a normal unprivileged user can't set the milestone.
        no_priv = getUtility(IPersonSet).getByEmail('no-priv@canonical.com')
        with ExpectedException(UserCannotEditBugTaskMilestone, ''):
            con_devel_task.transitionToMilestone(noway_milestone, no_priv)
        self.assertEqual(con_devel_task.milestone.name, 'test')

        con_devel_task.transitionToMilestone(test_milestone, conjoined.owner)

        self.assertEqual(con_generic_task.milestone.name, 'test')
        self.assertEqual(con_devel_task.milestone.name, 'test')

    def test_non_current_dev_lacks_conjoined(self):
        """Tasks not the current dev focus lacks conjoined masters or slaves.
        """
        # Only owners, experts, or admins can create a series.
        login('foo.bar@canonical.com')
        launchbag = getUtility(ILaunchBag)
        ubuntu = getUtility(IDistributionSet).get(1)
        alsa_utils = getUtility(IProductSet)['alsa-utils']
        ubuntu_netapplet = ubuntu.getSourcePackage("netapplet")

        params = CreateBugParams(owner=launchbag.user,
                                 title="a test bug",
                                 comment="test bug description")
        ubuntu_netapplet_bug = ubuntu_netapplet.createBug(params)

        alsa_utils_stable = alsa_utils.newSeries(launchbag.user,
                                                 'stable',
                                                 'The stable series.')

        login('test@canonical.com')
        Store.of(alsa_utils_stable).flush()
        self.assertNotEqual(alsa_utils.development_focus, alsa_utils_stable)

        stable_netapplet_task = getUtility(IBugTaskSet).createTask(
            ubuntu_netapplet_bug, launchbag.user, alsa_utils_stable)
        self.assertIsNone(stable_netapplet_task.conjoined_master)
        self.assertIsNone(stable_netapplet_task.conjoined_slave)

        warty = ubuntu.getSeries('warty')
        self.assertNotEqual(warty, ubuntu.currentseries)

        warty_netapplet_task = getUtility(IBugTaskSet).createTask(
            ubuntu_netapplet_bug, launchbag.user,
            warty.getSourcePackage(ubuntu_netapplet.sourcepackagename))

        self.assertIsNone(warty_netapplet_task.conjoined_master)
        self.assertIsNone(warty_netapplet_task.conjoined_slave)

    def test_no_conjoined_without_current_series(self):
        """Distributions without current series lack a conjoined master/slave.
        """
        login('foo.bar@canonical.com')
        launchbag = getUtility(ILaunchBag)
        ubuntu = getUtility(IDistributionSet).get(1)
        ubuntu_netapplet = ubuntu.getSourcePackage("netapplet")
        params = CreateBugParams(owner=launchbag.user,
                                 title="a test bug",
                                 comment="test bug description")
        ubuntu_netapplet_bug = ubuntu_netapplet.createBug(params)

        gentoo = getUtility(IDistributionSet).getByName('gentoo')
        self.assertIsNone(gentoo.currentseries)

        gentoo_netapplet_task = getUtility(IBugTaskSet).createTask(
            ubuntu_netapplet_bug, launchbag.user,
            gentoo.getSourcePackage(ubuntu_netapplet.sourcepackagename))
        self.assertIsNone(gentoo_netapplet_task.conjoined_master)
        self.assertIsNone(gentoo_netapplet_task.conjoined_slave)

    def test_conjoined_broken_relationship(self):
        """A conjoined relationship can be broken, though.

        If the development task (i.e the conjoined master) is Won't Fix, it
        means that the bug is deferred to the next series. In this case the
        development task should be Won't Fix, while the generic task keeps the
        value it had before, allowing it to stay open.
        """
        data = self._setupBugData()
        login('foo.bar@canonical.com')
        generic_netapplet_task = data.generic_task
        current_series_netapplet_task = data.series_task

        # First let's change the status from Fix Released, since it doesn't
        # make sense to reject such a task.
        current_series_netapplet_task.transitionToStatus(
            BugTaskStatus.CONFIRMED, getUtility(ILaunchBag).user)
        self.assertEqual(generic_netapplet_task.status.title,
            'Confirmed')
        self.assertEqual(current_series_netapplet_task.status.title,
            'Confirmed')
        self.assertIsNone(generic_netapplet_task.date_closed)
        self.assertIsNone(current_series_netapplet_task.date_closed)

        # Now, if we set the current series task to Won't Fix, the generic task
        # will still be confirmed.
        netapplet_owner = current_series_netapplet_task.pillar.owner
        current_series_netapplet_task.transitionToStatus(
            BugTaskStatus.WONTFIX, netapplet_owner)

        self.assertEqual(generic_netapplet_task.status.title,
            'Confirmed')
        self.assertEqual(current_series_netapplet_task.status.title,
            "Won't Fix")

        self.assertIsNone(generic_netapplet_task.date_closed)
        self.assertIsNotNone(current_series_netapplet_task.date_closed)

        # And the bugtasks are no longer conjoined:
        self.assertIsNone(generic_netapplet_task.conjoined_master)
        self.assertIsNone(current_series_netapplet_task.conjoined_slave)

        # If the current development release is marked as Invalid, then the
        # bug is invalid for all future series too, and so the general bugtask
        # is therefore Invalid also. In other words, conjoined again.

        current_series_netapplet_task.transitionToStatus(
            BugTaskStatus.NEW, getUtility(ILaunchBag).user)

        # XXX Gavin Panella 2007-06-06 bug=112746:
        # We must make two transitions.
        current_series_netapplet_task.transitionToStatus(
            BugTaskStatus.INVALID, getUtility(ILaunchBag).user)

        self.assertEqual(generic_netapplet_task.status.title,
            'Invalid')
        self.assertEqual(current_series_netapplet_task.status.title,
            'Invalid')

        self.assertIsNotNone(generic_netapplet_task.date_closed)
        self.assertIsNotNone(current_series_netapplet_task.date_closed)

    def test_conjoined_tasks_sync(self):
        """Conjoined properties are sync'd."""
        launchbag = getUtility(ILaunchBag)
        login('foo.bar@canonical.com')

        sample_person = getUtility(IPersonSet).getByEmail('test@canonical.com')

        ubuntu = getUtility(IDistributionSet).get(1)
        params = CreateBugParams(owner=launchbag.user,
                                 title="a test bug",
                                 comment="test bug description")
        ubuntu_bug = ubuntu.createBug(params)

        ubuntu_netapplet = ubuntu.getSourcePackage("netapplet")
        ubuntu_netapplet_bug = ubuntu_netapplet.createBug(params)
        generic_netapplet_task = ubuntu_netapplet_bug.bugtasks[0]

        # First, we'll target the bug for the current Ubuntu series, Hoary.
        # Note that the synced attributes are copied when the series-specific
        # tasks are created. We'll set non-default attribute values for each
        # generic task to demonstrate.
        self.assertEqual('hoary', ubuntu.currentseries.name)

        # Only owners, experts, or admins can create a milestone.
        ubuntu_edgy_milestone = ubuntu.currentseries.newMilestone("knot1")

        login('test@canonical.com')
        generic_netapplet_task.transitionToStatus(
            BugTaskStatus.INPROGRESS, getUtility(ILaunchBag).user)
        generic_netapplet_task.transitionToAssignee(sample_person)
        generic_netapplet_task.milestone = ubuntu_edgy_milestone
        generic_netapplet_task.transitionToImportance(
            BugTaskImportance.CRITICAL, ubuntu.owner)

        getUtility(IBugTaskSet).createTask(ubuntu_bug, launchbag.user,
            ubuntu.currentseries)
        current_series_netapplet_task = getUtility(IBugTaskSet).createTask(
            ubuntu_netapplet_bug, launchbag.user,
            ubuntu_netapplet.development_version)

        # The attributes were synced with the generic task.
        self.assertEqual('In Progress',
            current_series_netapplet_task.status.title)
        self.assertEqual('Sample Person',
            current_series_netapplet_task.assignee.displayname)
        self.assertEqual('knot1',
            current_series_netapplet_task.milestone.name)
        self.assertEqual('Critical',
            current_series_netapplet_task.importance.title)

        self.assertEqual(current_series_netapplet_task.date_assigned,
            generic_netapplet_task.date_assigned)
        self.assertEqual(current_series_netapplet_task.date_confirmed,
           generic_netapplet_task.date_confirmed)
        self.assertEqual(current_series_netapplet_task.date_inprogress,
            generic_netapplet_task.date_inprogress)
        self.assertEqual(current_series_netapplet_task.date_closed,
           generic_netapplet_task.date_closed)

        # We'll also add some product and productseries tasks.
        alsa_utils = getUtility(IProductSet)['alsa-utils']
        self.assertEqual('trunk', alsa_utils.development_focus.name)

        current_series_netapplet_task.transitionToStatus(
            BugTaskStatus.FIXRELEASED, getUtility(ILaunchBag).user)

        self.assertIsInstance(generic_netapplet_task.date_left_new, datetime)
        self.assertEqual(generic_netapplet_task.date_left_new,
                         current_series_netapplet_task.date_left_new)

        self.assertIsInstance(generic_netapplet_task.date_triaged, datetime)
        self.assertEqual(generic_netapplet_task.date_triaged,
                         current_series_netapplet_task.date_triaged)

        self.assertIsInstance(generic_netapplet_task.date_fix_committed,
                              datetime)
        self.assertEqual(generic_netapplet_task.date_fix_committed,
                         current_series_netapplet_task.date_fix_committed)

        self.assertEqual('Fix Released', generic_netapplet_task.status.title)
        self.assertEqual('Fix Released',
                         current_series_netapplet_task.status.title)

        self.assertIsInstance(generic_netapplet_task.date_closed, datetime)
        self.assertEqual(generic_netapplet_task.date_closed,
                         current_series_netapplet_task.date_closed)
        self.assertIsInstance(generic_netapplet_task.date_fix_released,
                              datetime)
        self.assertEqual(generic_netapplet_task.date_fix_released,
                         current_series_netapplet_task.date_fix_released)


# START TEMPORARY BIT FOR BUGTASK AUTOCONFIRM FEATURE FLAG.
# When feature flag code is removed, delete these tests (up to "# END
# TEMPORARY BIT FOR BUGTASK AUTOCONFIRM FEATURE FLAG.")


class TestAutoConfirmBugTasksFlagForProduct(TestCaseWithFactory):
    """Tests for auto-confirming bug tasks."""
    # Tests for _checkAutoconfirmFeatureFlag.

    layer = DatabaseFunctionalLayer

    def makeTarget(self):
        return self.factory.makeProduct()

    flag = u'bugs.autoconfirm.enabled_product_names'
    alt_flag = u'bugs.autoconfirm.enabled_distribution_names'

    def test_False(self):
        # With no feature flags turned on, we do not auto-confirm.
        bug_task = self.factory.makeBugTask(target=self.makeTarget())
        self.assertFalse(
            removeSecurityProxy(bug_task)._checkAutoconfirmFeatureFlag())

    def test_flag_False(self):
        bug_task = self.factory.makeBugTask(target=self.makeTarget())
        with FeatureFixture({self.flag: u'   '}):
            self.assertFalse(
                removeSecurityProxy(bug_task)._checkAutoconfirmFeatureFlag())

    def test_explicit_flag(self):
        bug_task = self.factory.makeBugTask(target=self.makeTarget())
        with FeatureFixture({self.flag: bug_task.pillar.name}):
            self.assertTrue(
                removeSecurityProxy(bug_task)._checkAutoconfirmFeatureFlag())

    def test_explicit_flag_of_many(self):
        bug_task = self.factory.makeBugTask(target=self.makeTarget())
        flag_value = u'  foo bar  ' + bug_task.pillar.name + '    baz '
        with FeatureFixture({self.flag: flag_value}):
            self.assertTrue(
                removeSecurityProxy(bug_task)._checkAutoconfirmFeatureFlag())

    def test_match_all_flag(self):
        bug_task = self.factory.makeBugTask(target=self.makeTarget())
        with FeatureFixture({self.flag: u'*'}):
            self.assertTrue(
                removeSecurityProxy(bug_task)._checkAutoconfirmFeatureFlag())

    def test_alt_flag_does_not_affect(self):
        bug_task = self.factory.makeBugTask(target=self.makeTarget())
        with FeatureFixture({self.alt_flag: bug_task.pillar.name}):
            self.assertFalse(
                removeSecurityProxy(bug_task)._checkAutoconfirmFeatureFlag())


class TestAutoConfirmBugTasksFlagForProductSeries(
    TestAutoConfirmBugTasksFlagForProduct):
    """Tests for auto-confirming bug tasks."""

    def makeTarget(self):
        return self.factory.makeProductSeries()


class TestAutoConfirmBugTasksFlagForDistribution(
    TestAutoConfirmBugTasksFlagForProduct):
    """Tests for auto-confirming bug tasks."""

    flag = TestAutoConfirmBugTasksFlagForProduct.alt_flag
    alt_flag = TestAutoConfirmBugTasksFlagForProduct.flag

    def makeTarget(self):
        return self.factory.makeDistribution()


class TestAutoConfirmBugTasksFlagForDistributionSeries(
    TestAutoConfirmBugTasksFlagForDistribution):
    """Tests for auto-confirming bug tasks."""

    def makeTarget(self):
        return self.factory.makeDistroSeries()


class TestAutoConfirmBugTasksFlagForDistributionSourcePackage(
    TestAutoConfirmBugTasksFlagForDistribution):
    """Tests for auto-confirming bug tasks."""

    def makeTarget(self):
        return self.factory.makeDistributionSourcePackage()


class TestAutoConfirmBugTasksTransitionToTarget(TestCaseWithFactory):
    """Tests for auto-confirming bug tasks."""
    # Tests for making sure that switching a task from one project that
    # does not auto-confirm to another that does performs the auto-confirm
    # correctly, if appropriate.  This is only necessary for as long as a
    # project may not participate in auto-confirm.

    layer = DatabaseFunctionalLayer

    def test_no_transitionToTarget(self):
        # We can change the target.  If the normal bug conditions do not
        # hold, there will be no transition.
        person = self.factory.makePerson()
        autoconfirm_product = self.factory.makeProduct(owner=person)
        no_autoconfirm_product = self.factory.makeProduct(owner=person)
        with FeatureFixture({
            u'bugs.autoconfirm.enabled_product_names':
            autoconfirm_product.name}):
            bug_task = self.factory.makeBugTask(
                target=no_autoconfirm_product, owner=person)
            with person_logged_in(person):
                bug_task.maybeConfirm()
                self.assertEqual(BugTaskStatus.NEW, bug_task.status)
                bug_task.transitionToTarget(autoconfirm_product, person)
                self.assertEqual(BugTaskStatus.NEW, bug_task.status)

    def test_transitionToTarget(self):
        # If the conditions *do* hold, though, we will auto-confirm.
        person = self.factory.makePerson()
        another_person = self.factory.makePerson()
        autoconfirm_product = self.factory.makeProduct(owner=person)
        no_autoconfirm_product = self.factory.makeProduct(owner=person)
        with FeatureFixture({
            u'bugs.autoconfirm.enabled_product_names':
            autoconfirm_product.name}):
            bug_task = self.factory.makeBugTask(
                target=no_autoconfirm_product, owner=person)
            with person_logged_in(another_person):
                bug_task.bug.markUserAffected(another_person)
            with person_logged_in(person):
                bug_task.maybeConfirm()
                self.assertEqual(BugTaskStatus.NEW, bug_task.status)
                bug_task.transitionToTarget(autoconfirm_product, person)
                self.assertEqual(BugTaskStatus.CONFIRMED, bug_task.status)
# END TEMPORARY BIT FOR BUGTASK AUTOCONFIRM FEATURE FLAG.


class TestAutoConfirmBugTasks(TestCaseWithFactory):
    """Tests for auto-confirming bug tasks."""
    # Tests for maybeConfirm

    layer = DatabaseFunctionalLayer

    def test_auto_confirm(self):
        # A typical new bugtask auto-confirms.  Doing so changes the status of
        # the bug task, creates a status event, and creates a new comment
        # indicating the reason the Janitor auto-confirmed.
        # When feature flag code is removed, remove the next two lines and
        # dedent the rest.
        with feature_flags():
            set_feature_flag(u'bugs.autoconfirm.enabled_product_names', u'*')
            bug_task = self.factory.makeBugTask()
            bug = bug_task.bug
            self.assertEqual(BugTaskStatus.NEW, bug_task.status)
            original_comment_count = bug.messages.count()
            with EventRecorder() as recorder:
                bug_task.maybeConfirm()
                self.assertEqual(BugTaskStatus.CONFIRMED, bug_task.status)
                self.assertEqual(2, len(recorder.events))
                msg_event, mod_event = recorder.events
                self.assertEqual(getUtility(ILaunchpadCelebrities).janitor,
                                 mod_event.user)
                self.assertEqual(['status'], mod_event.edited_fields)
                self.assertEqual(BugTaskStatus.NEW,
                                 mod_event.object_before_modification.status)
                self.assertEqual(bug_task, mod_event.object)
                # A new comment is recorded.
                self.assertEqual(
                    original_comment_count + 1, bug.messages.count())
                self.assertEqual(
                    u"Status changed to 'Confirmed' because the bug affects "
                    "multiple users.",
                    bug.messages[-1].text_contents)

    def test_do_not_confirm_bugwatch_tasks(self):
        # A bugwatch bugtask does not auto-confirm.
        # When feature flag code is removed, remove the next two lines and
        # dedent the rest.
        with feature_flags():
            set_feature_flag(u'bugs.autoconfirm.enabled_product_names', u'*')
            product = self.factory.makeProduct()
            with person_logged_in(product.owner):
                bug = self.factory.makeBug(
                    target=product, owner=product.owner)
                bug_task = bug.getBugTask(product)
                watch = self.factory.makeBugWatch(bug=bug)
                bug_task.bugwatch = watch
            self.assertEqual(BugTaskStatus.NEW, bug_task.status)
            with EventRecorder() as recorder:
                bug_task.maybeConfirm()
                self.assertEqual(BugTaskStatus.NEW, bug_task.status)
                self.assertEqual(0, len(recorder.events))

    def test_only_confirm_new_tasks(self):
        # A non-new bugtask does not auto-confirm.
        # When feature flag code is removed, remove the next two lines and
        # dedent the rest.
        with feature_flags():
            set_feature_flag(u'bugs.autoconfirm.enabled_product_names', u'*')
            bug_task = self.factory.makeBugTask()
            removeSecurityProxy(bug_task).transitionToStatus(
                BugTaskStatus.CONFIRMED, bug_task.bug.owner)
            self.assertEqual(BugTaskStatus.CONFIRMED, bug_task.status)
            with EventRecorder() as recorder:
                bug_task.maybeConfirm()
                self.assertEqual(BugTaskStatus.CONFIRMED, bug_task.status)
                self.assertEqual(0, len(recorder.events))


class TestValidateTransitionToTarget(TestCaseWithFactory):
    """Tests for BugTask.validateTransitionToTarget."""

    layer = DatabaseFunctionalLayer

    def makeAndCheckTransition(self, old, new, extra=None):
        task = self.factory.makeBugTask(target=old)
        if extra:
            self.factory.makeBugTask(bug=task.bug, target=extra)
        with person_logged_in(task.owner):
            task.validateTransitionToTarget(new)

    def assertTransitionWorks(self, a, b, extra=None):
        """Check that a transition between two targets works both ways."""
        self.makeAndCheckTransition(a, b, extra)
        self.makeAndCheckTransition(b, a, extra)

    def assertTransitionForbidden(self, a, b, extra=None):
        """Check that a transition between two targets fails both ways."""
        self.assertRaises(
            IllegalTarget, self.makeAndCheckTransition, a, b, extra)
        self.assertRaises(
            IllegalTarget, self.makeAndCheckTransition, b, a, extra)

    def test_product_to_product_works(self):
        self.assertTransitionWorks(
            self.factory.makeProduct(),
            self.factory.makeProduct())

    def test_product_to_distribution_works(self):
        self.assertTransitionWorks(
            self.factory.makeProduct(),
            self.factory.makeDistributionSourcePackage())

    def test_product_to_package_works(self):
        self.assertTransitionWorks(
            self.factory.makeProduct(),
            self.factory.makeDistributionSourcePackage())

    def test_distribution_to_distribution_works(self):
        self.assertTransitionWorks(
            self.factory.makeDistribution(),
            self.factory.makeDistribution())

    def test_distribution_to_package_works(self):
        distro = self.factory.makeDistribution()
        dsp = self.factory.makeDistributionSourcePackage(distribution=distro)
        self.assertEquals(dsp.distribution, distro)
        self.assertTransitionWorks(distro, dsp)

    def test_package_to_package_works(self):
        distro = self.factory.makeDistribution()
        self.assertTransitionWorks(
            self.factory.makeDistributionSourcePackage(distribution=distro),
            self.factory.makeDistributionSourcePackage(distribution=distro))

    def test_sourcepackage_to_sourcepackage_in_same_series_works(self):
        sp1 = self.factory.makeSourcePackage(publish=True)
        sp2 = self.factory.makeSourcePackage(distroseries=sp1.distroseries,
                                             publish=True)
        self.assertTransitionWorks(sp1, sp2)

    def test_sourcepackage_to_same_series_works(self):
        sp = self.factory.makeSourcePackage()
        self.assertTransitionWorks(sp, sp.distroseries)

    def test_different_distros_works(self):
        self.assertTransitionWorks(
            self.factory.makeDistributionSourcePackage(),
            self.factory.makeDistributionSourcePackage())

    def test_cannot_transition_to_productseries(self):
        product = self.factory.makeProduct()
        self.assertTransitionForbidden(
            product,
            self.factory.makeProductSeries(product=product))

    def test_cannot_transition_to_distroseries(self):
        distro = self.factory.makeDistribution()
        series = self.factory.makeDistroSeries(distribution=distro)
        self.assertTransitionForbidden(distro, series)

    def test_cannot_transition_to_sourcepackage(self):
        dsp = self.factory.makeDistributionSourcePackage()
        series = self.factory.makeDistroSeries(distribution=dsp.distribution)
        sp = self.factory.makeSourcePackage(
            distroseries=series, sourcepackagename=dsp.sourcepackagename)
        self.assertTransitionForbidden(dsp, sp)

    def test_cannot_transition_to_sourcepackage_in_different_series(self):
        distro = self.factory.makeDistribution()
        ds1 = self.factory.makeDistroSeries(distribution=distro)
        sp1 = self.factory.makeSourcePackage(distroseries=ds1)
        ds2 = self.factory.makeDistroSeries(distribution=distro)
        sp2 = self.factory.makeSourcePackage(distroseries=ds2)
        self.assertTransitionForbidden(sp1, sp2)

    # If series tasks for a distribution exist, the pillar of the
    # non-series task cannot be changed. This is due to the strange
    # rules around creation of DS/SP tasks.
    def test_cannot_transition_pillar_of_distro_task_if_series_involved(self):
        # If a Distribution task has subordinate DistroSeries tasks, its
        # pillar cannot be changed.
        series = self.factory.makeDistroSeries()
        product = self.factory.makeProduct()
        distro = self.factory.makeDistribution()
        self.assertRaises(
            IllegalTarget, self.makeAndCheckTransition,
            series.distribution, product, series)
        self.assertRaises(
            IllegalTarget, self.makeAndCheckTransition,
            series.distribution, distro, series)

    def test_cannot_transition_dsp_task_if_sp_tasks_exist(self):
        # If a DistributionSourcePackage task has subordinate
        # SourcePackage tasks, its pillar cannot be changed.
        sp = self.factory.makeSourcePackage(publish=True)
        product = self.factory.makeProduct()
        distro = self.factory.makeDistribution()
        self.assertRaises(
            IllegalTarget, self.makeAndCheckTransition,
            sp.distribution_sourcepackage, product, sp)
        self.assertRaises(
            IllegalTarget, self.makeAndCheckTransition,
            sp.distribution_sourcepackage, distro, sp)

    def test_cannot_transition_to_distro_with_series_tasks(self):
        # If there are any series (DistroSeries or SourcePackage) tasks
        # for a distribution, you can't transition from another pillar
        # to that distribution.
        ds = self.factory.makeDistroSeries()
        sp1 = self.factory.makeSourcePackage(distroseries=ds, publish=True)
        sp2 = self.factory.makeSourcePackage(distroseries=ds, publish=True)
        product = self.factory.makeProduct()
        self.assertRaises(
            IllegalTarget, self.makeAndCheckTransition,
            product, ds.distribution, ds)
        self.assertRaises(
            IllegalTarget, self.makeAndCheckTransition,
            product, ds.distribution, sp2)
        self.assertRaises(
            IllegalTarget, self.makeAndCheckTransition,
            product, sp1.distribution_sourcepackage, ds)
        self.assertRaises(
            IllegalTarget, self.makeAndCheckTransition,
            product, sp1.distribution_sourcepackage, sp2)

    def test_can_transition_dsp_task_with_sp_task_to_different_spn(self):
        # Even if a Distribution or DistributionSourcePackage task has
        # subordinate series tasks, the sourcepackagename can be
        # changed, added or removed. A Storm validator on
        # sourcepackagename changes all the related tasks.
        ds = self.factory.makeDistroSeries()
        sp1 = self.factory.makeSourcePackage(distroseries=ds, publish=True)
        sp2 = self.factory.makeSourcePackage(distroseries=ds, publish=True)
        dsp1 = sp1.distribution_sourcepackage
        dsp2 = sp2.distribution_sourcepackage
        # The sourcepackagename can be changed
        self.makeAndCheckTransition(dsp1, dsp2, sp1)
        self.makeAndCheckTransition(dsp2, dsp1, sp2)
        # Or removed or added.
        self.makeAndCheckTransition(dsp1, ds.distribution, sp1)
        self.makeAndCheckTransition(ds.distribution, dsp1, ds)

    def test_validate_target_is_called(self):
        p = self.factory.makeProduct()
        task1 = self.factory.makeBugTask(target=p)
        task2 = self.factory.makeBugTask(
            bug=task1.bug, target=self.factory.makeProduct())
        with person_logged_in(task2.owner):
            self.assertRaisesWithContent(
                IllegalTarget,
                "A fix for this bug has already been requested for %s"
                % p.displayname, task2.transitionToTarget, p, task2.owner)


class TestTransitionToTarget(TestCaseWithFactory):
    """Tests for BugTask.transitionToTarget."""

    layer = DatabaseFunctionalLayer

    def makeAndTransition(self, old, new):
        task = self.factory.makeBugTask(target=old)
        p = self.factory.makePerson()
        self.assertEqual(old, task.target)
        old_state = Snapshot(task, providing=providedBy(task))
        with person_logged_in(task.owner):
            task.bug.subscribe(p, p)
            task.transitionToTarget(new, p)
            notify(ObjectModifiedEvent(task, old_state, ["target"]))
        return task

    def assertTransitionWorks(self, a, b):
        """Check that a transition between two targets works both ways."""
        self.assertEqual(b, self.makeAndTransition(a, b).target)
        self.assertEqual(a, self.makeAndTransition(b, a).target)

    def test_transition_works(self):
        self.assertTransitionWorks(
            self.factory.makeProduct(),
            self.factory.makeProduct())

    def test_target_type_transition_works(self):
        # A transition from one type of target to another works.
        self.assertTransitionWorks(
            self.factory.makeProduct(),
            self.factory.makeDistributionSourcePackage())

    def test_validation(self):
        # validateTransitionToTarget is called before any transition.
        p = self.factory.makeProduct()
        task = self.factory.makeBugTask(target=p)

        # Patch out validateTransitionToTarget to raise an exception
        # that we can check. Also check that the target was not changed.
        msg = self.factory.getUniqueString()
        removeSecurityProxy(task).validateTransitionToTarget = FakeMethod(
            failure=IllegalTarget(msg))
        with person_logged_in(task.owner):
            self.assertRaisesWithContent(
                IllegalTarget, msg,
                task.transitionToTarget, self.factory.makeProduct(),
                task.owner)
        self.assertEqual(p, task.target)

    def test_transition_to_same_is_noop(self):
        # While a no-op transition would normally be rejected due to
        # task duplication, transitionToTarget short-circuits.
        p = self.factory.makeProduct()
        self.assertTransitionWorks(p, p)

    def test_milestone_unset_on_transition(self):
        # A task's milestone is reset when its target changes.
        product = self.factory.makeProduct()
        task = self.factory.makeBugTask(target=product)
        with person_logged_in(task.owner):
            task.milestone = self.factory.makeMilestone(product=product)
            task.transitionToTarget(self.factory.makeProduct(), task.owner)
        self.assertIs(None, task.milestone)

    def test_milestone_preserved_if_transition_rejected(self):
        # If validation rejects a transition, the milestone is not unset.
        product = self.factory.makeProduct()
        task = self.factory.makeBugTask(target=product)
        with person_logged_in(task.owner):
            task.milestone = milestone = self.factory.makeMilestone(
                product=product)
            self.assertRaises(
                IllegalTarget,
                task.transitionToTarget, self.factory.makeSourcePackage(),
                task.owner)
        self.assertEqual(milestone, task.milestone)

    def test_milestone_preserved_within_a_pillar(self):
        # Milestones are pillar-global, so transitions between packages
        # don't unset them.
        sp = self.factory.makeSourcePackage(publish=True)
        dsp = sp.distribution_sourcepackage
        task = self.factory.makeBugTask(target=dsp.distribution)
        with person_logged_in(task.owner):
            task.milestone = milestone = self.factory.makeMilestone(
                distribution=dsp.distribution)
            task.transitionToTarget(dsp, task.owner)
        self.assertEqual(milestone, task.milestone)

    def test_targetnamecache_updated(self):
        new_product = self.factory.makeProduct()
        task = self.factory.makeBugTask()
        with person_logged_in(task.owner):
            task.transitionToTarget(new_product, task.owner)
        self.assertEqual(
            new_product.bugtargetdisplayname,
            removeSecurityProxy(task).targetnamecache)

    def test_cached_recipients_cleared(self):
        # The bug's notification recipients caches are cleared when
        # transitionToTarget() is called.
        new_product = self.factory.makeProduct()
        task = self.factory.makeBugTask()
        # The factory caused COMMENT notifications which filled the bug cache.
        cache = get_property_cache(task.bug)
        self.assertIsNotNone(
            getattr(cache, '_notification_recipients_for_comments', None))
        with person_logged_in(task.owner):
            task.transitionToTarget(new_product, task.owner)
        self.assertIsNone(
            getattr(cache, '_notification_recipients_for_comments', None))

    def test_accesspolicyartifacts_updated(self):
        # transitionToTarget updates the AccessPolicyArtifacts related
        # to the bug.
        new_product = self.factory.makeProduct()
        bug = self.factory.makeBug(information_type=InformationType.USERDATA)

        with admin_logged_in():
            bug.default_bugtask.transitionToTarget(
                new_product, new_product.owner)

        [expected_policy] = getUtility(IAccessPolicySource).find(
            [(new_product, InformationType.USERDATA)])
        self.assertContentEqual(
            [expected_policy], get_policies_for_artifact(bug))

    def test_matching_sourcepackage_tasks_updated_when_name_changed(self):
        # If the sourcepackagename is changed, it's changed on all tasks
        # with the same distribution and sourcepackagename.

        # Create a distribution and distroseries with tasks.
        ds = self.factory.makeDistroSeries()
        bug = self.factory.makeBug(target=ds.distribution)
        ds_task = self.factory.makeBugTask(bug=bug, target=ds)

        # Also create a task for another distro. It will not be touched.
        other_distro = self.factory.makeDistribution()
        self.factory.makeBugTask(bug=bug, target=other_distro)

        self.assertContentEqual(
            (task.target for task in bug.bugtasks),
            [ds, ds.distribution, other_distro])
        sp = self.factory.makeSourcePackage(distroseries=ds, publish=True)
        with person_logged_in(ds_task.owner):
            ds_task.transitionToTarget(sp, ds_task.owner)
        self.assertContentEqual(
            (t.target for t in bug.bugtasks),
            [sp, sp.distribution_sourcepackage, other_distro])


class TransitionToMilestoneTestCase(TestCaseWithFactory):
    """Tests for BugTask.transitionToMilestone."""

    layer = DatabaseFunctionalLayer

    def test_cached_recipients_cleared(self):
        # The bug's notification recipients caches are cleared when
        # transitionToMilestone() is called.
        task = self.factory.makeBugTask()
        product = task.target
        milestone = self.factory.makeMilestone(product=product)
        # The factory caused COMMENT notifications which filled the bug cache.
        cache = get_property_cache(task.bug)
        self.assertIsNotNone(
            getattr(cache, '_notification_recipients_for_comments', None))
        with person_logged_in(task.target.owner):
            task.transitionToMilestone(milestone, task.target.owner)
        self.assertIsNone(
            getattr(cache, '_notification_recipients_for_comments', None))


class TestTransitionsRemovesSubscribersJob(TestCaseWithFactory):
    """Test that various bug transitions invoke RemoveArtifactSubscribers
    job."""

    layer = CeleryJobLayer

    def setUp(self):
        self.useFixture(FeatureFixture({
            'jobs.celery.enabled_classes': 'RemoveArtifactSubscriptionsJob',
        }))
        super(TestTransitionsRemovesSubscribersJob, self).setUp()

    def _assert_bug_change_unsubscribes(self, change_callback,
                                        ignore_policy_grantee_check=False):
        # Subscribers are unsubscribed if the bug becomes invisible due to a
        # task being retargetted.
        product = self.factory.makeProduct()
        owner = self.factory.makePerson()
        [policy] = getUtility(IAccessPolicySource).find(
            [(product, InformationType.USERDATA)])
        # The policy grantees will lose access.
        policy_grantee = self.factory.makePerson()

        self.factory.makeAccessPolicyGrant(policy, policy_grantee, owner)
        login_person(owner)
        bug = self.factory.makeBug(
            owner=owner, target=product,
            information_type=InformationType.USERDATA)

        # The artifact grantees will not lose access when the job is run.
        artifact_grantee = self.factory.makePerson()

        bug.subscribe(policy_grantee, owner)
        bug.subscribe(artifact_grantee, owner)
        # Subscribing policy_grantee has created an artifact grant so we
        # need to revoke that to test the job.
        getUtility(IAccessArtifactGrantSource).revokeByArtifact(
            getUtility(IAccessArtifactSource).find(
                [bug]), [policy_grantee])

        # policy grantees are subscribed because the job has not been run yet.
        subscribers = removeSecurityProxy(bug).getDirectSubscribers()
        self.assertIn(policy_grantee, subscribers)

        # Change bug bug attributes so that it can become inaccessible for
        # some users.
        change_callback(bug, owner)

        with block_on_job(self):
            transaction.commit()

        # Check the result. Policy grantees will be unsubscribed.
        subscribers = removeSecurityProxy(bug).getDirectSubscribers()
        # XXX wallyworld 2912-06-19 bug=1014922
        # All direct subscribers are granted access to the bug when it changes
        # and this includes people with policy grants who could see the bug
        # before a change in information type.
        if not ignore_policy_grantee_check:
            self.assertNotIn(policy_grantee, subscribers)
        self.assertIn(artifact_grantee, subscribers)

    def test_change_information_type(self):
        # Changing the information type of a bug unsubscribes users who can no
        # longer see the bug.
        def change_information_type(bug, owner):
            bug.transitionToInformationType(
                InformationType.PRIVATESECURITY, owner)

        self._assert_bug_change_unsubscribes(change_information_type, True)

    def test_change_target(self):
        # Changing the target of a bug unsubscribes users who can no
        # longer see the bug.
        def change_target(bug, owner):
            another_product = self.factory.makeProduct()
            removeSecurityProxy(bug).default_bugtask.transitionToTarget(
                another_product, owner)

        self._assert_bug_change_unsubscribes(change_target)


class TestBugTargetKeys(TestCaseWithFactory):
    """Tests for bug_target_to_key and bug_target_from_key."""

    layer = DatabaseFunctionalLayer

    def assertTargetKeyWorks(self, target, flat):
        """Check that a target flattens to the dict and back."""
        self.assertEqual(flat, bug_target_to_key(target))
        self.assertEqual(target, bug_target_from_key(**flat))

    def test_product(self):
        product = self.factory.makeProduct()
        self.assertTargetKeyWorks(
            product,
            dict(
                product=product,
                productseries=None,
                distribution=None,
                distroseries=None,
                sourcepackagename=None,
                ))

    def test_productseries(self):
        series = self.factory.makeProductSeries()
        self.assertTargetKeyWorks(
            series,
            dict(
                product=None,
                productseries=series,
                distribution=None,
                distroseries=None,
                sourcepackagename=None,
                ))

    def test_distribution(self):
        distro = self.factory.makeDistribution()
        self.assertTargetKeyWorks(
            distro,
            dict(
                product=None,
                productseries=None,
                distribution=distro,
                distroseries=None,
                sourcepackagename=None,
                ))

    def test_distroseries(self):
        distroseries = self.factory.makeDistroSeries()
        self.assertTargetKeyWorks(
            distroseries,
            dict(
                product=None,
                productseries=None,
                distribution=None,
                distroseries=distroseries,
                sourcepackagename=None,
                ))

    def test_distributionsourcepackage(self):
        dsp = self.factory.makeDistributionSourcePackage()
        self.assertTargetKeyWorks(
            dsp,
            dict(
                product=None,
                productseries=None,
                distribution=dsp.distribution,
                distroseries=None,
                sourcepackagename=dsp.sourcepackagename,
                ))

    def test_sourcepackage(self):
        sp = self.factory.makeSourcePackage()
        self.assertTargetKeyWorks(
            sp,
            dict(
                product=None,
                productseries=None,
                distribution=None,
                distroseries=sp.distroseries,
                sourcepackagename=sp.sourcepackagename,
                ))

    def test_no_key_for_non_targets(self):
        self.assertRaises(
            AssertionError, bug_target_to_key, self.factory.makePerson())

    def test_no_target_for_bad_keys(self):
        self.assertRaises(
            AssertionError, bug_target_from_key, None, None, None, None, None)


class ValidateTargetMixin:
    """ A mixin used to test validate_target and validate_new_target when used
        a private bugs to check for multi-tenant constraints.
    """

    def test_private_incorrect_pillar_task_forbidden(self):
        # Another pillar cannot be added if there is already a bugtask.
        p1 = self.factory.makeProduct(
            bug_sharing_policy=BugSharingPolicy.PROPRIETARY_OR_PUBLIC)
        p2 = self.factory.makeProduct(
            bug_sharing_policy=BugSharingPolicy.PROPRIETARY_OR_PUBLIC)
        owner = self.factory.makePerson()
        bug = self.factory.makeBug(target=p1, owner=owner)
        # validate_target allows cross-pillar transitions if there's
        # only one task, so we might need to create a second task to test.
        if not self.multi_tenant_test_one_task_only:
            self.factory.makeBugTask(
                bug=bug, target=self.factory.makeProductSeries(product=p1))
        with person_logged_in(owner):
            self.assertRaisesWithContent(
                IllegalTarget,
                "This proprietary bug already affects %s. "
                "Proprietary bugs cannot affect multiple projects."
                    % p1.displayname,
                self.validate_method, bug, p2)
            bug.transitionToInformationType(
                InformationType.USERDATA, bug.owner)
            self.validate_method(bug, p2)

    def test_private_incorrect_product_series_task_forbidden(self):
        # A product series cannot be added if there is already a bugtask for
        # a different product.
        p1 = self.factory.makeProduct(
            bug_sharing_policy=BugSharingPolicy.PROPRIETARY_OR_PUBLIC)
        p2 = self.factory.makeProduct(
            bug_sharing_policy=BugSharingPolicy.PROPRIETARY_OR_PUBLIC)
        series = self.factory.makeProductSeries(product=p2)
        owner = self.factory.makePerson()
        bug = self.factory.makeBug(target=p1, owner=owner)
        # validate_target allows cross-pillar transitions if there's
        # only one task, so we might need to create a second task to test.
        if not self.multi_tenant_test_one_task_only:
            self.factory.makeBugTask(
                bug=bug, target=self.factory.makeProductSeries(product=p1))
        with person_logged_in(owner):
            self.assertRaisesWithContent(
                IllegalTarget,
                "This proprietary bug already affects %s. "
                "Proprietary bugs cannot affect multiple projects."
                    % p1.displayname,
                self.validate_method, bug, series)
            bug.transitionToInformationType(
                InformationType.USERDATA, bug.owner)
            self.validate_method(bug, series)


class TestValidateTarget(TestCaseWithFactory, ValidateTargetMixin):

    layer = DatabaseFunctionalLayer

    multi_tenant_test_one_task_only = False

    @property
    def validate_method(self):
        # Used for ValidateTargetMixin.
        return validate_target

    def test_new_product_is_allowed(self):
        # A new product not on the bug is OK.
        p1 = self.factory.makeProduct()
        task = self.factory.makeBugTask(target=p1)
        p2 = self.factory.makeProduct()
        validate_target(task.bug, p2)

    def test_same_product_is_forbidden(self):
        # A product with an existing task is not.
        p = self.factory.makeProduct()
        task = self.factory.makeBugTask(target=p)
        self.assertRaisesWithContent(
            IllegalTarget,
            "A fix for this bug has already been requested for %s"
            % p.displayname,
            validate_target, task.bug, p)

    def test_new_distribution_is_allowed(self):
        # A new distribution not on the bug is OK.
        d1 = self.factory.makeDistribution()
        task = self.factory.makeBugTask(target=d1)
        d2 = self.factory.makeDistribution()
        validate_target(task.bug, d2)

    def test_new_productseries_is_allowed(self):
        # A new productseries not on the bug is OK.
        ds1 = self.factory.makeProductSeries()
        task = self.factory.makeBugTask(target=ds1)
        ds2 = self.factory.makeProductSeries()
        validate_target(task.bug, ds2)

    def test_new_distroseries_is_allowed(self):
        # A new distroseries not on the bug is OK.
        ds1 = self.factory.makeDistroSeries()
        task = self.factory.makeBugTask(target=ds1)
        ds2 = self.factory.makeDistroSeries()
        validate_target(task.bug, ds2)

    def test_new_sourcepackage_is_allowed(self):
        # A new sourcepackage not on the bug is OK.
        sp1 = self.factory.makeSourcePackage(publish=True)
        task = self.factory.makeBugTask(target=sp1)
        sp2 = self.factory.makeSourcePackage(publish=True)
        validate_target(task.bug, sp2)

    def test_multiple_packageless_distribution_tasks_are_forbidden(self):
        # A distribution with an existing task is not.
        d = self.factory.makeDistribution()
        task = self.factory.makeBugTask(target=d)
        self.assertRaisesWithContent(
            IllegalTarget,
            "A fix for this bug has already been requested for %s"
            % d.displayname,
            validate_target, task.bug, d)

    def test_distributionsourcepackage_task_is_allowed(self):
        # A DistributionSourcePackage task can coexist with a task for
        # its Distribution.
        d = self.factory.makeDistribution()
        task = self.factory.makeBugTask(target=d)
        dsp = self.factory.makeDistributionSourcePackage(distribution=d)
        validate_target(task.bug, dsp)

    def test_different_distributionsourcepackage_tasks_are_allowed(self):
        # A DistributionSourcePackage task can also coexist with a task
        # for another one.
        dsp1 = self.factory.makeDistributionSourcePackage()
        task = self.factory.makeBugTask(target=dsp1)
        dsp2 = self.factory.makeDistributionSourcePackage(
            distribution=dsp1.distribution)
        validate_target(task.bug, dsp2)

    def test_same_distributionsourcepackage_task_is_forbidden(self):
        # But a DistributionSourcePackage task cannot coexist with a
        # task for itself.
        dsp = self.factory.makeDistributionSourcePackage()
        task = self.factory.makeBugTask(target=dsp)
        self.assertRaisesWithContent(
            IllegalTarget,
            "A fix for this bug has already been requested for %s in %s"
            % (dsp.sourcepackagename.name, dsp.distribution.displayname),
            validate_target, task.bug, dsp)

    def test_dsp_without_publications_disallowed(self):
        # If a distribution has series, a DistributionSourcePackage task
        # can only be created if the package is published in a distro
        # archive.
        series = self.factory.makeDistroSeries()
        dsp = self.factory.makeDistributionSourcePackage(
            distribution=series.distribution)
        task = self.factory.makeBugTask()
        self.assertRaisesWithContent(
            IllegalTarget,
            "Package %s not published in %s"
            % (dsp.sourcepackagename.name, dsp.distribution.displayname),
            validate_target, task.bug, dsp)

    def test_dsp_with_publications_allowed(self):
        # If a distribution has series, a DistributionSourcePackage task
        # can only be created if the package is published in a distro
        # archive.
        series = self.factory.makeDistroSeries()
        dsp = self.factory.makeDistributionSourcePackage(
            distribution=series.distribution)
        task = self.factory.makeBugTask()
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=series, sourcepackagename=dsp.sourcepackagename,
            archive=series.main_archive)
        validate_target(task.bug, dsp)

    def test_dsp_with_only_ppa_publications_disallowed(self):
        # If a distribution has series, a DistributionSourcePackage task
        # can only be created if the package is published in a distro
        # archive. PPA publications don't count.
        series = self.factory.makeDistroSeries()
        dsp = self.factory.makeDistributionSourcePackage(
            distribution=series.distribution)
        task = self.factory.makeBugTask()
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=series, sourcepackagename=dsp.sourcepackagename,
            archive=self.factory.makeArchive(purpose=ArchivePurpose.PPA))
        self.assertRaisesWithContent(
            IllegalTarget,
            "Package %s not published in %s"
            % (dsp.sourcepackagename.name, dsp.distribution.displayname),
            validate_target, task.bug, dsp)

    def test_illegal_information_type_disallowed(self):
        # The bug's current information_type must be permitted by the
        # new target.
        free_prod = self.factory.makeProduct()
        other_free_prod = self.factory.makeProduct()
        commercial_prod = self.factory.makeProduct(
            bug_sharing_policy=BugSharingPolicy.PROPRIETARY)
        bug = self.factory.makeBug(target=free_prod)

        # The new bug is Public, which is legal on the other free product.
        self.assertIs(None, validate_target(bug, other_free_prod))

        # But not on the proprietary-only product.
        self.assertRaisesWithContent(
            IllegalTarget,
            "%s doesn't allow Public bugs." % commercial_prod.displayname,
            validate_target, bug, commercial_prod)

    def test_illegal_information_type_allowed_if_pillar_not_new(self):
        # The bug's current information_type does not have to be permitted if
        # we already affect the pillar.
        prod = self.factory.makeProduct()
        series = self.factory.makeProductSeries(product=prod)
        bug = self.factory.makeBug(
            target=prod, information_type=InformationType.USERDATA)
        self.factory.makeCommercialSubscription(prod)
        with person_logged_in(prod.owner):
            prod.setBugSharingPolicy(BugSharingPolicy.PROPRIETARY)
            validate_target(bug, series)


class TestValidateNewTarget(TestCaseWithFactory, ValidateTargetMixin):

    layer = DatabaseFunctionalLayer

    multi_tenant_test_one_task_only = True

    @property
    def validate_method(self):
        # Used for ValidateTargetMixin.
        return validate_new_target

    def test_products_are_ok(self):
        p1 = self.factory.makeProduct()
        task = self.factory.makeBugTask(target=p1)
        p2 = self.factory.makeProduct()
        validate_new_target(task.bug, p2)

    def test_calls_validate_target(self):
        p = self.factory.makeProduct()
        task = self.factory.makeBugTask(target=p)
        self.assertRaisesWithContent(
            IllegalTarget,
            "A fix for this bug has already been requested for %s"
            % p.displayname,
            validate_new_target, task.bug, p)

    def test_package_task_with_distribution_task_forbidden(self):
        d = self.factory.makeDistribution()
        dsp = self.factory.makeDistributionSourcePackage(distribution=d)
        task = self.factory.makeBugTask(target=d)
        self.assertRaisesWithContent(
            IllegalTarget,
            "This bug is already open on %s with no package specified. "
            "You should fill in a package name for the existing bug."
            % d.displayname,
            validate_new_target, task.bug, dsp)

    def test_distribution_task_with_package_task_forbidden(self):
        d = self.factory.makeDistribution()
        dsp = self.factory.makeDistributionSourcePackage(distribution=d)
        task = self.factory.makeBugTask(target=dsp)
        self.assertRaisesWithContent(
            IllegalTarget,
            "This bug is already on %s. Please specify an affected "
            "package in which the bug has not yet been reported."
            % d.displayname,
            validate_new_target, task.bug, d)


class TestWebservice(TestCaseWithFactory):
    """Tests for the webservice."""

    layer = AppServerLayer

    def test_delete_bugtask(self):
        """Test that a bugtask can be deleted."""
        owner = self.factory.makePerson()
        some_person = self.factory.makePerson()
        db_bug = self.factory.makeBug()
        db_bugtask = self.factory.makeBugTask(bug=db_bug, owner=owner)
        transaction.commit()
        logout()

        # It will fail for an unauthorised user.
        launchpad = self.factory.makeLaunchpadService(some_person)
        bugtask = ws_object(launchpad, db_bugtask)
        self.assertRaises(Unauthorized, bugtask.lp_delete)

        launchpad = self.factory.makeLaunchpadService(owner)
        bugtask = ws_object(launchpad, db_bugtask)
        bugtask.lp_delete()
        transaction.commit()
        # Check the delete really worked.
        with person_logged_in(removeSecurityProxy(db_bug).owner):
            self.assertEqual([db_bug.default_bugtask], db_bug.bugtasks)


class TestBugTaskUserHasBugSupervisorPrivileges(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBugTaskUserHasBugSupervisorPrivileges, self).setUp()
        self.celebrities = getUtility(ILaunchpadCelebrities)

    def test_admin_is_allowed(self):
        # An admin always has privileges.
        bugtask = self.factory.makeBugTask()
        self.assertTrue(
            bugtask.userHasBugSupervisorPrivileges(self.celebrities.admin))

    def test_bug_celebrities_are_allowed(self):
        # The three bug celebrities (bug watcher, bug importer and
        # janitor always have privileges.
        bugtask = self.factory.makeBugTask()
        for celeb in (
            self.celebrities.bug_watch_updater,
            self.celebrities.bug_importer, self.celebrities.janitor):
            self.assertTrue(bugtask.userHasBugSupervisorPrivileges(celeb))

    def test_pillar_owner_is_allowed(self):
        # The pillar owner has privileges.
        pillar = self.factory.makeProduct()
        bugtask = self.factory.makeBugTask(target=pillar)
        self.assertTrue(bugtask.userHasBugSupervisorPrivileges(pillar.owner))

    def test_pillar_driver_is_allowed(self):
        # The pillar driver has privileges.
        pillar = self.factory.makeProduct()
        removeSecurityProxy(pillar).driver = self.factory.makePerson()
        bugtask = self.factory.makeBugTask(target=pillar)
        self.assertTrue(
            bugtask.userHasBugSupervisorPrivileges(pillar.driver))

    def test_pillar_bug_supervisor(self):
        # The pillar bug supervisor has privileges.
        bugsupervisor = self.factory.makePerson()
        pillar = self.factory.makeProduct(bug_supervisor=bugsupervisor)
        bugtask = self.factory.makeBugTask(target=pillar)
        self.assertTrue(
            bugtask.userHasBugSupervisorPrivileges(bugsupervisor))

    def test_productseries_driver_is_allowed(self):
        # The series driver has privileges.
        series = self.factory.makeProductSeries()
        removeSecurityProxy(series).driver = self.factory.makePerson()
        bugtask = self.factory.makeBugTask(target=series)
        self.assertTrue(
            bugtask.userHasBugSupervisorPrivileges(series.driver))

    def test_distroseries_driver_is_allowed(self):
        # The series driver has privileges.
        distroseries = self.factory.makeDistroSeries()
        removeSecurityProxy(distroseries).driver = self.factory.makePerson()
        bugtask = self.factory.makeBugTask(target=distroseries)
        self.assertTrue(
            bugtask.userHasBugSupervisorPrivileges(distroseries.driver))

    def test_commercial_admin_has_no_privileges(self):
        # Commercial admins have no privileges.
        pillar = self.factory.makeProduct()
        self.factory.makeCommercialSubscription(pillar)
        bugtask = self.factory.makeBugTask(target=pillar)
        commercial_admin = self.factory.makeCommercialAdmin()
        self.assertFalse(
            bugtask.userHasBugSupervisorPrivileges(commercial_admin))

    def test_random_has_no_privileges(self):
        # Joe Random has no privileges.
        bugtask = self.factory.makeBugTask()
        self.assertFalse(
            bugtask.userHasBugSupervisorPrivileges(
                self.factory.makePerson()))


class TestBugTaskUserHasBugSupervisorPrivilegesContext(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def assert_userHasBugSupervisorPrivilegesContext(self, obj):
        self.assertFalse(
            BugTask.userHasBugSupervisorPrivilegesContext(
                obj, self.factory.makePerson()))

    def test_distribution(self):
        distribution = self.factory.makeDistribution()
        self.assert_userHasBugSupervisorPrivilegesContext(distribution)

    def test_distributionsourcepackage(self):
        dsp = self.factory.makeDistributionSourcePackage()
        self.assert_userHasBugSupervisorPrivilegesContext(dsp)

    def test_product(self):
        product = self.factory.makeProduct()
        self.assert_userHasBugSupervisorPrivilegesContext(product)

    def test_productseries(self):
        productseries = self.factory.makeProductSeries()
        self.assert_userHasBugSupervisorPrivilegesContext(productseries)

    def test_sourcepackage(self):
        source = self.factory.makeSourcePackage()
        self.assert_userHasBugSupervisorPrivilegesContext(source)


class TestTargetNameCache(TestCase):
    """BugTask table has a stored computed attribute.

    This targetnamecache attribute which stores a computed value to allow us
    to sort and search on that value without having to do lots of SQL joins.
    This cached value gets updated daily by the
    update-bugtask-targetnamecaches cronscript and whenever the bugtask is
    changed.  Of course, it's also computed and set when a bugtask is
    created.

    `BugTask.bugtargetdisplayname` simply returns `targetnamecache`, and
    the latter is not exposed in `IBugTask`, so the `bugtargetdisplayname`
    is used here.

    XXX: rharding 2012-05-14 bug=999298: These tests are ported from doctests
    and do too much work. They should be split into simpler and better unit
    tests.
    """

    layer = DatabaseFunctionalLayer

    def test_cron_updating_targetnamecache(self):
        """Verify the initial target name cache."""
        login('foo.bar@canonical.com')
        bug_one = getUtility(IBugSet).get(1)
        mark = getUtility(IPersonSet).getByEmail('mark@example.com')
        netapplet = getUtility(IProductSet).get(11)

        upstream_task = getUtility(IBugTaskSet).createTask(
            bug_one, mark, netapplet,
            status=BugTaskStatus.NEW, importance=BugTaskImportance.MEDIUM)
        self.assertEqual(upstream_task.bugtargetdisplayname, u'NetApplet')

        thunderbird = getUtility(IProductSet).get(8)
        upstream_task_id = upstream_task.id
        upstream_task.transitionToTarget(thunderbird, bug_one.owner)
        self.assertEqual(upstream_task.bugtargetdisplayname,
                         u'Mozilla Thunderbird')

        thunderbird.name = 'thunderbird-ng'
        thunderbird.displayname = 'Mozilla Thunderbird NG'

        # XXX Guilherme Salgado 2005-11-07 bug=3989:
        # This flush_database_updates() shouldn't be needed because we
        # already have the transaction.commit() here, but without it
        # (flush_database_updates), the cronscript won't see the thunderbird
        # name change.
        flush_database_updates()
        transaction.commit()

        process = subprocess.Popen(
            'cronscripts/update-bugtask-targetnamecaches.py', shell=True,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        (out, err) = process.communicate()

        self.assertTrue(err.startswith(("INFO    Creating lockfile: "
            "/var/lock/launchpad-launchpad-targetnamecacheupdater.lock")))
        self.assertTrue('INFO    Updating targetname cache of bugtasks' in err)
        self.assertTrue('INFO    Calculating targets.' in err)
        self.assertTrue('INFO    Will check ', err)
        self.assertTrue("INFO    Updating (u'Mozilla Thunderbird',)" in err)
        self.assertTrue('INFO    Updated 1 target names.' in err)
        self.assertTrue('INFO    Finished updating targetname cache' in err)

        self.assertEqual(process.returncode, 0)

        # XXX Guilherme Salgado 2005-11-07:
        # If we don't call flush_database_caches() here, we won't see the
        # changes made by the cronscript in objects we already have cached.
        flush_database_caches()
        transaction.commit()

        self.assertEqual(
            getUtility(IBugTaskSet).get(upstream_task_id).bugtargetdisplayname,
            u'Mozilla Thunderbird NG')

        # With sourcepackage bugtasks that have accepted nominations to a
        # series, additional sourcepackage bugtasks are automatically
        # nominated to the same series. The nominations are implicitly
        # accepted and have targetnamecache updated.
        ubuntu = getUtility(IDistributionSet).get(1)

        params = CreateBugParams(
            mark, 'New Bug', comment='New Bug',
            target=ubuntu.getSourcePackage('mozilla-firefox'))
        new_bug, new_bug_event = getUtility(IBugSet).createBug(
            params, notify_event=False)

        # The first message of a new bug has index 0.
        self.assertEqual(new_bug.bug_messages[0].index, 0)

        # The first task has been created and successfully nominated to Hoary.
        new_bug.addNomination(mark, ubuntu.currentseries).approve(mark)

        task_set = [task.bugtargetdisplayname for task in new_bug.bugtasks]
        self.assertEqual(task_set, [
            'mozilla-firefox (Ubuntu)',
            'mozilla-firefox (Ubuntu Hoary)',
        ])

        getUtility(IBugTaskSet).createTask(
            new_bug, mark, ubuntu.getSourcePackage('alsa-utils'))

        # The second task has been created and has also been successfully
        # nominated to Hoary.

        task_set = [task.bugtargetdisplayname for task in new_bug.bugtasks]
        self.assertEqual(task_set, [
            'alsa-utils (Ubuntu)',
            'mozilla-firefox (Ubuntu)',
            'alsa-utils (Ubuntu Hoary)',
            'mozilla-firefox (Ubuntu Hoary)',
        ])

        # The updating of targetnamecaches is usually done by the cronjob,
        # however it can also be invoked directly.
        thunderbird.name = 'thunderbird'
        thunderbird.displayname = 'Mozilla Thunderbird'
        transaction.commit()

        self.assertEqual(upstream_task.bugtargetdisplayname,
            u'Mozilla Thunderbird NG')

        logger = FakeLogger()
        updater = BugTaskTargetNameCacheUpdater(transaction, logger)
        updater.run()

        flush_database_caches()
        transaction.commit()
        self.assertEqual(upstream_task.bugtargetdisplayname,
            u'Mozilla Thunderbird')
