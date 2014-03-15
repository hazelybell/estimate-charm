# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'MessageSharingMerge',
    'TransactionManager',
    'TranslationMerger',
    ]


from operator import methodcaller

from storm.locals import (
    ClassAlias,
    Store,
    )
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.registry.interfaces.product import IProductSet
from lp.registry.interfaces.sourcepackagename import ISourcePackageNameSet
from lp.registry.model.distroseries import DistroSeries
from lp.registry.model.packaging import Packaging
from lp.services.database.interfaces import IStore
from lp.services.orderingcheck import OrderingCheck
from lp.services.scripts.base import (
    LaunchpadScript,
    LaunchpadScriptFailure,
    )
from lp.services.scripts.logger import (
    DEBUG2,
    log,
    )
from lp.translations.interfaces.potemplate import IPOTemplateSet
from lp.translations.interfaces.side import TranslationSide
from lp.translations.interfaces.translations import TranslationConstants
from lp.translations.model.potemplate import (
    POTemplate,
    POTemplateSubset,
    )
from lp.translations.model.potmsgset import POTMsgSet
from lp.translations.model.translationmessage import TranslationMessage


def get_potmsgset_key(potmsgset):
    """Get the tuple of identifying properties of a POTMsgSet.

    A POTMsgSet is identified by its msgid, optional plural msgid, and
    optional context identifier.
    """
    potmsgset = removeSecurityProxy(potmsgset)
    return (
        potmsgset.msgid_singularID, potmsgset.msgid_pluralID,
        potmsgset.context)


def merge_pofiletranslators(from_template, to_template):
    """Merge POFileTranslator entries from one template into another.
    """
    # Import here to avoid circular import.
    from lp.translations.interfaces.pofiletranslator import (
        IPOFileTranslatorSet)

    pofiletranslatorset = getUtility(IPOFileTranslatorSet)
    affected_rows = pofiletranslatorset.getForTemplate(from_template)
    for pofiletranslator in affected_rows:
        person = pofiletranslator.person
        from_pofile = pofiletranslator.pofile
        to_pofile = to_template.getPOFileByLang(from_pofile.language.code)

        pofiletranslator = removeSecurityProxy(pofiletranslator)
        if to_pofile is None:
            # There's no POFile to move this to.  We could create one,
            # but it's probably not worth the trouble.
            pofiletranslator.destroySelf()
        else:
            existing_row = pofiletranslatorset.getForPersonPOFile(
                person, to_pofile)
            date_last_touched = pofiletranslator.date_last_touched
            if existing_row is None:
                # Move POFileTranslator over to representative POFile.
                pofiletranslator.pofile = to_pofile
            elif existing_row.date_last_touched < date_last_touched:
                removeSecurityProxy(existing_row).destroySelf()
            else:
                pofiletranslator.destroySelf()


def merge_translationtemplateitems(subordinate, representative,
                                   representative_template):
    """Merge subordinate POTMsgSet into its representative POTMsgSet.

    This adds all of the subordinate's TranslationTemplateItems to the
    representative's set of TranslationTemplateItems.

    Any duplicates are deleted, so after this, the subordinate will no
    longer have any TranslationTemplateItems.
    """
    source = subordinate.getAllTranslationTemplateItems()
    targets = representative.getAllTranslationTemplateItems()
    templates = set(item.potemplate for item in targets)

    for item in source:
        item = removeSecurityProxy(item)
        if item.potemplate in templates:
            # The representative POTMsgSet is already in this template.
            item.destroySelf()
        else:
            # Transfer linking-table entry to representative POTMsgSet.
            item.potmsgset = representative
            templates.add(item.potemplate)

        merge_pofiletranslators(item.potemplate, representative_template)


def filter_clashes(clashing_ubuntu, clashing_upstream, twin):
    """Filter clashes for harmless clashes with an identical message.

    Takes the three forms of clashes a message can have in a context
    it's being merged into:
     * Another message that also has the is_current_ubuntu flag.
     * Another message that also has the is_current_upstream flag.
     * Another message with the same translations.

    If either of the first two clashes matches the third, that is not a
    real clash since it can be resolved by merging the message into the
    twin.

    This function returns the same tuple but with these "harmless"
    clashes eliminated.
    """
    if clashing_ubuntu == twin:
        clashing_ubuntu = None
    if clashing_upstream == twin:
        clashing_upstream = None
    return clashing_ubuntu, clashing_upstream, twin


def sacrifice_flags(message, incumbents=None):
    """Drop current/imported flags if held by any of `incumbents`.

    :param message: a `TranslationMessage` to drop flags on.
    :param incumbents: a sequence of reference messages.  If any of
        these has either is_current_ubuntu or is_current_upstream set, that
        same flag will be dropped on message (if set).
    """
    if incumbents:
        for incumbent in incumbents:
            if incumbent is not None and incumbent.is_current_ubuntu:
                message.is_current_ubuntu = False
            if incumbent is not None and incumbent.is_current_upstream:
                message.is_current_upstream = False


def bequeathe_flags(source_message, target_message, incumbents=None):
    """Destroy `source_message`, leaving flags to `target_message`.

    If `source_message` holds the is_current_ubuntu flag, and there are no
    `incumbents` that hold the same flag, then `target_message` inherits
    it.  Similar for the is_current_upstream flag.
    """
    sacrifice_flags(source_message, incumbents)

    if (source_message.is_current_ubuntu and
        not target_message.is_current_ubuntu):
        # Transfer is_current_ubuntu flag.
        source_message.is_current_ubuntu = False
        target_message.is_current_ubuntu = True
        Store.of(source_message).add_flush_order(
            source_message, target_message)

    if (source_message.is_current_upstream and
        not target_message.is_current_upstream):
        # Transfer is_current_upstream flag.
        source_message.is_current_upstream = False
        target_message.is_current_upstream = True
        Store.of(source_message).add_flush_order(
            source_message, target_message)

    source_message.destroySelf()


class MessageSharingMerge(LaunchpadScript):

    template_set = None

    commit_count = 0

    def add_my_options(self):
        self.parser.add_option('-d', '--distribution', dest='distribution',
            help="Distribution to merge messages for.")
        self.parser.add_option('-D', '--remove-duplicates',
            dest='remove_duplicates', action='store_true',
            help="Phase 1: Remove problematic duplicate TranslationMessages.")
        self.parser.add_option('-p', '--product', dest='product',
            help="Product to merge messages for.")
        self.parser.add_option('-P', '--merge-potmsgsets',
            action='store_true', dest='merge_potmsgsets',
            help="Phase 2: Merge POTMsgSets.")
        self.parser.add_option('-s', '--source-package', dest='sourcepackage',
            help="Source package name within a distribution.")
        self.parser.add_option('-t', '--template-names',
            dest='template_names',
            help="Merge for templates with name matching this regex pattern.")
        self.parser.add_option('-T', '--merge-translationmessages',
            action='store_true', dest='merge_translationmessages',
            help="Phase 3: Merge TranslationMessages.")
        self.parser.add_option('-x', '--dry-run', dest='dry_run',
            action='store_true',
            help="Dry run, don't really make any changes.")

    def _setUpUtilities(self):
        """Prepare a few members that several methods need.

        Calling this again later does nothing.
        """
        if self.template_set is None:
            self.template_set = getUtility(IPOTemplateSet)

    def main(self):
        actions = (
            self.options.remove_duplicates or
            self.options.merge_potmsgsets or
            self.options.merge_translationmessages)

        if not actions:
            raise LaunchpadScriptFailure(
                "Select at least one action: remove duplicates, merge "
                "POTMsgSets, and/or merge TranslationMessages.")

        if self.options.product and self.options.distribution:
            raise LaunchpadScriptFailure(
                "Merge a product or a distribution, but not both.")

        if not (self.options.product or self.options.distribution):
            raise LaunchpadScriptFailure(
                "Specify a product or distribution to merge.")

        if self.options.sourcepackage and not self.options.distribution:
            raise LaunchpadScriptFailure(
                "Selecting a package only makes sense for distributions.")

        if self.options.product:
            product = getUtility(IProductSet).getByName(self.options.product)
            distribution = None
            if product is None:
                raise LaunchpadScriptFailure(
                    "Unknown product: '%s'" % self.options.product)
        else:
            product = None
            # import here to avoid circular import.
            from lp.registry.interfaces.distribution import IDistributionSet
            distribution = getUtility(IDistributionSet).getByName(
                self.options.distribution)
            if distribution is None:
                raise LaunchpadScriptFailure(
                    "Unknown distribution: '%s'" % self.options.distribution)

        if self.options.sourcepackage is None:
            sourcepackagename = None
        else:
            sourcepackagename = getUtility(ISourcePackageNameSet).queryByName(
                self.options.sourcepackage)
            if sourcepackagename is None:
                raise LaunchpadScriptFailure(
                    "Unknown source package name: '%s'" %
                        self.options.sourcepackage)

        self._setUpUtilities()

        subset = self.template_set.getSharingSubset(
                product=product, distribution=distribution,
                sourcepackagename=sourcepackagename)
        equivalence_classes = subset.groupEquivalentPOTemplates(
                                                self.options.template_names)

        class_count = len(equivalence_classes)
        log.info("Merging %d template equivalence classes." % class_count)

        tm = TransactionManager(self.txn, self.options.dry_run)
        for number, name in enumerate(sorted(equivalence_classes.iterkeys())):
            templates = equivalence_classes[name]
            log.info(
                "Merging equivalence class '%s': %d template(s) (%d / %d)" % (
                    name, len(templates), number + 1, class_count))
            log.debug("Templates: %s" % str(templates))
            merger = TranslationMerger(templates, tm)
            if self.options.remove_duplicates:
                log.info("Removing duplicate messages.")
                merger.removeDuplicateMessages()
                tm.endTransaction(intermediate=True)

            if self.options.merge_potmsgsets:
                log.info("Merging POTMsgSets.")
                merger.mergePOTMsgSets()
                tm.endTransaction(intermediate=True)

            if self.options.merge_translationmessages:
                log.info("Merging TranslationMessages.")
                merger.mergeTranslationMessages()

            tm.endTransaction()

        log.info("Done.")


class TransactionManager:
    """Manage transactions for script runs.

    For normal operation, every tenth intermediate transaction is actually
    committed.  At the end, the final transaction is committed.

    For dry runs, no transactions are committed and the final transaction is
    aborted.
    """

    def __init__(self, txn, dry_run):
        """Constructor.

        :param txn: The transaction to commit or abort.
        :param dry_run: If true, this is a dry run.
        """
        self.txn = txn
        self.dry_run = dry_run
        self.commit_count = 0

    def endTransaction(self, intermediate=False):
        """End this transaction and start a new one.

        :param intermediate: Whether this is an intermediate commit.
            Dry-run mode aborts transactions rather than committing
            them; where doing that may break dependencies between steps
            of the algorithm, pass `True` so that the abort can be
            skipped.
        """
        if self.txn is None:
            return

        self.commit_count += 1

        if intermediate and self.commit_count % 10 != 0:
            return

        if self.dry_run:
            if not intermediate:
                self.txn.abort()
        else:
            self.txn.commit()


class TranslationMerger:
    """Merge translations across a set of potemplates."""

    @staticmethod
    def findMergeablePackagings():
        """Find packagings where both product and package have templates."""
        store = IStore(Packaging)
        PackageTemplate = ClassAlias(POTemplate, 'PackageTemplate')
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        result = store.find(
            Packaging,
            Packaging.productseries == POTemplate.productseriesID,
            Packaging.distroseries == PackageTemplate.distroseriesID,
            Packaging.distroseries == DistroSeries.id,
            DistroSeries.distribution == ubuntu.id,
            Packaging.sourcepackagename ==
                PackageTemplate.sourcepackagenameID,
            )
        result.config(distinct=True)
        return result

    @classmethod
    def mergePackagingTemplates(cls, productseries, sourcepackagename,
                                distroseries, tm):
        template_map = dict()
        all_templates = list(POTemplateSubset(
            sourcepackagename=sourcepackagename,
            distroseries=distroseries))
        all_templates.extend(POTemplateSubset(
            productseries=productseries))
        for template in all_templates:
            template_map.setdefault(template.name, []).append(template)
        for name, templates in template_map.iteritems():
            templates.sort(key=POTemplate.sharingKey, reverse=True)
            merger = cls(templates, tm)
            merger.mergePOTMsgSets()

    @classmethod
    def mergeModifiedTemplates(cls, potemplate, tm):
        subset = getUtility(IPOTemplateSet).getSharingSubset(
            distribution=potemplate.distribution,
            sourcepackagename=potemplate.sourcepackagename,
            product=potemplate.product)
        templates = list(subset.getSharingPOTemplates(potemplate.name))
        templates.sort(key=methodcaller('sharingKey'), reverse=True)
        merger = cls(templates, tm)
        merger.mergeAll()

    def mergeAll(self):
        """Properly merge POTMsgSets and TranslationMessages."""
        self._removeDuplicateMessages()
        self.tm.endTransaction(intermediate=True)
        self.mergePOTMsgSets()
        self.tm.endTransaction(intermediate=True)
        self.mergeTranslationMessages()
        self.tm.endTransaction()

    def __init__(self, potemplates, tm):
        """Constructor.

        :param potemplates: The templates to merge across.
        """
        self.potemplates = potemplates
        self.tm = tm

    def _removeDuplicateMessages(self):
        """Get rid of duplicate `TranslationMessages` where needed."""
        representatives = {}
        order_check = OrderingCheck(
            key=methodcaller('sharingKey'), reverse=True)

        for template in self.potemplates:
            order_check.check(template)
            for potmsgset in template.getPOTMsgSets(False, prefetch=False):
                key = get_potmsgset_key(potmsgset)
                if key not in representatives:
                    representatives[key] = potmsgset.id

        self.tm.endTransaction(intermediate=True)

        for representative_id in representatives.itervalues():
            representative = POTMsgSet.get(representative_id)
            self._scrubPOTMsgSetTranslations(representative)
            self.tm.endTransaction(intermediate=True)

    def _mapRepresentatives(self):
        """Map out POTMsgSets' subordinates and templates.

        :return: A tuple of dicts.  The first maps each `POTMsgSet`'s
            key (as returned by `get_potmsgset_key`) to a list of its
            subordinate `POTMsgSet`s.  The second maps each
            representative `POTMsgSet` to its representative
            `POTemplate`.
        """
        # Map each POTMsgSet key (context, msgid, plural) to its
        # representative POTMsgSet.
        representatives = {}

        # Map each representative POTMsgSet to a list of subordinate
        # POTMsgSets it represents.
        subordinates = {}

        # Map each representative POTMsgSet to its representative
        # POTemplate.
        representative_templates = {}

        # Figure out representative potmsgsets and their subordinates.  Go
        # through the templates, starting at the most representative and
        # moving towards the least representative.  For any unique potmsgset
        # key we find, the first POTMsgSet is the representative one.
        order_check = OrderingCheck(
            key=methodcaller('sharingKey'), reverse=True)

        for template in self.potemplates:
            order_check.check(template)
            for potmsgset in template.getPOTMsgSets(False, prefetch=False):
                key = get_potmsgset_key(potmsgset)
                if key not in representatives:
                    representatives[key] = potmsgset
                    representative_templates[potmsgset] = template
                representative = representatives[key]
                if representative in subordinates:
                    subordinates[representative].append(potmsgset)
                else:
                    subordinates[representative] = []

        return subordinates, representative_templates

    def mergePOTMsgSets(self):
        """Merge POTMsgSets for given sequence of sharing templates."""
        subordinates, representative_templates = self._mapRepresentatives()

        num_representatives = len(subordinates)
        representative_num = 0

        for representative, potmsgsets in subordinates.iteritems():
            representative_num += 1
            log.debug("Message %d/%d: %d subordinate(s)." % (
                representative_num, num_representatives, len(potmsgsets)))

            seen_potmsgsets = set([representative.id])

            potmsgset_deletions = 0
            tm_deletions = 0

            # Merge each subordinate POTMsgSet into its representative.
            for subordinate in potmsgsets:
                if subordinate.id in seen_potmsgsets:
                    continue

                seen_potmsgsets.add(subordinate.id)

                for message in subordinate.getAllTranslationMessages():
                    message = removeSecurityProxy(message)

                    clashing_current, clashing_imported, twin = (
                        self._findClashes(
                            message, representative, message.potemplate))

                    if clashing_current or clashing_imported:
                        saved = self._saveByDiverging(
                            message, representative, subordinate)
                    else:
                        saved = False

                    if not saved:
                        if twin is None:
                            # This message will have to lose some flags, but
                            # then it can still move to the new potmsgset.
                            sacrifice_flags(
                                message,
                                (clashing_current, clashing_imported))
                            message.potmsgset = representative
                        else:
                            # This message is identical in contents to one
                            # that was more representative.  It'll have to
                            # die, but maybe it can bequeathe some of its
                            # status to the existing message.
                            # Since there are no clashes, there's no need to
                            # check for clashes with other current/imported
                            # messages in the target context.
                            bequeathe_flags(
                                message, twin,
                                (clashing_current, clashing_imported))
                            tm_deletions += 1

                merge_translationtemplateitems(
                    subordinate, representative,
                    representative_templates[representative])
                removeSecurityProxy(subordinate).destroySelf()
                potmsgset_deletions += 1

                self.tm.endTransaction(intermediate=True)

            report = "Deleted POTMsgSets: %d.  TranslationMessages: %d." % (
                potmsgset_deletions, tm_deletions)
            if potmsgset_deletions > 0 or tm_deletions > 0:
                log.info(report)
            else:
                log.log(DEBUG2, report)

    @staticmethod
    def _getPOTMsgSetIds(template):
        """Get list of ids for `template`'s `POTMsgSet`s."""
        return [
            potmsgset.id
            for potmsgset in template.getPOTMsgSets(False, prefetch=False)]

    def mergeTranslationMessages(self):
        """Share `TranslationMessage`s between templates where possible."""
        order_check = OrderingCheck(
            key=methodcaller('sharingKey'), reverse=True)
        for template_number, template in enumerate(self.potemplates):
            log.info("Merging template %d/%d." % (
                template_number + 1, len(self.potemplates)))
            deletions = 0
            order_check.check(template)
            potmsgset_ids = self._getPOTMsgSetIds(template)
            for potmsgset_id in potmsgset_ids:
                potmsgset = POTMsgSet.get(potmsgset_id)

                tm_ids = self._partitionTranslationMessageIds(potmsgset)
                before = sum([len(sublist) for sublist in tm_ids], 0)

                for ids in tm_ids:
                    for id in ids:
                        message = TranslationMessage.get(id)
                        removeSecurityProxy(message).shareIfPossible()

                self.tm.endTransaction(intermediate=True)

                after = potmsgset.getAllTranslationMessages().count()
                deletions += max(0, before - after)

            report = "Deleted TranslationMessages: %d." % deletions
            if deletions > 0:
                log.info(report)
            else:
                log.log(DEBUG2, report)

    @staticmethod
    def _getPOTMsgSetTranslationMessageKey(tm):
        """Return tuple that identifies a TranslationMessage in a POTMsgSet.

        A TranslationMessage is identified by (potemplate, potmsgset,
        language, msgstr0, ...).  In this case we leave out the
        potmsgset (because we start out with one) and potemplate (because
        that's sorted out in the nested dicts).
        """
        tm = removeSecurityProxy(tm)
        msgstr_ids = tuple([
            getattr(tm, 'msgstr%dID' % form)
            for form in xrange(TranslationConstants.MAX_PLURAL_FORMS)])

        return (tm.potemplateID, tm.languageID) + msgstr_ids

    @staticmethod
    def _partitionTranslationMessageIds(potmsgset):
        """Partition `TranslationMessage`s by language.

        Only the ids are stored, not the `TranslationMessage` objects
        themselves, so as to avoid pinning the objects in memory.

        :param potmsgset: A `POTMsgSet`.  All its `TranslationMessage`s
            will be read and partitioned.
        :return: A list of lists of `TranslationMessage` ids.  Each of
            the inner lists represents one language.
        """
        ids_per_language = {}
        tms = potmsgset.getAllTranslationMessages().order_by(
            TranslationMessage.languageID)
        for tm in tms:
            language = removeSecurityProxy(tm).languageID
            if language not in ids_per_language:
                ids_per_language[language] = []
            ids_per_language[language].append(tm.id)

        return ids_per_language.values()

    def _scrubPOTMsgSetTranslations(self, potmsgset):
        """Map out translations for `potmsgset`, and eliminate duplicates.

        In the transition period for message sharing, there may be
        duplicate TranslationMessages that may upset assumptions in the
        code.  Clean those up.
        """
        # XXX JeroenVermeulen 2009-06-15
        # spec=message-sharing-prevent-duplicates: We're going to have a
        # unique index again at some point that will prevent this.  When
        # it becomes impossible to test this function, this whole
        # migration phase can be scrapped.
        ids_per_language = self._partitionTranslationMessageIds(potmsgset)

        self.tm.endTransaction(intermediate=True)

        deletions = 0

        for ids in ids_per_language:
            translations = {}

            for tm_id in ids:
                tm = TranslationMessage.get(tm_id)
                key = self._getPOTMsgSetTranslationMessageKey(tm)

                if key in translations:
                    language_code = tm.language.code
                    log.info(
                        "Cleaning up identical '%s' message for: \"%s\"" % (
                            language_code, potmsgset.singular_text))

                    existing_tm = translations[key]
                    assert tm != existing_tm, (
                        "Message is duplicate of itself.")
                    assert tm.potmsgset == existing_tm.potmsgset, (
                        "Different potmsgsets considered identical.")
                    assert tm.potemplate == existing_tm.potemplate, (
                        "Different potemplates considered identical.")

                    # Transfer any current/imported flags to the existing
                    # message, and delete the duplicate.
                    bequeathe_flags(tm, existing_tm)
                    deletions += 1
                else:
                    translations[key] = tm

            self.tm.endTransaction(intermediate=True)

        report = "Deleted TranslationMessages: %d" % deletions
        if deletions > 0:
            log.info(report)
        else:
            log.log(DEBUG2, report)

    @staticmethod
    def _findClashes(message, target_potmsgset, target_potemplate):
        """What would clash if we moved `message` to the target environment?

        A clash can be either `message` being current when the target
        environment already has a current message for that language, or
        similar for the message being imported.

        :return: a tuple of a clashing ubuntu message or None, a
            clashing upstream message or None, and a message that is
            identical to the one you passed in, if present.
        """
        clashing_ubuntu = None
        if message.is_current_ubuntu:
            found = target_potmsgset.getCurrentTranslation(
                potemplate=target_potemplate, language=message.language,
                side=TranslationSide.UBUNTU)
            if found is not None and found.potemplate == target_potemplate:
                clashing_ubuntu = found

        clashing_upstream = None
        if message.is_current_upstream:
            found = target_potmsgset.getCurrentTranslation(
                potemplate=target_potemplate, language=message.language,
                side=TranslationSide.UPSTREAM)
            if found is not None and found.potemplate == target_potemplate:
                clashing_upstream = found

        twin = message.findIdenticalMessage(
            target_potmsgset, target_potemplate)

        # Clashes with a twin message are not real clashes: in such cases the
        # message can be merged into the twin without problems.
        return filter_clashes(clashing_ubuntu, clashing_upstream, twin)

    def _saveByDiverging(self, message, target_potmsgset, source_potmsgset):
        """Avoid a TranslationMessage clash during POTMsgSet merge.

        The clash in this case is that we're trying to move `message`
        into a target environment (POTMsgSet and either POTemplate or
        shared status) that already has a current/imported message.

        This function tries to preserve the message for its original
        environment by making it diverged.  If successful, the message
        will become a diverged one for one POTemplate that
        source_potmsgset is linked to, preferring the one it was linked
        to first.
        """
        if message.potemplate is None:
            # This message was shared.  Maybe we can still save it for at
            # least one template by making it diverged.
            target_ttis = source_potmsgset.getAllTranslationTemplateItems()
            target_templates = [tti.potemplate for tti in target_ttis]
            target_templates.sort(
                key=methodcaller('sharingKey'), reverse=True)
            for template in target_templates:
                if self._divergeTo(message, target_potmsgset, template):
                    return True

        # No, there's no place where this message can be preserved.  It'll
        # have to go.
        return False

    @classmethod
    def _divergeTo(cls, message, target_potmsgset, target_potemplate):
        """Attempt to save `message` by diverging to `target_potemplate`.

        :param message: a TranslationMessage to save by diverging.
        :param target_potmsgset: the POTMsgSet that `message` is to be
            attached to.
        :param target_potemplate: a POTemplate that the message might be
            able to diverge to.
        :return: whether a solution was found for this message.  If
            True, you're done with `message`.  If False, you'll have to
            find another place for it.
        """
        clashing_current, clashing_imported, twin = cls._findClashes(
            message, target_potmsgset, target_potemplate)

        if clashing_current is not None or clashing_imported is not None:
            return False

        if twin is None:
            # The message can diverge to this template and keep its
            # flags.
            message.potemplate = target_potemplate
            message.potmsgset = target_potmsgset
        else:
            # This template has an identical message.  All we need to do
            # is transfer the message's current/imported status to it,
            # and we can get rid of the original message.
            bequeathe_flags(message, twin)

        return True


class MergeExistingPackagings(LaunchpadScript):
    """Script to perform translation on existing packagings."""

    def main(self):
        tm = TransactionManager(self.txn, False)
        for packaging in TranslationMerger.findMergeablePackagings():
            log.info('Merging %s/%s and %s/%s.' % (
                packaging.productseries.product.name,
                packaging.productseries.name,
                packaging.sourcepackagename.name,
                packaging.distroseries.name))
            TranslationMerger.mergePackagingTemplates(
                packaging.productseries, packaging.sourcepackagename,
                packaging.distroseries, tm)
            tm.endTransaction(False)
