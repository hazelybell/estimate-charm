# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'Hooks',
    'PoppyInterfaceFailure',
    ]


import logging
import os
import shutil
import stat
import time

from contrib.glock import GlobalLock


class PoppyInterfaceFailure(Exception):
    pass


class Hooks:

    clients = {}
    LOG_MAGIC = "Post-processing finished"
    _targetcount = 0

    def __init__(self, targetpath, logger, allow_user, cmd=None,
                 targetstart=0, perms=None, prefix=''):
        self.targetpath = targetpath
        self.logger = logging.getLogger("%s.Hooks" % logger.name)
        self.cmd = cmd
        self.allow_user = allow_user
        self.perms = perms
        self.prefix = prefix

    @property
    def targetcount(self):
        """A guaranteed unique integer for ensuring unique upload dirs."""
        Hooks._targetcount += 1
        return Hooks._targetcount

    def new_client_hook(self, fsroot, host, port):
        """Prepare a new client record indexed by fsroot..."""
        self.clients[fsroot] = {
            "host": host,
            "port": port
            }
        self.logger.debug("Accepting new session in fsroot: %s" % fsroot)
        self.logger.debug("Session from %s:%s" % (host, port))

    def client_done_hook(self, fsroot, host, port):
        """A client has completed. If it authenticated then it stands a chance
        of having uploaded a file to the set. If not; then it is simply an
        aborted transaction and we remove the fsroot."""

        if fsroot not in self.clients:
            raise PoppyInterfaceFailure("Unable to find fsroot in client set")

        self.logger.debug("Processing session complete in %s" % fsroot)

        client = self.clients[fsroot]
        if "distro" not in client:
            # Login username defines the distribution context of the upload.
            # So abort unauthenticated sessions by removing its contents
            shutil.rmtree(fsroot)
            return

        # Protect from race condition between creating the directory
        # and creating the distro file, and also in cases where the
        # temporary directory and the upload directory are not in the
        # same filesystem (non-atomic "rename").
        lockfile_path = os.path.join(self.targetpath, ".lock")
        self.lock = GlobalLock(lockfile_path)

        # XXX cprov 20071024 bug=156795: We try to acquire the lock as soon
        # as possible after creating the lockfile but are still open to
        # a race.
        self.lock.acquire(blocking=True)
        mode = stat.S_IMODE(os.stat(lockfile_path).st_mode)

        # XXX cprov 20081024 bug=185731: The lockfile permission can only be
        # changed by its owner. Since we can't predict which process will
        # create it in production systems we simply ignore errors when trying
        # to grant the right permission. At least, one of the process will
        # be able to do so.
        try:
            os.chmod(lockfile_path, mode | stat.S_IWGRP)
        except OSError:
            pass

        try:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            path = "upload%s-%s-%06d" % (
                self.prefix, timestamp, self.targetcount)
            target_fsroot = os.path.join(self.targetpath, path)

            # Create file to store the distro used.
            self.logger.debug("Upload was targetted at %s" % client["distro"])
            distro_filename = target_fsroot + ".distro"
            distro_file = open(distro_filename, "w")
            distro_file.write(client["distro"])
            distro_file.close()

            # Move the session directory to the target directory.
            if os.path.exists(target_fsroot):
                self.logger.warn("Targeted upload already present: %s" % path)
                self.logger.warn("System clock skewed ?")
            else:
                try:
                    shutil.move(fsroot, target_fsroot)
                except (OSError, IOError):
                    if not os.path.exists(target_fsroot):
                        raise

            # XXX cprov 20071024: We should replace os.system call by os.chmod
            # and fix the default permission value accordingly in poppy-upload
            if self.perms is not None:
                os.system("chmod %s -R %s" % (self.perms, target_fsroot))

            # Invoke processing script, if provided.
            if self.cmd:
                cmd = self.cmd
                cmd = cmd.replace("@fsroot@", target_fsroot)
                cmd = cmd.replace("@distro@", client["distro"])
                self.logger.debug("Running upload handler: %s" % cmd)
                os.system(cmd)
        finally:
            # We never delete the lockfile, this way the inode will be
            # constant while the machine is up. See comment on 'acquire'
            self.lock.release(skip_delete=True)

        self.clients.pop(fsroot)
        # This is mainly done so that tests know when the
        # post-processing hook has finished.
        self.logger.info(self.LOG_MAGIC)

    def auth_verify_hook(self, fsroot, user, password):
        """Verify that the username matches a distribution we care about.

        The password is irrelevant to auth, as is the fsroot"""
        if fsroot not in self.clients:
            raise PoppyInterfaceFailure("Unable to find fsroot in client set")

        # local authentication
        self.clients[fsroot]["distro"] = self.allow_user
        return True

        # When we get on with the poppy path stuff, the below may be useful
        # and is thus left in rather than being removed.

        #try:
        #    d = Distribution.byName(user)
        #    if d:
        #        self.logger.debug("Accepting login for %s" % user)
        #        self.clients[fsroot]["distro"] = user
        #        return True
        #except object as e:
        #    print e
        #return False

