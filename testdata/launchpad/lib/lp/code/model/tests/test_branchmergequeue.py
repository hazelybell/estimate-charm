# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for methods of BranchMergeQueue."""

from __future__ import with_statement

import simplejson

from lp.code.errors import InvalidMergeQueueConfig
from lp.code.interfaces.branchmergequeue import IBranchMergeQueue
from lp.code.model.branchmergequeue import BranchMergeQueue
from lp.services.database.interfaces import IStore
from lp.testing import (
    ANONYMOUS,
    launchpadlib_for,
    person_logged_in,
    TestCaseWithFactory,
    verifyObject,
    ws_object,
    )
from lp.testing.layers import (
    AppServerLayer,
    DatabaseFunctionalLayer,
    )


class TestBranchMergeQueueInterface(TestCaseWithFactory):
    """Test IBranchMergeQueue interface."""

    layer = DatabaseFunctionalLayer

    def test_implements_interface(self):
        queue = self.factory.makeBranchMergeQueue()
        IStore(BranchMergeQueue).add(queue)
        verifyObject(IBranchMergeQueue, queue)


class TestBranchMergeQueueSource(TestCaseWithFactory):
    """Test the methods of IBranchMergeQueueSource."""

    layer = DatabaseFunctionalLayer

    def test_new(self):
        owner = self.factory.makePerson()
        name = u'SooperQueue'
        description = u'This is Sooper Queue'
        config = unicode(simplejson.dumps({'test': 'make check'}))

        queue = BranchMergeQueue.new(
            name, owner, owner, description, config)

        self.assertEqual(queue.name, name)
        self.assertEqual(queue.owner, owner)
        self.assertEqual(queue.registrant, owner)
        self.assertEqual(queue.description, description)
        self.assertEqual(queue.configuration, config)


class TestBranchMergeQueue(TestCaseWithFactory):
    """Test the functions of the BranchMergeQueue."""

    layer = DatabaseFunctionalLayer

    def test_branches(self):
        """Test that a merge queue can get all its managed branches."""
        store = IStore(BranchMergeQueue)

        queue = self.factory.makeBranchMergeQueue()
        store.add(queue)

        branch = self.factory.makeBranch()
        store.add(branch)
        with person_logged_in(branch.owner):
            branch.addToQueue(queue)

        self.assertEqual(
            list(queue.branches),
            [branch])

    def test_setMergeQueueConfig(self):
        """Test that the configuration is set properly."""
        queue = self.factory.makeBranchMergeQueue()
        config = unicode(simplejson.dumps({
            'test': 'make test'}))

        with person_logged_in(queue.owner):
            queue.setMergeQueueConfig(config)

        self.assertEqual(queue.configuration, config)

    def test_setMergeQueueConfig_invalid_json(self):
        """Test that invalid json can't be set as the config."""
        queue = self.factory.makeBranchMergeQueue()

        with person_logged_in(queue.owner):
            self.assertRaises(
                InvalidMergeQueueConfig,
                queue.setMergeQueueConfig,
                'abc')


class TestWebservice(TestCaseWithFactory):

    layer = AppServerLayer

    def test_properties(self):
        """Test that the correct properties are exposed."""
        with person_logged_in(ANONYMOUS):
            name = u'teh-queue'
            description = u'Oh hai! I are a queues'
            configuration = unicode(simplejson.dumps({'test': 'make check'}))

            queuer = self.factory.makePerson()
            db_queue = self.factory.makeBranchMergeQueue(
                registrant=queuer, owner=queuer, name=name,
                description=description,
                configuration=configuration)
            branch1 = self.factory.makeBranch()
            with person_logged_in(branch1.owner):
                branch1.addToQueue(db_queue)
            branch2 = self.factory.makeBranch()
            with person_logged_in(branch2.owner):
                branch2.addToQueue(db_queue)
            launchpad = launchpadlib_for('test', db_queue.owner,
                service_root="http://api.launchpad.dev:8085")

        queuer = ws_object(launchpad, queuer)
        queue = ws_object(launchpad, db_queue)
        branch1 = ws_object(launchpad, branch1)
        branch2 = ws_object(launchpad, branch2)

        self.assertEqual(queue.registrant, queuer)
        self.assertEqual(queue.owner, queuer)
        self.assertEqual(queue.name, name)
        self.assertEqual(queue.description, description)
        self.assertEqual(queue.configuration, configuration)
        self.assertEqual(queue.date_created, db_queue.date_created)
        self.assertEqual(len(queue.branches), 2)

    def test_set_configuration(self):
        """Test the mutator for setting configuration."""
        with person_logged_in(ANONYMOUS):
            db_queue = self.factory.makeBranchMergeQueue()
            launchpad = launchpadlib_for('test', db_queue.owner,
                service_root="http://api.launchpad.dev:8085")

        configuration = simplejson.dumps({'test': 'make check'})

        queue = ws_object(launchpad, db_queue)
        queue.configuration = configuration
        queue.lp_save()

        queue2 = ws_object(launchpad, db_queue)
        self.assertEqual(queue2.configuration, configuration)
