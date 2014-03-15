#!/usr/bin/python -S

# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
#
# This code is based on William Grant's make-ubuntu-sane.py script, but
# reorganized to fit Launchpad coding guidelines, and extended.  The
# code is included under Canonical copyright with his permission
# (2010-02-24).

"""Clean up sample data so it will allow Soyuz to run locally.

DO NOT RUN ON PRODUCTION SYSTEMS.  This script deletes lots of
Ubuntu-related data.

This script creates a user "ppa-user" (email ppa-user@example.com,
password test) who is able to create PPAs.
"""

__metaclass__ = type

import _pythonpath

import os
import re
import subprocess
import sys
from textwrap import dedent

from storm.store import Store
import transaction
from zope.component import getUtility
from zope.event import notify
from zope.lifecycleevent import ObjectCreatedEvent
from zope.security.proxy import removeSecurityProxy

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.interfaces.codeofconduct import ISignedCodeOfConductSet
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.model.codeofconduct import SignedCodeOfConduct
from lp.services.database.interfaces import (
    IMasterStore,
    ISlaveStore,
    )
from lp.services.scripts.base import LaunchpadScript
from lp.soyuz.enums import SourcePackageFormat
from lp.soyuz.interfaces.component import IComponentSet
from lp.soyuz.interfaces.processor import IProcessorSet
from lp.soyuz.interfaces.section import ISectionSet
from lp.soyuz.interfaces.sourcepackageformat import (
    ISourcePackageFormatSelectionSet,
    )
from lp.soyuz.model.component import ComponentSelection
from lp.soyuz.model.section import SectionSelection
from lp.soyuz.scripts.initialize_distroseries import InitializeDistroSeries
from lp.testing.factory import LaunchpadObjectFactory


user_name = 'ppa-user'
default_email = '%s@example.com' % user_name


class DoNotRunOnProduction(Exception):
    """Error: do not run this script on production (-like) systems."""


def get_max_id(store, table_name):
    """Find highest assigned id in given table."""
    max_id = store.execute("SELECT max(id) FROM %s" % table_name).get_one()
    if max_id is None:
        return None
    else:
        return max_id[0]


def check_preconditions(options):
    """Try to ensure that it's safe to run.

    This script must not run on a production server, or anything
    remotely like it.
    """
    store = ISlaveStore(ComponentSelection)

    # Just a guess, but dev systems aren't likely to have ids this high
    # in this table.  Production data does.
    real_data = (get_max_id(store, "TranslationMessage") >= 1000000)
    if real_data and not options.force:
        raise DoNotRunOnProduction(
            "Refusing to delete Ubuntu data unless you --force me.")

    # For some configs it's just absolutely clear this script shouldn't
    # run.  Don't even accept --force there.
    forbidden_configs = re.compile('(edge|lpnet|production)')
    current_config = os.getenv('LPCONFIG', 'an unknown config')
    if forbidden_configs.match(current_config):
        raise DoNotRunOnProduction(
            "I won't delete Ubuntu data on %s and you can't --force me."
            % current_config)


def get_person_set():
    """Return `IPersonSet` utility."""
    return getUtility(IPersonSet)


def retire_series(distribution):
    """Mark all `DistroSeries` for `distribution` as obsolete."""
    for series in distribution.series:
        series.status = SeriesStatus.OBSOLETE


def retire_active_publishing_histories(histories, requester):
    """Retire all active publishing histories in the given collection."""
    # Avoid circular import.
    from lp.soyuz.interfaces.publishing import active_publishing_status
    for history in histories(status=active_publishing_status):
        history.requestDeletion(
            requester, "Cleaned up because of missing Librarian files.")


def retire_distro_archives(distribution, culprit):
    """Retire all items in `distribution`'s archives."""

    # Temporarily mark all `DistroSeries` as in-development so that we can
    # delete publications from them.  We're about to delete the series
    # anyway.
    for series in distribution.series:
        series.status = SeriesStatus.DEVELOPMENT

    for archive in distribution.all_distro_archives:
        retire_active_publishing_histories(
            archive.getPublishedSources, culprit)
        retire_active_publishing_histories(
            archive.getAllPublishedBinaries, culprit)


def retire_ppas(distribution):
    """Disable all PPAs for `distribution`."""
    for ppa in distribution.getAllPPAs():
        removeSecurityProxy(ppa).publish = False


def add_architecture(distroseries, architecture_name):
    """Add a DistroArchSeries for the given architecture to `distroseries`."""
    # Avoid circular import.
    from lp.soyuz.model.distroarchseries import DistroArchSeries

    processor = getUtility(IProcessorSet).getByName(architecture_name)
    archseries = DistroArchSeries(
        distroseries=distroseries, processor=processor,
        owner=distroseries.owner, official=True,
        architecturetag=architecture_name)
    IMasterStore(DistroArchSeries).add(archseries)


def create_sections(distroseries):
    """Set up some sections for `distroseries`."""
    section_names = (
        'admin', 'cli-mono', 'comm', 'database', 'devel', 'debug', 'doc',
        'editors', 'electronics', 'embedded', 'fonts', 'games', 'gnome',
        'graphics', 'gnu-r', 'gnustep', 'hamradio', 'haskell', 'httpd',
        'interpreters', 'java', 'kde', 'kernel', 'libs', 'libdevel', 'lisp',
        'localization', 'mail', 'math', 'misc', 'net', 'news', 'ocaml',
        'oldlibs', 'otherosfs', 'perl', 'php', 'python', 'ruby', 'science',
        'shells', 'sound', 'tex', 'text', 'utils', 'vcs', 'video', 'web',
        'x11', 'xfce', 'zope')
    store = Store.of(distroseries)
    for section_name in section_names:
        section = getUtility(ISectionSet).ensure(section_name)
        if section not in distroseries.sections:
            store.add(
                SectionSelection(distroseries=distroseries, section=section))


def create_components(distroseries, uploader):
    """Set up some components for `distroseries`."""
    component_names = ('main', 'restricted', 'universe', 'multiverse')
    store = Store.of(distroseries)
    main_archive = distroseries.distribution.main_archive
    for component_name in component_names:
        component = getUtility(IComponentSet).ensure(component_name)
        if component not in distroseries.components:
            store.add(
                ComponentSelection(
                    distroseries=distroseries, component=component))
        main_archive.newComponentUploader(uploader, component)
        main_archive.newQueueAdmin(uploader, component)


def create_series(parent, full_name, version, status):
    """Set up a `DistroSeries`."""
    distribution = parent.distribution
    registrant = parent.owner
    name = full_name.split()[0].lower()
    title = "The " + full_name
    displayname = full_name.split()[0]
    new_series = distribution.newSeries(name=name, title=title,
        displayname=displayname, summary='Ubuntu %s is good.' % version,
        description='%s is awesome.' % version, version=version,
        previous_series=None, registrant=registrant)
    new_series.status = status
    notify(ObjectCreatedEvent(new_series))

    new_series.previous_series = parent
    ids = InitializeDistroSeries(new_series, [parent.id])
    ids.initialize()
    return new_series


def create_sample_series(original_series, log):
    """Set up sample `DistroSeries`.

    :param original_series: The parent for the first new series to be
        created.  The second new series will have the first as a parent,
        and so on.
    """
    series_descriptions = [
        ('Dapper Drake', SeriesStatus.OBSOLETE, '6.06'),
        ('Edgy Eft', SeriesStatus.OBSOLETE, '6.10'),
        ('Feisty Fawn', SeriesStatus.OBSOLETE, '7.04'),
        ('Gutsy Gibbon', SeriesStatus.OBSOLETE, '7.10'),
        ('Hardy Heron', SeriesStatus.SUPPORTED, '8.04'),
        ('Intrepid Ibex', SeriesStatus.OBSOLETE, '8.10'),
        ('Jaunty Jackalope', SeriesStatus.OBSOLETE, '9.04'),
        ('Karmic Koala', SeriesStatus.OBSOLETE, '9.10'),
        ('Lucid Lynx', SeriesStatus.SUPPORTED, '10.04'),
        ('Maverick Meerkat', SeriesStatus.OBSOLETE, '10.10'),
        ('Natty Narwhal', SeriesStatus.OBSOLETE, '11.04'),
        ('Oneiric Ocelot', SeriesStatus.SUPPORTED, '11.10'),
        ('Precise Pangolin', SeriesStatus.SUPPORTED, '12.04'),
        ('Quantal Quetzal', SeriesStatus.SUPPORTED, '12.10'),
        ('Raring Ringtail', SeriesStatus.CURRENT, '13.04'),
        ('Saucy Salamander', SeriesStatus.DEVELOPMENT, '13.10'),
        ]

    parent = original_series
    for full_name, status, version in series_descriptions:
        log.info('Creating %s...' % full_name)
        parent = create_series(parent, full_name, version, status)
        # Karmic is the first series in which the 3.0 formats are
        # allowed. Subsequent series will inherit them.
        if version == '9.10':
            spfss = getUtility(ISourcePackageFormatSelectionSet)
            spfss.add(parent, SourcePackageFormat.FORMAT_3_0_QUILT)
            spfss.add(parent, SourcePackageFormat.FORMAT_3_0_NATIVE)


def add_series_component(series):
    """Permit a component in the given series."""
    component = getUtility(IComponentSet)['main']
    IMasterStore(ComponentSelection).add(
        ComponentSelection(distroseries=series, component=component))


def clean_up(distribution, log):
    # First we eliminate all active publishings in the Ubuntu main archives.
    # None of the librarian files exist, so it kills the publisher.

    # Could use IPublishingSet.requestDeletion() on the published sources to
    # get rid of the binaries too, but I don't trust that there aren't
    # published binaries without corresponding sources.

    log.info("Deleting all items in official archives...")
    retire_distro_archives(distribution, get_person_set().getByName('name16'))

    # Disable publishing of all PPAs, as they probably have broken
    # publishings too.
    log.info("Disabling all PPAs...")
    retire_ppas(distribution)

    retire_series(distribution)

    # grumpy has no components, which upsets the publisher.
    add_series_component(distribution['grumpy'])


def set_source_package_format(distroseries):
    """Register a series' source package format selection."""
    utility = getUtility(ISourcePackageFormatSelectionSet)
    format = SourcePackageFormat.FORMAT_1_0
    if utility.getBySeriesAndFormat(distroseries, format) is None:
        utility.add(distroseries, format)


def populate(distribution, previous_series_name, uploader_name, options, log):
    """Set up sample data on `distribution`."""
    previous_series = distribution.getSeries(previous_series_name)

    log.info("Configuring sections...")
    create_sections(previous_series)
    add_architecture(previous_series, 'amd64')

    log.info("Configuring components and permissions...")
    uploader = get_person_set().getByName(uploader_name)
    create_components(previous_series, uploader)

    set_source_package_format(previous_series)

    create_sample_series(previous_series, log)


def sign_code_of_conduct(person, log):
    """Sign Ubuntu Code of Conduct for `person`, if necessary."""
    if person.is_ubuntu_coc_signer:
        # Already signed.
        return

    log.info("Signing Ubuntu code of conduct.")
    signedcocset = getUtility(ISignedCodeOfConductSet)
    person_id = person.id
    if signedcocset.searchByUser(person_id).count() == 0:
        fake_gpg_key = LaunchpadObjectFactory().makeGPGKey(person)
        Store.of(person).add(SignedCodeOfConduct(
            owner=person, signingkey=fake_gpg_key,
            signedcode="Normally a signed CoC would go here.", active=True))


def create_ppa_user(username, options, approver, log):
    """Create new user, with password "test," and sign code of conduct."""
    person = get_person_set().getByName(username)
    if person is None:
        have_email = (options.email != default_email)
        command_line = [
            'utilities/make-lp-user', username, 'ubuntu-team']
        if have_email:
            command_line += ['--email', options.email]

        pipe = subprocess.Popen(command_line, stderr=subprocess.PIPE)
        stdout, stderr = pipe.communicate()
        if stderr != '':
            print stderr
        if pipe.returncode != 0:
            sys.exit(2)

    transaction.commit()

    person = getUtility(IPersonSet).getByName(username)
    sign_code_of_conduct(person, log)

    return person


def create_ppa(distribution, person, name):
    """Create a PPA for `person`."""
    ppa = LaunchpadObjectFactory().makeArchive(
        distribution=distribution, owner=person, name=name, virtualized=False,
        description="Automatically created test PPA.")
    ppa.external_dependencies = (
        "deb http://archive.ubuntu.com/ubuntu %(series)s "
        "main restricted universe multiverse\n")


class SoyuzSampledataSetup(LaunchpadScript):

    description = "Set up fresh Ubuntu series and %s identity." % user_name

    def add_my_options(self):
        self.parser.add_option(
            '-f', '--force', action='store_true', dest='force',
            help="DANGEROUS: run even if the database looks production-like.")
        self.parser.add_option(
            '-e', '--email', action='store', dest='email',
            default=default_email,
            help=(
                "Email address to use for %s.  Should match your GPG key."
                % user_name))

    def main(self):
        check_preconditions(self.options.force)

        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        clean_up(ubuntu, self.logger)

        # Use Hoary as the root, as Breezy and Grumpy are broken.
        populate(ubuntu, 'hoary', 'ubuntu-team', self.options, self.logger)

        admin = get_person_set().getByName('name16')
        person = create_ppa_user(user_name, self.options, admin, self.logger)

        create_ppa(ubuntu, person, 'test-ppa')

        transaction.commit()
        self.logger.info("Done.")

        print dedent("""
            Now start your local Launchpad with "make run_codehosting" and log
            into https://launchpad.dev/ as "%(email)s" with "test" as the
            password.
            Your user name will be %(user_name)s."""
            % {
                'email': self.options.email,
                'user_name': user_name,
                })


if __name__ == "__main__":
    SoyuzSampledataSetup('soyuz-sampledata-setup').lock_and_run()
