#!/usr/bin/python
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Move a python module in the tree.

It uses bzr mv to rename the module and will try to find all imports.

rename-module.py src_file+ target

Both files must be under lib/.

If more than one src files is given, target must be a directory.
"""

__metaclass__ = type
__all__ = []

import os
import subprocess
import sys


def fail(message):
    os.sys.stderr.write(message + "\n")
    sys.exit(1)


def log(message):
    os.sys.stdout.write(message + "\n")


def file2module(module_file):
    """From a filename, return the python module name."""
    start_path = 'lib' + os.path.sep
    assert module_file.startswith(start_path), "File should start with lib"
    if module_file.endswith('.py'):
        module_file = module_file[:-3]
    return module_file[len(start_path):].replace(os.path.sep, '.')


def rename_module(src_file, target_file):
    # Move the file using bzr.
    p = subprocess.Popen(['bzr', 'mv', src_file, target_file])
    if (p.wait() != 0):
        fail("bzr mv failed: %d" % p.returncode)
    if os.path.exists(src_file + 'c'):
        os.remove(src_file + 'c')
    log("Renamed %s -> %s" % (src_file, target_file))

    # Find the files to update.
    src_module = file2module(src_file)
    p = subprocess.Popen([
        'egrep', '-rl', '--exclude', '*.pyc', '%s' % src_module, 'lib'],
        stdout=subprocess.PIPE)
    files = [f.strip() for f in p.stdout.readlines()]
    p.wait()
    # grep fails if it didn't find anything to update. So ignore return code.

    target_module = file2module(target_file)
    log("Found %d files with imports to update." % len(files))
    src_module_re = src_module.replace('.', '\\.')
    target_module_re = target_module.replace('.', '\\.')
    for f in files:
        # YES! Perl
        cmdline = [
            'perl', '-i', '-pe',
            's/%s\\b/%s/g;' % (src_module_re, target_module_re),
            f]
        p = subprocess.Popen(cmdline)
        rv = p.wait()
        if rv != 0:
            log('Failed to update %s' % f)
        else:
            log('Updated %s' % f)


def main():
    if len(sys.argv) < 3:
        fail('Usage: %s src_file+ target' % os.path.basename(sys.argv[0]))
    src_files = sys.argv[1:-1]
    target = sys.argv[-1]

    if os.path.exists(target) and not os.path.isdir(target):
        fail('Destination file "%s" already exists.' % target)
    if not target.startswith('lib'):
        fail('Destination file "%s" must be under lib.' % target)
    if len(src_files) > 1 and not os.path.isdir(target):
        fail('Destination must be a directory.')

    for src_file in src_files:
        if not os.path.exists(src_file):
            log('Source file "%s" doesn\'t exists. Skipping' % src_file)
            continue
        if not src_file.startswith('lib'):
            log('Source file "%s" must be under lib. Skipping' % src_file)
            continue
        if not (src_file.endswith('.py') or os.path.isdir(src_file)):
            log('Source file "%s" should end with .py or be a directory. '
                'Skipping' % src_file)
            continue

        if os.path.isdir(target):
            target_file = os.path.join(target, os.path.basename(src_file))
        else:
            target_file = target

        rename_module(src_file, target_file)

if __name__ == '__main__':
    main()
