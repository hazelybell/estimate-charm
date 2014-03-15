# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the dynamic RewriteMap used to serve branches over HTTP."""

__metaclass__ = type

import os
import re
import signal
import subprocess

import transaction
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import InformationType
from lp.code.interfaces.codehosting import branch_id_alias
from lp.codehosting.rewrite import BranchRewriter
from lp.codehosting.vfs import branch_id_to_path
from lp.services.config import config
from lp.services.log.logger import BufferLogger
from lp.testing import (
    FakeTime,
    nonblocking_readline,
    person_logged_in,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.fixture import PGBouncerFixture
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    DatabaseLayer,
    )


class TestBranchRewriter(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBranchRewriter, self).setUp()
        self.fake_time = FakeTime(0)

    def makeRewriter(self):
        return BranchRewriter(BufferLogger(), self.fake_time.now)

    def getLoggerOutput(self, rewriter):
        return rewriter.logger.getLogBuffer()

    def test_rewriteLine_found_dot_bzr(self):
        # Requests for /$branch_name/.bzr/... are redirected to where the
        # branches are served from by ID.
        rewriter = self.makeRewriter()
        branches = [
            self.factory.makeProductBranch(),
            self.factory.makePersonalBranch(),
            self.factory.makePackageBranch()]
        transaction.commit()
        output = [
            rewriter.rewriteLine("/%s/.bzr/README" % branch.unique_name)
            for branch in branches]
        expected = [
            'file:///var/tmp/bazaar.launchpad.dev/mirrors/%s/.bzr/README'
            % branch_id_to_path(branch.id)
            for branch in branches]
        self.assertEqual(expected, output)

    def test_rewriteLine_found_not_dot_bzr(self):
        # Requests for /$branch_name/... that are not to .bzr directories are
        # redirected to codebrowse.
        rewriter = self.makeRewriter()
        branches = [
            self.factory.makeProductBranch(),
            self.factory.makePersonalBranch(),
            self.factory.makePackageBranch()]
        transaction.commit()
        output = [
            rewriter.rewriteLine("/%s/changes" % branch.unique_name)
            for branch in branches]
        expected = [
            'http://localhost:8080/%s/changes' % branch.unique_name
            for branch in branches]
        self.assertEqual(expected, output)

    def test_rewriteLine_private(self):
        # All requests for /$branch_name/... for private branches are
        # rewritten to codebrowse, which will then redirect them to https and
        # handle them there.
        rewriter = self.makeRewriter()
        branch = self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA)
        unique_name = removeSecurityProxy(branch).unique_name
        transaction.commit()
        output = [
            rewriter.rewriteLine("/%s/changes" % unique_name),
            rewriter.rewriteLine("/%s/.bzr" % unique_name)
            ]
        self.assertEqual(
            ['http://localhost:8080/%s/changes' % unique_name,
             'http://localhost:8080/%s/.bzr' % unique_name],
            output)

    def test_rewriteLine_id_alias_found_dot_bzr(self):
        # Requests for /+branch-id/$id/.bzr/... are redirected to where the
        # branches are served from by ID if they are public.
        rewriter = self.makeRewriter()
        branches = [
            self.factory.makeProductBranch(),
            self.factory.makePersonalBranch(),
            self.factory.makePackageBranch()]
        transaction.commit()
        output = [
            rewriter.rewriteLine(
                "%s/.bzr/README" % branch_id_alias(branch))
            for branch in branches]
        expected = [
            'file:///var/tmp/bazaar.launchpad.dev/mirrors/%s/.bzr/README'
            % branch_id_to_path(branch.id)
            for branch in branches]
        self.assertEqual(expected, output)

    def test_rewriteLine_id_alias_private(self):
        # All requests for /+branch-id/$id/... for private branches return
        # 'NULL'.  This is translated by apache to a 404.
        rewriter = self.makeRewriter()
        branch = self.factory.makeAnyBranch(
            information_type=InformationType.USERDATA)
        path = branch_id_alias(removeSecurityProxy(branch))
        transaction.commit()
        output = [
            rewriter.rewriteLine("%s/changes" % path),
            rewriter.rewriteLine("%s/.bzr" % path)
            ]
        self.assertEqual(['NULL', 'NULL'], output)

    def test_rewriteLine_id_alias_logs_cache_hit(self):
        # The second request for a branch using the alias hits the cache.
        rewriter = self.makeRewriter()
        branch = self.factory.makeAnyBranch()
        transaction.commit()
        path = "%s/.bzr/README" % branch_id_alias(branch)
        rewriter.rewriteLine(path)
        rewriter.rewriteLine(path)
        logging_output_lines = self.getLoggerOutput(
            rewriter).strip().split('\n')
        self.assertEqual(2, len(logging_output_lines))
        self.assertIsNot(
            None,
            re.match("INFO .* -> .* (.*s, cache: HIT)",
                     logging_output_lines[-1]),
            "No hit found in %r" % logging_output_lines[-1])

    def test_rewriteLine_static(self):
        # Requests to /static are rewritten to codebrowse urls.
        rewriter = self.makeRewriter()
        output = rewriter.rewriteLine("/static/foo")
        self.assertEqual(
            'http://localhost:8080/static/foo',
            output)

    def test_rewriteLine_not_found(self):
        # If the request does not map to a branch, we redirect it to
        # codebrowse as it can generate a 404.
        rewriter = self.makeRewriter()
        not_found_path = "/~nouser/noproduct"
        output = rewriter.rewriteLine(not_found_path)
        self.assertEqual(
            'http://localhost:8080%s' % not_found_path,
            output)

    def test_rewriteLine_logs_cache_miss(self):
        # The first request for a branch misses the cache and logs this fact.
        rewriter = self.makeRewriter()
        branch = self.factory.makeAnyBranch()
        transaction.commit()
        rewriter.rewriteLine('/' + branch.unique_name + '/.bzr/README')
        logging_output = self.getLoggerOutput(rewriter)
        self.assertIsNot(
            None,
            re.match("INFO .* -> .* (.*s, cache: MISS)", logging_output),
            "No miss found in %r" % logging_output)

    def test_rewriteLine_logs_cache_hit(self):
        # The second request for a branch misses the cache and logs this fact.
        rewriter = self.makeRewriter()
        branch = self.factory.makeAnyBranch()
        transaction.commit()
        rewriter.rewriteLine('/' + branch.unique_name + '/.bzr/README')
        rewriter.rewriteLine('/' + branch.unique_name + '/.bzr/README')
        logging_output_lines = self.getLoggerOutput(
            rewriter).strip().split('\n')
        self.assertEqual(2, len(logging_output_lines))
        self.assertIsNot(
            None,
            re.match("INFO .* -> .* (.*s, cache: HIT)",
                     logging_output_lines[-1]),
            "No hit found in %r" % logging_output_lines[-1])

    def test_rewriteLine_cache_expires(self):
        # The second request for a branch misses the cache and logs this fact.
        rewriter = self.makeRewriter()
        branch = self.factory.makeAnyBranch()
        transaction.commit()
        rewriter.rewriteLine('/' + branch.unique_name + '/.bzr/README')
        self.fake_time.advance(
            config.codehosting.branch_rewrite_cache_lifetime + 1)
        rewriter.rewriteLine('/' + branch.unique_name + '/.bzr/README')
        logging_output_lines = self.getLoggerOutput(
            rewriter).strip().split('\n')
        self.assertEqual(2, len(logging_output_lines))
        self.assertIsNot(
            None,
            re.match("INFO .* -> .* (.*s, cache: MISS)",
                     logging_output_lines[-1]),
            "No miss found in %r" % logging_output_lines[-1])

    def test_getBranchIdAndTrailingPath_cached(self):
        """When results come from cache, they should be the same."""
        rewriter = self.makeRewriter()
        branch = self.factory.makeAnyBranch()
        transaction.commit()
        id_path = (branch.id, u'/.bzr/README',)
        result = rewriter._getBranchIdAndTrailingPath(
            '/' + branch.unique_name + '/.bzr/README')
        self.assertEqual(id_path + ('MISS',), result)
        result = rewriter._getBranchIdAndTrailingPath(
            '/' + branch.unique_name + '/.bzr/README')
        self.assertEqual(id_path + ('HIT',), result)

    def test_branch_id_alias_private(self):
        # Private branches are not found at all (this is for anonymous access)
        owner = self.factory.makePerson()
        branch = self.factory.makeAnyBranch(
            owner=owner, information_type=InformationType.USERDATA)
        with person_logged_in(owner):
            path = branch_id_alias(branch)
        result = self.makeRewriter()._getBranchIdAndTrailingPath(path)
        self.assertEqual((None, None, 'MISS'), result)

    def test_branch_id_alias_transitive_private(self):
        # Transitively private branches are not found at all
        # (this is for anonymous access)
        owner = self.factory.makePerson()
        private_branch = self.factory.makeAnyBranch(
            owner=owner, information_type=InformationType.USERDATA)
        branch = self.factory.makeAnyBranch(
            stacked_on=private_branch, owner=owner)
        with person_logged_in(owner):
            path = branch_id_alias(branch)
        result = self.makeRewriter()._getBranchIdAndTrailingPath(path)
        self.assertEqual((None, None, 'MISS'), result)


class TestBranchRewriterScript(TestCaseWithFactory):
    """Acceptance test for the branch-rewrite.py script."""

    layer = DatabaseFunctionalLayer

    def test_script(self):
        branches = [
            self.factory.makeProductBranch(),
            self.factory.makePersonalBranch(),
            self.factory.makePackageBranch()]
        input_lines = [
            "/%s/.bzr/README" % branch.unique_name for branch in branches] + [
            "/%s/changes" % branch.unique_name for branch in branches]
        expected_lines = [
            'file:///var/tmp/bazaar.launchpad.dev/mirrors/%s/.bzr/README'
            % branch_id_to_path(branch.id)
            for branch in branches] + [
            'http://localhost:8080/%s/changes' % branch.unique_name
            for branch in branches]
        transaction.commit()
        script_file = os.path.join(
            config.root, 'scripts', 'branch-rewrite.py')
        proc = subprocess.Popen(
            [script_file], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, bufsize=0)
        output_lines = []
        # For each complete line of input, the script should, without
        # buffering, write a complete line of output.
        for input_line in input_lines:
            proc.stdin.write(input_line + '\n')
            output_lines.append(
                nonblocking_readline(proc.stdout, 60).rstrip('\n'))
        # If we create a new branch after the branch-rewrite.py script has
        # connected to the database, or edit a branch name that has already
        # been rewritten, both are rewritten successfully.
        new_branch = self.factory.makeAnyBranch()
        edited_branch = removeSecurityProxy(branches[0])
        edited_branch.name = self.factory.getUniqueString()
        transaction.commit()

        new_branch_input = '/%s/.bzr/README' % new_branch.unique_name
        expected_lines.append(
            'file:///var/tmp/bazaar.launchpad.dev/mirrors/%s/.bzr/README'
            % branch_id_to_path(new_branch.id))
        proc.stdin.write(new_branch_input + '\n')
        output_lines.append(
            nonblocking_readline(proc.stdout, 60).rstrip('\n'))

        edited_branch_input = '/%s/.bzr/README' % edited_branch.unique_name
        expected_lines.append(
            'file:///var/tmp/bazaar.launchpad.dev/mirrors/%s/.bzr/README'
            % branch_id_to_path(edited_branch.id))
        proc.stdin.write(edited_branch_input + '\n')
        output_lines.append(
            nonblocking_readline(proc.stdout, 60).rstrip('\n'))

        os.kill(proc.pid, signal.SIGINT)
        err = proc.stderr.read()
        # The script produces logging output, but not to stderr.
        self.assertEqual('', err)
        self.assertEqual(expected_lines, output_lines)


class TestBranchRewriterScriptHandlesDisconnects(TestCase):
    """Ensure branch-rewrite.py survives fastdowntime deploys."""
    layer = DatabaseLayer

    def spawn(self):
        script_file = os.path.join(
            config.root, 'scripts', 'branch-rewrite.py')

        self.rewriter_proc = subprocess.Popen(
            [script_file], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, bufsize=0)

        self.addCleanup(self.rewriter_proc.terminate)

    def request(self, query):
        self.rewriter_proc.stdin.write(query + '\n')
        self.rewriter_proc.stdin.flush()

        # 60 second timeout as we might need to wait for the script to
        # finish starting up.
        result = nonblocking_readline(self.rewriter_proc.stdout, 60)

        if result.endswith('\n'):
            return result[:-1]
        self.fail(
            "Incomplete line or no result retrieved from subprocess: %s"
            % repr(result.getvalue()))

    def test_reconnects_when_disconnected(self):
        pgbouncer = self.useFixture(PGBouncerFixture())

        self.spawn()

        # Everything should be working, and we get valid output.
        out = self.request('foo')
        self.assertEndsWith(out, '/foo')

        pgbouncer.stop()

        # Now with pgbouncer down, we should get NULL messages and
        # stderr spam, and this keeps happening. We test more than
        # once to ensure that we will keep trying to reconnect even
        # after several failures.
        for count in range(5):
            out = self.request('foo')
            self.assertEqual(out, 'NULL')

        pgbouncer.start()

        # Everything should be working, and we get valid output.
        out = self.request('foo')
        self.assertEndsWith(out, '/foo')

    def test_starts_with_db_down(self):
        pgbouncer = self.useFixture(PGBouncerFixture())

        # Start with the database down.
        pgbouncer.stop()

        self.spawn()

        for count in range(5):
            out = self.request('foo')
            self.assertEqual(out, 'NULL')

        pgbouncer.start()

        out = self.request('foo')
        self.assertEndsWith(out, '/foo')
