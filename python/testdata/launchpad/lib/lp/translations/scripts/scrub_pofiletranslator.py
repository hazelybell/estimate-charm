# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Keep `POFileTranslator` more or less consistent with the real data."""

__metaclass__ = type
__all__ = [
    'ScrubPOFileTranslator',
    ]

from collections import namedtuple

from storm.expr import (
    Coalesce,
    Desc,
    )
import transaction

from lp.registry.model.distribution import Distribution
from lp.registry.model.distroseries import DistroSeries
from lp.registry.model.product import Product
from lp.registry.model.productseries import ProductSeries
from lp.services.database.bulk import (
    load,
    load_related,
    )
from lp.services.database.interfaces import IStore
from lp.services.looptuner import TunableLoop
from lp.services.worlddata.model.language import Language
from lp.translations.model.pofile import POFile
from lp.translations.model.pofiletranslator import POFileTranslator
from lp.translations.model.potemplate import POTemplate
from lp.translations.model.translationmessage import TranslationMessage
from lp.translations.model.translationtemplateitem import (
    TranslationTemplateItem,
    )


def get_pofile_ids():
    """Retrieve ids of POFiles to scrub.

    The result's ordering is aimed at maximizing cache effectiveness:
    by POTemplate name for locality of shared POTMsgSets, and by language
    for locality of shared TranslationMessages.
    """
    store = IStore(POFile)
    query = store.find(
        POFile.id,
        POFile.potemplateID == POTemplate.id,
        POTemplate.iscurrent == True)
    return query.order_by(POTemplate.name, POFile.languageID)


def summarize_pofiles(pofile_ids):
    """Retrieve relevant parts of `POFile`s with given ids.

    This gets just enough information to determine whether any of the
    `POFile`s need their `POFileTranslator` records fixed.

    :param pofile_ids: Iterable of `POFile` ids.
    :return: Dict mapping each id in `pofile_ids` to a duple of
        `POTemplate` id and `Language` id for the associated `POFile`.
    """
    store = IStore(POFile)
    rows = store.find(
        (POFile.id, POFile.potemplateID, POFile.languageID),
        POFile.id.is_in(pofile_ids))
    return dict((row[0], row[1:]) for row in rows)


def get_potmsgset_ids(potemplate_id):
    """Get the ids for each current `POTMsgSet` in a `POTemplate`."""
    store = IStore(POTemplate)
    return store.find(
        TranslationTemplateItem.potmsgsetID,
        TranslationTemplateItem.potemplateID == potemplate_id,
        TranslationTemplateItem.sequence > 0)


def summarize_contributors(potemplate_id, language_id, potmsgset_ids):
    """Return the set of ids of persons who contributed to a `POFile`.

    This is a limited version of `get_contributions` that is easier to
    compute.
    """
    store = IStore(POFile)
    contribs = store.find(
        TranslationMessage.submitterID,
        TranslationMessage.potmsgsetID.is_in(potmsgset_ids),
        TranslationMessage.languageID == language_id,
        TranslationMessage.msgstr0 != None,
        Coalesce(TranslationMessage.potemplateID, potemplate_id) ==
            potemplate_id)
    contribs.config(distinct=True)
    return set(contribs)


def get_contributions(pofile, potmsgset_ids):
    """Map all users' most recent contributions to a `POFile`.

    Returns a dict mapping `Person` id to the creation time of their most
    recent `TranslationMessage` in `POFile`.

    This leaves some small room for error: a contribution that is masked by
    a diverged entry in this POFile will nevertheless produce a
    POFileTranslator record.  Fixing that would complicate the work more than
    it is probably worth.

    :param pofile: The `POFile` to find contributions for.
    :param potmsgset_ids: The ids of the `POTMsgSet`s to look for, as returned
        by `get_potmsgset_ids`.
    """
    store = IStore(pofile)
    language_id = pofile.language.id
    template_id = pofile.potemplate.id
    contribs = store.find(
        (TranslationMessage.submitterID, TranslationMessage.date_created),
        TranslationMessage.potmsgsetID.is_in(potmsgset_ids),
        TranslationMessage.languageID == language_id,
        TranslationMessage.msgstr0 != None,
        Coalesce(TranslationMessage.potemplateID, template_id) ==
            template_id)
    contribs = contribs.config(distinct=(TranslationMessage.submitterID,))
    contribs = contribs.order_by(
        TranslationMessage.submitterID, Desc(TranslationMessage.date_created))
    return dict(contribs)


def get_pofiletranslators(pofile_id):
    """Get `Person` ids from `POFileTranslator` entries for a `POFile`.

    Returns a `set` of `Person` ids.
    """
    store = IStore(POFileTranslator)
    return set(store.find(
        POFileTranslator.personID,
        POFileTranslator.pofileID == pofile_id))


def remove_pofiletranslators(logger, pofile, person_ids):
    """Delete `POFileTranslator` records."""
    logger.debug(
        "Removing %d POFileTranslator(s) for %s.",
        len(person_ids), pofile.title)
    store = IStore(pofile)
    pofts = store.find(
        POFileTranslator,
        POFileTranslator.pofileID == pofile.id,
        POFileTranslator.personID.is_in(person_ids))
    pofts.remove()


def remove_unwarranted_pofiletranslators(logger, pofile, pofts, contribs):
    """Delete `POFileTranslator` records that shouldn't be there."""
    excess = pofts - set(contribs)
    if len(excess) > 0:
        remove_pofiletranslators(logger, pofile, excess)


def create_missing_pofiletranslators(logger, pofile, pofts, contribs):
    """Create `POFileTranslator` records that were missing."""
    shortage = set(contribs) - pofts
    if len(shortage) == 0:
        return
    logger.debug(
        "Adding %d POFileTranslator(s) for %s.",
        len(shortage), pofile.title)
    store = IStore(pofile)
    for missing_contributor in shortage:
        store.add(POFileTranslator(
            pofile=pofile, personID=missing_contributor,
            date_last_touched=contribs[missing_contributor]))


def fix_pofile(logger, pofile, potmsgset_ids, pofiletranslators):
    """This `POFile` needs fixing.  Load its data & fix it."""
    contribs = get_contributions(pofile, potmsgset_ids)
    remove_unwarranted_pofiletranslators(
        logger, pofile, pofiletranslators, contribs)
    create_missing_pofiletranslators(
        logger, pofile, pofiletranslators, contribs)


def needs_fixing(template_id, language_id, potmsgset_ids, pofiletranslators):
    """Does the `POFile` with given details need `POFileTranslator` changes?

    :param template_id: id of the `POTemplate` for the `POFile`.
    :param language_id: id of the `Language` the `POFile` translates to.
    :param potmsgset_ids: ids of the `POTMsgSet` items participating in the
        template.
    :param pofiletranslators: `POFileTranslator` objects for the `POFile`.
    :return: Bool: does the existing set of `POFileTranslator` need fixing?
    """
    contributors = summarize_contributors(
        template_id, language_id, potmsgset_ids)
    return pofiletranslators != set(contributors)


# A tuple describing a POFile that needs its POFileTranslators fixed.
WorkItem = namedtuple("WorkItem", [
    'pofile_id',
    'potmsgset_ids',
    'pofiletranslators',
    ])


def gather_work_items(pofile_ids):
    """Produce `WorkItem`s for those `POFile`s that need fixing.

    :param pofile_ids: An iterable of `POFile` ids to check.
    :param pofile_summaries: Dict as returned by `summarize_pofiles`.
    :return: A sequence of `WorkItem`s for those `POFile`s that need fixing.
    """
    pofile_summaries = summarize_pofiles(pofile_ids)
    cached_potmsgsets = {}
    work_items = []
    for pofile_id in pofile_ids:
        template_id, language_id = pofile_summaries[pofile_id]
        if template_id not in cached_potmsgsets:
            cached_potmsgsets[template_id] = get_potmsgset_ids(template_id)
        potmsgset_ids = cached_potmsgsets[template_id]
        pofts = get_pofiletranslators(pofile_id)
        if needs_fixing(template_id, language_id, potmsgset_ids, pofts):
            work_items.append(WorkItem(pofile_id, potmsgset_ids, pofts))

    return work_items


def preload_work_items(work_items):
    """Bulk load data that will be needed to process `work_items`.

    :param work_items: A sequence of `WorkItem` records.
    :return: A dict mapping `POFile` ids from `work_items` to their
        respective `POFile` objects.
    """
    pofiles = load(POFile, [work_item.pofile_id for work_item in work_items])
    load_related(Language, pofiles, ['languageID'])
    templates = load_related(POTemplate, pofiles, ['potemplateID'])
    distroseries = load_related(DistroSeries, templates, ['distroseriesID'])
    load_related(Distribution, distroseries, ['distributionID'])
    productseries = load_related(
        ProductSeries, templates, ['productseriesID'])
    load_related(Product, productseries, ['productID'])
    return dict((pofile.id, pofile) for pofile in pofiles)


def process_work_items(logger, work_items, pofiles):
    """Fix the `POFileTranslator` records covered by `work_items`."""
    for work_item in work_items:
        pofile = pofiles[work_item.pofile_id]
        fix_pofile(
            logger, pofile, work_item.potmsgset_ids,
            work_item.pofiletranslators)


class ScrubPOFileTranslator(TunableLoop):
    """Tunable loop, meant for running from inside Garbo."""

    maximum_chunk_size = 500

    def __init__(self, *args, **kwargs):
        super(ScrubPOFileTranslator, self).__init__(*args, **kwargs)
        self.pofile_ids = tuple(get_pofile_ids())
        self.next_offset = 0

    def __call__(self, chunk_size):
        """See `ITunableLoop`."""
        start_offset = self.next_offset
        self.next_offset = start_offset + int(chunk_size)
        batch = self.pofile_ids[start_offset:self.next_offset]
        if len(batch) == 0:
            self.next_offset = None
        else:
            work_items = gather_work_items(batch)
            pofiles = preload_work_items(work_items)
            process_work_items(self.log, work_items, pofiles)
            transaction.commit()

    def isDone(self):
        """See `ITunableLoop`."""
        return self.next_offset is None
