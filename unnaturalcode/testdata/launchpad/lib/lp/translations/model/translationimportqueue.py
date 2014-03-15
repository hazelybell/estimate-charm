# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'collect_import_info',
    'TranslationImportQueueEntry',
    'TranslationImportQueue',
    ]

from cStringIO import StringIO
import datetime
import logging
from operator import attrgetter
import os.path
import re
import tarfile
from textwrap import dedent

import posixpath
import pytz
from sqlobject import (
    BoolCol,
    ForeignKey,
    SQLObjectNotFound,
    StringCol,
    )
from storm.expr import (
    And,
    Or,
    Select,
    )
from storm.locals import (
    Int,
    Reference,
    )
from zope.component import (
    getUtility,
    queryAdapter,
    )
from zope.interface import implements

from lp.app.errors import NotFoundError
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.app.interfaces.security import IAuthorization
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.person import (
    IPerson,
    validate_person,
    )
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.productseries import IProductSeries
from lp.registry.interfaces.role import IPersonRoles
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.interfaces.sourcepackage import ISourcePackage
from lp.services.database.constants import (
    DEFAULT,
    UTC_NOW,
    )
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import (
    IMasterStore,
    ISlaveStore,
    IStore,
    )
from lp.services.database.sqlbase import (
    cursor,
    quote,
    quote_like,
    SQLBase,
    sqlvalues,
    )
from lp.services.librarian.interfaces.client import ILibrarianClient
from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.translations.enums import RosettaImportStatus
from lp.translations.interfaces.pofile import IPOFileSet
from lp.translations.interfaces.potemplate import (
    IPOTemplate,
    IPOTemplateSet,
    )
from lp.translations.interfaces.translationfileformat import (
    TranslationFileFormat,
    )
from lp.translations.interfaces.translationimporter import (
    ITranslationImporter,
    )
from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    ITranslationImportQueueEntry,
    SpecialTranslationImportTargetFilter,
    translation_import_queue_entry_age,
    TranslationImportQueueConflictError,
    UserCannotSetTranslationImportStatus,
    )
from lp.translations.interfaces.translations import TranslationConstants
from lp.translations.model.approver import TranslationNullApprover
from lp.translations.utilities.gettext_po_importer import GettextPOImporter


def is_gettext_name(path):
    """Does given file name indicate it's in gettext (PO or POT) format?"""
    base_name, extension = os.path.splitext(path)
    return extension in GettextPOImporter().file_extensions


def collect_import_info(queue_entry, imported_object, warnings):
    """Collect basic information about import for feedback to user.

    :return: a dict providing substitutions for various items used in
        generating import notices.
    """
    info = {
        'dateimport': queue_entry.dateimported.strftime('%F %Rz'),
        'elapsedtime': queue_entry.getElapsedTimeText(),
        'file_link': queue_entry.content.http_url,
        'importer': queue_entry.importer.displayname,
        'max_plural_forms': TranslationConstants.MAX_PLURAL_FORMS,
        'warnings': '',
    }

    if IPOTemplate.providedBy(imported_object):
        template = imported_object
    else:
        template = imported_object.potemplate
    info['template'] = template.displayname

    if warnings:
        info['warnings'] = dedent("""
            There were warnings while parsing the file.  These are not
            fatal, but please correct them if you can.

            %s""") % '\n\n'.join(warnings)

    return info


def compose_approval_conflict_notice(domain, templates_count, sample):
    """Create a note to warn about an approval conflict.

    The note warns about the situation where one productseries, or source
    package, or in some cases distroseries has multiple actice templates
    with the same translation domain.

    :param domain: The domain that's causing trouble.
    :param templates_count: The number of clashing templates.
    :param sample: Iterable of matching templates.  Does not need to be
        complete, just enough to report the problem usefully.
    :return: A string describing the problematic clash.
    """
    sample_names = sorted([
        '"%s"' % template.displayname for template in sample])
    if templates_count > len(sample_names):
        sample_names.append("and more (not shown here)")
    return dedent("""\
        Can't auto-approve upload: it is not clear what template it belongs
        to.

        There are %d competing templates with translation domain '%s':
        %s.

        This may mean that Launchpad's auto-approver is looking for the wrong
        domain, or that these templates' domains should be changed, or that
        some of these templates are obsolete and need to be disabled.
        """
        ) % (templates_count, domain, ';\n'.join(sample_names))


class TranslationImportQueueEntry(SQLBase):
    implements(ITranslationImportQueueEntry)

    _table = 'TranslationImportQueueEntry'

    path = StringCol(dbName='path', notNull=True)
    content = ForeignKey(foreignKey='LibraryFileAlias', dbName='content',
        notNull=False)
    importer = ForeignKey(
        dbName='importer', foreignKey='Person',
        storm_validator=validate_person,
        notNull=True)
    dateimported = UtcDateTimeCol(dbName='dateimported', notNull=True,
        default=DEFAULT)
    sourcepackagename_id = Int(name='sourcepackagename', allow_none=True)
    sourcepackagename = Reference(
        sourcepackagename_id, 'SourcePackageName.id')
    distroseries_id = Int(name='distroseries', allow_none=True)
    distroseries = Reference(distroseries_id, 'DistroSeries.id')
    productseries_id = Int(name='productseries', allow_none=True)
    productseries = Reference(productseries_id, 'ProductSeries.id')
    by_maintainer = BoolCol(notNull=True)
    pofile = ForeignKey(foreignKey='POFile', dbName='pofile',
        notNull=False, default=None)
    potemplate = ForeignKey(foreignKey='POTemplate',
        dbName='potemplate', notNull=False, default=None)
    format = EnumCol(dbName='format', schema=TranslationFileFormat,
        default=TranslationFileFormat.PO, notNull=True)
    status = EnumCol(dbName='status', notNull=True,
        schema=RosettaImportStatus, default=RosettaImportStatus.NEEDS_REVIEW)
    date_status_changed = UtcDateTimeCol(dbName='date_status_changed',
        notNull=True, default=DEFAULT)
    error_output = StringCol(notNull=False, default=None)

    @property
    def is_targeted_to_ubuntu(self):
        return (self.distroseries is not None and
            self.distroseries.distribution ==
            getUtility(ILaunchpadCelebrities).ubuntu)

    @property
    def sourcepackage(self):
        """See ITranslationImportQueueEntry."""
        from lp.registry.model.sourcepackage import SourcePackage

        if self.sourcepackagename is None or self.distroseries is None:
            return None

        return SourcePackage(self.sourcepackagename, self.distroseries)

    @property
    def guessed_potemplate(self):
        """See ITranslationImportQueueEntry."""
        importer = getUtility(ITranslationImporter)
        assert importer.isTemplateName(self.path), (
            "We cannot handle file %s here: not a template." % self.path)

        potemplate_set = getUtility(IPOTemplateSet)
        candidate = potemplate_set.getPOTemplateByPathAndOrigin(
            self.path, productseries=self.productseries,
            distroseries=self.distroseries,
            sourcepackagename=self.sourcepackagename)
        if candidate is not None:
            # This takes care of most of the auto-approvable cases.
            return candidate

        directory, filename = os.path.split(self.path)
        if not directory:
            # Uploads don't always have paths associated with them, but
            # there may still be a unique single active template with
            # the right filename.
            subset = potemplate_set.getSubset(
                distroseries=self.distroseries,
                sourcepackagename=self.sourcepackagename,
                productseries=self.productseries, iscurrent=True)
            return subset.findUniquePathlessMatch(filename)

        # I give up.
        return None

    @property
    def _guessed_potemplate_for_pofile_from_path(self):
        """Return an `IPOTemplate` that we think is related to this entry.

        We make this guess by matching the path of the queue entry with those
        of the `IPOTemplate`s for the same product series, or for the same
        distro series and source package name (whichever applies to this
        request).

        So if there is a candidate template in the same directory as the
        request's translation file, and we find no other templates in the same
        directory in the database, we have a winner.
        """
        importer = getUtility(ITranslationImporter)
        potemplateset = getUtility(IPOTemplateSet)
        translationimportqueue = getUtility(ITranslationImportQueue)

        assert importer.isTranslationName(self.path), (
            "We cannot handle file %s here: not a translation." % self.path)

        subset = potemplateset.getSubset(
            distroseries=self.distroseries,
            sourcepackagename=self.sourcepackagename,
            productseries=self.productseries,
            iscurrent=True)
        entry_dirname = os.path.dirname(self.path)
        guessed_potemplate = None
        for potemplate in subset:
            if guessed_potemplate is not None:
                # We already got a winner, should check if we could have
                # another one, which means we cannot be sure which one is the
                # right one.
                if (os.path.dirname(guessed_potemplate.path) ==
                    os.path.dirname(potemplate.path)):
                    # Two matches, cannot be sure which one is the good one.
                    return None
                else:
                    # Current potemplate is in other directory, need to check
                    # the next.
                    continue
            elif entry_dirname == os.path.dirname(potemplate.path):
                # We have a match; we can't stop checking, though, because
                # there may be other matches.
                guessed_potemplate = potemplate

        if guessed_potemplate is None:
            return None

        # We have a winner, but to be 100% sure, we should not have
        # a template file pending or being imported in our queue.
        if self.productseries is None:
            target = self.sourcepackage
        else:
            target = self.productseries

        entries = translationimportqueue.getAllEntries(
            target=target,
            file_extensions=importer.template_suffixes)

        for entry in entries:
            if (os.path.dirname(entry.path) == os.path.dirname(
                guessed_potemplate.path) and
                entry.status not in (
                RosettaImportStatus.IMPORTED, RosettaImportStatus.DELETED)):
                # There is a template entry pending to be imported that has
                # the same path.
                return None

        return guessed_potemplate

    @property
    def _guessed_pofile_from_path(self):
        """Return an IPOFile that we think is related to this entry.

        We get it based on the path it's stored or None.
        """
        pofile_set = getUtility(IPOFileSet)
        return pofile_set.getPOFilesByPathAndOrigin(
            self.path, productseries=self.productseries,
            distroseries=self.distroseries,
            sourcepackagename=self.sourcepackagename,
            ignore_obsolete=True).one()

    def canAdmin(self, roles):
        """See `ITranslationImportQueueEntry`."""
        next_adapter = queryAdapter(self, IAuthorization, 'launchpad.Admin')
        if next_adapter is None:
            return False
        else:
            return next_adapter.checkAuthenticated(roles)

    def canEdit(self, roles):
        """See `ITranslationImportQueueEntry`."""
        next_adapter = queryAdapter(self, IAuthorization, 'launchpad.Edit')
        if next_adapter is None:
            return False
        else:
            return next_adapter.checkAuthenticated(roles)

    def canSetStatus(self, new_status, user):
        """See `ITranslationImportQueueEntry`."""
        if user is None:
            # Anonymous user cannot do anything.
            return False
        roles = IPersonRoles(user)
        if new_status == RosettaImportStatus.APPROVED:
            # Only administrators are able to set the APPROVED status, and
            # that's only possible if we know where to import it
            # (import_into not None).
            return self.canAdmin(roles) and self.import_into is not None
        if new_status == RosettaImportStatus.NEEDS_INFORMATION:
            # Only administrators are able to set the NEEDS_INFORMATION
            # status.
            return self.canAdmin(roles)
        if new_status == RosettaImportStatus.IMPORTED:
            # Only rosetta experts are able to set the IMPORTED status, and
            # that's only possible if we know where to import it
            # (import_into not None).
            return ((roles.in_admin or roles.in_rosetta_experts) and
                    self.import_into is not None)
        if new_status == RosettaImportStatus.FAILED:
            # Only rosetta experts are able to set the FAILED status.
            return roles.in_admin or roles.in_rosetta_experts
        if new_status == RosettaImportStatus.BLOCKED:
            # Importers are not allowed to set BLOCKED
            return self.canAdmin(roles)
        # All other statuses can be set set by all authorized persons.
        return self.canEdit(roles)

    def setStatus(self, new_status, user):
        """See `ITranslationImportQueueEntry`."""
        if not self.canSetStatus(new_status, user):
            raise UserCannotSetTranslationImportStatus()
        self.status = new_status
        self.date_status_changed = UTC_NOW

    def setErrorOutput(self, output):
        """See `ITranslationImportQueueEntry`."""
        self.error_output = output

    def addWarningOutput(self, output):
        """See `ITranslationImportQueueEntry`."""
        # Very crude implementation: if there is no error output, and
        # there is warning output, set error_output to the warning text.
        # Otherwise, merely keep whatever error_output there already is.
        if output and not self.error_output:
            self.setErrorOutput(output)

    def _findCustomLanguageCode(self, language_code):
        """Find applicable custom language code, if any."""
        if self.distroseries is not None:
            target = self.distroseries.distribution.getSourcePackage(
                self.sourcepackagename)
        else:
            target = self.productseries.product

        return target.getCustomLanguageCode(language_code)

    def _guessLanguage(self):
        """See ITranslationImportQueueEntry."""
        importer = getUtility(ITranslationImporter)
        if not importer.isTranslationName(self.path):
            # This does not look like the name of a translation file.
            return None
        filename = os.path.basename(self.path)
        language_code, file_ext = os.path.splitext(filename)

        custom_language_code = self._findCustomLanguageCode(language_code)
        if custom_language_code:
            if custom_language_code.language is None:
                language_code = None
            else:
                language_code = custom_language_code.language.code

        return language_code

    @property
    def import_into(self):
        """See ITranslationImportQueueEntry."""
        importer = getUtility(ITranslationImporter)
        if self.pofile is not None:
            # The entry has an IPOFile associated where it should be imported.
            return self.pofile
        elif (self.potemplate is not None and
              importer.isTemplateName(self.path)):
            # The entry has an IPOTemplate associated where it should be
            # imported.
            return self.potemplate
        else:
            # We don't know where this entry should be imported.
            return None

    def reportApprovalConflict(self, domain, templates_count, sample):
        """Report an approval conflict."""
        # Not sending out email for now; just tack a notice onto the
        # queue entry where the user can find it through the queue UI.
        notice = compose_approval_conflict_notice(
            domain, templates_count, sample)
        if notice != self.error_output:
            self.setErrorOutput(notice)

    def matchPOTemplateByDomain(self, domain, sourcepackagename=None):
        """Attempt to find the one matching template, by domain.

        Looks within the context of the queue entry.  If multiple templates
        match, reports an approval conflict.

        :param domain: Translation domain to look for.
        :param sourcepackagename: Optional `SourcePackageName` to look for.
            If not given, source package name is not considered in the
            search.
        :return: A single `POTemplate`, or None.
        """
        potemplateset = getUtility(IPOTemplateSet)
        subset = potemplateset.getSubset(
            productseries=self.productseries, distroseries=self.distroseries,
            sourcepackagename=sourcepackagename, iscurrent=True)
        templates_query = subset.getPOTemplatesByTranslationDomain(domain)

        # Get a limited sample of the templates.  All we need from the
        # sample is (1) to detect the presence or more than one match,
        # and (2) to report a helpful sampling of the problem.
        samples = list(templates_query[:5])

        if len(samples) == 0:
            # No matches found, sorry.
            return None
        elif len(samples) == 1:
            # Found the one template we're looking for.
            return samples[0]
        else:
            # There's a conflict.  Report the real number of competing
            # templates, plus a sampling of template names.
            self.reportApprovalConflict(
                domain, templates_query.count(), samples)
            return None

    def _get_pofile_from_language(self, lang_code, translation_domain,
        sourcepackagename=None):
        """Return an IPOFile for the given language and domain.

        :arg lang_code: The language code we are interested on.
        :arg translation_domain: The translation domain for the given
            language.
        :arg sourcepackagename: The ISourcePackageName that uses this
            translation or None if we don't know it.
        """
        assert (lang_code is not None and translation_domain is not None), (
            "lang_code and translation_domain cannot be None")

        language_set = getUtility(ILanguageSet)
        language = language_set.getLanguageByCode(lang_code)

        if language is None or not language.visible:
            # Either we don't know the language or the language is hidden by
            # default what means that we got a bad import and that should be
            # reviewed by someone before importing. The 'visible' check is to
            # prevent the import of languages like 'es_ES' or 'fr_FR' instead
            # of just 'es' or 'fr'.
            return None

        # Normally we find the translation's template in the
        # source package or productseries where the translation was
        # uploaded.  Exactly one template should have the domain we're
        # looking for.
        potemplate = self.matchPOTemplateByDomain(
            translation_domain, sourcepackagename=self.sourcepackagename)

        is_for_distro = self.distroseries is not None
        know_package = (
            sourcepackagename is not None and
            self.sourcepackagename is not None and
            self.sourcepackagename.name == sourcepackagename.name)

        if potemplate is None and is_for_distro and not know_package:
            # This translation was uploaded to a source package, but the
            # package does not have the matching template.  Try finding
            # it elsewhere in the distribution.
            potemplate = self.matchPOTemplateByDomain(translation_domain)

        if potemplate is None:
            # The potemplate is not yet imported; we cannot attach this
            # translation file.
            return None

        # Get or create an IPOFile based on the info we guess.
        pofile = potemplate.getPOFileByLang(language.code)
        if pofile is None:
            pofile = potemplate.newPOFile(language.code)
            if pofile.canEditTranslations(self.importer):
                pofile.owner = self.importer

        if self.by_maintainer:
            # This was uploaded by the maintainer, which means that the path
            # we got is exactly the right one. If it's different from what
            # pofile has, that would mean that either the entry changed its
            # path since previous upload or that we had to guess it and now
            # that we got the right path, we should fix it.
            pofile.setPathIfUnique(self.path)

        if (sourcepackagename is None and
            potemplate.sourcepackagename is not None):
            # We didn't know the sourcepackagename when we called this method,
            # but now we know it.
            sourcepackagename = potemplate.sourcepackagename

        if (self.sourcepackagename is not None and
            self.sourcepackagename.name != sourcepackagename.name):
            # We need to note the sourcepackagename from where this entry came
            # because it's different from the place where we are going to
            # import it.
            pofile.from_sourcepackagename = self.sourcepackagename

        return pofile

    def getGuessedPOFile(self):
        """See `ITranslationImportQueueEntry`."""
        importer = getUtility(ITranslationImporter)
        assert importer.isTranslationName(self.path), (
            "We cannot handle file %s here: not a translation." % self.path)

        if self.potemplate is None:
            # We don't have the IPOTemplate object associated with this entry.
            # Try to guess it from the file path.
            pofile = self._guessed_pofile_from_path
            if pofile is not None:
                # We were able to guess an IPOFile.
                return pofile

            # Multi-directory trees layout are non-standard layouts of gettext
            # files where the .pot file and its .po files are stored in
            # different directories.
            if is_gettext_name(self.path):
                pofile = self._guess_multiple_directories_with_pofile()
                if pofile is not None:
                    # This entry is fits our multi directory trees layout and
                    # we found a place where it should be imported.
                    return pofile

            # We were not able to find an IPOFile based on the path, try
            # to guess an IPOTemplate before giving up.
            potemplate = self._guessed_potemplate_for_pofile_from_path
            if potemplate is None:
                # No way to guess anything...
                return None

            existing_entry = TranslationImportQueueEntry.selectOneBy(
                importer=self.importer, path=self.path, potemplate=potemplate,
                distroseries=self.distroseries,
                sourcepackagename=self.sourcepackagename,
                productseries=self.productseries)
            if existing_entry is not None:
                warning = ("%s: can't approve entry %d ('%s') "
                           "because entry %d is in the way." % (
                               potemplate.title, self.id, self.path,
                               existing_entry.id))
                logging.warn(warning)
                return None

            # We got the potemplate, try to guess the language from
            # the info we have.
            self.potemplate = potemplate

        # We know the IPOTemplate associated with this entry so we can try to
        # detect the right IPOFile.
        # Let's try to guess the language.
        guessed_language = self._guessLanguage()
        if guessed_language is None:
            # Custom language code says to ignore imports with this language
            # code.
            self.setStatus(RosettaImportStatus.DELETED,
                           getUtility(ILaunchpadCelebrities).rosetta_experts)
            return None
        elif guessed_language == '':
            # We don't recognize this as a translation file with a name
            # consisting of language code and format extension.  Look for an
            # existing translation file based on path match.
            return self._guessed_pofile_from_path
        else:
            return self._get_pofile_from_language(guessed_language,
                self.potemplate.translation_domain,
                sourcepackagename=self.potemplate.sourcepackagename)

    def _guess_multiple_directories_with_pofile(self):
        """Return `IPOFile` that we think is related to this entry, or None.

        Multi-directory tree layouts are non-standard layouts where the .pot
        file and its .po files are stored in different directories.  We only
        know of this happening with gettext files.

        The known layouts are:

        DIRECTORY/TRANSLATION_DOMAIN.pot
        DIRECTORY/LANG_CODE/TRANSLATION_DOMAIN.po

        or

        DIRECTORY/TRANSLATION_DOMAIN.pot
        DIRECTORY/LANG_CODE/messages/TRANSLATION_DOMAIN.po

        or

        DIRECTORY/TRANSLATION_DOMAIN.pot
        DIRECTORY/LANG_CODE/LC_MESSAGES/TRANSLATION_DOMAIN.po

        or

        DIRECTORY/TRANSLATION_DOMAIN.pot
        DIRECTORY/LANG_CODE/LANG_CODE.po

        where DIRECTORY would be any path, even '', LANG_CODE is a language
        code and TRANSLATION_DOMAIN the translation domain is the one used for
        that .po file.

        If this isn't enough, there are some packages that have a non standard
        layout where the .pot files are stored inside the sourcepackage with
        the binaries that will use it and the translations are stored in
        external packages following the same language pack ideas that we use
        with Ubuntu.

        This layout breaks completely Rosetta because we don't have a way
        to link the .po and .pot files coming from different packages. The
        solution we take is to look for the translation domain across the
        whole distro series. In the concrete case of KDE language packs, they
        have the sourcepackagename following the pattern 'kde-i18n-LANGCODE'
        (KDE3) or kde-l10n-LANGCODE (KDE4).
        """
        # Recognize "kde-i18n-LANGCODE" and "kde-l10n-LANGCODE" as
        # special cases.
        kde_prefix_pattern = '^kde-(i18n|l10n)-'

        importer = getUtility(ITranslationImporter)

        assert is_gettext_name(self.path), (
            "We cannot handle file %s here: not a gettext file." % self.path)
        assert importer.isTranslationName(self.path), (
            "We cannot handle file %s here: not a translation." % self.path)

        if self.productseries is not None:
            # This method only works for sourcepackages. It makes no sense use
            # it with productseries.
            return None

        if re.match(kde_prefix_pattern, self.sourcepackagename.name):
            # We need to extract the language information from the package
            # name

            # These language codes have special meanings.
            lang_mapping = {
                'ca-valencia': 'ca@valencia',
                'engb': 'en_GB',
                'ptbr': 'pt_BR',
                'srlatn': 'sr@Latn',
                'sr-latin': 'sr@latin',
                'zhcn': 'zh_CN',
                'zhtw': 'zh_TW',
                }

            lang_code = re.sub(
                kde_prefix_pattern, '', self.sourcepackagename.name)

            path_components = os.path.normpath(self.path).split(os.path.sep)
            # Top-level directory (path_components[0]) is something like
            # "source" or "messages", and only then comes the
            # language code: we generalize it so it supports language code
            # in any part of the path.
            for path_component in path_components:
                if path_component.startswith(lang_code + '@'):
                    # There are language variants inside a language pack.
                    lang_code = path_component
                    break
            lang_code = lang_mapping.get(lang_code, lang_code)
        elif (self.sourcepackagename.name == 'koffice-l10n' and
              self.path.startswith('koffice-i18n-')):
            # This package has the language information included as part of a
            # directory: koffice-i18n-LANG_CODE-VERSION
            # Extract the language information.
            match = re.match('koffice-i18n-(\S+)-(\S+)', self.path)
            if match is None:
                # No idea what to do with this.
                return None
            lang_code = match.group(1)
        else:
            # In this case, we try to get the language information from the
            # path name.
            dir_path = os.path.dirname(self.path)
            dir_name = os.path.basename(dir_path)

            if dir_name == 'messages' or dir_name == 'LC_MESSAGES':
                # We have another directory between the language code
                # directory and the filename (second and third case).
                dir_path = os.path.dirname(dir_path)
                lang_code = os.path.basename(dir_path)
            else:
                # The .po file is stored inside the directory with the
                # language code as its name or an unsupported layout.
                lang_code = dir_name

            if lang_code is None:
                return None

        basename = os.path.basename(self.path)
        filename, file_ext = os.path.splitext(basename)

        # Let's check if whether the filename is a valid language.
        language_set = getUtility(ILanguageSet)
        language = language_set.getLanguageByCode(filename)

        if language is None:
            # The filename is not a valid language, so let's try it as a
            # translation domain.
            translation_domain = filename
        elif filename == lang_code:
            # The filename is a valid language so we need to look for the
            # template nearest to this pofile to link with it.
            potemplateset = getUtility(IPOTemplateSet)
            potemplate_subset = potemplateset.getSubset(
                distroseries=self.distroseries,
                sourcepackagename=self.sourcepackagename)
            potemplate = potemplate_subset.getClosestPOTemplate(self.path)
            if potemplate is None:
                # We were not able to find such template, someone should
                # review it manually.
                return None
            translation_domain = potemplate.translation_domain
        else:
            # The guessed language from the directory doesn't match the
            # language from the filename. Leave it for an admin.
            return None

        if (self.sourcepackagename.name in ('k3b-i18n', 'koffice-l10n') or
            re.match(kde_prefix_pattern, self.sourcepackagename.name)):
            # K3b and official KDE packages store translations and code in
            # different packages, so we don't know the sourcepackagename that
            # use the translations.
            return self._get_pofile_from_language(
                lang_code, translation_domain)
        else:
            # We assume that translations and code are together in the same
            # package.
            return self._get_pofile_from_language(
                lang_code, translation_domain,
                sourcepackagename=self.sourcepackagename)

    def getFileContent(self):
        """See ITranslationImportQueueEntry."""
        client = getUtility(ILibrarianClient)
        return client.getFileByAlias(self.content.id).read()

    def getTemplatesOnSameDirectory(self):
        """See ITranslationImportQueueEntry."""
        importer = getUtility(ITranslationImporter)
        path = os.path.dirname(self.path)

        suffix_clauses = [
            "path LIKE '%%' || %s" % quote_like(suffix)
            for suffix in importer.template_suffixes]

        clauses = [
            "path LIKE %s || '%%'" % quote_like(path),
            "id <> %s" % quote(self.id),
            "(%s)" % " OR ".join(suffix_clauses)]

        if self.distroseries is not None:
            clauses.append('distroseries = %s' % quote(self.distroseries))
        if self.sourcepackagename is not None:
            clauses.append(
                'sourcepackagename = %s' % quote(self.sourcepackagename))
        if self.productseries is not None:
            clauses.append("productseries = %s" % quote(self.productseries))

        return TranslationImportQueueEntry.select(" AND ".join(clauses))

    def getElapsedTimeText(self):
        """See ITranslationImportQueue."""
        UTC = pytz.timezone('UTC')
        # XXX: Carlos Perello Marin 2005-06-29: This code should be using the
        # solution defined by PresentingLengthsOfTime spec when it's
        # implemented.
        elapsedtime = (
            datetime.datetime.now(UTC) - self.dateimported)
        elapsedtime_text = ''
        hours = elapsedtime.seconds / 3600
        minutes = (elapsedtime.seconds % 3600) / 60
        if elapsedtime.days > 0:
            elapsedtime_text += '%d days ' % elapsedtime.days
        if hours > 0:
            elapsedtime_text += '%d hours ' % hours
        if minutes > 0:
            elapsedtime_text += '%d minutes ' % minutes

        if len(elapsedtime_text) > 0:
            elapsedtime_text += 'ago'
        else:
            elapsedtime_text = 'just requested'

        return elapsedtime_text


def list_product_request_targets(user, status_condition):
    """Return list of Products with import queue entries.

    :param status_condition: Storm conditional restricting the
        queue-entry status to look for.
    :return: A list of `Product`, distinct and ordered by name.
    """
    # Avoid circular imports.
    from lp.registry.model.product import Product, ProductSet
    from lp.registry.model.productseries import ProductSeries

    privacy_filter = ProductSet.getProductPrivacyFilter(user)

    products = IStore(Product).find(
        Product,
        Product.id == ProductSeries.productID,
        Product.active == True,
        ProductSeries.id.is_in(Select(
            TranslationImportQueueEntry.productseries_id,
            And(
                TranslationImportQueueEntry.productseries_id != None,
                status_condition),
            distinct=True)),
        privacy_filter)

    # Products may occur multiple times due to the join with
    # ProductSeries.
    products = products.config(distinct=True)

    # Sort python-side; doing it in SQL conflicts with the
    # "distinct."
    return sorted(products, key=attrgetter('name'))


def list_distroseries_request_targets(status_condition):
    """Return list of DistroSeries with import queue entries.

    :param status_condition: Storm conditional restricting the
        queue-entry status to look for.
    :return: A list of `DistroSeries`, distinct and ordered by
        (`Distribution.name`, `DistroSeries.name`).
    """
    # Avoid circular imports.
    from lp.registry.model.distribution import Distribution
    from lp.registry.model.distroseries import DistroSeries

    # DistroSeries with queue entries.
    distroseries = IStore(DistroSeries).find(
        DistroSeries,
        DistroSeries.defer_translation_imports == False,
        Distribution.id == DistroSeries.distributionID,
        DistroSeries.id.is_in(Select(
            TranslationImportQueueEntry.distroseries_id,
            And(
                TranslationImportQueueEntry.distroseries_id != None,
                status_condition),
            distinct=True)))
    distroseries = distroseries.order_by(Distribution.name, DistroSeries.name)
    return list(distroseries)


class TranslationImportQueue:
    implements(ITranslationImportQueue)

    def __iter__(self):
        """See ITranslationImportQueue."""
        return iter(self.getAllEntries())

    def __getitem__(self, id):
        """See ITranslationImportQueue."""
        try:
            idnumber = int(id)
        except ValueError:
            raise NotFoundError(id)

        entry = self.get(idnumber)

        if entry is None:
            # The requested entry does not exist.
            raise NotFoundError(str(id))

        return entry

    def countEntries(self):
        """See `ITranslationImportQueue`."""
        return TranslationImportQueueEntry.select().count()

    def _iterNeedsReview(self):
        """Iterate over all entries in the queue that need review."""
        return iter(TranslationImportQueueEntry.selectBy(
            status=RosettaImportStatus.NEEDS_REVIEW,
            orderBy=['dateimported']))

    def _getMatchingEntry(self, path, importer, potemplate, pofile,
                           sourcepackagename, distroseries, productseries):
        """Find an entry that best matches the given parameters, if such an
        entry exists.

        When the user uploads a file, we need to figure out whether to update
        an existing entry or create a new one.  There may be zero, one, or
        multiple entries that match the new upload.  If it's more than one,
        that will be because one matching entry is more specific than the
        other.  'More specific' refers to how well the import location has
        been specified for this entry.  There are three cases, ordered from
        least specific to most specific:

        1. potemplate and pofile are None,
        2. potemplate is not None but pofile is None,
        3. potemplate and pofile are both not None.

        If no exactly matching entry can be found, the next more specific
        entry is chosen, if it exists. If there is more than one such entry,
        there is no best choice and `TranslationImportQueueConflictError`
        is raised.

        :return: The matching entry or None, if no matching entry was found
            at all."""

        # We disallow entries with the identical path, importer, potemplate
        # and target (eg. productseries or distroseries/sourcepackagename).
        clauses = [
            TranslationImportQueueEntry.path == path,
            TranslationImportQueueEntry.importer == importer,
            ]
        if potemplate is not None:
            clauses.append(
                TranslationImportQueueEntry.potemplate == potemplate)
        if pofile is not None:
            clauses.append(Or(
                TranslationImportQueueEntry.pofile == pofile,
                TranslationImportQueueEntry.pofile == None))
        if productseries is None:
            assert sourcepackagename is not None and distroseries is not None
            clauses.extend([
                (TranslationImportQueueEntry.distroseries_id ==
                 distroseries.id),
                (TranslationImportQueueEntry.sourcepackagename_id ==
                 sourcepackagename.id),
                ])
        else:
            clauses.append(
                TranslationImportQueueEntry.productseries_id ==
                productseries.id)
        store = IMasterStore(TranslationImportQueueEntry)
        entries = store.find(
            TranslationImportQueueEntry, *clauses)
        entries = list(
            entries.order_by(
                ['pofile is null desc', 'potemplate is null desc']))
        count = len(entries)

        # Deal with the simple cases.
        if count == 0:
            return None
        if count == 1:
            return entries[0]

        # Check that the top two entries differ in levels of specificity.
        # Other entries don't matter because they are either of the same
        # or even greater specificity, as specified in the query.
        pofile_specificity_is_equal = (
            (entries[0].pofile is None) == (entries[1].pofile is None))
        potemplate_specificity_is_equal = (
            (entries[0].potemplate is None) ==
            (entries[1].potemplate is None))
        if pofile_specificity_is_equal and potemplate_specificity_is_equal:
            raise TranslationImportQueueConflictError

        return entries[0]

    def _getFormatAndImporter(self, filename, content, format=None):
        """Get the appropriate format and importer for this upload.

        :param filename: Name of the uploaded file.
        :param content: Contents of the uploaded file.
        :param format: Optional hard choice of format.  If none is
            given, a format will be divined from the file's name and
            contents.
        :return: a tuple of the selected format and its importer.
        """
        if format is None:
            root, ext = os.path.splitext(filename)
            translation_importer = getUtility(ITranslationImporter)
            format = translation_importer.getTranslationFileFormat(
                ext, content)

        translation_importer = getUtility(ITranslationImporter)
        return (
            format, translation_importer.getTranslationFormatImporter(format))

    def addOrUpdateEntry(self, path, content, by_maintainer, importer,
                         sourcepackagename=None, distroseries=None,
                         productseries=None, potemplate=None, pofile=None,
                         format=None):
        """See `ITranslationImportQueue`."""
        assert (distroseries is None) != (productseries is None), (
            "An upload must be for a productseries or a distroseries.  "
            "This one has either neither or both.")
        assert productseries is None or sourcepackagename is None, (
            "Can't upload to a sourcepackagename in a productseries.")
        assert content is not None and content != '', "Upload has no content."
        assert path is not None and path != '', "Upload has no path."

        filename = os.path.basename(path)
        format, format_importer = self._getFormatAndImporter(
            filename, content, format=format)

        # Upload the file into librarian.
        size = len(content)
        file = StringIO(content)
        client = getUtility(ILibrarianClient)
        alias = client.addFile(
            name=filename, size=size, file=file,
            contentType=format_importer.content_type)

        try:
            entry = self._getMatchingEntry(path, importer, potemplate,
                    pofile, sourcepackagename, distroseries, productseries)
        except TranslationImportQueueConflictError:
            return None

        if entry is None:
            # It's a new row.
            entry = TranslationImportQueueEntry(path=path, content=alias,
                importer=importer, sourcepackagename=sourcepackagename,
                distroseries=distroseries, productseries=productseries,
                by_maintainer=by_maintainer, potemplate=potemplate,
                pofile=pofile, format=format)
        else:
            # It's an update.
            entry.setErrorOutput(None)
            entry.content = alias
            entry.by_maintainer = by_maintainer
            if potemplate is not None:
                # Only set the linked IPOTemplate object if it's not None.
                entry.potemplate = potemplate

            if pofile is not None:
                # Set always the IPOFile link if we know it.
                entry.pofile = pofile

            if entry.status == RosettaImportStatus.IMPORTED:
                # The entry was already imported, so we need to update its
                # dateimported field so it doesn't get preference over old
                # entries.
                entry.dateimported = UTC_NOW

            if (entry.status == RosettaImportStatus.DELETED or
                entry.status == RosettaImportStatus.FAILED or
                entry.status == RosettaImportStatus.IMPORTED):
                # We got an update for this entry. If the previous import is
                # deleted or failed or was already imported we should retry
                # the import now, just in case it can be imported now.
                entry.setStatus(RosettaImportStatus.NEEDS_REVIEW, importer)

            entry.date_status_changed = UTC_NOW
            entry.format = format
            entry.sync()

        return entry

    def _iterTarballFiles(self, tarball):
        """Iterate through all non-emtpy files in the tarball."""
        for tarinfo in tarball:
            if tarinfo.isfile() and tarinfo.size > 0:
                # Don't be tricked into reading directories, symlinks,
                # or worst of all: devices.
                yield tarinfo.name

    def _makePath(self, name, path_filter):
        """Make the file path from the name stored in the tarball."""
        path = posixpath.normpath(name).lstrip('/')
        if path_filter:
            path = path_filter(path)
        return path

    def _isTranslationFile(self, path, only_templates):
        """Is this a translation file that should be uploaded?"""
        if path is None or path == '':
            return False

        translation_importer = getUtility(ITranslationImporter)
        if translation_importer.isHidden(path):
            # Dotfile.  Probably an editor backup or somesuch.
            return False

        base, ext = posixpath.splitext(path)
        if ext not in translation_importer.supported_file_extensions:
            # Doesn't look like a supported translation file type.
            return False

        if only_templates and not translation_importer.isTemplateName(path):
            return False

        return True

    def addOrUpdateEntriesFromTarball(self, content, by_maintainer, importer,
        sourcepackagename=None, distroseries=None, productseries=None,
        potemplate=None, filename_filter=None, approver_factory=None,
        only_templates=False):
        """See ITranslationImportQueue."""
        num_files = 0
        conflict_files = []

        tarball_io = StringIO(content)
        try:
            tarball = tarfile.open('', 'r|*', tarball_io)
        except (tarfile.CompressionError, tarfile.ReadError):
            # If something went wrong with the tarfile, assume it's
            # busted and let the user deal with it.
            return (num_files, conflict_files)

        # Build a list of files to upload.
        upload_files = {}
        for name in self._iterTarballFiles(tarball):
            path = self._makePath(name, filename_filter)
            if self._isTranslationFile(path, only_templates):
                upload_files[name] = path
        tarball.close()

        if approver_factory is None:
            approver_factory = TranslationNullApprover
        approver = approver_factory(
            upload_files.values(),
            productseries=productseries,
            distroseries=distroseries, sourcepackagename=sourcepackagename)

        # Re-opening because we are using sequential access ("r|*") which is
        # so much faster.
        tarball_io.seek(0)
        tarball = tarfile.open('', 'r|*', tarball_io)
        for tarinfo in tarball:
            if tarinfo.name not in upload_files:
                continue
            file_content = tarball.extractfile(tarinfo).read()

            path = upload_files[tarinfo.name]
            entry = approver.approve(self.addOrUpdateEntry(
                path, file_content, by_maintainer, importer,
                sourcepackagename=sourcepackagename,
                distroseries=distroseries, productseries=productseries,
                potemplate=potemplate))
            if entry == None:
                conflict_files.append(path)
            else:
                num_files += 1

        tarball.close()

        return (num_files, conflict_files)

    def get(self, id):
        """See ITranslationImportQueue."""
        try:
            return TranslationImportQueueEntry.get(id)
        except SQLObjectNotFound:
            return None

    def _getQueryByFiltering(self, target=None, status=None,
                             file_extensions=None):
        """See `ITranslationImportQueue.`"""
        queries = ["TRUE"]
        clause_tables = []
        if target is not None:
            if IPerson.providedBy(target):
                queries.append('importer = %s' % sqlvalues(target))
            elif IProduct.providedBy(target):
                queries.append('productseries = ProductSeries.id')
                queries.append(
                    'ProductSeries.product = %s' % sqlvalues(target))
                clause_tables.append('ProductSeries')
            elif IProductSeries.providedBy(target):
                queries.append('productseries = %s' % sqlvalues(target))
            elif IDistribution.providedBy(target):
                queries.append('distroseries = DistroSeries.id')
                queries.append(
                    'DistroSeries.distribution = %s' % sqlvalues(target))
                clause_tables.append('DistroSeries')
            elif IDistroSeries.providedBy(target):
                queries.append('distroseries = %s' % sqlvalues(target))
            elif ISourcePackage.providedBy(target):
                queries.append(
                    'distroseries = %s' % sqlvalues(target.distroseries))
                queries.append(
                    'sourcepackagename = %s' % sqlvalues(
                        target.sourcepackagename))
            elif target == SpecialTranslationImportTargetFilter.PRODUCT:
                queries.append('productseries IS NOT NULL')
            elif target == SpecialTranslationImportTargetFilter.DISTRIBUTION:
                queries.append('distroseries IS NOT NULL')
            else:
                raise AssertionError(
                    'Target argument must be one of IPerson, IProduct,'
                    ' IProductSeries, IDistribution, IDistroSeries or'
                    ' ISourcePackage')
        if status is not None:
            queries.append(
                'TranslationImportQueueEntry.status = %s' % sqlvalues(status))
        if file_extensions:
            extension_clauses = [
                "path LIKE '%%' || %s" % quote_like(extension)
                for extension in file_extensions]
            queries.append("(%s)" % " OR ".join(extension_clauses))

        return queries, clause_tables

    def getAllEntries(self, target=None, import_status=None,
                      file_extensions=None):
        """See ITranslationImportQueue."""
        queries, clause_tables = self._getQueryByFiltering(
            target, import_status, file_extensions)
        return TranslationImportQueueEntry.select(
            " AND ".join(queries), clauseTables=clause_tables,
            orderBy=['status', 'dateimported', 'id'])

    def getFirstEntryToImport(self, target=None):
        """See ITranslationImportQueue."""
        # Prepare the query to get only APPROVED entries.
        queries, clause_tables = self._getQueryByFiltering(
            target, status=RosettaImportStatus.APPROVED)

        if (IDistribution.providedBy(target) or
            IDistroSeries.providedBy(target) or
            ISourcePackage.providedBy(target)):
            # If the Distribution series has actived the option to defer
            # translation imports, we ignore those entries.
            if 'DistroSeries' not in clause_tables:
                clause_tables.append('DistroSeries')
                queries.append('distroseries = DistroSeries.id')

            queries.append('DistroSeries.defer_translation_imports IS FALSE')

        return TranslationImportQueueEntry.selectFirst(
            " AND ".join(queries), clauseTables=clause_tables,
            orderBy=['dateimported'])

    def getRequestTargets(self, user, status=None):
        """See `ITranslationImportQueue`."""

        if status is None:
            status_clause = True
        else:
            status_clause = (TranslationImportQueueEntry.status == status)

        distroseries = list_distroseries_request_targets(status_clause)
        products = list_product_request_targets(user, status_clause)

        return distroseries + products

    def _attemptToSet(self, entry, potemplate=None, pofile=None):
        """Set potemplate or pofile on a `TranslationImportQueueEntry`.

        This will do nothing if setting potemplate or pofile would clash
        with another entry.
        """
        if potemplate == entry.potemplate and pofile == entry.pofile:
            # Nothing to do here.
            return False

        existing_entry = self._getMatchingEntry(
            entry.path, entry.importer, potemplate, pofile,
            entry.sourcepackagename, entry.distroseries, entry.productseries)

        if existing_entry is None or existing_entry == entry:
            entry.potemplate = potemplate
            entry.pofile = pofile

    def _attemptToApprove(self, entry):
        """Attempt to approve one queue entry."""
        if entry.status != RosettaImportStatus.NEEDS_REVIEW:
            return False

        if entry.import_into is None:
            # We don't have a place to import this entry. Try to guess it.
            importer = getUtility(ITranslationImporter)
            if importer.isTranslationName(entry.path):
                potemplate = entry.potemplate
                pofile = entry.getGuessedPOFile()
            else:
                # It's a template.
                # Check if we can guess where it should be imported.
                potemplate = entry.guessed_potemplate
                pofile = entry.pofile

            self._attemptToSet(entry, potemplate=potemplate, pofile=pofile)

        if entry.import_into is None:
            # Still no dice.
            return False

        # Yay!  We have a POTemplate or POFile to import this entry
        # into.  Approve.
        entry.setStatus(
            RosettaImportStatus.APPROVED,
            getUtility(ILaunchpadCelebrities).rosetta_experts)
        entry.setErrorOutput(None)

        return True

    def executeOptimisticApprovals(self, txn=None):
        """See `ITranslationImportQueue`."""
        approved_entries = False
        for entry in self._iterNeedsReview():
            success = self._attemptToApprove(entry)
            if success:
                approved_entries = True
            if txn is not None:
                txn.commit()

        return approved_entries

    def _getSlaveStore(self):
        """Return the slave store for the import queue.

        Tests can override this to avoid unnecessary synchronization
        issues.
        """
        return ISlaveStore(TranslationImportQueueEntry)

    def _getBlockableDirectories(self):
        """Describe all directories where uploads are to be blocked.

        Returns a set of tuples, each containing:
         * `DistroSeries` id
         * `SourcePackageName` id
         * `ProductSeries` id
         * Directory path.

        A `TranslationImportQueueEntry` should be blocked if the tuple
        of its distroseries.id, sourcepackagename.id, productseries.id,
        and the directory component of its path is found in the result
        set.

        See `_isBlockable`, which matches a queue entry against the set
        returned by this method.
        """
        importer = getUtility(ITranslationImporter)
        template_patterns = "(%s)" % ' OR '.join([
            "path LIKE ('%%' || %s)" % quote_like(suffix)
            for suffix in importer.template_suffixes])

        store = self._getSlaveStore()
        result = store.execute("""
            SELECT
                distroseries,
                sourcepackagename,
                productseries,
                regexp_replace(
                    regexp_replace(path, '^[^/]*$', ''),
                    '/[^/]*$',
                    '') AS directory
            FROM TranslationImportQueueEntry
            WHERE %(is_template)s
            GROUP BY distroseries, sourcepackagename, productseries, directory
            HAVING bool_and(status = %(blocked)s)
            ORDER BY distroseries, sourcepackagename, productseries, directory
            """ % {
                'blocked': quote(RosettaImportStatus.BLOCKED),
                'is_template': template_patterns,
            })

        return set(result)

    def _isBlockable(self, entry, blocklist):
        """Is `entry` one that should be blocked according to `blocklist`?

        :param entry: A `TranslationImportQueueEntry` that may be a
            candidate for blocking.
        :param blocklist: A description of blockable directories as
            returned by `_getBlockableDirectories`.
        """
        description = (
            entry.distroseries_id,
            entry.sourcepackagename_id,
            entry.productseries_id,
            os.path.dirname(entry.path),
            )
        return description in blocklist

    def executeOptimisticBlock(self, txn=None):
        """See ITranslationImportQueue."""
        # Find entries where all template entries for the same
        # translation target that are in the same directory are in the
        # Blocked state.  Set those entries to Blocked as well.
        blocklist = self._getBlockableDirectories()
        num_blocked = 0
        for entry in self._iterNeedsReview():
            if self._isBlockable(entry, blocklist):
                # All templates on the same directory as this entry are
                # blocked, so we can block it too.
                entry.setStatus(
                    RosettaImportStatus.BLOCKED,
                    getUtility(ILaunchpadCelebrities).rosetta_experts)
                num_blocked += 1
                if txn is not None:
                    txn.commit()

        return num_blocked

    def _cleanUpObsoleteEntries(self, store):
        """Delete obsolete queue entries.

        :param store: The Store to delete from.
        :return: Number of entries deleted.
        """
        now = datetime.datetime.now(pytz.UTC)
        deletion_clauses = []
        for status, max_age in translation_import_queue_entry_age.iteritems():
            cutoff = now - max_age
            deletion_clauses.append(And(
                TranslationImportQueueEntry.status == status,
                TranslationImportQueueEntry.date_status_changed < cutoff))

        # Also clean out Blocked PO files for Ubuntu that haven't been
        # touched for a year.  Keep blocked templates because they may
        # determine the blocking of future translation uploads.
        blocked_cutoff = now - datetime.timedelta(days=365)
        deletion_clauses.append(And(
            TranslationImportQueueEntry.distroseries_id != None,
            TranslationImportQueueEntry.date_status_changed < blocked_cutoff,
            TranslationImportQueueEntry.path.like(u'%.po')))

        entries = store.find(
            TranslationImportQueueEntry, Or(*deletion_clauses))

        return entries.remove()

    def _cleanUpInactiveProductEntries(self, store):
        """Delete queue entries for deactivated `Product`s.

        :param store: The Store to delete from.
        :return: Number of entries deleted.
        """
        # XXX JeroenVermeulen 2009-09-18 bug=271938: Stormify this once
        # the Storm remove() syntax starts working properly for joins.
        cur = cursor()
        cur.execute("""
            DELETE FROM TranslationImportQueueEntry AS Entry
            USING ProductSeries, Product
            WHERE
                ProductSeries.id = Entry.productseries AND
                Product.id = ProductSeries.product AND
                Product.active IS FALSE
            """)
        return cur.rowcount

    def _cleanUpObsoleteDistroEntries(self, store):
        """Delete some queue entries for obsolete `DistroSeries`.

        :param store: The Store to delete from.
        :return: Number of entries deleted.
        """
        # XXX JeroenVermeulen 2009-09-18 bug=271938,432484: Stormify
        # this once Storm's remove() supports joins and slices.
        cur = cursor()
        cur.execute("""
            DELETE FROM TranslationImportQueueEntry
            WHERE id IN (
                SELECT Entry.id
                FROM TranslationImportQueueEntry Entry
                JOIN DistroSeries ON
                    DistroSeries.id = Entry.distroseries
                JOIN Distribution ON
                    Distribution.id = DistroSeries.distribution
                WHERE DistroSeries.releasestatus = %s
                LIMIT 100)
            """ % quote(SeriesStatus.OBSOLETE))
        return cur.rowcount

    def cleanUpQueue(self):
        """See `ITranslationImportQueue`."""
        store = IMasterStore(TranslationImportQueueEntry)

        return (
            self._cleanUpObsoleteEntries(store) +
            self._cleanUpInactiveProductEntries(store) +
            self._cleanUpObsoleteDistroEntries(store))

    def remove(self, entry):
        """See ITranslationImportQueue."""
        TranslationImportQueueEntry.delete(entry.id)
