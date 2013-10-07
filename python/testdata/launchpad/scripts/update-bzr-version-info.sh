#!/bin/bash
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
#
# Update bzr-version-info.py -- but only if the revision number has
# changed
#

if ! which bzr > /dev/null || !  test -x $(which bzr); then
    echo "No working 'bzr' executable found"
    exit 1
fi

newfile=bzr-version-info-${RANDOM}.py
bzr version-info --format=python > $newfile 2>/dev/null;
# There's a leading space here that I don't care to trim.. 
revno=$(python $newfile | grep revision: | cut -d: -f2)
if ! [ -f bzr-version-info.py ]; then
    echo "Creating bzr-version-info.py at revno$revno"
    mv ${newfile} bzr-version-info.py
else
    # Here we compare the actual output instead of the contents of the
    # file because bzr includes a build-date that is actually updated
    # every time you run bzr version-info.
    newcontents=$(python $newfile)
    oldcontents=$(python bzr-version-info.py)
    if [ "$newcontents" != "$oldcontents" ]; then
        echo "Updating bzr-version-info.py to revno$revno"
        mv ${newfile} bzr-version-info.py
    else
        echo "Skipping bzr-version-info.py update; already at revno$revno"
        rm ${newfile}
    fi
fi
