#!/bin/sh
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# This script performs nightly chores. It should be run from
# cron as the launchpad user once a day. Typically the output
# will be sent to an email address for inspection.

# Note that http/ftp proxies are needed by the product
# release finder


LOGDIR=$1
LOGFILE=$LOGDIR/nightly.log

LOCK=/var/lock/launchpad_nightly.lock
lockfile -r0 -l 259200 $LOCK
if [ $? -ne 0 ]; then
    echo $(date): Unable to grab $LOCK lock - aborting | tee -a $LOGFILE
    ps fuxwww
    exit 1
fi

cd `dirname $0`

echo $(date): Grabbed lock >> $LOGFILE

echo $(date): Expiring memberships >> $LOGFILE
python -S flag-expired-memberships.py -q --log-file=DEBUG:$LOGDIR/flag-expired-memberships.log

echo $(date): Allocating revision karma >> $LOGFILE
python -S allocate-revision-karma.py -q --log-file=DEBUG:$LOGDIR/allocate-revision-karma.log

echo $(date): Recalculating karma >> $LOGFILE
python -S foaf-update-karma-cache.py -q --log-file=INFO:$LOGDIR/foaf-update-karma-cache.log

echo $(date): Updating cached statistics >> $LOGFILE
python -S update-stats.py -q --log-file=DEBUG:$LOGDIR/update-stats.log

echo $(date): Expiring questions >> $LOGFILE
python -S expire-questions.py -q --log-file=DEBUG:$LOGDIR/expire-questions.log

echo $(date): Updating bugtask target name caches >> $LOGFILE
python -S update-bugtask-targetnamecaches.py -q --log-file=DEBUG:$LOGDIR/update-bugtask-targetnamecaches.log

echo $(date): Updating personal standings >> $LOGFILE
python -S update-standing.py -q --log-file=DEBUG:$LOGDIR/update-standing.log

echo $(date): Updating CVE database >> $LOGFILE
python -S update-cve.py -q --log-file=DEBUG:$LOGDIR/update-cve.log

echo $(date): Removing lock >> $LOGFILE
rm -f $LOCK
