#!/bin/bash
#
# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
#
# Determine the changed files in Bazaar piplines, looms and plain branches.

bzr() {
    # PYTHONPATH may point to the ./lib directory in the launchpad tree. This
    # directory includes a bzrlib. When this script calls bzr, we want it to
    # use the system bzrlib, not the one in the launchpad tree.
    PYTHONPATH='' `which bzr` "$@"
}

bzr diff > /dev/null
diff_status=$?
if [ $diff_status -eq 0 ] ; then
    # No uncommitted changes in the tree.
    bzr status | grep "^Current thread:" > /dev/null
    if [ $? -eq 0 ] ; then
        # This is a loom, lint changes relative to the lower thread.
        rev_option="-r thread:"
    elif [ "$(bzr pipes | sed -n -e "/^\\*/q;p" | wc -l)" -gt 0 ]; then
        # This is a pipeline with at least one pipe before the
        # current, lint changes relative to the previous pipe
        rev_option="-r ancestor::prev"
    else
        # Lint changes relative to the parent.
        rev=`bzr info | sed \
            '/parent branch:/!d; s/ *parent branch: /ancestor:/'`
        rev_option="-r $rev"
    fi
elif [ $diff_status -eq 1 ] ; then
    # Uncommitted changes in the tree, return those files.
    rev_option=""
else
    # bzr diff failed
    exit 1
fi
# Extract filename from status line.  Skip symlinks.
files=`bzr st --short $rev_option |
    sed -e '/^.[MN]/!d; s/.* //' -e '/@$/d'`

echo $files

