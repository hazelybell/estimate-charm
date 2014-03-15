# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test scrubbing of `POFileTranslator`."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )

import pytz
import transaction

from lp.services.database.constants import UTC_NOW
from lp.services.database.interfaces import IStore
from lp.services.log.logger import DevNullLogger
from lp.testing import TestCaseWithFactory
from lp.testing.layers import ZopelessDatabaseLayer
from lp.translations.model.pofiletranslator import POFileTranslator
from lp.translations.scripts.scrub_pofiletranslator import (
    fix_pofile,
    gather_work_items,
    get_contributions,
    get_pofile_ids,
    get_pofiletranslators,
    get_potmsgset_ids,
    ScrubPOFileTranslator,
    summarize_contributors,
    summarize_pofiles,
    )


fake_logger = DevNullLogger()


def size_distance(sequence, item1, item2):
    """Return the absolute distance between items in a sequence."""
    container = list(sequence)
    return abs(container.index(item2) - container.index(item1))


class TestScrubPOFileTranslator(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def query_pofiletranslator(self, pofile, person):
        """Query `POFileTranslator` for a specific record.

        :return: Storm result set.
        """
        store = IStore(pofile)
        return store.find(POFileTranslator, pofile=pofile, person=person)

    def make_message_with_pofiletranslator(self, pofile=None):
        """Create a normal `TranslationMessage` with `POFileTranslator`."""
        if pofile is None:
            pofile = self.factory.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(
            potemplate=pofile.potemplate,
            sequence=self.factory.getUniqueInteger())
        # A database trigger on TranslationMessage automatically creates
        # a POFileTranslator record for each new TranslationMessage.
        return self.factory.makeSuggestion(pofile=pofile, potmsgset=potmsgset)

    def make_message_without_pofiletranslator(self, pofile=None):
        """Create a `TranslationMessage` without `POFileTranslator`."""
        tm = self.make_message_with_pofiletranslator(pofile)
        IStore(pofile).flush()
        self.becomeDbUser('postgres')
        self.query_pofiletranslator(pofile, tm.submitter).remove()
        return tm

    def make_pofiletranslator_without_message(self, pofile=None):
        """Create a `POFileTranslator` without `TranslationMessage`."""
        if pofile is None:
            pofile = self.factory.makePOFile()
        poft = POFileTranslator(
            pofile=pofile, person=self.factory.makePerson(),
            date_last_touched=UTC_NOW)
        IStore(poft.pofile).add(poft)
        return poft

    def test_get_pofile_ids_gets_pofiles_for_active_templates(self):
        pofile = self.factory.makePOFile()
        self.assertIn(pofile.id, get_pofile_ids())

    def test_get_pofile_ids_skips_inactive_templates(self):
        pofile = self.factory.makePOFile()
        pofile.potemplate.iscurrent = False
        self.assertNotIn(pofile.id, get_pofile_ids())

    def test_get_pofile_ids_clusters_by_template_name(self):
        # POFiles for templates with the same name are bunched together
        # in the get_pofile_ids() output.
        templates = [
            self.factory.makePOTemplate(name='shared'),
            self.factory.makePOTemplate(name='other'),
            self.factory.makePOTemplate(name='andanother'),
            self.factory.makePOTemplate(
                name='shared', distroseries=self.factory.makeDistroSeries()),
            ]
        pofiles = [
            self.factory.makePOFile(potemplate=template)
            for template in templates]
        ordering = get_pofile_ids()
        self.assertEqual(
            1, size_distance(ordering, pofiles[0].id, pofiles[-1].id))

    def test_get_pofile_ids_clusters_by_language(self):
        # POFiles for sharing templates and the same language are
        # bunched together in the get_pofile_ids() output.
        templates = [
            self.factory.makePOTemplate(
                name='shared', distroseries=self.factory.makeDistroSeries())
            for counter in range(2)]
        # POFiles per language & template.  We create these in a strange
        # way to avoid the risk of mistaking accidental orderings such
        # as per-id from being mistaken for the proper order.
        languages = ['nl', 'fr']
        pofiles_per_language = dict((language, []) for language in languages)
        for language, pofiles in pofiles_per_language.items():
            for template in templates:
                pofiles.append(
                    self.factory.makePOFile(language, potemplate=template))

        ordering = get_pofile_ids()
        for pofiles in pofiles_per_language.values():
            self.assertEqual(
                1, size_distance(ordering, pofiles[0].id, pofiles[1].id))

    def test_summarize_pofiles_maps_id_to_template_and_language_ids(self):
        pofile = self.factory.makePOFile()
        self.assertEqual(
            {pofile.id: (pofile.potemplate.id, pofile.language.id)},
            summarize_pofiles([pofile.id]))

    def test_get_potmsgset_ids_returns_potmsgset_ids(self):
        pofile = self.factory.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(
            potemplate=pofile.potemplate, sequence=1)
        self.assertContentEqual(
            [potmsgset.id], get_potmsgset_ids(pofile.potemplate.id))

    def test_get_potmsgset_ids_ignores_inactive_messages(self):
        pofile = self.factory.makePOFile()
        self.factory.makePOTMsgSet(
            potemplate=pofile.potemplate, sequence=0)
        self.assertContentEqual([], get_potmsgset_ids(pofile.potemplate.id))

    def test_summarize_contributors_gets_contributors(self):
        pofile = self.factory.makePOFile()
        tm = self.factory.makeSuggestion(pofile=pofile)
        potmsgset_ids = get_potmsgset_ids(pofile.potemplate.id)
        self.assertContentEqual(
            [tm.submitter.id],
            summarize_contributors(
                pofile.potemplate.id, pofile.language.id, potmsgset_ids))

    def test_summarize_contributors_ignores_inactive_potmsgsets(self):
        pofile = self.factory.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(
            potemplate=pofile.potemplate, sequence=0)
        self.factory.makeSuggestion(pofile=pofile, potmsgset=potmsgset)
        potmsgset_ids = get_potmsgset_ids(pofile.potemplate.id)
        self.assertContentEqual(
            [],
            summarize_contributors(
                pofile.potemplate.id, pofile.language.id, potmsgset_ids))

    def test_summarize_contributors_includes_diverged_msgs_for_template(self):
        pofile = self.factory.makePOFile()
        tm = self.factory.makeSuggestion(pofile=pofile)
        tm.potemplate = pofile.potemplate
        potmsgset_ids = get_potmsgset_ids(pofile.potemplate.id)
        self.assertContentEqual(
            [tm.submitter.id],
            summarize_contributors(
                pofile.potemplate.id, pofile.language.id, potmsgset_ids))

    def test_summarize_contributors_excludes_other_diverged_messages(self):
        pofile = self.factory.makePOFile()
        tm = self.factory.makeSuggestion(pofile=pofile)
        tm.potemplate = self.factory.makePOTemplate()
        potmsgset_ids = get_potmsgset_ids(pofile.potemplate.id)
        self.assertContentEqual(
            [],
            summarize_contributors(
                pofile.potemplate.id, pofile.language.id, potmsgset_ids))

    def test_get_contributions_gets_contributions(self):
        pofile = self.factory.makePOFile()
        tm = self.factory.makeSuggestion(pofile=pofile)
        potmsgset_ids = get_potmsgset_ids(pofile.potemplate.id)
        self.assertEqual(
            {tm.submitter.id: tm.date_created},
            get_contributions(pofile, potmsgset_ids))

    def test_get_contributions_uses_latest_contribution(self):
        pofile = self.factory.makePOFile()
        today = datetime.now(pytz.UTC)
        yesterday = today - timedelta(1, 1, 1)
        old_tm = self.factory.makeSuggestion(
            pofile=pofile, date_created=yesterday)
        new_tm = self.factory.makeSuggestion(
            translator=old_tm.submitter, pofile=pofile, date_created=today)
        potmsgset_ids = get_potmsgset_ids(pofile.potemplate.id)
        self.assertNotEqual(old_tm.date_created, new_tm.date_created)
        self.assertContentEqual(
            [new_tm.date_created],
            get_contributions(pofile, potmsgset_ids).values())

    def test_get_contributions_ignores_inactive_potmsgsets(self):
        pofile = self.factory.makePOFile()
        potmsgset = self.factory.makePOTMsgSet(
            potemplate=pofile.potemplate, sequence=0)
        self.factory.makeSuggestion(pofile=pofile, potmsgset=potmsgset)
        potmsgset_ids = get_potmsgset_ids(pofile.potemplate.id)
        self.assertEqual({}, get_contributions(pofile, potmsgset_ids))

    def test_get_contributions_includes_diverged_messages_for_template(self):
        pofile = self.factory.makePOFile()
        tm = self.factory.makeSuggestion(pofile=pofile)
        tm.potemplate = pofile.potemplate
        potmsgset_ids = get_potmsgset_ids(pofile.potemplate.id)
        self.assertContentEqual(
            [tm.submitter.id], get_contributions(pofile, potmsgset_ids))

    def test_get_contributions_excludes_other_diverged_messages(self):
        pofile = self.factory.makePOFile()
        tm = self.factory.makeSuggestion(pofile=pofile)
        tm.potemplate = self.factory.makePOTemplate()
        potmsgset_ids = get_potmsgset_ids(pofile.potemplate.id)
        self.assertEqual({}, get_contributions(pofile, potmsgset_ids))

    def test_get_pofiletranslators_gets_translators_for_pofile(self):
        pofile = self.factory.makePOFile()
        tm = self.make_message_with_pofiletranslator(pofile)
        self.assertContentEqual(
            [tm.submitter.id], get_pofiletranslators(pofile.id))

    def test_fix_pofile_leaves_good_pofiletranslator_in_place(self):
        pofile = self.factory.makePOFile()
        tm = self.make_message_with_pofiletranslator(pofile)
        old_poft = self.query_pofiletranslator(pofile, tm.submitter).one()

        fix_pofile(
            fake_logger, pofile, [tm.potmsgset.id], set([tm.submitter.id]))

        new_poft = self.query_pofiletranslator(pofile, tm.submitter).one()
        self.assertEqual(old_poft, new_poft)

    def test_fix_pofile_deletes_unwarranted_entries(self):
        # Deleting POFileTranslator records is not something the app
        # server ever does, so it requires special privileges.
        self.becomeDbUser('postgres')
        poft = self.make_pofiletranslator_without_message()
        (pofile, person) = (poft.pofile, poft.person)
        fix_pofile(fake_logger, pofile, [], set([person.id]))
        self.assertIsNone(self.query_pofiletranslator(pofile, person).one())

    def test_fix_pofile_adds_missing_entries(self):
        pofile = self.factory.makePOFile()
        tm = self.make_message_without_pofiletranslator(pofile)

        fix_pofile(fake_logger, pofile, [tm.potmsgset.id], set())

        new_poft = self.query_pofiletranslator(pofile, tm.submitter).one()
        self.assertEqual(tm.submitter, new_poft.person)
        self.assertEqual(pofile, new_poft.pofile)

    def test_gather_work_items_caches_potmsgset_ids_for_same_template(self):
        template = self.factory.makePOTemplate()
        pofiles = [
            self.factory.makePOFile(potemplate=template)
            for counter in range(2)]
        for pofile in pofiles:
            self.make_message_without_pofiletranslator(pofile)
        work_items = gather_work_items([pofile.id for pofile in pofiles])
        # The potmsgset_ids entries are references to one and the same
        # object.
        self.assertIs(
            work_items[0].potmsgset_ids, work_items[1].potmsgset_ids)

    def test_gather_work_items_does_not_cache_across_templates(self):
        pofiles = [self.factory.makePOFile() for counter in range(2)]
        for pofile in pofiles:
            self.make_message_without_pofiletranslator(pofile)
        work_items = gather_work_items([pofile.id for pofile in pofiles])
        # The POFiles are for different templates, so they do not share
        # the same potmsgset_ids.
        self.assertNotEqual(
            work_items[0].potmsgset_ids, work_items[1].potmsgset_ids)

    def test_tunable_loop(self):
        pofile = self.factory.makePOFile()
        tm = self.make_message_without_pofiletranslator(pofile)
        bad_poft = self.make_pofiletranslator_without_message(pofile)
        noncontributor = bad_poft.person
        transaction.commit()

        self.becomeDbUser('garbo')
        ScrubPOFileTranslator(fake_logger).run()
        # Try to break the loop if it failed to commit its changes.
        transaction.abort()

        # An unwarranted POFileTranslator record has been deleted.
        self.assertIsNotNone(
            self.query_pofiletranslator(pofile, tm.submitter).one())
        # A missing POFileTranslator has been created.
        self.assertIsNone(
            self.query_pofiletranslator(pofile, noncontributor).one())
