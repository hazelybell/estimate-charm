# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'TranslationLinksAggregator',
    ]

from lp.services.webapp import canonical_url
from lp.translations.interfaces.pofile import IPOFile
from lp.translations.model.productserieslanguage import ProductSeriesLanguage


class TranslationLinksAggregator:
    """Aggregate `POFile`s and/or `POTemplate`s into meaningful targets.

    Here, `POFile`s and `POTemplate`s are referred to collectively as
    "sheets."
    """

    # Suffix to append to URL when linking to a POFile.
    pofile_link_suffix = ''

    def describe(self, target, link, covered_sheets):
        """Overridable: return description of given translations link.

        :param target: `Product` or `SourcePackage`.
        :param link: URL linking to `covered_sheets` in the UI.
        :param covered_sheets: `POFile`s and/or `POTemplate`s being
            linked and described together.
        :return: Some description that will get added to a list and
            returned by `aggregate`.
        """
        raise NotImplementedError()

    def _bundle(self, sheets):
        """Bundle `sheets` based on target: `Product` or `SourcePackage`.

        :param sheets: Sequence of `POFile`s and/or `POTemplate`s.
        :return: Dict mapping each targets to a list representing its
            `POFile`s and `POTemplate`s as found in `sheets`.
        """
        targets = {}
        for sheet in sheets:
            if IPOFile.providedBy(sheet):
                template = sheet.potemplate
            else:
                template = sheet

            if template.productseries:
                target = template.productseries.product
            else:
                distroseries = template.distroseries
                sourcepackagename = template.sourcepackagename
                target = distroseries.getSourcePackage(sourcepackagename)

            if target not in targets:
                targets[target] = []

            targets[target].append(sheet)

        return targets

    def _composeLink(self, sheet):
        """Produce a link to a `POFile` or `POTemplate`."""
        link = canonical_url(sheet)
        if IPOFile.providedBy(sheet):
            link += self.pofile_link_suffix

        return link

    def _getTemplate(self, sheet):
        """Return `POTemplate` for `sheet`.

        :param sheet: A `POTemplate` or `POFile`.
        """
        if IPOFile.providedBy(sheet):
            return sheet.potemplate
        else:
            return sheet

    def _getLanguage(self, sheet):
        """Return language `sheet` is in, if `sheet` is an `IPOFile`."""
        if IPOFile.providedBy(sheet):
            return sheet.language
        else:
            return None

    def _countLanguages(self, sheets):
        """Count languages among `sheets`.

        A template's language is None, which also counts.
        """
        return len(set(self._getLanguage(sheet) for sheet in sheets))

    def _circumscribe(self, sheets):
        """Find the best common UI link to cover all of `sheets`.

        :param sheets: List of `POFile`s and/or `POTemplate`s.
        :return: Dict containing a set of links and the respective lists
            of `sheets` they cover.
        """
        first_sheet = sheets[0]
        if len(sheets) == 1:
            # Simple case: one sheet.
            return {self._composeLink(first_sheet): sheets}

        templates = set([self._getTemplate(sheet) for sheet in sheets])

        productseries = set(
            template.productseries
            for template in templates
            if template.productseries)

        products = set(series.product for series in productseries)

        sourcepackagenames = set(
            template.sourcepackagename 
            for template in templates
            if template.sourcepackagename)

        distroseries = set(
            template.distroseries
            for template in templates
            if template.sourcepackagename)

        assert len(products) <= 1, "Got more than one product."
        assert len(sourcepackagenames) <= 1, "Got more than one package."
        assert len(distroseries) <= 1, "Got more than one distroseries."
        assert len(products) + len(sourcepackagenames) == 1, (
            "Didn't get exactly one product or one package.")

        first_template = self._getTemplate(first_sheet)

        if len(templates) == 1:
            # Multiple inputs, but all for the same template.  Link to
            # the template.
            return {self._composeLink(first_template): sheets}

        if sourcepackagenames:
            # Multiple inputs, but they have to be all for the same
            # source package.  Show its template listing.
            distroseries = first_template.distroseries
            packagename = first_template.sourcepackagename
            link = canonical_url(distroseries.getSourcePackage(packagename))
            return {link: sheets}

        if len(productseries) == 1:
            # All for the same ProductSeries.
            series = first_template.productseries
            if self._countLanguages(sheets) == 1:
                # All for the same language in the same ProductSeries,
                # though still for different templates.  Link to
                # ProductSeriesLanguage.
                productserieslanguage = ProductSeriesLanguage(
                    series, first_sheet.language)
                return {canonical_url(productserieslanguage): sheets}
            else:
                # Multiple templates and languages in the same product
                # series, or a mix of templates and at least one
                # language.  Show the product series' templates listing.
                return {canonical_url(series): sheets}

        # Different release series of the same product.  Break down into
        # individual sheets.  We could try recursing here to get a better
        # set of aggregated links, but may not be worth the trouble.
        return dict(
            (self._composeLink(sheet), [sheet]) for sheet in sheets)

    def aggregate(self, sheets):
        """Aggregate `sheets` into a list of translation target descriptions.

        Targets are aggregated into "sensible" chunks first.c
        
        :return: A list of whatever the implementation for `describe`
            returns for the sensible chunks.
        """
        links = []
        for target, sheets in self._bundle(sheets).iteritems():
            assert sheets, "Translation target has no POFiles or templates."
            links_and_sheets = self._circumscribe(sheets)
            for link, covered_sheets in links_and_sheets.iteritems():
                links.append(self.describe(target, link, covered_sheets))

        return links
