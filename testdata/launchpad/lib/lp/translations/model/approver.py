# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'TranslationNullApprover',
    'TranslationBranchApprover',
    'TranslationBuildApprover',
    ]

from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.translations.enums import RosettaImportStatus
from lp.translations.interfaces.potemplate import IPOTemplateSet
from lp.translations.utilities.template import (
    make_domain,
    make_name,
    make_name_from_path,
    )
from lp.translations.utilities.translation_import import TranslationImporter


def get_product_name(productseries):
    """Get the series' product name, if any.

    :return: A string; either the product's name or, if `productseries`
        is None, the empty string.
    """
    if productseries is None:
        return ''
    else:
        return productseries.product.name


class TranslationNullApprover(object):
    """Does not approve any files."""

    def __init__(self, *args, **kwargs):
        """Ignore parameters."""

    def approve(self, entry):
        """Leave entry unchanged."""
        return entry


class TranslationBranchApprover(object):
    """Automatic approval of template files uploaded from bzr branches."""

    def __init__(self, files, productseries=None,
                 distroseries=None, sourcepackagename=None):
        """Create the approver and build the approval list by comparing
        the given files as found in the source tree to the database entries.

        Either productseries or distroseries/sourcepackagename must be given
        but not all.

        :param files: A list of paths to the translation files.
        :param productseries: The productseries that this upload is for.
        :param distroseries: The distroseries that this upload is for.
        :param sourcepackagename: The sourcepackagename that this upload
            is for.
        """

        assert (distroseries is None or sourcepackagename is not None), (
                "Please specify distroseries and sourcepackagename together.")

        self._potemplates = {}
        self._n_matched = 0
        self.is_approval_possible = True

        potemplate_names = set()
        product_name = get_product_name(productseries)

        importer = TranslationImporter()
        self._potemplateset = getUtility(IPOTemplateSet).getSubset(
            iscurrent=True, productseries=productseries,
            distroseries=distroseries, sourcepackagename=sourcepackagename)
        for path in files:
            if importer.isTemplateName(path):
                potemplate = self._potemplateset.getPOTemplateByPath(path)
                if potemplate is None:
                    name = make_name_from_path(path, default=product_name)
                    potemplate = self._potemplateset.getPOTemplateByName(name)
                else:
                    name = potemplate.name
                # Template names must occur only once.
                if name in potemplate_names:
                    self.is_approval_possible = False
                else:
                    potemplate_names.add(name)
                if potemplate is not None:
                    self._n_matched += 1
                self._potemplates[path] = potemplate
        # The simplest case of exactly one file and one POTemplate object is
        # always approved.
        if len(self._potemplateset) == len(self._potemplates) == 1:
            self._potemplates[self._potemplates.keys()[0]] = (
                list(self._potemplateset)[0])
            self.is_approval_possible = True

    @property
    def unmatched_objects(self):
        """The number of IPOTemplate objects that are not matched by path
        to a file being imported.
        """
        return len(self._potemplateset) - self._n_matched

    @property
    def unmatched_files(self):
        """The number of files being imported that are not matched by path
        to an IPOTemplate object.
        """
        return len(self._potemplates) - self._n_matched

    def approve(self, entry):
        """Check the given ImportQueueEntry against the internal approval
        list and set its values accordingly.

        :param entry: The queue entry that needs to be approved.
        """
        if entry is None:
            return None

        if not self.is_approval_possible:
            return entry
        potemplate = None
        # Path must be a template path.
        if entry.path not in self._potemplates:
            return entry

        product_name = get_product_name(entry.productseries)
        domain = make_domain(entry.path, default=product_name)
        if self._potemplates[entry.path] is None:
            if self.unmatched_objects > 0:
                # Unmatched entries in database, do not approve.
                return entry
            # Path must provide a translation domain.
            if domain == '':
                return entry
            # No (possibly) matching entry found: create one.
            name = make_name(domain)
            if not self._potemplateset.isNameUnique(name):
                # The name probably matches an inactive template.
                return entry
            potemplate = self._potemplateset.new(
                name, domain, entry.path, entry.importer)
            self._potemplates[entry.path] = potemplate
            self._n_matched += 1
        else:
            # A matching entry is found, the import can be approved.
            potemplate = self._potemplates[entry.path]
            potemplate.path = entry.path
            if domain != '':
                potemplate.translation_domain = domain

        # Approve the entry
        entry.potemplate = potemplate
        if entry.status == RosettaImportStatus.NEEDS_REVIEW:
            entry.setStatus(RosettaImportStatus.APPROVED,
                            getUtility(ILaunchpadCelebrities).rosetta_experts)
        return entry


class TranslationBuildApprover(object):
    """Automatic approval of automatically build translation templates."""

    def __init__(
        self, filenames,
        productseries=None, distroseries=None, sourcepackagename=None):

        # Productseries and distroseries will be asserted in getSubset but
        # not sourcepackagename.
        assert (distroseries is None and sourcepackagename is None or
                distroseries is not None and sourcepackagename is not None), (
                "Please specify distroseries and sourcepackagename together.")

        importer = TranslationImporter()
        # We only care for templates.
        self.filenames = filter(importer.isTemplateName, filenames)
        self._potemplateset = getUtility(IPOTemplateSet).getSubset(
            productseries=productseries,
            distroseries=distroseries,
            sourcepackagename=sourcepackagename)
        if productseries is not None:
            self.owner = productseries.product.owner
        else:
            self.owner = distroseries.distribution.owner

    def _getOrCreateGenericTemplate(self, path):
        """Try to find or create a template for a generic path.

        Because a generic path (e.g. messages.pot) does not provide
        a template name, the name of the product or sourcepackagename is used
        when creating a new template.

        :param path: The path of the template file.
        :return: The template or None.
        """
        if len(self.filenames) != 1:
            # Generic paths can only be approved if they are alone.
            return None
        potemplateset_size = len(self._potemplateset)
        if potemplateset_size == 0:
            # Create template from product or sourcepackagename name.
            if self._potemplateset.productseries is not None:
                domain = self._potemplateset.productseries.product.name
            else:
                domain = self._potemplateset.sourcepackagename.name
            name = domain
            if not self._potemplateset.isNameUnique(name):
                # The name probably matches an inactive template.
                return None
            return self._potemplateset.new(name, domain, path, self.owner)
        elif potemplateset_size == 1:
            # Use the one template that is there.
            # Can only be accessed through iterator.
            for pot in self._potemplateset:
                return pot
        else:
            # If more than one template is available we don't know which to
            # chose.
            return None

    def _getOrCreatePOTemplateForPath(self, path):
        """Find the POTemplate that path should be imported into.

        If no existing template could be found it creates one if possible.

        :param path: The path of the file to be imported.
        :return: The POTemplate instance or None.
        """
        if path not in self.filenames:
            # The file is not a template file.
            return None

        potemplate = self._potemplateset.getPOTemplateByPath(path)
        if potemplate is None:
            domain = make_domain(path)
            name = make_name(domain)
            if name == '':
                # A generic name does not contain a translation domain.
                potemplate = self._getOrCreateGenericTemplate(path)
            else:
                potemplate = self._potemplateset.getPOTemplateByName(name)
                if potemplate is None:
                    # Still no template found, create a new one.
                    if not self._potemplateset.isNameUnique(name):
                        # The name probably matches an inactive template.
                        return None
                    potemplate = self._potemplateset.new(
                        name, domain, path, self.owner)
        return potemplate

    def approve(self, entry):
        """Approve a queue entry."""
        assert (
            entry.productseries == self._potemplateset.productseries and
            entry.distroseries == self._potemplateset.distroseries and
            entry.sourcepackagename ==
                self._potemplateset.sourcepackagename), (
            "Entry must be for same target as approver.")

        # This method is intended to be used to wrap
        # TranslationImportQueue.addOrUpdateEntry which may return None.
        if entry is None:
            return None

        potemplate = self._getOrCreatePOTemplateForPath(entry.path)

        if potemplate is not None:
            # We have a POTemplate, the entry can be approved.
            entry.potemplate = potemplate
            potemplate.path = entry.path
            if entry.status == RosettaImportStatus.NEEDS_REVIEW:
                entry.setStatus(
                    RosettaImportStatus.APPROVED,
                    getUtility(ILaunchpadCelebrities).rosetta_experts)
        return entry
