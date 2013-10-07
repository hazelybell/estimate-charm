# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tools for maintaining the Launchpad source code."""

__metaclass__ = type
__all__ = [
    'interpret_config',
    'parse_config_file',
    'plan_update',
    ]

import errno
import json
import optparse
import os
import shutil
import sys

from bzrlib import ui
from bzrlib.branch import Branch
from bzrlib.errors import (
    BzrError,
    IncompatibleRepositories,
    NotBranchError,
    )
from bzrlib.plugin import load_plugins
from bzrlib.revisionspec import RevisionSpec
from bzrlib.trace import (
    enable_default_logging,
    report_exception,
    )
from bzrlib.upgrade import upgrade
from bzrlib.workingtree import WorkingTree

from devscripts import get_launchpad_root


def parse_config_file(file_handle):
    """Parse the source code config file 'file_handle'.

    :param file_handle: A file-like object containing sourcecode
        configuration.
    :return: A sequence of lines of either '[key, value]' or
        '[key, value, optional]'.
    """
    for line in file_handle:
        if line == '\n' or line.startswith('#'):
            continue
        yield line.split()


def interpret_config_entry(entry, use_http=False):
    """Interpret a single parsed line from the config file."""
    branch_name = entry[0]
    components = entry[1].split(';revno=')
    branch_url = components[0]
    if use_http:
        branch_url = branch_url.replace('lp:', 'http://bazaar.launchpad.net/')
    if len(components) == 1:
        revision = None
    else:
        assert len(components) == 2, 'Bad branch URL: ' + entry[1]
        revision = components[1] or None
    if len(entry) > 2:
        assert len(entry) == 3 and entry[2].lower() == 'optional', (
            'Bad configuration line: should be space delimited values of '
            'sourcecode directory name, branch URL [, "optional"]\n' +
            ' '.join(entry))
        optional = True
    else:
        optional = False
    return branch_name, branch_url, revision, optional


def load_cache(cache_filename):
    try:
        cache_file = open(cache_filename, 'rb')
    except IOError as e:
        if e.errno == errno.ENOENT:
            return {}
        else:
            raise
    with cache_file:
        return json.load(cache_file)


def interpret_config(config_entries, public_only, use_http=False):
    """Interpret a configuration stream, as parsed by 'parse_config_file'.

    :param configuration: A sequence of parsed configuration entries.
    :param public_only: If true, ignore private/optional branches.
    :param use_http: If True, force all branch URLs to use http://
    :return: A dict mapping the names of the sourcecode dependencies to a
        2-tuple of their branches and whether or not they are optional.
    """
    config = {}
    for entry in config_entries:
        branch_name, branch_url, revision, optional = interpret_config_entry(
            entry, use_http)
        if not optional or not public_only:
            config[branch_name] = (branch_url, revision, optional)
    return config


def _subset_dict(d, keys):
    """Return a dict that's a subset of 'd', based on the keys in 'keys'."""
    return dict((key, d[key]) for key in keys)


def plan_update(existing_branches, configuration):
    """Plan the update to existing branches based on 'configuration'.

    :param existing_branches: A sequence of branches that already exist.
    :param configuration: A dictionary of sourcecode configuration, such as is
        returned by `interpret_config`.
    :return: (new_branches, update_branches, removed_branches), where
        'new_branches' are the branches in the configuration that don't exist
        yet, 'update_branches' are the branches in the configuration that do
        exist, and 'removed_branches' are the branches that exist locally, but
        not in the configuration. 'new_branches' and 'update_branches' are
        dicts of the same form as 'configuration', 'removed_branches' is a
        set of the same form as 'existing_branches'.
    """
    existing_branches = set(existing_branches)
    config_branches = set(configuration.keys())
    new_branches = config_branches - existing_branches
    removed_branches = existing_branches - config_branches
    update_branches = config_branches.intersection(existing_branches)
    return (
        _subset_dict(configuration, new_branches),
        _subset_dict(configuration, update_branches),
        removed_branches)


def find_branches(directory):
    """List the directory names in 'directory' that are branches."""
    branches = []
    for name in os.listdir(directory):
        if name in ('.', '..'):
            continue
        try:
            Branch.open(os.path.join(directory, name))
            branches.append(name)
        except NotBranchError:
            pass
    return branches


def get_revision_id(revision, from_branch, tip=False):
    """Return revision id for a revision number and a branch.

    If the revision is empty, the revision_id will be None.

    If ``tip`` is True, the revision value will be ignored.
    """
    if not tip and revision:
        spec = RevisionSpec.from_string(revision)
        return spec.as_revision_id(from_branch)
    # else return None


def _format_revision_name(revision, tip=False):
    """Formatting helper to return human-readable identifier for revision.

    If ``tip`` is True, the revision value will be ignored.
    """
    if not tip and revision:
        return 'revision %s' % (revision,)
    else:
        return 'tip'


def get_branches(sourcecode_directory, new_branches,
                 possible_transports=None, tip=False, quiet=False):
    """Get the new branches into sourcecode."""
    for project, (branch_url, revision, optional) in new_branches.iteritems():
        destination = os.path.join(sourcecode_directory, project)
        try:
            remote_branch = Branch.open(
                branch_url, possible_transports=possible_transports)
        except BzrError:
            if optional:
                report_exception(sys.exc_info(), sys.stderr)
                continue
            else:
                raise
        possible_transports.append(
            remote_branch.bzrdir.root_transport)
        if not quiet:
            print 'Getting %s from %s at %s' % (
                    project, branch_url, _format_revision_name(revision, tip))
        # If the 'optional' flag is set, then it's a branch that shares
        # history with Launchpad, so we should share repositories. Otherwise,
        # we should avoid sharing repositories to avoid format
        # incompatibilities.
        force_new_repo = not optional
        revision_id = get_revision_id(revision, remote_branch, tip)
        remote_branch.bzrdir.sprout(
            destination, revision_id=revision_id, create_tree_if_local=True,
            source_branch=remote_branch, force_new_repo=force_new_repo,
            possible_transports=possible_transports)


def find_stale(updated, cache, sourcecode_directory, quiet):
    """Find branches whose revision info doesn't match the cache."""
    new_updated = dict(updated)
    for project, (branch_url, revision, optional) in updated.iteritems():
        cache_revision_info = cache.get(project)
        if cache_revision_info is None:
            continue
        if cache_revision_info[0] != int(revision):
            continue
        destination = os.path.join(sourcecode_directory, project)
        try:
            branch = Branch.open(destination)
        except BzrError:
            continue
        if list(branch.last_revision_info()) != cache_revision_info:
            continue
        if not quiet:
            print '%s is already up to date.' % project
        del new_updated[project]
    return new_updated


def update_cache(cache, cache_filename, changed, sourcecode_directory, quiet):
    """Update the cache with the changed branches."""
    old_cache = dict(cache)
    for project, (branch_url, revision, optional) in changed.iteritems():
        destination = os.path.join(sourcecode_directory, project)
        branch = Branch.open(destination)
        cache[project] = list(branch.last_revision_info())
    if cache == old_cache:
        return
    with open(cache_filename, 'wb') as cache_file:
        json.dump(cache, cache_file, indent=4, sort_keys=True)
    if not quiet:
        print 'Cache updated.  Please commit "%s".' % cache_filename


def update_branches(sourcecode_directory, update_branches,
                    possible_transports=None, tip=False, quiet=False):
    """Update the existing branches in sourcecode."""
    if possible_transports is None:
        possible_transports = []
    # XXX: JonathanLange 2009-11-09: Rather than updating one branch after
    # another, we could instead try to get them in parallel.
    for project, (branch_url, revision, optional) in (
        update_branches.iteritems()):
        # Update project from branch_url.
        destination = os.path.join(sourcecode_directory, project)
        if not quiet:
            print 'Updating %s to %s' % (
                    project, _format_revision_name(revision, tip))
        local_tree = WorkingTree.open(destination)
        try:
            remote_branch = Branch.open(
                branch_url, possible_transports=possible_transports)
        except BzrError:
            if optional:
                report_exception(sys.exc_info(), sys.stderr)
                continue
            else:
                raise
        possible_transports.append(
            remote_branch.bzrdir.root_transport)
        revision_id = get_revision_id(revision, remote_branch, tip)
        try:
            result = local_tree.pull(
                remote_branch, stop_revision=revision_id, overwrite=True,
                possible_transports=possible_transports)
        except IncompatibleRepositories:
            # XXX JRV 20100407: Ideally remote_branch.bzrdir._format
            # should be passed into upgrade() to ensure the format is the same
            # locally and remotely. Unfortunately smart server branches
            # have their _format set to RemoteFormat rather than an actual
            # format instance.
            upgrade(destination)
            # Upgraded, repoen working tree
            local_tree = WorkingTree.open(destination)
            result = local_tree.pull(
                remote_branch, stop_revision=revision_id, overwrite=True,
                possible_transports=possible_transports)
        if result.old_revid == result.new_revid:
            if not quiet:
                print '  (No change)'
        else:
            if result.old_revno < result.new_revno:
                change = 'Updated'
            else:
                change = 'Reverted'
            if not quiet:
                print '  (%s from %s to %s)' % (
                    change, result.old_revno, result.new_revno)


def remove_branches(sourcecode_directory, removed_branches, quiet=False):
    """Remove sourcecode that's no longer there."""
    for project in removed_branches:
        destination = os.path.join(sourcecode_directory, project)
        if not quiet:
            print 'Removing %s' % project
        try:
            shutil.rmtree(destination)
        except OSError:
            os.unlink(destination)


def update_sourcecode(sourcecode_directory, config_filename, cache_filename,
                      public_only, tip, dry_run, quiet=False, use_http=False):
    """Update the sourcecode."""
    config_file = open(config_filename)
    config = interpret_config(
        parse_config_file(config_file), public_only, use_http)
    config_file.close()
    cache = load_cache(cache_filename)
    branches = find_branches(sourcecode_directory)
    new, updated, removed = plan_update(branches, config)
    possible_transports = []
    if dry_run:
        print 'Branches to fetch:', new.keys()
        print 'Branches to update:', updated.keys()
        print 'Branches to remove:', list(removed)
    else:
        get_branches(
            sourcecode_directory, new, possible_transports, tip, quiet)
        updated = find_stale(updated, cache, sourcecode_directory, quiet)
        update_branches(
            sourcecode_directory, updated, possible_transports, tip, quiet)
        changed = dict(updated)
        changed.update(new)
        update_cache(
            cache, cache_filename, changed, sourcecode_directory, quiet)
        remove_branches(sourcecode_directory, removed, quiet)


# XXX: JonathanLange 2009-09-11: By default, the script will operate on the
# current checkout. Most people only have symlinks to sourcecode in their
# checkouts. This is fine for updating, but breaks for removing (you can't
# shutil.rmtree a symlink) and breaks for adding, since it adds the new branch
# to the checkout, rather than to the shared sourcecode area. Ideally, the
# script would see that the sourcecode directory is full of symlinks and then
# follow these symlinks to find the shared source directory. If the symlinks
# differ from each other (because of developers fiddling with things), we can
# take a survey of all of them, and choose the most popular.


def main(args):
    parser = optparse.OptionParser("usage: %prog [options] [root [conffile]]")
    parser.add_option(
        '--public-only', action='store_true',
        help='Only fetch/update the public sourcecode branches.')
    parser.add_option(
        '--tip', action='store_true',
        help='Ignore revision constraints for all branches and pull tip')
    parser.add_option(
        '--dry-run', action='store_true',
        help='Do nothing, but report what would have been done.')
    parser.add_option(
        '--quiet', action='store_true',
        help="Don't print informational messages.")
    parser.add_option(
        '--use-http', action='store_true',
        help="Force bzr to use http to get the sourcecode branches "
             "rather than using bzr+ssh.")
    options, args = parser.parse_args(args)
    root = get_launchpad_root()
    if len(args) > 1:
        sourcecode_directory = args[1]
    else:
        sourcecode_directory = os.path.join(root, 'sourcecode')
    if len(args) > 2:
        config_filename = args[2]
    else:
        config_filename = os.path.join(root, 'utilities', 'sourcedeps.conf')
    cache_filename = os.path.join(
        root, 'utilities', 'sourcedeps.cache')
    if len(args) > 3:
        parser.error("Too many arguments.")
    if not options.quiet:
        print 'Sourcecode: %s' % (sourcecode_directory,)
        print 'Config: %s' % (config_filename,)
    enable_default_logging()
    # Tell bzr to use the terminal (if any) to show progress bars
    ui.ui_factory = ui.make_ui_for_terminal(
        sys.stdin, sys.stdout, sys.stderr)
    load_plugins()
    update_sourcecode(
        sourcecode_directory, config_filename, cache_filename,
        options.public_only, options.tip, options.dry_run, options.quiet,
        options.use_http)
    return 0
