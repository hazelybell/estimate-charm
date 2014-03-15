# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Browser views for sourcepackages."""

__metaclass__ = type

__all__ = [
    'PackageUpstreamTracking',
    'SourcePackageAssociationPortletView',
    'SourcePackageBreadcrumb',
    'SourcePackageChangeUpstreamView',
    'SourcePackageFacets',
    'SourcePackageNavigation',
    'SourcePackageOverviewMenu',
    'SourcePackageRemoveUpstreamView',
    'SourcePackageUpstreamConnectionsView',
    'SourcePackageView',
    ]

import string
import urllib

from apt_pkg import (
    parse_src_depends,
    upstream_version,
    version_compare,
    )
from lazr.enum import (
    EnumeratedType,
    Item,
    )
from lazr.restful.interface import copy_field
from lazr.restful.utils import smartquote
from z3c.ptcompat import ViewPageTemplateFile
from zope.component import (
    adapter,
    getMultiAdapter,
    getUtility,
    )
from zope.formlib.form import Fields
from zope.formlib.interfaces import IInputWidget
from zope.formlib.widgets import DropdownWidget
from zope.interface import (
    implements,
    Interface,
    )
from zope.schema import (
    Choice,
    TextLine,
    )
from zope.schema.vocabulary import (
    getVocabularyRegistry,
    SimpleTerm,
    SimpleVocabulary,
    )

from lp import _
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadFormView,
    ReturnToReferrerMixin,
    )
from lp.app.browser.multistep import (
    MultiStepView,
    StepView,
    )
from lp.app.browser.tales import CustomizableFormatter
from lp.app.enums import (
    InformationType,
    ServiceUsage,
    )
from lp.app.widgets.itemswidgets import LaunchpadRadioWidget
from lp.bugs.browser.bugtask import BugTargetTraversalMixin
from lp.registry.browser.product import ProjectAddStepOne
from lp.registry.interfaces.packaging import (
    IPackaging,
    IPackagingUtil,
    )
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.product import IProductSet
from lp.registry.interfaces.productseries import IProductSeries
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.interfaces.sourcepackage import ISourcePackage
from lp.registry.model.product import Product
from lp.services.webapp import (
    ApplicationMenu,
    canonical_url,
    GetitemNavigation,
    Link,
    StandardLaunchpadFacets,
    stepto,
    )
from lp.services.webapp.breadcrumb import Breadcrumb
from lp.services.webapp.escaping import structured
from lp.services.webapp.interfaces import IBreadcrumb
from lp.services.webapp.publisher import LaunchpadView
from lp.services.worlddata.helpers import browser_languages
from lp.services.worlddata.interfaces.country import ICountry
from lp.soyuz.browser.packagerelationship import relationship_builder
from lp.translations.interfaces.potemplate import IPOTemplateSet


def get_register_upstream_url(source_package):
    displayname = string.capwords(source_package.name.replace('-', ' '))
    distroseries_string = "%s/%s" % (
        source_package.distroseries.distribution.name,
        source_package.distroseries.name)
    current_release = source_package.currentrelease
    if current_release is not None and current_release.homepage is not None:
        homepage = current_release.homepage
    else:
        homepage = ''
    params = {
        '_return_url': canonical_url(source_package),
        'field.source_package_name': source_package.sourcepackagename.name,
        'field.distroseries': distroseries_string,
        'field.name': source_package.name,
        'field.displayname': displayname,
        'field.title': displayname,
        'field.homepageurl': homepage,
        'field.__visited_steps__': ProjectAddStepOne.step_name,
        'field.actions.continue': 'Continue',
        }
    if len(source_package.releases) == 0:
        params['field.summary'] = ''
    else:
        # This is based on the SourcePackageName.summary attribute, but
        # it eliminates the binary.name and duplicate summary lines.
        summary_set = set()
        for binary in source_package.releases[0].sample_binary_packages:
            summary_set.add(binary.summary)
        params['field.summary'] = '\n'.join(sorted(summary_set))
    query_string = urllib.urlencode(
        sorted(params.items()), doseq=True)
    return '/projects/+new?%s' % query_string


class SourcePackageFormatterAPI(CustomizableFormatter):
    """Adapter for ISourcePackage objects to a formatted string."""

    _link_permission = 'zope.Public'

    _link_summary_template = '%(displayname)s'

    def _link_summary_values(self):
        displayname = self._context.displayname
        return {'displayname': displayname}


class SourcePackageNavigation(GetitemNavigation, BugTargetTraversalMixin):

    usedfor = ISourcePackage

    @stepto('+pots')
    def pots(self):
        potemplateset = getUtility(IPOTemplateSet)
        sourcepackage_pots = potemplateset.getSubset(
            distroseries=self.context.distroseries,
            sourcepackagename=self.context.sourcepackagename)

        # If we are able to view the translations for distribution series
        # we should also be allowed to see them for a distribution
        # source package.
        # If not, raise TranslationUnavailable.
        from lp.translations.browser.distroseries import (
            check_distroseries_translations_viewable)
        check_distroseries_translations_viewable(self.context.distroseries)

        return sourcepackage_pots

    @stepto('+filebug')
    def filebug(self):
        """Redirect to the IDistributionSourcePackage +filebug page."""
        distro_sourcepackage = self.context.distribution_sourcepackage

        redirection_url = canonical_url(
            distro_sourcepackage, view_name='+filebug')
        if self.request.form.get('no-redirect') is not None:
            redirection_url += '?no-redirect'
        return self.redirectSubTree(redirection_url, status=303)

    @stepto('+gethelp')
    def gethelp(self):
        """Redirect to the IDistributionSourcePackage +gethelp page."""
        dsp = self.context.distribution_sourcepackage
        redirection_url = canonical_url(dsp, view_name='+gethelp')
        return self.redirectSubTree(redirection_url, status=303)


@adapter(ISourcePackage)
class SourcePackageBreadcrumb(Breadcrumb):
    """Builds a breadcrumb for an `ISourcePackage`."""
    implements(IBreadcrumb)

    @property
    def text(self):
        return smartquote('"%s" source package') % (self.context.name)


class SourcePackageFacets(StandardLaunchpadFacets):

    usedfor = ISourcePackage
    enable_only = ['overview', 'bugs', 'branches', 'translations']

    def overview(self):
        text = 'Overview'
        summary = u'General information about {0}'.format(
            self.context.displayname)
        return Link('', text, summary)

    def bugs(self):
        text = 'Bugs'
        summary = u'Bugs reported about {0}'.format(self.context.displayname)
        return Link('', text, summary)

    def branches(self):
        text = 'Code'
        summary = u'Branches for {0}'.format(self.context.displayname)
        return Link('', text, summary)

    def translations(self):
        text = 'Translations'
        summary = u'Translations of {0} in Launchpad'.format(
            self.context.displayname)
        return Link('', text, summary)


class SourcePackageOverviewMenu(ApplicationMenu):

    usedfor = ISourcePackage
    facet = 'overview'
    links = [
        'distribution_source_package', 'edit_packaging', 'remove_packaging',
        'changelog', 'copyright', 'builds', 'set_upstream',
        ]

    def distribution_source_package(self):
        target = canonical_url(self.context.distribution_sourcepackage)
        text = 'All versions of %s source in %s' % (
            self.context.name, self.context.distribution.displayname)
        return Link(target, text, icon='package-source')

    def changelog(self):
        return Link('+changelog', 'View changelog', icon='list')

    def copyright(self):
        return Link('+copyright', 'View copyright', icon='info')

    def edit_packaging(self):
        return Link(
            '+edit-packaging', 'Change upstream link', icon='edit',
            enabled=self.userCanDeletePackaging())

    def remove_packaging(self):
        return Link(
            '+remove-packaging', 'Remove upstream link', icon='remove',
            enabled=self.userCanDeletePackaging())

    def set_upstream(self):
        return Link(
            "+edit-packaging", "Set upstream link", icon="add",
            enabled=self.userCanDeletePackaging())

    def builds(self):
        text = 'Show builds'
        return Link('+builds', text, icon='info')

    def userCanDeletePackaging(self):
        packaging = self.context.direct_packaging
        if packaging is None:
            return True
        return packaging.userCanDelete()


class SourcePackageChangeUpstreamStepOne(ReturnToReferrerMixin, StepView):
    """A view to set the `IProductSeries` of a sourcepackage."""
    schema = Interface
    _field_names = []

    step_name = 'sourcepackage_change_upstream_step1'
    template = ViewPageTemplateFile(
        '../templates/sourcepackage-edit-packaging.pt')
    label = 'Link to an upstream project'
    page_title = label
    step_description = 'Choose project'
    product = None

    def setUpFields(self):
        super(SourcePackageChangeUpstreamStepOne, self).setUpFields()
        series = self.context.productseries
        if series is not None:
            default = series.product
        else:
            default = None
        product_field = copy_field(
            IProductSeries['product'], default=default)
        self.form_fields += Fields(product_field)

    # Override ReturnToReferrerMixin.next_url.
    next_url = None

    def main_action(self, data):
        """See `MultiStepView`."""
        self.next_step = SourcePackageChangeUpstreamStepTwo
        self.request.form['product'] = data['product']

    def validateStep(self, data):
        super(SourcePackageChangeUpstreamStepOne, self).validateStep(data)
        product = data.get('product')
        if product is None:
            return
        if product.private:
            self.setFieldError('product',
                'Only Public projects can be packaged, not %s.' %
                data['product'].information_type.title)

    @property
    def register_upstream_url(self):
        return get_register_upstream_url(self.context)


class SourcePackageChangeUpstreamStepTwo(ReturnToReferrerMixin, StepView):
    """A view to set the `IProductSeries` of a sourcepackage."""
    schema = IProductSeries
    _field_names = ['product']

    step_name = 'sourcepackage_change_upstream_step2'
    template = ViewPageTemplateFile(
        '../templates/sourcepackage-edit-packaging.pt')
    label = 'Link to an upstream project'
    page_title = label
    step_description = 'Choose project series'
    product = None

    # The DropdownWidget is used, since the VocabularyPickerWidget
    # does not support visible=False to turn it into a hidden input
    # to continue passing the variable in the form.
    custom_widget('product', DropdownWidget, visible=False)
    custom_widget('productseries', LaunchpadRadioWidget)

    def setUpFields(self):
        super(SourcePackageChangeUpstreamStepTwo, self).setUpFields()

        # The vocabulary for the product series is overridden to just
        # include active series from the product selected in the
        # previous step.
        product_name = self.request.form['field.product']
        self.product = getUtility(IProductSet)[product_name]
        series_list = [
            series for series in self.product.series
            if series.status != SeriesStatus.OBSOLETE]

        # If the product is not being changed, then the current
        # productseries can be the default choice. Otherwise,
        # it will not exist in the vocabulary.
        if (self.context.productseries is not None
            and self.context.productseries.product == self.product):
            series_default = self.context.productseries
            # This only happens for obsolete series, since they aren't
            # added to the vocabulary normally.
            if series_default not in series_list:
                series_list.append(series_default)
        else:
            series_default = None

        # Put the development focus at the top of the list and create
        # the vocabulary.
        dev_focus = self.product.development_focus
        if dev_focus in series_list:
            series_list.remove(dev_focus)
        vocab_terms = [
            SimpleTerm(series, series.name, series.name)
            for series in series_list]
        dev_focus_term = SimpleTerm(
            dev_focus, dev_focus.name, "%s (Recommended)" % dev_focus.name)
        vocab_terms.insert(0, dev_focus_term)

        productseries_choice = Choice(
            __name__='productseries',
            title=_("Series"),
            description=_("The series in this project."),
            vocabulary=SimpleVocabulary(vocab_terms),
            default=series_default,
            required=True)

        # The product selected in the previous step should be displayed,
        # but a widget can't be readonly and pass its value with the
        # form, so the real product field passes the value, and this fake
        # product field displays it.
        display_product_field = TextLine(
            __name__='fake_product',
            title=_("Project"),
            default=self.product.displayname,
            readonly=True)

        self.form_fields = (
            Fields(display_product_field, productseries_choice)
            + self.form_fields)

    # Override ReturnToReferrerMixin.next_url until the main_action()
    # is called.
    next_url = None

    main_action_label = u'Change'

    def main_action(self, data):
        productseries = data['productseries']
        # Because it is part of a multistep view, the next_url can't
        # be set until the action is called, or it will skip the step.
        self.next_url = self._return_url
        if self.context.productseries == productseries:
            # There is nothing to do.
            return
        self.context.setPackaging(productseries, self.user)
        self.request.response.addNotification('Upstream link updated.')


class SourcePackageChangeUpstreamView(MultiStepView):
    """A view to set the `IProductSeries` of a sourcepackage."""
    page_title = SourcePackageChangeUpstreamStepOne.page_title
    label = SourcePackageChangeUpstreamStepOne.label
    total_steps = 2
    first_step = SourcePackageChangeUpstreamStepOne


class SourcePackageRemoveUpstreamView(ReturnToReferrerMixin,
                                      LaunchpadFormView):
    """A view for removing the link to an upstream package."""

    schema = Interface
    field_names = []
    label = 'Unlink an upstream project'
    page_title = label

    @action('Unlink')
    def unlink(self, action, data):
        old_series = self.context.productseries
        if self.context.direct_packaging is not None:
            getUtility(IPackagingUtil).deletePackaging(
                self.context.productseries,
                self.context.sourcepackagename,
                self.context.distroseries)
            self.request.response.addInfoNotification(
                'Removed upstream association between %s and %s.' % (
                old_series.title, self.context.distroseries.displayname))
        else:
            self.request.response.addInfoNotification(
                'The packaging link has already been deleted.')


class SourcePackageView(LaunchpadView):
    """A view for (distro series) source packages."""

    def initialize(self):
        # lets add a widget for the product series to which this package is
        # mapped in the Packaging table
        raw_field = IPackaging['productseries']
        bound_field = raw_field.bind(self.context)
        self.productseries_widget = getMultiAdapter(
            (bound_field, self.request), IInputWidget)
        self.productseries_widget.setRenderedValue(self.context.productseries)
        # List of languages the user is interested on based on their browser,
        # IP address and launchpad preferences.
        self.status_message = None
        self.error_message = None
        self.processForm()

    @property
    def label(self):
        return self.context.title

    @property
    def cancel_url(self):
        return canonical_url(self.context)

    def processForm(self):
        # look for an update to any of the things we track
        form = self.request.form
        if 'packaging' in form:
            if self.productseries_widget.hasValidInput():
                new_ps = self.productseries_widget.getInputValue()
                # we need to create or update the packaging
                self.context.setPackaging(new_ps, self.user)
                self.productseries_widget.setRenderedValue(new_ps)
                self.request.response.addInfoNotification(
                    'Upstream link updated, thank you!')
                self.request.response.redirect(canonical_url(self.context))
            else:
                self.error_message = structured('Invalid series given.')

    def published_by_pocket(self):
        """This morfs the results of ISourcePackage.published_by_pocket into
        something easier to parse from a page template. It becomes a list of
        dictionaries, sorted in dbschema item order, each representing a
        pocket and the packages in it."""
        result = []
        thedict = self.context.published_by_pocket
        for pocket in PackagePublishingPocket.items:
            newdict = {'pocketdetails': pocket}
            newdict['packages'] = thedict[pocket]
            result.append(newdict)
        return result

    def binaries(self):
        """Format binary packages into binarypackagename and archtags"""
        results = {}
        all_arch = sorted([arch.architecturetag for arch in
                           self.context.distroseries.architectures])
        for bin in self.context.currentrelease.binaries:
            distroarchseries = bin.build.distro_arch_series
            if bin.name not in results:
                results[bin.name] = []

            if bin.architecturespecific:
                results[bin.name].append(distroarchseries.architecturetag)
            else:
                results[bin.name] = all_arch
            results[bin.name].sort()

        return results

    def _relationship_parser(self, content):
        """Wrap the relationship_builder for SourcePackages.

        Define apt_pkg.parse_src_depends as a relationship 'parser' and
        IDistroSeries.getBinaryPackage as 'getter'.
        """
        getter = self.context.distroseries.getBinaryPackage
        parser = parse_src_depends
        return relationship_builder(content, parser=parser, getter=getter)

    @property
    def builddepends(self):
        return self._relationship_parser(
            self.context.currentrelease.builddepends)

    @property
    def builddependsindep(self):
        return self._relationship_parser(
            self.context.currentrelease.builddependsindep)

    @property
    def build_conflicts(self):
        return self._relationship_parser(
            self.context.currentrelease.build_conflicts)

    @property
    def build_conflicts_indep(self):
        return self._relationship_parser(
            self.context.currentrelease.build_conflicts_indep)

    def requestCountry(self):
        return ICountry(self.request, None)

    def browserLanguages(self):
        return browser_languages(self.request)

    @property
    def potemplates(self):
        return list(self.context.getCurrentTranslationTemplates())


class SourcePackageAssociationPortletView(LaunchpadFormView):
    """A view for linking to an upstream package."""

    schema = Interface
    custom_widget(
        'upstream', LaunchpadRadioWidget, orientation='vertical')
    product_suggestions = None
    initial_focus_widget = None
    max_suggestions = 9
    other_upstream = object()
    register_upstream = object()

    def setUpFields(self):
        """See `LaunchpadFormView`."""
        super(SourcePackageAssociationPortletView, self).setUpFields()
        self.request.annotations['show_edit_buttons'] = True
        # Find registered products that are similarly named to the source
        # package.
        product_vocab = getVocabularyRegistry().get(None, 'Product')
        matches = product_vocab.searchForTerms(self.context.name,
            vocab_filter=[Product._information_type ==
                          InformationType.PUBLIC])
        # Based upon the matching products, create a new vocabulary with
        # term descriptions that include a link to the product.
        self.product_suggestions = []
        vocab_terms = []
        for item in matches[:self.max_suggestions]:
            product = item.value
            self.product_suggestions.append(product)
            item_url = canonical_url(product)
            description = structured(
                '<a href="%s">%s</a>', item_url, product.displayname)
            vocab_terms.append(SimpleTerm(product, product.name, description))
        # Add an option to represent the user's decision to choose a
        # different project. Note that project names cannot be uppercase.
        vocab_terms.append(
            SimpleTerm(self.other_upstream, 'OTHER_UPSTREAM',
                       'Choose another upstream project'))
        vocab_terms.append(
            SimpleTerm(self.register_upstream, 'REGISTER_UPSTREAM',
                       'Register the upstream project'))
        upstream_vocabulary = SimpleVocabulary(vocab_terms)

        self.form_fields = Fields(
            Choice(__name__='upstream',
                   title=_('Registered upstream project'),
                   default=self.other_upstream,
                   vocabulary=upstream_vocabulary,
                   required=True))

    @action('Link to Upstream Project', name='link')
    def link(self, action, data):
        upstream = data.get('upstream')
        if upstream is self.other_upstream:
            # The user wants to link to an alternate upstream project.
            self.next_url = canonical_url(
                self.context, view_name="+edit-packaging")
            return
        elif upstream is self.register_upstream:
            # The user wants to create a new project.
            url = get_register_upstream_url(self.context)
            self.request.response.redirect(url)
            return
        self.context.setPackaging(upstream.development_focus, self.user)
        self.request.response.addInfoNotification(
            'The project %s was linked to this source package.' %
            upstream.displayname)
        self.next_url = self.request.getURL()


class PackageUpstreamTracking(EnumeratedType):
    """The state of the package's tracking of the upstream version."""

    NONE = Item("""
        None

        There is not enough information to compare the current package version
        to the upstream version.
        """)

    CURRENT = Item("""
        Current version

        The package version is the current upstream version.
        """)

    OLDER = Item("""
        Older upstream version

        The upstream version is older than the package version. Launchpad
        Launchpad is missing upstream data.
        """)

    NEWER = Item("""
        Newer upstream version

        The upstream version is newer than the package version. The package
        can be updated to the upstream version.
        """)


class SourcePackageUpstreamConnectionsView(LaunchpadView):
    """A shared view with upstream connection info."""

    @property
    def has_bugtracker(self):
        """Does the product have a bugtracker set?"""
        if self.context.productseries is None:
            return False
        product = self.context.productseries.product
        if product.bug_tracking_usage == ServiceUsage.LAUNCHPAD:
            return True
        bugtracker = product.bugtracker
        if bugtracker is None:
            if product.project is not None:
                bugtracker = product.project.bugtracker
        if bugtracker is None:
            return False
        return True

    @property
    def current_release_tracking(self):
        """The PackageUpstreamTracking state for the current release."""
        upstream_release = self.context.productseries.getLatestRelease()
        current_release = self.context.currentrelease
        if upstream_release is None or current_release is None:
            # Launchpad is missing data. There is not enough information to
            # track releases.
            return PackageUpstreamTracking.NONE
        # Compare the base version contained in the full debian version
        # to upstream release's version.
        base_version = upstream_version(current_release.version)
        age = version_compare(upstream_release.version, base_version)
        if age > 0:
            return PackageUpstreamTracking.NEWER
        elif age < 0:
            return PackageUpstreamTracking.OLDER
        else:
            # age == 0:
            return PackageUpstreamTracking.CURRENT
