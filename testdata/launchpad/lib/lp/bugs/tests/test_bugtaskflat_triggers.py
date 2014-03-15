# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from collections import namedtuple
from contextlib import contextmanager

from testtools.matchers import MatchesStructure
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.bugs.interfaces.bugtask import BugTaskStatus
from lp.bugs.model.bug import Bug
from lp.registry.interfaces.accesspolicy import (
    IAccessArtifactGrantSource,
    IAccessArtifactSource,
    IAccessPolicyArtifactSource,
    IAccessPolicySource,
    )
from lp.services.database.interfaces import IStore
from lp.testing import (
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.dbuser import dbuser
from lp.testing.layers import DatabaseFunctionalLayer


BUGTASKFLAT_COLUMNS = (
    'bugtask',
    'bug',
    'datecreated',
    'latest_patch_uploaded',
    'date_closed',
    'date_last_updated',
    'duplicateof',
    'bug_owner',
    'fti',
    'information_type',
    'heat',
    'product',
    'productseries',
    'distribution',
    'distroseries',
    'sourcepackagename',
    'status',
    'importance',
    'assignee',
    'milestone',
    'owner',
    'active',
    'access_policies',
    'access_grants',
    )

BugTaskFlat = namedtuple('BugTaskFlat', BUGTASKFLAT_COLUMNS)


class BugTaskFlatTestMixin(TestCaseWithFactory):

    def checkFlattened(self, bugtask, check_only=True):
        if hasattr(bugtask, 'id'):
            bugtask = bugtask.id
        result = IStore(Bug).execute(
            "SELECT bugtask_flatten(?, ?)", (bugtask, check_only))
        return result.get_one()[0]

    def assertFlattened(self, bugtask):
        # Assert that the BugTask is correctly represented in
        # BugTaskFlat.
        self.assertIs(True, self.checkFlattened(bugtask))

    def assertFlattens(self, bugtask):
        # Assert that the BugTask isn't correctly represented in
        # BugTaskFlat, but a call to bugtask_flatten fixes it.
        self.assertFalse(self.checkFlattened(bugtask))
        self.checkFlattened(bugtask, check_only=False)
        self.assertTrue(self.checkFlattened(bugtask))

    def getBugTaskFlat(self, bugtask):
        if hasattr(bugtask, 'id'):
            bugtask = bugtask.id
        assert bugtask is not None
        result = IStore(Bug).execute(
            "SELECT %s FROM bugtaskflat WHERE bugtask = ?"
            % ', '.join(BUGTASKFLAT_COLUMNS), (bugtask,)).get_one()
        if result is not None:
            result = BugTaskFlat(*result)
        return result

    def makeLoggedInTask(self, private=False):
        owner = self.factory.makePerson()
        if private:
            information_type = InformationType.USERDATA
        else:
            information_type = InformationType.PUBLIC
        login_person(owner)
        bug = self.factory.makeBug(
            information_type=information_type, owner=owner)
        return bug.default_bugtask

    @contextmanager
    def bugtaskflat_is_deleted(self, bugtask):
        old_row = self.getBugTaskFlat(bugtask)
        self.assertFlattened(bugtask)
        self.assertIsNot(None, old_row)
        yield
        new_row = self.getBugTaskFlat(bugtask)
        self.assertFlattened(bugtask)
        self.assertIs(None, new_row)

    @contextmanager
    def bugtaskflat_is_updated(self, bugtask, expected_fields):
        old_row = self.getBugTaskFlat(bugtask)
        self.assertFlattened(bugtask)
        yield
        new_row = self.getBugTaskFlat(bugtask)
        self.assertFlattened(bugtask)
        changed_fields = [
            field for field in BugTaskFlat._fields
            if getattr(old_row, field) != getattr(new_row, field)]
        self.assertEqual(expected_fields, changed_fields)

    @contextmanager
    def bugtaskflat_is_identical(self, bugtask):
        old_row = self.getBugTaskFlat(bugtask)
        self.assertFlattened(bugtask)
        yield
        new_row = self.getBugTaskFlat(bugtask)
        self.assertFlattened(bugtask)
        self.assertEqual(old_row, new_row)


class TestBugTaskFlatten(BugTaskFlatTestMixin):

    layer = DatabaseFunctionalLayer

    def test_create(self):
        # bugtask_flatten() returns true if the BugTaskFlat is missing,
        # and optionally creates it.
        task = self.factory.makeBugTask()
        self.assertTrue(self.checkFlattened(task))
        with dbuser('testadmin'):
            IStore(Bug).execute(
                "DELETE FROM BugTaskFlat WHERE bugtask = ?", (task.id,))
        self.assertFlattens(task)

    def test_update(self):
        # bugtask_flatten() returns true if the BugTaskFlat is out of
        # date, and optionally updates it.
        task = self.factory.makeBugTask()
        self.assertTrue(self.checkFlattened(task))
        with dbuser('testadmin'):
            IStore(Bug).execute(
                "UPDATE BugTaskFlat SET status = ? WHERE bugtask = ?",
                (BugTaskStatus.UNKNOWN.value, task.id))
        self.assertFlattens(task)

    def test_delete(self):
        # bugtask_flatten() returns true if the BugTaskFlat exists but
        # the task doesn't, and optionally deletes it.
        self.assertTrue(self.checkFlattened(200))
        with dbuser('testadmin'):
            IStore(Bug).execute(
                "INSERT INTO bugtaskflat "
                "(bug, bugtask, bug_owner, information_type, "
                " date_last_updated, heat, status, importance, owner, "
                " active) "
                "VALUES "
                "(1, 200, 1, 1, "
                " current_timestamp at time zone 'UTC', 999, 1, 1, 1, true);")
        self.assertFlattens(200)

    def test_values(self):
        task = self.factory.makeBugTask()
        with person_logged_in(task.product.owner):
            task.transitionToAssignee(self.factory.makePerson())
            task.transitionToMilestone(
                self.factory.makeMilestone(product=task.product),
                task.product.owner)
            task.bug.markAsDuplicate(self.factory.makeBug())
        flat = self.getBugTaskFlat(task)
        self.assertThat(
            flat,
            MatchesStructure.byEquality(
                bugtask=task.id,
                bug=task.bug.id,
                datecreated=task.datecreated.replace(tzinfo=None),
                duplicateof=task.bug.duplicateof.id,
                bug_owner=task.bug.owner.id,
                information_type=task.bug.information_type.value,
                date_last_updated=task.bug.date_last_updated.replace(
                    tzinfo=None),
                heat=task.bug.heat,
                product=task.product.id,
                productseries=None,
                distribution=None,
                distroseries=None,
                sourcepackagename=None,
                status=task.status.value,
                importance=task.importance.value,
                assignee=task.assignee.id,
                milestone=task.milestone.id,
                owner=task.owner.id,
                active=task.product.active,
                access_policies=None,
                access_grants=None))
        self.assertIsNot(None, flat.fti)

    def test_productseries_target(self):
        ps = self.factory.makeProductSeries()
        task = self.factory.makeBugTask(target=ps)
        flat = self.getBugTaskFlat(task)
        self.assertThat(
            flat,
            MatchesStructure.byEquality(
                product=None, productseries=ps.id, distribution=None,
                distroseries=None, sourcepackagename=None, active=True))

    def test_distributionsourcepackage_target(self):
        dsp = self.factory.makeDistributionSourcePackage()
        task = self.factory.makeBugTask(target=dsp)
        flat = self.getBugTaskFlat(task)
        self.assertThat(
            flat,
            MatchesStructure.byEquality(
                product=None, productseries=None,
                distribution=dsp.distribution.id, distroseries=None,
                sourcepackagename=dsp.sourcepackagename.id, active=True))

    def test_sourcepackage_target(self):
        sp = self.factory.makeSourcePackage()
        task = self.factory.makeBugTask(target=sp)
        flat = self.getBugTaskFlat(task)
        self.assertThat(
            flat,
            MatchesStructure.byEquality(
                product=None, productseries=None, distribution=None,
                distroseries=sp.distroseries.id,
                sourcepackagename=sp.sourcepackagename.id, active=True))

    def test_product_active_flag_respected(self):
        # A bugtask created on a product or productseries respects the
        # product's active flag. Note that there are no triggers to
        # handle this change, as the number of changes can be too large.
        # A job will be used instead.
        p = self.factory.makeProduct()
        removeSecurityProxy(p).active = False
        ps = self.factory.makeProductSeries(product=p)
        ptask = self.factory.makeBugTask(target=p)
        pstask = self.factory.makeBugTask(target=ps)
        self.assertEqual(False, self.getBugTaskFlat(ptask).active)
        self.assertEqual(False, self.getBugTaskFlat(pstask).active)

    def test_public_access_cache_is_null(self):
        # access_policies and access_grants for a public bug are NULL.
        bugtask = self.makeLoggedInTask()
        flat = self.getBugTaskFlat(bugtask.id)
        self.assertIs(None, flat.access_policies)
        self.assertIs(None, flat.access_grants)

    def test_private_access_cache_is_set(self):
        # access_policies and access_grants for a private bug are
        # mirrored appropriately.
        bugtask = self.makeLoggedInTask(private=True)
        flat = self.getBugTaskFlat(bugtask.id)
        [policy] = getUtility(IAccessPolicySource).find(
            [(bugtask.pillar, InformationType.USERDATA)])
        self.assertContentEqual([policy.id], flat.access_policies)
        self.assertContentEqual(
            [p.id for p in bugtask.bug.getDirectSubscribers()],
            flat.access_grants)


class TestBugTaskFlatTriggers(BugTaskFlatTestMixin):

    layer = DatabaseFunctionalLayer

    def test_bugtask_create(self):
        # Triggers maintain BugTaskFlat when a task is created.
        task = self.factory.makeBugTask()
        self.assertFlattened(task)

    def test_bugtask_delete(self):
        # Triggers maintain BugTaskFlat when a task is deleted.
        task = self.makeLoggedInTask()
        # We need a second task before it will let us delete the first.
        self.factory.makeBugTask(bug=task.bug)
        with self.bugtaskflat_is_deleted(task):
            task.delete()

    def test_bugtask_change(self):
        # Triggers maintain BugTaskFlat when a task is changed.
        task = self.makeLoggedInTask()
        with self.bugtaskflat_is_updated(task, ['status']):
            task.transitionToStatus(BugTaskStatus.UNKNOWN, task.owner)

    def test_bugtask_change_unflattened(self):
        # Some fields on BugTask aren't mirrored, so don't trigger updates.
        task = self.makeLoggedInTask()
        with self.bugtaskflat_is_identical(task):
            task.bugwatch = self.factory.makeBugWatch()

    def test_bug_change(self):
        # Triggers maintain BugTaskFlat when a bug is changed
        task = self.makeLoggedInTask()
        with self.bugtaskflat_is_updated(task, ['information_type']):
            removeSecurityProxy(task.bug).information_type = (
                InformationType.PUBLICSECURITY)

    def test_bug_make_private(self):
        # Triggers maintain BugTaskFlat when a bug is made private.
        task = self.makeLoggedInTask()
        with self.bugtaskflat_is_updated(
            task, ['information_type', 'access_policies', 'access_grants']):
            removeSecurityProxy(task.bug).information_type = (
                InformationType.USERDATA)

    def test_bug_make_public(self):
        # Triggers maintain BugTaskFlat when a bug is made public.
        task = self.makeLoggedInTask(private=True)
        with self.bugtaskflat_is_updated(
            task, [
                'information_type', 'heat', 'access_policies',
                'access_grants']):
            task.bug.setPrivate(False, task.owner)

    def test_bug_change_unflattened(self):
        # Some fields on Bug aren't mirrored, so don't trigger updates.
        task = self.makeLoggedInTask()
        with self.bugtaskflat_is_identical(task):
            removeSecurityProxy(task.bug).who_made_private = task.owner

    def test_accessartifactgrant_create(self):
        # Creating an AccessArtifactGrant updates the relevant bugs.
        task = self.makeLoggedInTask(private=True)
        [artifact] = getUtility(IAccessArtifactSource).find([task.bug])
        with self.bugtaskflat_is_updated(task, ['access_grants']):
            self.factory.makeAccessArtifactGrant(artifact=artifact)

    def test_accessartifactgrant_update(self):
        # Updating an AccessArtifactGrant updates the relevant bugs.
        # Person merge is the main use case here.
        task = self.makeLoggedInTask(private=True)
        [artifact] = getUtility(IAccessArtifactSource).find([task.bug])
        grant = self.factory.makeAccessArtifactGrant(artifact=artifact)
        with self.bugtaskflat_is_updated(task, ['access_grants']):
            removeSecurityProxy(grant).grantee = self.factory.makePerson()

    def test_accessartifactgrant_delete(self):
        # Deleting an AccessArtifactGrant updates the relevant bugs.
        task = self.makeLoggedInTask(private=True)
        [artifact] = getUtility(IAccessArtifactSource).find([task.bug])
        self.factory.makeAccessArtifactGrant(artifact=artifact)
        with self.bugtaskflat_is_updated(task, ['access_grants']):
            getUtility(IAccessArtifactGrantSource).revokeByArtifact(
                [artifact])

    def test_accesspolicyartifact_create(self):
        # Creating an AccessPolicyArtifact updates the relevant bugtasks.
        task = self.makeLoggedInTask(private=True)
        [artifact] = getUtility(IAccessArtifactSource).find([task.bug])
        with self.bugtaskflat_is_updated(task, ['access_policies']):
            self.factory.makeAccessPolicyArtifact(artifact=artifact)

    def test_accesspolicyartifact_update(self):
        # Updating an AccessPolicyArtifact updates the relevant bugs.
        # There are currently no users of this, but it still works.
        task = self.makeLoggedInTask(private=True)
        [artifact] = getUtility(IAccessArtifactSource).find([task.bug])
        link = self.factory.makeAccessPolicyArtifact(artifact=artifact)
        with self.bugtaskflat_is_updated(task, ['access_policies']):
            removeSecurityProxy(link).policy = self.factory.makeAccessPolicy()

    def test_accesspolicyartifact_delete(self):
        # Deleting an AccessPolicyArtifact updates the relevant bugtasks.
        task = self.makeLoggedInTask(private=True)
        [artifact] = getUtility(IAccessArtifactSource).find([task.bug])
        self.factory.makeAccessPolicyArtifact(artifact=artifact)
        with self.bugtaskflat_is_updated(task, ['access_policies']):
            getUtility(IAccessPolicyArtifactSource).deleteByArtifact(
                [artifact])

    def test_access_create_public(self):
        # Creating a grant or policy link on a public bug has no effect.
        # The access caches remain null.
        task = self.makeLoggedInTask()
        with self.bugtaskflat_is_identical(task):
            [artifact] = getUtility(IAccessArtifactSource).ensure([task.bug])
            self.factory.makeAccessPolicyArtifact(artifact=artifact)
            self.factory.makeAccessArtifactGrant(artifact=artifact)

    def test_accessartifact_delete(self):
        # Deleting an AccessArtifact removes the corresponding
        # AccessArtifactGrant and AccessPolicyArtifact rows. Even though
        # it's hopefully impossible for a private bug to not have an
        # AccessArtifact, access_policies and access_grants are empty
        # lists, not NULL.
        task = self.makeLoggedInTask(private=True)
        with self.bugtaskflat_is_updated(
            task, ['access_policies', 'access_grants']):
            getUtility(IAccessArtifactSource).delete([task.bug])
        flat = self.getBugTaskFlat(task.id)
        self.assertEqual([], flat.access_policies)
        self.assertEqual([], flat.access_grants)
