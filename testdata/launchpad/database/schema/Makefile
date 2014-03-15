# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
#
# Quick hack makefile to (re)create the Launchpad database.
# One day the guts of this will be migrated to Python
#

PYTHON=../../bin/py

# The database dump to restore on database creation
SAMPLEDATA=../sampledata/current.sql
SAMPLEDATA_DEV=../sampledata/current-dev.sql

# The database dump to create for lint reports
LINTDATA=../sampledata/lintdata.sql
LINTDATA_DEV=../sampledata/lintdata-dev.sql

# The development database
DBNAME_DEV=launchpad_dev
TEMPLATE_WITH_DEV_SAMPLEDATA=launchpad_dev_template

# A template for databases used by functional tests.
# It is not used directly, but used as a template in a createdb command
# to quickly build a populated database to run tests against.
TEMPLATE_WITH_TEST_SAMPLEDATA=launchpad_ftest_template
EMPTY_DBNAME=launchpad_empty
TEST_SESSION_DBNAME=session_ftest

# The database which is a copy of launchpad_ftest_template and can be accessed
# via http://launchpad.dev when you use LPCONFIG=test-playground.
TEST_PLAYGROUND_DBNAME=launchpad_ftest_playground

# The session database name.
SESSION_DBNAME=session_dev

# The command we use to drop a database.
DROPDB=${PYTHON} ../../utilities/pgmassacre.py
# The command we use to drop (if exists) and recreate a database.
CREATEDB=${PYTHON} ../../utilities/pgmassacre.py -t

YEAR=$(shell date +'%Y')
HEADER="-- Copyright 2010-${YEAR} Canonical Ltd.  This software is licensed \
  under the\n-- GNU Affero General Public License version 3 (see the file \
	LICENSE)."

# The command used (in conjunction with $(call)) to dump the contents of the
# given database ($1) into an SQL file ($2).
build_new_sampledata=$(PYTHON) fti.py --null -d ${1} -q && \
	echo $(HEADER) > $(2) && \
    echo -n "-- Created using " >> $(2) && \
    pg_dump --version >> $(2) && \
    pg_dump --schema=public --disable-triggers -a --column-inserts -O ${1} \
    | grep -v "\( TOC \|INSERT INTO launchpaddatabase\|sessiondata\|sessionpkgdata\|SELECT pg_catalog\.setval\|^--\| fticache \|'fticache'\|ALTER TABLE secret\|INSERT INTO secret\)" \
    | $(PYTHON) sort_sql.py >> $(2) && \
    $(PYTHON) fti.py --live-rebuild -d ${1} -q


# The latest schema dump from production. Database patches are relative
# to this baseline. This dump should be updated occasionally from production
# to ensure that the development database remains in sync with reality
# on production. It is generated using newbaseline.py in
# bzr+ssh://devpad.canonical.com/code/stub/dbascripts
#
REV=2209
BASELINE=launchpad-${REV}-00-0.sql
MD5SUM=cc7a493c924196409a22392a16443d52  launchpad-2209-00-0.sql

default: all

# Create a launchpad_ftest_template DB and load the test sample data into it.
test: create
	@ echo "* Creating database \"$(TEMPLATE_WITH_TEST_SAMPLEDATA)\"."
	@ ${CREATEDB} ${EMPTY_DBNAME} ${TEMPLATE_WITH_TEST_SAMPLEDATA}
	@ echo "* Loading sample data"
	@ psql -v ON_ERROR_STOP=1 -d ${TEMPLATE_WITH_TEST_SAMPLEDATA} -f $(SAMPLEDATA) > /dev/null
	@ echo "* Rebuilding full text indexes"
	@ ${PYTHON} fti.py --live-rebuild -q -d ${TEMPLATE_WITH_TEST_SAMPLEDATA}
	@ echo "* Resetting sequences"
	@ ${PYTHON} reset_sequences.py -d ${TEMPLATE_WITH_TEST_SAMPLEDATA}
	@ echo "* Disabling autovacuum"
	@ ${PYTHON} unautovacuumable.py -d ${TEMPLATE_WITH_TEST_SAMPLEDATA}
	@ echo "* Vacuuming"
	@ vacuumdb -fz ${TEMPLATE_WITH_TEST_SAMPLEDATA}

# Create a launchpad_dev_template DB and load the dev sample data into it.
# Also create a launchpad_ftest_playground DB as a copy of
# launchpad_ftest_template.
dev: test
	@ echo "* Creating ${TEMPLATE_WITH_DEV_SAMPLEDATA}"
	@ ${CREATEDB} ${EMPTY_DBNAME} ${TEMPLATE_WITH_DEV_SAMPLEDATA}
	@ echo "* Loading sample data"
	@ psql -v ON_ERROR_STOP=1 -d ${TEMPLATE_WITH_DEV_SAMPLEDATA} -f $(SAMPLEDATA_DEV) > /dev/null
	@ echo "* Rebuilding full text indexes"
	@ ${PYTHON} fti.py --live-rebuild -q -d ${TEMPLATE_WITH_DEV_SAMPLEDATA}
	@ echo "* Resetting sequences"
	@ ${PYTHON} reset_sequences.py -d ${TEMPLATE_WITH_DEV_SAMPLEDATA}
	@ echo "* Disabling autovacuum"
	@ ${PYTHON} unautovacuumable.py -d ${TEMPLATE_WITH_DEV_SAMPLEDATA}
	@ echo "* Vacuuming"
	@ vacuumdb -fz ${TEMPLATE_WITH_DEV_SAMPLEDATA}
	@ echo "* Creating ${DBNAME_DEV}"
	@ ${CREATEDB} ${TEMPLATE_WITH_DEV_SAMPLEDATA} ${DBNAME_DEV}
	@ echo "* Creating ${TEST_PLAYGROUND_DBNAME}"
	@ ${CREATEDB} ${TEMPLATE_WITH_TEST_SAMPLEDATA} ${TEST_PLAYGROUND_DBNAME}

# This will create a DB named launchpad_empty and load the base
# database schema, full text indexes and grants into it.
# It will also create session DBs for the test and dev environments.
# No sample data is added at this point.
create:
	@ echo "* If this fails you need to run as the postgresql superuser"
	@ echo "* eg. sudo -u postgres make create"
	@ echo
	@ echo "* Creating database \"$(EMPTY_DBNAME)\"."
	@ ${CREATEDB} template0 ${EMPTY_DBNAME}
	@ echo "* Loading base database schema"
	@ psql -d ${EMPTY_DBNAME} -f ${BASELINE} | grep : | cat
	@ echo "* Patching the database schema"
	@ ${PYTHON} upgrade.py -d ${EMPTY_DBNAME}
	@ echo "* Security setup"
	@ ${PYTHON} security.py -q -d ${EMPTY_DBNAME}
	@ echo "* Disabling autovacuum"
	@ ${PYTHON} unautovacuumable.py -d ${EMPTY_DBNAME}
	@ echo "* Vacuuming"
	@ vacuumdb -fz ${EMPTY_DBNAME}

	@ echo "* Creating session database '${SESSION_DBNAME}' (if necessary)"
	@if [ "$$((`psql -l | grep -w ${SESSION_DBNAME} | wc -l`))" = '0' ]; \
	    then ${CREATEDB} template0 ${SESSION_DBNAME} ; \
	    psql -q -d ${SESSION_DBNAME} -f launchpad_session.sql ; \
	fi
	@ echo "* Creating session database '${TEST_SESSION_DBNAME}'"
	@ ${CREATEDB} template0 ${TEST_SESSION_DBNAME}
	@ psql -q -d ${TEST_SESSION_DBNAME} -f launchpad_session.sql

# Confirm that launchpad-XX-00-0.sql hasn't been messed with - this file
# is our baseline telling us what was installed into production
check: search_path
	@if [ "`md5sum ${BASELINE}`" != "${MD5SUM}" ]; then echo "* ${BASELINE} is corrupt or has been modified"; exit 1; else echo "* Using ${BASELINE} as baseline"; fi

search_path:
	@psql -d template1 -q -A -t -c 'show search_path'
	@if [ `psql -d template1 -q -A -t -c 'show search_path'` != '$$user,public,ts2' ] && [ `psql -d template1 -q -A -t -c 'show search_path'` != '"$$user",public,ts2' ]; then \
		echo "* It appears your search path is unconfigured."; \
		echo "	Have you read <https://launchpad.canonical.com/DatabaseSetup>?";  \
		echo; \
		echo "* Add the following to /etc/postgresql/X.X/main/postgresql.conf"; \
		echo " (where X.X is the version of the PostgreSQL DB you're connecting to):"; \
		echo "    search_path='\$$user,public,ts2'"; \
		echo "* Then reload PostgreSQL:";  \
		echo "    sudo /etc/init.d/postgresql reload";  \
		exit 1; \
	 fi


all: dev test
	@ echo "* All done"

doc:
	postgresql_autodoc -d ${DBNAME_DEV} -f launchpad -t html
	tidy -asxhtml launchpad.html > ,launchpad.html || mv ,launchpad.html launchpad.html

newsampledata_test:
	$(call build_new_sampledata,${TEST_PLAYGROUND_DBNAME},${SAMPLEDATA})

newsampledata_dev:
	$(call build_new_sampledata,${DBNAME_DEV},${SAMPLEDATA_DEV})

newsampledata: newsampledata_dev newsampledata_test

lintdata:
	$(call build_new_sampledata,${TEMPLATE_WITH_TEST_SAMPLEDATA},${LINTDATA})
	$(call build_new_sampledata,${TEMPLATE_WITH_DEV_SAMPLEDATA},${LINTDATA_DEV})

.PHONY: default test dev create check search_path all doc diagram newsampledata_test newsampledata_dev newsampledata lintdata

