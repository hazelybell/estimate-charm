# This file modified from Zope3/Makefile
# Licensed under the ZPL, (c) Zope Corporation and contributors.

PYTHON:=$(shell sed -e \
    '/RELEASE/!d; s/.*=1[23].*/python2.7/; s/.*=.*/python2.6/' /etc/lsb-release)

WD:=$(shell pwd)
PY=$(WD)/bin/py
PYTHONPATH:=$(WD)/lib:$(WD)/lib/mailman:${PYTHONPATH}
BUILDOUT_CFG=buildout.cfg
VERBOSITY=-vv

TESTFLAGS=-p $(VERBOSITY)
TESTOPTS=

SHHH=utilities/shhh.py

LPCONFIG?=development

LISTEN_ADDRESS?=127.0.0.88

ICING=lib/canonical/launchpad/icing
LP_BUILT_JS_ROOT=${ICING}/build

JS_BUILD_DIR := build/js
YUI_VERSIONS := 3.10.3
YUI_BUILDS := $(patsubst %,$(JS_BUILD_DIR)/yui-%, $(YUI_VERSIONS))
YUI_DEFAULT := yui-3.10.3
YUI_DEFAULT_SYMLINK := $(JS_BUILD_DIR)/yui
LP_JS_BUILD := $(JS_BUILD_DIR)/lp

MINS_TO_SHUTDOWN=15

CODEHOSTING_ROOT=/var/tmp/bazaar.launchpad.dev

CONVOY_ROOT?=/srv/launchpad.dev/convoy

BZR_VERSION_INFO = bzr-version-info.py

APIDOC_DIR = lib/canonical/launchpad/apidoc
APIDOC_TMPDIR = $(APIDOC_DIR).tmp/
API_INDEX = $(APIDOC_DIR)/index.html

# Do not add bin/buildout to this list.
# It is impossible to get buildout to tell us all the files it would
# build, since each egg's setup.py doesn't tell us that information.
#
# NB: It's important BUILDOUT_BIN only mentions things genuinely produced by
# buildout.
BUILDOUT_BIN = \
    $(PY) bin/apiindex bin/combine-css bin/fl-build-report \
    bin/fl-credential-ctl bin/fl-install-demo bin/fl-monitor-ctl \
    bin/fl-record bin/fl-run-bench bin/fl-run-test bin/googletestservice \
    bin/i18ncompile bin/i18nextract bin/i18nmergeall bin/i18nstats \
    bin/harness bin/iharness bin/ipy bin/jsbuild bin/lpjsmin\
    bin/killservice bin/kill-test-services bin/lint.sh bin/retest \
    bin/run bin/run-testapp bin/sprite-util bin/start_librarian bin/stxdocs \
    bin/tags bin/test bin/tracereport bin/twistd bin/update-download-cache \
    bin/watch_jsbuild

BUILDOUT_TEMPLATES = buildout-templates/_pythonpath.py.in

# DO NOT ALTER : this should just build by default
default: inplace

schema: build
	$(MAKE) -C database/schema
	$(RM) -r /var/tmp/fatsam

newsampledata:
	$(MAKE) -C database/schema newsampledata

hosted_branches: $(PY)
	$(PY) ./utilities/make-dummy-hosted-branches

$(API_INDEX): $(BZR_VERSION_INFO) $(PY)
	$(RM) -r $(APIDOC_DIR) $(APIDOC_DIR).tmp
	mkdir -p $(APIDOC_DIR).tmp
	LPCONFIG=$(LPCONFIG) $(PY) ./utilities/create-lp-wadl-and-apidoc.py \
	    --force "$(APIDOC_TMPDIR)"
	mv $(APIDOC_TMPDIR) $(APIDOC_DIR)

apidoc:
ifdef LP_MAKE_NO_WADL
	@echo "Skipping WADL generation."
else
	$(MAKE) compile $(API_INDEX)
endif

# Used to generate HTML developer documentation for Launchpad.
doc:
	$(MAKE) -C doc/ html

# Run by PQM.
check_config: build
	bin/test -m lp.services.config.tests -vvt test_config

# Clean before running the test suite, since the build might fail depending
# what source changes happened. (e.g. apidoc depends on interfaces)
check: clean build
	# Run all tests. test_on_merge.py takes care of setting up the
	# database.
	${PY} -t ./test_on_merge.py $(VERBOSITY) $(TESTOPTS)
	bzr status --no-pending

check_mailman: build
	# Run all tests, including the Mailman integration
	# tests. test_on_merge.py takes care of setting up the database.
	${PY} -t ./test_on_merge.py $(VERBOSITY) $(TESTOPTS) \
		lp.services.mailman.tests

lint: ${PY}
	@bash ./bin/lint.sh

lint-verbose: ${PY}
	@bash ./bin/lint.sh -v

logs:
	mkdir logs

codehosting-dir:
	mkdir -p $(CODEHOSTING_ROOT)/mirrors
	mkdir -p $(CODEHOSTING_ROOT)/config
	mkdir -p /var/tmp/bzrsync
	touch $(CODEHOSTING_ROOT)/rewrite.log
	chmod 777 $(CODEHOSTING_ROOT)/rewrite.log
	touch $(CODEHOSTING_ROOT)/config/launchpad-lookup.txt

inplace: build logs clean_logs codehosting-dir
	if [ -d /srv/launchpad.dev ]; then \
		ln -sfn $(WD)/build/js $(CONVOY_ROOT); \
	fi

build: compile apidoc jsbuild css_combine

# LP_SOURCEDEPS_PATH should point to the sourcecode directory, but we
# want the parent directory where the download-cache and eggs directory
# are. We re-use the variable that is using for the rocketfuel-get script.
download-cache:
ifdef LP_SOURCEDEPS_PATH
	utilities/link-external-sourcecode $(LP_SOURCEDEPS_PATH)/..
else
	@echo "Missing ./download-cache."
	@echo "Developers: please run utilities/link-external-sourcecode."
	@exit 1
endif

css_combine: jsbuild_widget_css
	${SHHH} bin/sprite-util create-image
	${SHHH} bin/sprite-util create-css
	ln -sfn ../../../../build/js/$(YUI_DEFAULT) $(ICING)/yui
	${SHHH} bin/combine-css

jsbuild_widget_css: bin/jsbuild
	${SHHH} bin/jsbuild \
	    --srcdir lib/lp/app/javascript \
	    --builddir $(LP_BUILT_JS_ROOT)

jsbuild_watch:
	$(PY) bin/watch_jsbuild

$(JS_BUILD_DIR):
	mkdir -p $@

$(YUI_BUILDS): | $(JS_BUILD_DIR)
	mkdir -p $@/tmp
	unzip -q download-cache/dist/yui_$(subst build/js/yui-,,$@).zip -d $@/tmp 'yui/build/*'
	# We don't use the Flash components and they have a bad security
	# record. Kill them.
	find $@/tmp/yui/build -name '*.swf' -delete
	mv $@/tmp/yui/build/* $@
	$(RM) -r $@/tmp

$(YUI_DEFAULT_SYMLINK): $(YUI_BUILDS)
	ln -sfn $(YUI_DEFAULT) $@

$(LP_JS_BUILD): | $(JS_BUILD_DIR)
	-mkdir $@
	for jsdir in lib/lp/*/javascript; do \
		app=$$(echo $$jsdir | sed -e 's,lib/lp/\(.*\)/javascript,\1,'); \
		cp -a $$jsdir $@/$$app; \
	done
	find $@ -name 'tests' -type d | xargs rm -rf
	bin/lpjsmin -p $@

jsbuild: $(LP_JS_BUILD) $(YUI_DEFAULT_SYMLINK)
	utilities/js-deps -n LP_MODULES -s build/js/lp -x '-min.js' -o \
	build/js/lp/meta.js >/dev/null
	utilities/check-js-deps

eggs:
	# Usually this is linked via link-external-sourcecode, but in
	# deployment we create this ourselves.
	mkdir eggs

buildonce_eggs: $(PY)
	find eggs -name '*.pyc' -exec rm {} \;

# The download-cache dependency comes *before* eggs so that developers get the
# warning before the eggs directory is made.  The target for the eggs
# directory is only there for deployment convenience.
# Note that the buildout version must be maintained here and in versions.cfg
# to make sure that the build does not go over the network.
#
# buildout won't touch files that would have the same contents, but for Make's
# sake we need them to get fresh timestamps, so we touch them after building.
bin/buildout: download-cache eggs
	$(SHHH) PYTHONPATH= $(PYTHON) bootstrap.py\
		--setup-source=ez_setup.py \
		--download-base=download-cache/dist --eggs=eggs \
		--version=1.7.1
	touch --no-create $@

# This target is used by LOSAs to prepare a build to be pushed out to
# destination machines.  We only want eggs: they are the expensive bits,
# and the other bits might run into problems like bug 575037.  This
# target runs buildout, and then removes everything created except for
# the eggs.
build_eggs: $(BUILDOUT_BIN) clean_buildout

# This builds bin/py and all the other bin files except bin/buildout.
# Remove the target before calling buildout to ensure that buildout
# updates the timestamp.
buildout_bin: $(BUILDOUT_BIN)

# buildout won't touch files that would have the same contents, but for Make's
# sake we need them to get fresh timestamps, so we touch them after building.
#
# If we listed every target on the left-hand side, a parallel make would try
# multiple copies of this rule to build them all.  Instead, we nominally build
# just $(PY), and everything else is implicitly updated by that.
$(PY): bin/buildout versions.cfg $(BUILDOUT_CFG) setup.py \
		$(BUILDOUT_TEMPLATES)
	$(SHHH) PYTHONPATH= ./bin/buildout \
                configuration:instance_name=${LPCONFIG} -c $(BUILDOUT_CFG)
	touch $@

$(subst $(PY),,$(BUILDOUT_BIN)): $(PY)

compile: $(PY) $(BZR_VERSION_INFO)
	${SHHH} $(MAKE) -C sourcecode build PYTHON=${PYTHON} \
	    LPCONFIG=${LPCONFIG}
	${SHHH} LPCONFIG=${LPCONFIG} ${PY} -t buildmailman.py

test_build: build
	bin/test $(TESTFLAGS) $(TESTOPTS)

test_inplace: inplace
	bin/test $(TESTFLAGS) $(TESTOPTS)

ftest_build: build
	bin/test -f $(TESTFLAGS) $(TESTOPTS)

ftest_inplace: inplace
	bin/test -f $(TESTFLAGS) $(TESTOPTS)

run: build inplace stop
	bin/run -r librarian,google-webservice,memcached,rabbitmq,txlongpoll \
	-i $(LPCONFIG)

run-testapp: LPCONFIG=testrunner-appserver
run-testapp: build inplace stop
	LPCONFIG=$(LPCONFIG) INTERACTIVE_TESTS=1 bin/run-testapp \
	-r memcached -i $(LPCONFIG)

run.gdb:
	echo 'run' > run.gdb

start-gdb: build inplace stop support_files run.gdb
	nohup gdb -x run.gdb --args bin/run -i $(LPCONFIG) \
		-r librarian,google-webservice
		> ${LPCONFIG}-nohup.out 2>&1 &

run_all: build inplace stop
	bin/run \
	 -r librarian,sftp,forker,mailman,codebrowse,google-webservice,\
	memcached,rabbitmq,txlongpoll -i $(LPCONFIG)

run_codebrowse: compile
	BZR_PLUGIN_PATH=bzrplugins $(PY) scripts/start-loggerhead.py -f

start_codebrowse: compile
	BZR_PLUGIN_PATH=$(shell pwd)/bzrplugins $(PY) scripts/start-loggerhead.py

stop_codebrowse:
	$(PY) scripts/stop-loggerhead.py

run_codehosting: build inplace stop
	bin/run -r librarian,sftp,forker,codebrowse,rabbitmq -i $(LPCONFIG)

start_librarian: compile
	bin/start_librarian

stop_librarian:
	bin/killservice librarian

$(BZR_VERSION_INFO):
	scripts/update-bzr-version-info.sh

support_files: $(API_INDEX) $(BZR_VERSION_INFO)

# Intended for use on developer machines
start: inplace stop support_files initscript-start

# Run as a daemon - hack using nohup until we move back to using zdaemon
# properly. We also should really wait until services are running before
# exiting, as running 'make stop' too soon after running 'make start'
# will not work as expected. For use on production servers, where
# we know we don't need the extra steps in a full "make start"
# because of how the code is deployed/built.
initscript-start:
	nohup bin/run -i $(LPCONFIG) > ${LPCONFIG}-nohup.out 2>&1 &

# Intended for use on developer machines
stop: build initscript-stop

# Kill launchpad last - other services will probably shutdown with it,
# so killing them after is a race condition. For use on production
# servers, where we know we don't need the extra steps in a full
# "make stop" because of how the code is deployed/built.
initscript-stop:
	bin/killservice librarian launchpad mailman

shutdown: scheduleoutage stop
	$(RM) +maintenancetime.txt

scheduleoutage:
	echo Scheduling outage in ${MINS_TO_SHUTDOWN} mins
	date --iso-8601=minutes -u -d +${MINS_TO_SHUTDOWN}mins > +maintenancetime.txt
	echo Sleeping ${MINS_TO_SHUTDOWN} mins
	sleep ${MINS_TO_SHUTDOWN}m

harness: bin/harness
	bin/harness

iharness: bin/iharness
	bin/iharness

rebuildfti:
	@echo Rebuilding FTI indexes on launchpad_dev database
	$(PY) database/schema/fti.py -d launchpad_dev --force

clean_js:
	$(RM) -r $(JS_BUILD_DIR)
	$(RM) -r yui # Remove obsolete top-level directory for now.

clean_buildout:
	$(RM) -r build
	if [ -d $(CONVOY_ROOT) ]; then $(RM) -r $(CONVOY_ROOT) ; fi
	$(RM) -r bin
	$(RM) -r parts
	$(RM) -r develop-eggs
	$(RM) .installed.cfg
	$(RM) _pythonpath.py
	$(RM) -r yui/*
	$(RM) scripts/mlist-sync.py

clean_logs:
	$(RM) logs/thread*.request

clean_mailman:
	$(RM) -r /var/tmp/mailman /var/tmp/mailman-xmlrpc.test
ifdef LP_MAKE_KEEP_MAILMAN
	@echo "Keeping previously built mailman."
else
	$(RM) -r lib/mailman
endif

lxc-clean: clean_js clean_mailman clean_buildout clean_logs
	# XXX: BradCrittenden 2012-05-25 bug=1004514:
	# It is important for parallel tests inside LXC that the
	# $(CODEHOSTING_ROOT) directory not be completely removed.
	# This target removes its contents but not the directory and
	# it does everything expected from a clean target.  When the
	# referenced bug is fixed, this target may be reunited with
	# the 'clean' target.
	$(MAKE) -C sourcecode/pygettextpo clean
	# XXX gary 2009-11-16 bug 483782
	# The pygettextpo Makefile should have this next line in it for its make
	# clean, and then we should remove this line.
	$(RM) sourcecode/pygpgme/gpgme/*.so
	if test -f sourcecode/mailman/Makefile; then \
		$(MAKE) -C sourcecode/mailman clean; \
	fi
	find . -path ./eggs -prune -false -o \
		-type f \( -name '*.o' -o -name '*.so' -o -name '*.la' -o \
	    -name '*.lo' -o -name '*.py[co]' -o -name '*.dll' \) \
	    -print0 | xargs -r0 $(RM)
	$(RM) -r lib/subvertpy/*.so
	$(RM) -r $(LP_BUILT_JS_ROOT)/*
	$(RM) -r $(CODEHOSTING_ROOT)/*
	$(RM) -r $(APIDOC_DIR)
	$(RM) -r $(APIDOC_DIR).tmp
	$(RM) -r build
	$(RM) $(BZR_VERSION_INFO)
	$(RM) +config-overrides.zcml
	$(RM) -r /var/tmp/builddmaster \
			  /var/tmp/bzrsync \
			  /var/tmp/codehosting.test \
			  /var/tmp/codeimport \
			  /var/tmp/fatsam.test \
			  /var/tmp/lperr \
			  /var/tmp/lperr.test \
			  /var/tmp/mailman \
			  /var/tmp/mailman-xmlrpc.test \
			  /var/tmp/ppa \
			  /var/tmp/ppa.test \
			  /var/tmp/testkeyserver
	# /var/tmp/launchpad_mailqueue is created read-only on ec2test
	# instances.
	if [ -w /var/tmp/launchpad_mailqueue ]; then \
		$(RM) -r /var/tmp/launchpad_mailqueue; \
	fi

clean: lxc-clean
	$(RM) -r $(CODEHOSTING_ROOT)

realclean: clean
	$(RM) TAGS tags

zcmldocs:
	mkdir -p doc/zcml/namespaces.zope.org
	bin/stxdocs \
	    -f sourcecode/zope/src/zope/app/zcmlfiles/meta.zcml \
	    -o doc/zcml/namespaces.zope.org

potemplates: launchpad.pot

# Generate launchpad.pot by extracting message ids from the source
launchpad.pot:
	bin/i18nextract.py

# Called by the rocketfuel-setup script. You probably don't want to run this
# on its own.
install: reload-apache

copy-certificates:
	mkdir -p /etc/apache2/ssl
	cp configs/development/launchpad.crt /etc/apache2/ssl/
	cp configs/development/launchpad.key /etc/apache2/ssl/

copy-apache-config:
	# We insert the absolute path to the branch-rewrite script
	# into the Apache config as we copy the file into position.
	sed -e 's,%BRANCH_REWRITE%,$(shell pwd)/scripts/branch-rewrite.py,' \
		-e 's,%LISTEN_ADDRESS%,$(LISTEN_ADDRESS),' \
		configs/development/local-launchpad-apache > \
		/etc/apache2/sites-available/local-launchpad
	touch $(CODEHOSTING_ROOT)/rewrite.log
	chown -R $(SUDO_UID):$(SUDO_GID) $(CODEHOSTING_ROOT)
	if [ ! -d /srv/launchpad.dev ]; then \
		mkdir /srv/launchpad.dev; \
		chown $(SUDO_UID):$(SUDO_GID) /srv/launchpad.dev; \
	fi

enable-apache-launchpad: copy-apache-config copy-certificates
	a2ensite local-launchpad

reload-apache: enable-apache-launchpad
	/etc/init.d/apache2 restart

TAGS: compile
	# emacs tags
	bin/tags -e

tags: compile
	# vi tags
	bin/tags -v

ID: compile
	# idutils ID file
	bin/tags -i

PYDOCTOR = pydoctor
PYDOCTOR_OPTIONS =

pydoctor:
	$(PYDOCTOR) --make-html --html-output=apidocs --add-package=lib/lp \
		--add-package=lib/canonical --project-name=Launchpad \
		--docformat restructuredtext --verbose-about epytext-summary \
		$(PYDOCTOR_OPTIONS)

.PHONY: apidoc build_eggs buildonce_eggs buildout_bin check \
	check_config check_mailman clean clean_buildout clean_js	\
	clean_logs compile css_combine debug default doc ftest_build	\
	ftest_inplace hosted_branches jsbuild jsbuild_widget_css	\
	launchpad.pot pagetests pull_branches pydoctor realclean	\
	reload-apache run run-testapp runner scan_branches schema	\
	sprite_css sprite_image start stop sync_branches TAGS tags	\
	test_build test_inplace zcmldocs $(LP_JS_BUILD)
