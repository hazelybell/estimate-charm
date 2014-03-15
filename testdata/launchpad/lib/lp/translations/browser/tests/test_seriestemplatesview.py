# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `BaseSeriesTemplatesView` and descendants."""

__metaclass__ = type

import re

from zope.security.proxy import removeSecurityProxy

from lp.registry.model.distroseries import DistroSeries
from lp.registry.model.productseries import ProductSeries
from lp.services.webapp.publisher import canonical_url
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.testing import (
    login,
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.sampledata import ADMIN_EMAIL
from lp.translations.browser.distroseries import DistroSeriesTemplatesView
from lp.translations.browser.productseries import ProductSeriesTemplatesView


class SeriesTemplatesViewScenario:

    # The view class to test.
    view_class = None

    # The expected list of columns for the view_class, each shown as a
    # list holding the column's CSS class.
    columns = None

    def makeTemplateContext(self):
        """Create makePOTemplate arguments to create a series."""
        raise NotImplementedError()

    def _makeTemplate(self, **kwargs):
        """Create a distro- or productseries for the view."""
        args_dict = self.makeTemplateContext()
        args_dict.update(kwargs)
        return self.factory.makePOTemplate(**args_dict)

    def _getSeries(self, template):
        """Get `template`'s distro- or productseries."""
        return template.distroseries or template.productseries

    def _makeView(self, template=None):
        """Create a `BaseTemplatesView` containing `template`."""
        if template is None:
            template = self._makeTemplate()
        request = LaunchpadTestRequest()
        view = self.view_class(self._getSeries(template), request)
        view.initialize()
        return view

    def _findTagClasses(self, html, tag):
        """Find the CSS classes for all instances of `tag`s in `html`.

        Returns a list of lists.  The outer list represents instances of
        `tag`, in the order in which they are found.  The inner lists
        hold the respective sets of HTML classes for these tags, sorted
        alphabetically.
        """
        regex = '<%s [^>]*class="([^"]*)"' % tag
        return [
            sorted(css_class.split())
            for css_class in re.findall(regex, html)]

    def _findActions(self, html):
        """Find the available actions in an HTML actions column."""
        return re.findall('<[^>]*>([^<]*)</[^>]*', html)

    def test_has_the_right_columns(self):
        # Test the column headers against the expected list.
        view = self._makeView()
        header = view.renderTemplatesHeader()
        self.assertEqual(self.columns, self._findTagClasses(header, 'th'))

    def test_logging_in_adds_actions_column(self):
        # A logged-in user gets to see an extra "actions" column.
        template = self._makeTemplate()
        login_person(self.factory.makePerson())
        view = self._makeView(template)
        columns = self.columns + [['actions_column']]
        header = view.renderTemplatesHeader()
        self.assertEqual(columns, self._findTagClasses(header, 'th'))
        row = view.renderTemplateRow(template)
        self.assertEqual(columns, self._findTagClasses(row, 'td'))

    def test_user_actions(self):
        # The only action offered to regular users is Download.
        template = self._makeTemplate()
        url = canonical_url(template)
        login_person(self.factory.makePerson())
        view = self._makeView(template)

        self.assertEqual(
            ['Download'],
            self._findActions(view._renderActionsColumn(template, url)))

    def test_admin_actions(self):
        # An administrator gets to see all actions on a template.
        template = self._makeTemplate()
        url = canonical_url(template)
        login(ADMIN_EMAIL)
        view = self._makeView(template)

        self.assertEqual(
            ['Edit', 'Upload', 'Download', 'Administer'],
            self._findActions(view._renderActionsColumn(template, url)))

    def test_edit_actions(self):
        # A non-admin user with edit rights gets the Edit, Upload, and
        # Download actions.
        template = self._makeTemplate()
        url = canonical_url(template)
        login_person(self.factory.makePerson())
        view = self._makeView(template)
        view.can_edit = True

        self.assertEqual(
            ['Edit', 'Upload', 'Download'],
            self._findActions(view._renderActionsColumn(template, url)))

    def test_constructs_correct_urls(self):
        # The view classes can override constructTemplateURL with
        # optimized versions.  These can produce either an absolute URL
        # that exactly matches the template's canonical_url, or a
        # relative one starting from the series' canonical_url.
        template = self._makeTemplate()
        view = self._makeView(template)

        series_url = canonical_url(
            self._getSeries(template), rootsite='translations')
        constructed_url = view.constructTemplateURL(template)

        self.assertIn(
            canonical_url(template),
            (constructed_url, '/'.join([series_url, constructed_url])))

    def test_renderTemplateLink(self):
        # _renderTemplateLink renders a link to the template.
        template = self._makeTemplate()
        view = self._makeView(template)

        url = view.constructTemplateURL(template)
        link = view._renderTemplateLink(template, url)

        self.assertIn('<a ', link)
        self.assertIn('href="%s"' % url, link)
        self.assertIn('>%s<' % template.name, link)

    def test_renderTemplateLink_marks_disabled(self):
        # _renderTemplateLinks marks disabled templates as "(inactive)."
        template = self._makeTemplate()
        view = self._makeView(template)
        url = canonical_url(template)

        removeSecurityProxy(template).iscurrent = True
        self.assertNotIn(
            '(inactive)', view._renderTemplateLink(template, url))
        removeSecurityProxy(template).iscurrent = False
        self.assertIn('(inactive)', view._renderTemplateLink(template, url))

    def test_renderLastUpdateDate_sets_sortkey(self):
        # _renderLastUpdateDate sets the full date as the column's sort
        # key, so that clicking on the column header sorts by date (even
        # if sorting alphabetically by the visible date might produce a
        # different ordering).
        template = self._makeTemplate()
        view = self._makeView(template)

        date_field = view._renderLastUpdateDate(template)

        # The sort key is set in a span of class "sortkey."
        sortkey_match = re.findall(
            '<span class="sortkey">([^<]*)</span>', date_field)
        self.assertIsNot(None, sortkey_match)
        self.assertEqual(1, len(sortkey_match))

        # The column also has the same full date as a tooltip.
        full_date = sortkey_match[0].strip()
        self.assertIn('title="%s"' % full_date, date_field)

    def test_renderAction_returns_empty_string_if_not_enabled(self):
        view = self._makeView()
        self.assertEqual(
            '',
            view._renderAction('url', 'name', 'path', 'sprite', False))

    def test_renderAction(self):
        # If enabled, _renderAction produces a link to an action form
        # for a given template.
        view = self._makeView()

        url = self.factory.getUniqueString()
        name = self.factory.getUniqueString()
        path = self.factory.getUniqueString()
        sprite = self.factory.getUniqueString()

        action = view._renderAction(url, name, path, sprite, True)

        self.assertIn('<a ', action)
        self.assertIn('href="%s/%s"' % (url, path), action)
        self.assertIn(name, action)
        self.assertIn('class="sprite %s"' % sprite, action)

    def test_renderField_returns_empty_string_if_no_content(self):
        view = self._makeView()
        self.assertEqual('', view._renderField('x', None, tag='y'))

    def test_renderField_returns_empty_field_for_empty_content(self):
        field = self._makeView()._renderField('class', '', tag='tag')
        self.assertIn('<tag class="class">', field)
        self.assertIn('</tag>', field)

    def test_renderField(self):
        column_class = self.factory.getUniqueString()
        content = self.factory.getUniqueString()
        tag = self.factory.getUniqueString()

        field = self._makeView()._renderField(column_class, content, tag=tag)

        self.assertIn('<%s class="%s">' % (tag, column_class), field)
        self.assertIn(content, field)
        self.assertIn('</%s>' % tag, field)

    def test_renderTemplateRow(self):
        template = self._makeTemplate()
        view = self._makeView(template)

        row = view.renderTemplateRow(template)

        self.assertEqual(
            [sorted(['template_row', view.rowCSSClass(template)])],
            self._findTagClasses(row, 'tr'))

        self.assertEqual(self.columns, self._findTagClasses(row, 'td'))


class TestDistroSeriesTemplatesView(SeriesTemplatesViewScenario,
                                    TestCaseWithFactory):
    """Run the test scenario against `DistroSeriesTemplatesView`."""

    layer = DatabaseFunctionalLayer

    view_class = DistroSeriesTemplatesView

    columns = [
        ['priority_column'],
        ['sourcepackage_column'],
        ['template_column'],
        ['sharing'],
        ['length_column'],
        ['lastupdate_column'],
    ]

    def makeTemplateContext(self):
        """See `SeriesTemplatesViewScenario`."""
        return dict(
            sourcepackagename=self.factory.makeSourcePackageName(),
            distroseries=self.factory.makeDistroSeries())

    def test_makeTemplate(self):
        # In this test case, _makeTemplate produces a distroseries
        # template.
        template = self._makeTemplate()
        self.assertIsInstance(template.distroseries, DistroSeries)
        self.assertIs(None, template.productseries)

    def test_findTagClasses(self):
        # Tested here arbitrarily (no need to repeat it): the
        # _findTagClasses helper.
        self.assertEqual(
            [['b', 'c'], ['a']],
            self._findTagClasses('<x class="c b" /><x class="a">', 'x'))

    def test_findActions(self):
        # Tested here arbitrarily (no need to repeat it): the
        # _findActions helper.
        self.assertEqual(['Foo'], self._findActions('<a class="bar">Foo</a>'))

    def test_is_distroseries(self):
        self.assertTrue(self._makeView().is_distroseries)

    def test_renderSourcePackage(self):
        # _renderSourcePackage returns the template's source-package
        # name for a distroseries view.
        template = self._makeTemplate()
        view = self._makeView(template)

        self.assertEqual(
            template.sourcepackagename.name,
            view._renderSourcePackage(template))


class FauxSharedTemplate:
    """A stand-in for a template."""
    name = 'TEMPLATE_NAME'


class FauxSourcePackageName:
    """A stand-in for a SourcePackageName."""
    name = 'SOURCE_PACKAGE_NAME'


class FauxProductSeries:
    """A stand-in for a ProductSeries."""
    name = 'PRODUCT_SERIES_NAME'


class TestSharingColumn(TestDistroSeriesTemplatesView):
    """Test the _renderSharing method of BaseSeriesTemplatesView."""

    columns = [
        ['priority_column'],
        ['sourcepackage_column'],
        ['template_column'],
        ['sharing'],
        ['length_column'],
        ['lastupdate_column'],
    ]

    def test_unshared(self):
        # Unshared templates result in the text "not shared" and an edit link.
        template = self._makeTemplate()
        view = self._makeView(template)
        rendered = view._renderSharing(template, None, None, None, None, None)
        self.assertTrue('not shared' in rendered)
        edit_link_segment = ('+source/%s/+sharing-details' %
            template.sourcepackagename.name)
        self.assertTrue(edit_link_segment in rendered)

    def test_shared(self):
        view = self._makeView()
        rendered = view._renderSharing(FauxSharedTemplate, object(),
            FauxProductSeries, object(), object(), FauxSourcePackageName)
        # Shared templates are displayed with an edit link that leads to the
        # +sharing-details page...
        edit_link_segment = ('+source/%s/+sharing-details' %
            FauxSourcePackageName.name)
        self.assertTrue(edit_link_segment in rendered)
        # ...and a link to the shared template.
        template_link_segment = ('/+pots/%s' % FauxSharedTemplate.name)
        self.assertTrue(template_link_segment in rendered)


class TestProductSeriesTemplatesView(SeriesTemplatesViewScenario,
                                     TestCaseWithFactory):
    """Run the test scenario against `ProductSeriesTemplatesView`."""

    layer = DatabaseFunctionalLayer

    view_class = ProductSeriesTemplatesView

    columns = [
        ['priority_column'],
        ['template_column'],
        ['length_column'],
        ['lastupdate_column'],
    ]

    def makeTemplateContext(self):
        """See `SeriesTemplatesViewScenario`."""
        return dict(productseries=self.factory.makeProductSeries())

    def test_makeTemplate(self):
        # In this test case, _makeTemplate produces a productseries
        # template.
        template = self._makeTemplate()
        self.assertIs(None, template.distroseries)
        self.assertIsInstance(template.productseries, ProductSeries)

    def test_is_distroseries(self):
        self.assertFalse(self._makeView().is_distroseries)

    def test_renderSourcePackage(self):
        # _renderSourcePackage returns None for a productseries view.
        template = self._makeTemplate()
        view = self._makeView(template)
        self.assertIs(None, view._renderSourcePackage(template))
