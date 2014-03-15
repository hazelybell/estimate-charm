# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Browser code for PO templates."""

__metaclass__ = type

__all__ = [
    'POTemplateAdminView',
    'POTemplateBreadcrumb',
    'POTemplateEditView',
    'POTemplateFacets',
    'POTemplateExportView',
    'POTemplateMenu',
    'POTemplateNavigation',
    'POTemplateSetNavigation',
    'POTemplateSubsetNavigation',
    'POTemplateSubsetURL',
    'POTemplateSubsetView',
    'POTemplateURL',
    'POTemplateUploadView',
    'POTemplateView',
    'POTemplateViewPreferred',
    'BaseSeriesTemplatesView',
    ]

import datetime
import operator
import os.path

from lazr.restful.utils import smartquote
import pytz
from storm.expr import (
    And,
    Or,
    )
from storm.info import ClassAlias
from zope.component import getUtility
from zope.interface import implements
from zope.publisher.browser import FileUpload
from zope.security.proxy import removeSecurityProxy

from lp import _
from lp.app.browser.launchpadform import (
    action,
    LaunchpadEditFormView,
    ReturnToReferrerMixin,
    )
from lp.app.browser.tales import DateTimeFormatterAPI
from lp.app.enums import (
    service_uses_launchpad,
    ServiceUsage,
    )
from lp.app.errors import NotFoundError
from lp.app.validators.name import valid_name
from lp.registry.browser.productseries import ProductSeriesFacets
from lp.registry.browser.sourcepackage import SourcePackageFacets
from lp.registry.interfaces.productseries import IProductSeries
from lp.registry.interfaces.role import IPersonRoles
from lp.registry.interfaces.sourcepackage import ISourcePackage
from lp.registry.model.packaging import Packaging
from lp.registry.model.product import Product
from lp.registry.model.productseries import ProductSeries
from lp.registry.model.sourcepackagename import SourcePackageName
from lp.services.helpers import is_tar_filename
from lp.services.webapp import (
    canonical_url,
    enabled_with_permission,
    GetitemNavigation,
    Link,
    Navigation,
    NavigationMenu,
    StandardLaunchpadFacets,
    )
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.breadcrumb import Breadcrumb
from lp.services.webapp.escaping import (
    html_escape,
    structured,
    )
from lp.services.webapp.interfaces import (
    ICanonicalUrlData,
    ILaunchBag,
    )
from lp.services.webapp.publisher import (
    LaunchpadView,
    RedirectionView,
    )
from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.translations.browser.poexportrequest import BaseExportView
from lp.translations.browser.translations import TranslationsMixin
from lp.translations.browser.translationsharing import (
    TranslationSharingDetailsMixin,
    )
from lp.translations.interfaces.pofile import IPOFileSet
from lp.translations.interfaces.potemplate import (
    IPOTemplate,
    IPOTemplateSet,
    IPOTemplateSubset,
    )
from lp.translations.interfaces.side import TranslationSide
from lp.translations.interfaces.translationimporter import (
    ITranslationImporter,
    )
from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    )
from lp.translations.model.potemplate import POTemplate


class POTemplateNavigation(Navigation):

    usedfor = IPOTemplate

    def traverse(self, name):
        """Return the IPOFile associated with the given name."""

        assert self.request.method in ['GET', 'HEAD', 'POST'], (
            'We only know about GET, HEAD, and POST')

        user = getUtility(ILaunchBag).user

        # We do not want users to see the 'en' potemplate because
        # we store the messages we want to translate as English.
        if name == 'en':
            raise NotFoundError(name)

        pofile = self.context.getPOFileByLang(name)

        if pofile is not None:
            # Already have a valid POFile entry, just return it.
            return pofile
        elif self.request.method in ['GET', 'HEAD']:
            # It's just a query, get a fake one so we don't create new
            # POFiles just because someone is browsing the web.
            language = getUtility(ILanguageSet).getLanguageByCode(name)
            if language is None:
                raise NotFoundError(name)
            return self.context.getDummyPOFile(
                language, requester=user, check_for_existing=False)
        else:
            # It's a POST.
            # XXX CarlosPerelloMarin 2006-04-20 bug=40275: We should
            # check the kind of POST we got.  A logout will also be a
            # POST and we should not create a POFile in that case.
            return self.context.newPOFile(name, owner=user)


class POTemplateFacets(StandardLaunchpadFacets):
    usedfor = IPOTemplate

    def __init__(self, context):
        StandardLaunchpadFacets.__init__(self, context)
        target = context.translationtarget
        if IProductSeries.providedBy(target):
            self._is_product_series = True
            self.target_facets = ProductSeriesFacets(target)
        elif ISourcePackage.providedBy(target):
            self._is_product_series = False
            self.target_facets = SourcePackageFacets(target)
        else:
            # We don't know yet how to handle this target.
            raise NotImplementedError

        # Enable only the menus that the translation target uses.
        self.enable_only = self.target_facets.enable_only

        # From an IPOTemplate URL, we reach its translationtarget (either
        # ISourcePackage or IProductSeries using self.target.
        self.target = '../../'

    def overview(self):
        overview_link = self.target_facets.overview()
        overview_link.target = self.target
        return overview_link

    def translations(self):
        translations_link = self.target_facets.translations()
        translations_link.target = self.target
        return translations_link

    def bugs(self):
        bugs_link = self.target_facets.bugs()
        bugs_link.target = self.target
        return bugs_link

    def answers(self):
        answers_link = self.target_facets.answers()
        answers_link.target = self.target
        return answers_link

    def specifications(self):
        specifications_link = self.target_facets.specifications()
        specifications_link.target = self.target
        return specifications_link

    def branches(self):
        branches_link = self.target_facets.branches()
        if not self._is_product_series:
            branches_link.target = self.target
        return branches_link


class POTemplateMenu(NavigationMenu):
    """Navigation menus for `IPOTemplate` objects."""
    usedfor = IPOTemplate
    facet = 'translations'
    # XXX: henninge 2009-04-22 bug=365112: The order in this list was
    # rearranged so that the last item is public. The desired order is:
    # links = ['overview', 'upload', 'download', 'edit', 'administer']
    links = ['overview', 'edit', 'administer', 'upload', 'download']

    def overview(self):
        text = 'Overview'
        return Link('', text)

    @enabled_with_permission('launchpad.Edit')
    def upload(self):
        text = 'Upload'
        return Link('+upload', text, icon='add')

    def download(self):
        text = 'Download'
        return Link('+export', text, icon='download')

    @enabled_with_permission('launchpad.Edit')
    def edit(self):
        text = 'Edit'
        return Link('+edit', text, icon='edit')

    @enabled_with_permission('launchpad.TranslationsAdmin')
    def administer(self):
        text = 'Administer'
        return Link('+admin', text, icon='edit')


class POTemplateSubsetView(RedirectionView):

    def __init__(self, context, request):
        super(POTemplateSubsetView, self).__init__(
            '../+translations', request)


class POTemplateView(LaunchpadView,
                     TranslationsMixin, TranslationSharingDetailsMixin):

    SHOW_RELATED_TEMPLATES = 4

    label = "Translation status"

    def initialize(self):
        """Get the requested languages and submit the form."""
        self.description = self.context.description

    def requestPoFiles(self):
        """Yield a POFile or DummyPOFile for each of the languages in the
        request, which includes country languages from the request IP,
        browser preferences, and/or personal Launchpad language prefs.
        """
        for language in self._sortLanguages(self.translatable_languages):
            yield self._getPOFileOrDummy(language)

    def num_messages(self):
        N = self.context.messageCount()
        if N == 0:
            return "no messages at all"
        elif N == 1:
            return "1 message"
        else:
            return "%s messages" % N

    def pofiles(self, preferred_only=False):
        """Iterate languages shown when viewing this PO template.

        Yields a POFileView object for each language this template has
        been translated into, and for each of the user's languages.
        Where the template has no POFile for that language, we use
        a DummyPOFile.
        """
        # This inline import is needed to workaround a circular import problem
        # because lp.translations.browser.pofile imports
        # lp.translations.browser.potemplate.
        from lp.translations.browser.pofile import POFileView

        languages = self.translatable_languages
        if not preferred_only:
            # Union the languages the template has been translated into with
            # the user's selected languages.
            languages = set(self.context.languages()) | set(languages)

        for language in self._sortLanguages(languages):
            pofile = self._getPOFileOrDummy(language)
            pofileview = POFileView(pofile, self.request)
            # Initialize the view.
            pofileview.initialize()
            yield pofileview

    @property
    def group_parent(self):
        """Return a parent object implementing `ITranslationPolicy`."""
        if self.context.productseries is not None:
            return self.context.productseries.product
        else:
            return self.context.distroseries.distribution

    @property
    def has_translation_documentation(self):
        """Are there translation instructions for this project."""
        translation_group = self.group_parent.translationgroup
        return (translation_group is not None and
                translation_group.translation_guide_url is not None)

    @property
    def related_templates_by_source(self):
        by_source = list(
            self.context.relatives_by_source[:self.SHOW_RELATED_TEMPLATES])
        return by_source

    @property
    def more_templates_by_source_link(self):
        by_source_count = self.context.relatives_by_source.count()
        if (by_source_count > self.SHOW_RELATED_TEMPLATES):
            other = by_source_count - self.SHOW_RELATED_TEMPLATES
            if (self.context.distroseries):
                sourcepackage = self.context.distroseries.getSourcePackage(
                    self.context.sourcepackagename)
                url = canonical_url(
                    sourcepackage, rootsite="translations",
                    view_name='+translations')
            else:
                url = canonical_url(
                    self.context.productseries,
                    rootsite="translations",
                    view_name="+templates")
            if other == 1:
                return " and <a href=\"%s\">one other template</a>" % url
            else:
                return " and <a href=\"%s\">%d other templates</a>" % (
                    url, other)
        else:
            return ""

    @property
    def has_pofiles(self):
        languages = set(
            self.context.languages()).union(self.translatable_languages)
        return len(languages) > 0

    def _sortLanguages(self, languages):
        return sorted(languages, key=operator.attrgetter('englishname'))

    def _getPOFileOrDummy(self, language):
        pofile = self.context.getPOFileByLang(language.code)
        if pofile is None:
            pofileset = getUtility(IPOFileSet)
            pofile = pofileset.getDummy(self.context, language)
        return pofile

    @property
    def is_upstream_template(self):
        return self.context.translation_side == TranslationSide.UPSTREAM

    def is_sharing(self):
        potemplate = self.context.getOtherSidePOTemplate()
        return potemplate is not None

    @property
    def sharing_template(self):
        return self.context.getOtherSidePOTemplate()

    def getTranslationSourcePackage(self):
        """See `TranslationSharingDetailsMixin`."""
        if self.is_upstream_template:
            productseries = self.context.productseries
            return productseries.getUbuntuTranslationFocusPackage()
        else:
            return self.context.sourcepackage


class POTemplateUploadView(LaunchpadView, TranslationsMixin):
    """Upload translations and updated template."""

    label = "Upload translations"
    page_title = "Upload translations"

    @property
    def cancel_url(self):
        return canonical_url(self.context)

    def initialize(self):
        """Get the requested languages and submit the form."""
        self.submitForm()

    def submitForm(self):
        """Process any uploaded files."""

        if self.request.method == 'POST':
            if 'UPLOAD' in self.request.form:
                self.upload()

    def upload(self):
        """Handle a form submission to change the contents of the template.

        Uploads may fail if there are already entries with the same path name
        and uploader (importer) in the queue and the new upload cannot be
        safely matched to any of them.  The user will be informed about the
        failure with a warning message."""
        # XXX henninge 20008-12-03 bug=192925: This code is duplicated for
        # productseries and pofile and should be unified.
        file = self.request.form.get('file')
        if not isinstance(file, FileUpload):
            if not file:
                self.request.response.addErrorNotification(
                    "Your upload was ignored because you didn't select a "
                    "file. Please select a file and try again.")
            else:
                # XXX: Carlos Perello Marin 2004-12-30 bug=116:
                # Epiphany seems to have an unpredictable bug with upload
                # forms (or perhaps it's launchpad because I never had
                # problems with bugzilla). The fact is that some uploads don't
                # work and we get a unicode object instead of a file-like
                # object in "file". We show an error if we see that behaviour.
                self.request.response.addErrorNotification(
                    "Your upload failed because there was a problem receiving"
                    " data. Please try again.")
            return

        filename = file.filename
        content = file.read()

        if len(content) == 0:
            self.request.response.addWarningNotification(
                "Ignored your upload because the uploaded file is empty.")
            return

        translation_import_queue = getUtility(ITranslationImportQueue)
        root, ext = os.path.splitext(filename)
        translation_importer = getUtility(ITranslationImporter)
        if ext in translation_importer.supported_file_extensions:
            # Add it to the queue.
            entry = translation_import_queue.addOrUpdateEntry(
                filename, content, True, self.user,
                sourcepackagename=self.context.sourcepackagename,
                distroseries=self.context.distroseries,
                productseries=self.context.productseries,
                potemplate=self.context)

            if entry is None:
                self.request.response.addWarningNotification(
                    "Upload failed.  The name of the file you "
                    "uploaded matched multiple existing "
                    "uploads, for different templates.  This makes it "
                    "impossible to determine which template the new "
                    "upload was for.  Try uploading to a specific "
                    "template: visit the page for the template that you "
                    "want to upload to, and select the upload option "
                    "from there.")
            else:
                self.request.response.addInfoNotification(
                    structured(
                    'Thank you for your upload.  It will be automatically '
                    'reviewed in the next few hours.  If that is not '
                    'enough to determine whether and where your file '
                    'should be imported, it will be reviewed manually by an '
                    'administrator in the coming few days.  You can track '
                    'your upload\'s status in the '
                    '<a href="%s/+imports">Translation Import Queue</a>',
                        canonical_url(self.context.translationtarget)))

        elif is_tar_filename(filename):
            # Add the whole tarball to the import queue.
            (num, conflicts) = (
                translation_import_queue.addOrUpdateEntriesFromTarball(
                    content, True, self.user,
                    sourcepackagename=self.context.sourcepackagename,
                    distroseries=self.context.distroseries,
                    productseries=self.context.productseries,
                    potemplate=self.context))

            if num > 0:
                if num == 1:
                    plural_s = ''
                    itthey = 'it'
                else:
                    plural_s = 's'
                    itthey = 'they'
                self.request.response.addInfoNotification(
                    structured(
                    'Thank you for your upload. %s file%s from the tarball '
                    'will be automatically '
                    'reviewed in the next few hours.  If that is not enough '
                    'to determine whether and where your file%s should '
                    'be imported, %s will be reviewed manually by an '
                    'administrator in the coming few days.  You can track '
                    'your upload\'s status in the '
                    '<a href="%s/+imports">Translation Import Queue</a>',
                    num, plural_s, plural_s, itthey,
                    canonical_url(self.context.translationtarget)))
                if len(conflicts) > 0:
                    if len(conflicts) == 1:
                        warning = (
                            "A file could not be uploaded because its "
                            "name matched multiple existing uploads, for "
                            "different templates.")
                        ul_conflicts = structured(
                            "The conflicting file name was:<br /> "
                            "<ul><li>%s</li></ul>", conflicts[0])
                    else:
                        warning = structured(
                            "%s files could not be uploaded because their "
                            "names matched multiple existing uploads, for "
                            "different templates.", len(conflicts))
                        conflict_str = structured(
                            "</li><li>".join(["%s" % len(conflicts)]),
                            *conflicts)
                        ul_conflicts = structured(
                            "The conflicting file names were:<br /> "
                            "<ul><li>%s</li></ul>", conflict_str)
                    self.request.response.addWarningNotification(
                        structured(
                        "%s  This makes it "
                        "impossible to determine which template the new "
                        "upload was for.  Try uploading to a specific "
                        "template: visit the page for the template that you "
                        "want to upload to, and select the upload option "
                        "from there.<br />%s", warning, ul_conflicts))
            else:
                if len(conflicts) == 0:
                    self.request.response.addWarningNotification(
                        "Upload ignored.  The tarball you uploaded did not "
                        "contain any files that the system recognized as "
                        "translation files.")
                else:
                    self.request.response.addWarningNotification(
                        "Upload failed.  One or more of the files you "
                        "uploaded had names that matched multiple existing "
                        "uploads, for different templates.  This makes it "
                        "impossible to determine which template the new "
                        "upload was for.  Try uploading to a specific "
                        "template: visit the page for the template that you "
                        "want to upload to, and select the upload option "
                        "from there.")
        else:
            self.request.response.addWarningNotification(
                "Upload failed because the file you uploaded was not"
                " recognised as a file that can be imported.")


class POTemplateViewPreferred(POTemplateView):
    """View class that shows only users preferred templates."""

    def pofiles(self):
        return POTemplateView.pofiles(self, preferred_only=True)


class POTemplateEditView(ReturnToReferrerMixin, LaunchpadEditFormView):
    """View class that lets you edit a POTemplate object."""

    schema = IPOTemplate
    label = 'Edit translation template details'
    page_title = 'Edit details'
    PRIORITY_MIN_VALUE = 0
    PRIORITY_MAX_VALUE = 100000

    @property
    def field_names(self):
        field_names = [
            'name', 'translation_domain', 'description', 'priority',
            'path', 'iscurrent']
        if self.context.distroseries:
            field_names.extend([
                'sourcepackagename',
                'languagepack',
                ])
        else:
            field_names.append('owner')
        return field_names

    @property
    def _return_url(self):
        # We override the ReturnToReferrerMixin _return_url because it might
        # change when any of the productseries, distroseries,
        # sourcepackagename or name attributes change, and the basic version
        # only supports watching changes to a single attribute.

        # The referer header is a hidden input in the form.
        referrer = self.request.form.get('_return_url')
        returnChanged = False
        if referrer is None:
            # "referer" is misspelled in the HTTP specification.
            referrer = self.request.getHeader('referer')
            # If we were looking at the actual template, we want a new
            # URL constructed.
            if referrer is not None and '/+pots/' in referrer:
                returnChanged = True

        if (referrer is not None
            and not returnChanged
            and referrer.startswith(self.request.getApplicationURL())
            and referrer != self.request.getHeader('location')):
            return referrer
        else:
            return canonical_url(self.context)

    @action(_('Change'), name='change')
    def change_action(self, action, data):
        context = self.context
        iscurrent = data.get('iscurrent', context.iscurrent)
        context.setActive(iscurrent)
        old_description = context.description
        old_translation_domain = context.translation_domain
        self.updateContextFromData(data)
        if old_description != context.description:
            self.user.assignKarma(
                'translationtemplatedescriptionchanged',
                product=context.product, distribution=context.distribution,
                sourcepackagename=context.sourcepackagename)
        if old_translation_domain != context.translation_domain:
            # We only change date_last_updated when the translation_domain
            # field is changed because it is the only relevant field we
            # care about regarding the date of last update.
            naked_context = removeSecurityProxy(context)
            naked_context.date_last_updated = datetime.datetime.now(pytz.UTC)

    def _validateTargetAndGetTemplates(self, data):
        """Return a POTemplateSubset corresponding to the chosen target."""
        sourcepackagename = data.get('sourcepackagename',
                                     self.context.sourcepackagename)
        return getUtility(IPOTemplateSet).getSubset(
            distroseries=self.context.distroseries,
            sourcepackagename=sourcepackagename,
            productseries=self.context.productseries)

    def validate(self, data):
        name = data.get('name', None)
        if name is None or not valid_name(name):
            self.setFieldError(
                'name',
                'Template name can only start with lowercase letters a-z '
                'or digits 0-9, and other than those characters, can only '
                'contain "-", "+" and "." characters.')

        distroseries = data.get('distroseries', self.context.distroseries)
        sourcepackagename = data.get(
            'sourcepackagename', self.context.sourcepackagename)
        productseries = data.get('productseries', None)
        sourcepackage_changed = (
            distroseries is not None and
            (distroseries != self.context.distroseries or
             sourcepackagename != self.context.sourcepackagename))
        productseries_changed = (productseries is not None and
                                 productseries != self.context.productseries)
        similar_templates = self._validateTargetAndGetTemplates(data)
        if similar_templates is not None:
            self.validateName(
                name, similar_templates, sourcepackage_changed,
                productseries_changed)
            self.validateDomain(
                data.get('translation_domain'), similar_templates,
                sourcepackage_changed, productseries_changed)

        priority = data.get('priority')
        if priority is None:
            return

        if (priority < self.PRIORITY_MIN_VALUE or
            priority > self.PRIORITY_MAX_VALUE):
            self.setFieldError(
                'priority',
                'The priority value must be between %s and %s.' % (
                self.PRIORITY_MIN_VALUE, self.PRIORITY_MAX_VALUE))

    def validateName(self, name, similar_templates,
                     sourcepackage_changed, productseries_changed):
        """Check that the name does not clash with an existing template."""
        if similar_templates.getPOTemplateByName(name) is not None:
            if sourcepackage_changed:
                self.setFieldError(
                    'sourcepackagename',
                    "Source package already has a template with "
                    "that same name.")
            elif productseries_changed:
                self.setFieldError(
                    'productseries',
                    "Series already has a template with that same name.")
            elif name != self.context.name:
                self.setFieldError('name', "Name is already in use.")

    def validateDomain(self, domain, similar_templates,
                       sourcepackage_changed, productseries_changed):
        clashes = similar_templates.getPOTemplatesByTranslationDomain(domain)
        if not clashes.is_empty():
            if sourcepackage_changed:
                self.setFieldError(
                    'sourcepackagename',
                    "Source package already has a template with "
                    "that same domain.")
            elif productseries_changed:
                self.setFieldError(
                    'productseries',
                    "Series already has a template with that same domain.")
            elif domain != self.context.translation_domain:
                self.setFieldError(
                    'translation_domain', "Domain is already in use.")

    @property
    def _return_attribute_name(self):
        """See 'ReturnToReferrerMixin'."""
        return "name"


class POTemplateAdminView(POTemplateEditView):
    """View class that lets you admin a POTemplate object."""
    field_names = [
        'name', 'translation_domain', 'description', 'header', 'iscurrent',
        'owner', 'productseries', 'distroseries', 'sourcepackagename',
        'from_sourcepackagename', 'sourcepackageversion', 'binarypackagename',
        'languagepack', 'path', 'source_file_format', 'priority',
        'date_last_updated']
    label = 'Administer translation template'
    page_title = "Administer"

    def _validateTargetAndGetTemplates(self, data):
        """Return a POTemplateSubset corresponding to the chosen target."""
        distroseries = data.get('distroseries')
        sourcepackagename = data.get('sourcepackagename')
        productseries = data.get('productseries')

        if distroseries is not None and productseries is not None:
            message = ("Choose a distribution release series or a project "
                "release series, but not both.")
        elif distroseries is None and productseries is None:
            message = ("Choose either a distribution release series or a "
                "project release series.")
        else:
            message = None

        if message is not None:
            self.addError(message)
            return None
        return getUtility(IPOTemplateSet).getSubset(
            distroseries=distroseries, sourcepackagename=sourcepackagename,
            productseries=productseries)


class POTemplateExportView(BaseExportView):
    """Request downloads of a `POTemplate` and its translations."""

    label = "Download translations"
    page_title = "Download translations"

    @property
    def cancel_url(self):
        return canonical_url(self.context)

    def processForm(self):
        """Process a form submission requesting a translation export."""
        what = self.request.form.get('what')
        if what == 'all':
            export_potemplate = True

            pofiles = self.context.pofiles
        elif what == 'some':
            pofiles = []
            export_potemplate = 'potemplate' in self.request.form

            for code in self.request.form:
                pofile = self.context.getPOFileByLang(code)
                if pofile is not None:
                    pofiles.append(pofile)
        else:
            self.request.response.addErrorNotification(
                'Please choose whether you would like all files or only some '
                'of them.')
            return

        if export_potemplate:
            requested_templates = [self.context]
        else:
            requested_templates = None

        return (requested_templates, pofiles)

    def pofiles(self):
        """Return a list of PO files available for export."""

        class BrowserPOFile:

            def __init__(self, value, browsername):
                self.value = value
                self.browsername = browsername

        def pofile_sort_key(pofile):
            return pofile.language.englishname

        for pofile in sorted(self.context.pofiles, key=pofile_sort_key):
            value = pofile.getFullLanguageCode()
            browsername = pofile.getFullLanguageName()

            yield BrowserPOFile(value, browsername)

    def getDefaultFormat(self):
        return self.context.source_file_format


class POTemplateSubsetURL:
    implements(ICanonicalUrlData)

    rootsite = 'mainsite'

    def __init__(self, context):
        self.context = context

    @property
    def path(self):
        potemplatesubset = self.context
        if potemplatesubset.distroseries is not None:
            assert potemplatesubset.productseries is None
            assert potemplatesubset.sourcepackagename is not None
            return '+source/%s/+pots' % (
                potemplatesubset.sourcepackagename.name)
        else:
            assert potemplatesubset.productseries is not None
            return '+pots'

    @property
    def inside(self):
        potemplatesubset = self.context
        if potemplatesubset.distroseries is not None:
            assert potemplatesubset.productseries is None
            return potemplatesubset.distroseries
        else:
            assert potemplatesubset.productseries is not None
            return potemplatesubset.productseries


class POTemplateURL:
    implements(ICanonicalUrlData)

    rootsite = 'translations'

    def __init__(self, context):
        self.context = context
        potemplate = self.context
        potemplateset = getUtility(IPOTemplateSet)
        if potemplate.distroseries is not None:
            assert potemplate.productseries is None
            self.potemplatesubset = potemplateset.getSubset(
                distroseries=potemplate.distroseries,
                sourcepackagename=potemplate.sourcepackagename)
        else:
            assert potemplate.productseries is not None
            self.potemplatesubset = potemplateset.getSubset(
                productseries=potemplate.productseries)

    @property
    def path(self):
        potemplate = self.context
        return potemplate.name

    @property
    def inside(self):
        return self.potemplatesubset


class POTemplateSetNavigation(GetitemNavigation):

    usedfor = IPOTemplateSet


class POTemplateSubsetNavigation(Navigation):

    usedfor = IPOTemplateSubset

    def traverse(self, name):
        """Return the IPOTemplate associated with the given name."""

        assert self.request.method in ['GET', 'HEAD', 'PATCH', 'POST'], (
            'We only know about GET, HEAD, PATCH and POST')

        # Get the requested potemplate.
        potemplate = self.context.getPOTemplateByName(name)
        if potemplate is None:
            # The template doesn't exist.
            raise NotFoundError(name)

        # Get whether the target for the requested template is officially
        # using Launchpad Translations.
        if potemplate.distribution is None:
            product_or_distro = potemplate.productseries.product
        else:
            product_or_distro = potemplate.distroseries.distribution
        translations_usage = product_or_distro.translations_usage

        if (service_uses_launchpad(translations_usage) and
           potemplate.iscurrent):
            # This template is available for translation.
            return potemplate
        elif check_permission('launchpad.TranslationsAdmin', potemplate):
            # User has Edit privileges for this template and can access it.
            return potemplate
        else:
            raise NotFoundError(name)


class POTemplateBreadcrumb(Breadcrumb):
    """Breadcrumb for `IPOTemplate`."""

    @property
    def text(self):
        return smartquote('Template "%s"' % self.context.name)


class BaseSeriesTemplatesView(LaunchpadView):
    """Show a list of all templates for the Series."""

    is_distroseries = True
    distroseries = None
    productseries = None
    label = "Translation templates"
    page_title = "All templates"
    can_edit = None
    can_admin = None

    def initialize(self, series, is_distroseries=True):
        self._template_name_cache = {}
        self._packaging_cache = {}
        self.is_distroseries = is_distroseries
        if is_distroseries:
            self.distroseries = series
        else:
            self.productseries = series
        user = IPersonRoles(self.user, None)
        self.can_admin = (user is not None and
                          (user.in_admin or user.in_rosetta_experts))
        self.can_edit = (
            self.can_admin or
            check_permission('launchpad.TranslationsAdmin', series))

        self.user_is_logged_in = (self.user is not None)

    def iter_data(self):
        # If this is not a distroseries, then the query is much simpler.
        if not self.is_distroseries:
            potemplateset = getUtility(IPOTemplateSet)
            # The "shape" of the data returned by POTemplateSubset isn't quite
            # right so we have to run it through zip first.
            return zip(potemplateset.getSubset(
                productseries=self.productseries,
                distroseries=self.distroseries,
                ordered_by_names=True))

        # Otherwise we have to do more work, primarily for the "sharing"
        # column.
        OtherTemplate = ClassAlias(POTemplate)
        join = (self.context.getTemplatesCollection()
            .joinOuter(Packaging, And(
                Packaging.distroseries == self.context.id,
                Packaging.sourcepackagename ==
                    POTemplate.sourcepackagenameID))
            .joinOuter(ProductSeries,
                ProductSeries.id == Packaging.productseriesID)
            .joinOuter(Product, And(
                Product.id == ProductSeries.productID,
                Or(
                    Product.translations_usage == ServiceUsage.LAUNCHPAD,
                    Product.translations_usage == ServiceUsage.EXTERNAL)))
            .joinOuter(OtherTemplate, And(
                OtherTemplate.productseriesID == ProductSeries.id,
                OtherTemplate.name == POTemplate.name))
            .joinInner(SourcePackageName,
                SourcePackageName.id == POTemplate.sourcepackagenameID))

        return join.select(POTemplate, Packaging, ProductSeries, Product,
            OtherTemplate, SourcePackageName).order_by(
                SourcePackageName.name, POTemplate.priority, POTemplate.name)

    def rowCSSClass(self, template):
        if template.iscurrent:
            return "active-template"
        else:
            return "inactive-template"

    def _renderSourcePackage(self, template):
        """Render the `SourcePackageName` for `template`."""
        if self.is_distroseries:
            return html_escape(template.sourcepackagename.name)
        else:
            return None

    def _renderTemplateLink(self, template, url):
        """Render a link to `template`.

        :param template: The target `POTemplate`.
        :param url: The cached URL for `template`.
        :return: HTML for a link to `template`.
        """
        text = '<a href="%s">%s</a>' % (url, html_escape(template.name))
        if not template.iscurrent:
            text += ' (inactive)'
        return text

    def _renderSharing(self, template, packaging, productseries, upstream,
            other_template, sourcepackagename):
        """Render a link to `template`.

        :param template: The target `POTemplate`.
        :return: HTML for the "sharing" status of `template`.
        """
        # Testing is easier if we are willing to extract the sourcepackagename
        # from the template.
        if sourcepackagename is None:
            sourcepackagename = template.sourcepackagename
        # Build the edit link.
        escaped_source = html_escape(sourcepackagename.name)
        source_url = '+source/%s' % escaped_source
        details_url = source_url + '/+sharing-details'
        edit_link = (
            '<a class="sprite edit action-icon" href="%s">Edit</a>' %
            details_url)

        # If all the conditions are met for sharing...
        if packaging and upstream and other_template is not None:
            escaped_series = html_escape(productseries.name)
            escaped_template = html_escape(template.name)
            pot_url = ('/%s/%s/+pots/%s' %
                (escaped_source, escaped_series, escaped_template))
            return (edit_link + '<a href="%s">%s/%s</a>'
                % (pot_url, escaped_source, escaped_series))
        else:
            # Otherwise just say that the template isn't shared and give them
            # a link to change the sharing.
            return edit_link + 'not shared'

    def _renderLastUpdateDate(self, template):
        """Render a template's "last updated" column."""
        formatter = DateTimeFormatterAPI(template.date_last_updated)
        full_time = formatter.datetime()
        date = formatter.approximatedate()
        return ''.join([
            '<span class="sortkey">%s</span>' % full_time,
            '<span class="lastupdate_column" title="%s">%s</span>' % (
                full_time, date),
            ])

    def _renderAction(self, base_url, name, path, sprite, enabled):
        """Render an action for the "actions" column.

        :param base_url: The cached URL for `template`.
        :param name: Action name for display in the UI.
        :param path: Path suffix for the action (relative to `base_url`).
        :param sprite: Sprite class for the action.
        :param enabled: Show this action?  If not, return empty string.
        :return: HTML for the contents of the "actions" column.
        """
        if not enabled:
            return ''

        parameters = {
            'base_url': base_url,
            'name': name,
            'path': path,
            'sprite': sprite,
        }
        return (
            '<a class="sprite %(sprite)s" href="%(base_url)s/%(path)s">'
            '%(name)s'
            '</a>') % parameters

    def _renderActionsColumn(self, template, base_url):
        """Render a template's "actions" column."""
        if not self.user_is_logged_in:
            return None

        actions = [
            ('Edit', '+edit', 'edit', self.can_edit),
            ('Upload', '+upload', 'add', self.can_edit),
            ('Download', '+export', 'download', self.user_is_logged_in),
            ('Administer', '+admin', 'edit', self.can_admin),
        ]
        links = [
            self._renderAction(base_url, *action) for action in actions]
        html = '<div class="template_links">\n%s</div>'
        return html % '\n'.join(links)

    def _renderField(self, column_class, content, tag='td'):
        """Create a table field of the given class and contents.

        :param column_class: CSS class for this column.
        :param content: HTML to go into the column.  If None, the field
            will be omitted entirely.  (To produce an empty column, pass
            the empty string instead.)
        :param tag: The HTML tag to surround the field in.
        :return: HTML for the entire table field, or the empty string if
            `content` was None.
        """
        if content is None:
            return ''
        else:
            return '<%s class="%s">%s</%s>' % (
                tag, column_class, content, tag)

    def constructTemplateURL(self, template):
        """Build the URL for `template`.

        Since this is performance-critical, views are allowed to
        override it with optimized implementations.
        """
        return canonical_url(template)

    def renderTemplatesHeader(self):
        """Render HTML for the templates table header."""
        if self.is_distroseries:
            sourcepackage_header = "Source package"
        else:
            sourcepackage_header = None
        if self.user_is_logged_in:
            actions_header = "Actions"
        else:
            actions_header = None

        columns = [
            ('priority_column', "Priority"),
            ('sourcepackage_column', sourcepackage_header),
            ('template_column', "Template name"),
            ('length_column', "Length"),
            ('lastupdate_column', "Updated"),
            ('actions_column', actions_header),
            ]

        if self.is_distroseries:
            columns[3:3] = [('sharing', "Shared with")]

        return '\n'.join([
            self._renderField(css, text, tag='th')
            for (css, text) in columns])

    def renderTemplateRow(self, template, packaging=None, productseries=None,
            upstream=None, other_template=None, sourcepackagename=None):
        """Render HTML for an entire template row."""
        if not self.can_edit and not template.iscurrent:
            return ""

        # Cached URL for template.
        base_url = self.constructTemplateURL(template)

        fields = [
            ('priority_column', template.priority),
            ('sourcepackage_column', self._renderSourcePackage(template)),
            ('template_column', self._renderTemplateLink(template, base_url)),
            ('length_column', template.messagecount),
            ('lastupdate_column', self._renderLastUpdateDate(template)),
            ('actions_column', self._renderActionsColumn(template, base_url)),
        ]

        if self.is_distroseries:
            fields[3:3] = [(
                'sharing', self._renderSharing(template, packaging,
                    productseries, upstream, other_template,
                    sourcepackagename)
                )]

        tds = [self._renderField(*field) for field in fields]

        css = self.rowCSSClass(template)
        return '<tr class="template_row %s">\n%s</tr>\n' % (
            css, '\n'.join(tds))
