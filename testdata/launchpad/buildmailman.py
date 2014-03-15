#! /usr/bin/python
#
# Copyright 2009, 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import errno
import grp
import os
import pwd
import socket
import subprocess
import sys
import tempfile

from lazr.config import as_username_groupname

from lp.services.config import config
from lp.services.mailman.config import (
    configure_prefix,
    configure_siteowner,
    )
from lp.services.mailman.monkeypatches import monkey_patch


basepath = [part for part in sys.path if part]


def build_mailman():
    # Build and install Mailman if it is enabled and not yet built.
    if not config.mailman.build:
        # There's nothing to do.
        return 0
    mailman_path = configure_prefix(config.mailman.build_prefix)
    mailman_bin = os.path.join(mailman_path, 'bin')
    var_dir = os.path.abspath(config.mailman.build_var_dir)

    # If we can import the package, we assume Mailman is properly built at
    # the least.  This does not catch re-installs that might be necessary
    # should our copy in sourcecode be updated.  Do that manually.
    sys.path.append(mailman_path)
    try:
        import Mailman
    except ImportError:
        # sys.path_importer_cache is a mapping of elements of sys.path to
        # importer objects used to handle them. In Python2.5+ when an element
        # of sys.path is found to not exist on disk, a NullImporter is created
        # and cached - this causes Python to never bother re-inspecting the
        # disk for that path element. We must clear that cache element so that
        # our second attempt to import MailMan after building it will actually
        # check the disk.
        del sys.path_importer_cache[mailman_path]
        need_build = need_install = True
    else:
        need_build = need_install = False
        # Also check for Launchpad-specific bits stuck into the source tree by
        # monkey_patch(), in case this is half-installed.  See
        # <https://bugs.launchpad.net/launchpad-registry/+bug/683486>.
        try:
            from Mailman.Queue import XMLRPCRunner
            from Mailman.Handlers import LPModerate
        except ImportError:
            # Monkey patches not present, redo install and patch steps.
            need_install = True

    # Make sure the target directories exist and have the correct
    # permissions, otherwise configure will complain.
    user, group = as_username_groupname(config.mailman.build_user_group)
    # Now work backwards to get the uid and gid
    try:
        uid = pwd.getpwnam(user).pw_uid
    except KeyError:
        print >> sys.stderr, 'No user found:', user
        sys.exit(1)
    try:
        gid = grp.getgrnam(group).gr_gid
    except KeyError:
        print >> sys.stderr, 'No group found:', group
        sys.exit(1)

    # Ensure that the var_dir exists, is owned by the user:group, and has
    # the necessary permissions.  Set the mode separately after the
    # makedirs() call because some platforms ignore mkdir()'s mode (though
    # I think Linux does not ignore it -- better safe than sorry).
    try:
        os.makedirs(var_dir)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    else:
        # Just created the var directory, will need to install mailmain bits.
        need_install = True
    os.chown(var_dir, uid, gid)
    os.chmod(var_dir, 02775)

    # Skip mailman setup if nothing so far has shown a reinstall needed.
    if not need_install:
        return 0

    mailman_source = os.path.join('sourcecode', 'mailman')
    if config.mailman.build_host_name:
        build_host_name = config.mailman.build_host_name
    else:
        build_host_name = socket.getfqdn()

    # Build and install the Mailman software.  Note that we don't care about
    # --with-cgi-gid because we're not going to use that Mailman subsystem.
    executable = os.path.abspath('bin/py')
    configure_args = (
        './configure',
        '--prefix', mailman_path,
        '--with-var-prefix=' + var_dir,
        '--with-python=' + executable,
        '--with-username=' + user,
        '--with-groupname=' + group,
        '--with-mail-gid=' + group,
        '--with-mailhost=' + build_host_name,
        '--with-urlhost=' + build_host_name,
        )
    if need_build:
        # Configure.
        retcode = subprocess.call(configure_args, cwd=mailman_source)
        if retcode:
            print >> sys.stderr, 'Could not configure Mailman:'
            sys.exit(retcode)
        # Make.
        retcode = subprocess.call(('make', ), cwd=mailman_source)
        if retcode:
            print >> sys.stderr, 'Could not make Mailman.'
            sys.exit(retcode)
    retcode = subprocess.call(('make', 'install'), cwd=mailman_source)
    if retcode:
        print >> sys.stderr, 'Could not install Mailman.'
        sys.exit(retcode)
    # Try again to import the package.
    try:
        import Mailman
    except ImportError:
        print >> sys.stderr, 'Could not import the Mailman package'
        return 1

    # Check to see if the site list exists.  The output can go to /dev/null
    # because we don't really care about it.  The site list exists if
    # config_list returns a zero exit status, otherwise it doesn't
    # (probably).  Before we can do this however, we must monkey patch
    # Mailman, otherwise mm_cfg.py won't be set up correctly.
    monkey_patch(mailman_path, config)

    import Mailman.mm_cfg
    retcode = subprocess.call(
        ('./config_list', '-o', '/dev/null',
         Mailman.mm_cfg.MAILMAN_SITE_LIST),
        cwd=mailman_bin,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if retcode:
        addr, password = configure_siteowner(
            config.mailman.build_site_list_owner)

        # The site list does not yet exist, so create it now.
        retcode = subprocess.call(
            ('./newlist', '--quiet',
             '--emailhost=' + build_host_name,
             Mailman.mm_cfg.MAILMAN_SITE_LIST,
             addr, password),
            cwd=mailman_bin)
        if retcode:
            print >> sys.stderr, 'Could not create site list'
            return retcode

    retcode = configure_site_list(
        mailman_bin, Mailman.mm_cfg.MAILMAN_SITE_LIST)
    if retcode:
        print >> sys.stderr, 'Could not configure site list'
        return retcode

    # Create a directory to hold the gzip'd tarballs for the directories of
    # deactivated lists.
    try:
        os.mkdir(os.path.join(Mailman.mm_cfg.VAR_PREFIX, 'backups'))
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

    return 0


def configure_site_list(mailman_bin, site_list_name):
    """Configure the site list.

    Currently, the only thing we want to set is to not advertise the
    site list.
    """
    fd, config_file_name = tempfile.mkstemp()
    try:
        os.close(fd)
        config_file = open(config_file_name, 'w')
        try:
            print >> config_file, 'advertised = False'
        finally:
            config_file.close()
        return subprocess.call(
            ('./config_list', '-i', config_file_name, site_list_name),
            cwd=mailman_bin)
    finally:
        os.remove(config_file_name)


def main():
    # setting python paths
    program = sys.argv[0]

    src = 'lib'
    here = os.path.dirname(os.path.abspath(program))
    srcdir = os.path.join(here, src)
    sys.path = [srcdir, here] + basepath
    return build_mailman()


if __name__ == '__main__':
    return_code = main()
    sys.exit(return_code)
