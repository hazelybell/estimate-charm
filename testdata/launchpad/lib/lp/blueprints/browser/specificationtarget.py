# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""ISpecificationTarget browser views."""

__metaclass__ = type

__all__ = [
    'HasSpecificationsMenuMixin',
    'HasSpecificationsView',
    'RegisterABlueprintButtonPortlet',
    'SpecificationAssignmentsView',
    'SpecificationDocumentationView',
    ]

from operator import itemgetter

from lazr.restful.utils import (
    safe_hasattr,
    smartquote,
    )
from z3c.ptcompat import ViewPageTemplateFile
from zope.component import (
    getMultiAdapter,
    queryMultiAdapter,
    )

from lp import _
from lp.app.enums import service_uses_launchpad
from lp.app.interfaces.launchpad import (
    IPrivacy,
    IServiceUsage,
    )
from lp.blueprints.enums import (
    SpecificationFilter,
    SpecificationSort,
    )
from lp.blueprints.interfaces.specificationtarget import ISpecificationTarget
from lp.blueprints.interfaces.sprint import ISprint
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.person import IPerson
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.productseries import IProductSeries
from lp.registry.interfaces.projectgroup import (
    IProjectGroup,
    IProjectGroupSeries,
    )
from lp.registry.interfaces.role import IHasDrivers
from lp.services.config import config
from lp.services.helpers import shortlist
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    LaunchpadView,
    )
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.batching import BatchNavigator
from lp.services.webapp.breadcrumb import Breadcrumb
from lp.services.webapp.menu import (
    enabled_with_permission,
    Link,
    )


class HasSpecificationsMenuMixin:

    def listall(self):
        """Return a link to show all blueprints."""
        text = 'List all blueprints'
        return Link('+specs?show=all', text, icon='blueprint')

    def listaccepted(self):
        """Return a link to show the approved goals."""
        text = 'List approved blueprints'
        return Link('+specs?acceptance=accepted', text, icon='blueprint')

    def listproposed(self):
        """Return a link to show the proposed goals."""
        text = 'List proposed blueprints'
        return Link('+specs?acceptance=proposed', text, icon='blueprint')

    def listdeclined(self):
        """Return a link to show the declined goals."""
        text = 'List declined blueprints'
        return Link('+specs?acceptance=declined', text, icon='blueprint')

    def doc(self):
        text = 'List documentation'
        return Link('+documentation', text, icon='info')

    def setgoals(self):
        """Return a link to set the series goals."""
        text = 'Set series goals'
        return Link('+setgoals', text, icon='edit')

    def assignments(self):
        """Return a link to show the people assigned to the blueprint."""
        text = 'Assignments'
        return Link('+assignments', text, icon='person')

    def new(self):
        """Return a link to register a blueprint."""
        text = 'Register a blueprint'
        return Link('+addspec', text, icon='add')

    @enabled_with_permission('launchpad.View')
    def register_sprint(self):
        text = 'Register a meeting'
        summary = 'Register a developer sprint, summit, or gathering'
        return Link('/sprints/+new', text, summary=summary, icon='add')


class HasSpecificationsView(LaunchpadView):
    """Base class for several context-specific views that involve lists of
    specifications.

    This base class knows how to handle and represent lists of
    specifications, produced by a method view.specs(). The individual class
    view objects each implement that method in a way that is appropriate for
    them, because they each want to filter the list of specs in different
    ways. For example, in the case of PersonSpecsView, you want to filter
    based on the relationship the person has to the specs. In the case of a
    ProductSpecsView you want to filter primarily based on the completeness
    of the spec.
    """

    # these flags set the default column display. subclasses will override
    # them to add or remove columns from the default
    show_assignee = True
    show_target = False
    show_series = False
    show_milestone = False
    show_design = True
    show_implementation = True
    show_priority = True

    # these flags govern some of the content of the spec page, which allows
    # us to vary the text flow slightly without creating large numbers of
    # template fragments
    is_person = False
    is_pillar = False
    is_target = False
    is_project = False
    is_series = False
    is_sprint = False
    has_wiki = False
    has_drivers = False

    # Templates for the various conditions of blueprints:
    # * On Launchpad
    # * External
    # * Disabled
    # * Unknown
    default_template = ViewPageTemplateFile(
        '../templates/hasspecifications-specs.pt')
    not_launchpad_template = ViewPageTemplateFile(
        '../templates/unknown-specs.pt')

    @property
    def template(self):
        # Check for the magical "index" added by the browser:page template
        # machinery. If it exists this is actually the
        # zope.browserpage.simpleviewclass.simple class that is magically
        # mixed in by the browser:page zcml directive the template defined in
        # the directive should be used.
        if safe_hasattr(self, 'index'):
            return super(HasSpecificationsView, self).template

        # Sprints and Persons don't have a usage enum for blueprints, so we
        # have to fallback to the default.
        if (ISprint.providedBy(self.context)
            or IPerson.providedBy(self.context)):
            return self.default_template

        # ProjectGroups are a special case, as their products may be a
        # combination of usage settings. To deal with this, check all
        # products via the involvment menu.
        if (IProjectGroup.providedBy(self.context)
            or IProjectGroupSeries.providedBy(self.context)):
            involvement = getMultiAdapter(
                (self.context, self.request),
                name='+get-involved')
            if service_uses_launchpad(involvement.blueprints_usage):
                return self.default_template
            else:
                return self.not_launchpad_template

        # Otherwise, determine usage and provide the correct template.
        service_usage = IServiceUsage(self.context)
        if service_uses_launchpad(service_usage.blueprints_usage):
            return self.default_template
        else:
            return self.not_launchpad_template

    def render(self):
        return self.template()

    # XXX: jsk: 2007-07-12 bug=173972: This method might be improved by
    # replacing the conditional execution with polymorphism.
    def initialize(self):
        if IPerson.providedBy(self.context):
            self.is_person = True
        elif IDistribution.providedBy(self.context):
            self.is_target = True
            self.is_pillar = True
            self.show_series = True
        elif IProduct.providedBy(self.context):
            self.is_target = True
            self.is_pillar = True
            self.has_wiki = True
            self.show_series = True
        elif IProjectGroup.providedBy(self.context):
            self.is_project = True
            self.is_pillar = True
            self.has_wiki = True
            self.show_target = True
            self.show_series = True
        elif IProjectGroupSeries.providedBy(self.context):
            self.show_milestone = True
            self.show_target = True
            self.show_series = True
        elif (IProductSeries.providedBy(self.context) or
              IDistroSeries.providedBy(self.context)):
            self.is_series = True
            self.show_milestone = True
        elif ISprint.providedBy(self.context):
            self.is_sprint = True
            self.show_target = True
        else:
            raise AssertionError('Unknown blueprint listing site.')

        if IHasDrivers.providedBy(self.context):
            self.has_drivers = True

        self.batchnav = BatchNavigator(
            self.specs, self.request,
            size=config.launchpad.default_batch_size)

    @property
    def can_configure_blueprints(self):
        """Can the user configure blueprints for the `ISpecificationTarget`.
        """
        target = self.context
        if IProduct.providedBy(target) or IDistribution.providedBy(target):
            return check_permission('launchpad.Edit', self.context)
        else:
            return False

    @property
    def label(self):
        mapping = {'name': self.context.displayname}
        if self.is_person:
            return _('Blueprints involving $name', mapping=mapping)
        else:
            return _('Blueprints for $name', mapping=mapping)

    page_title = 'Blueprints'

    @cachedproperty
    def has_any_specifications(self):
        return not self.context.visible_specifications.is_empty()

    @cachedproperty
    def all_specifications(self):
        return shortlist(self.context.all_specifications(self.user))

    @cachedproperty
    def searchrequested(self):
        return self.searchtext is not None

    @cachedproperty
    def searchtext(self):
        st = self.request.form.get('searchtext')
        if st is None:
            st = self.request.form.get('field.searchtext')
        return st

    @cachedproperty
    def spec_filter(self):
        """The list of specs that are going to be displayed in this view.

        This method determines the appropriate filtering to be passed to
        context.specifications(). See IHasSpecifications.specifications
        for further details.

        The method can review the URL and decide what will be included,
        and what will not.

        The typical URL is of the form:

           ".../name1/+specs?show=complete&informational&acceptance=accepted"

        This method will interpret the show= part based on the kind of
        object that is the context of this request.
        """
        show = self.request.form.get('show')
        acceptance = self.request.form.get('acceptance')
        role = self.request.form.get('role')
        informational = self.request.form.get('informational', False)

        filter = []

        # include text for filtering if it was given
        if self.searchtext is not None and len(self.searchtext) > 0:
            filter.append(self.searchtext.replace('%', '%%'))

        # filter on completeness
        if show == 'all':
            filter.append(SpecificationFilter.ALL)
        elif show == 'complete':
            filter.append(SpecificationFilter.COMPLETE)
        elif show == 'incomplete':
            filter.append(SpecificationFilter.INCOMPLETE)

        # filter for informational status
        if informational is not False:
            filter.append(SpecificationFilter.INFORMATIONAL)

        # filter on relationship or role. the underlying class will give us
        # the aggregate of everything if we don't explicitly select one or
        # more
        if role == 'registrant':
            filter.append(SpecificationFilter.CREATOR)
        elif role == 'assignee':
            filter.append(SpecificationFilter.ASSIGNEE)
        elif role == 'drafter':
            filter.append(SpecificationFilter.DRAFTER)
        elif role == 'approver':
            filter.append(SpecificationFilter.APPROVER)
        elif role == 'subscriber':
            filter.append(SpecificationFilter.SUBSCRIBER)

        # filter for acceptance state
        if acceptance == 'declined':
            filter.append(SpecificationFilter.DECLINED)
        elif show == 'proposed':
            filter.append(SpecificationFilter.PROPOSED)
        elif show == 'accepted':
            filter.append(SpecificationFilter.ACCEPTED)

        return filter

    @property
    def specs(self):
        if (IPrivacy.providedBy(self.context)
                and self.context.private
                and not check_permission('launchpad.View', self.context)):
            return []
        return self.context.specifications(self.user, filter=self.spec_filter)

    @cachedproperty
    def specs_batched(self):
        navigator = BatchNavigator(self.specs, self.request, size=500)
        navigator.setHeadings('specification', 'specifications')
        return navigator

    @cachedproperty
    def spec_count(self):
        return self.specs.count()

    @cachedproperty
    def documentation(self):
        filter = [SpecificationFilter.COMPLETE,
                  SpecificationFilter.INFORMATIONAL]
        return shortlist(self.context.specifications(self.user, filter=filter))

    @cachedproperty
    def categories(self):
        """This organises the specifications related to this target by
        "category", where a category corresponds to a particular spec
        status. It also determines the order of those categories, and the
        order of the specs inside each category.

        It is also used in IPerson, which is not an ISpecificationTarget but
        which does have a IPerson.specifications. In this case, it will also
        detect which set of specifications you want to see. The options are:

         - all specs (self.context.specifications())
         - created by this person
         - assigned to this person
         - for review by this person
         - specs this person must approve
         - drafted by this person
         - subscribed by this person

        """
        categories = {}
        for spec in self.specs:
            if spec.definition_status in categories:
                category = categories[spec.definition_status]
            else:
                category = {}
                category['status'] = spec.definition_status
                category['specs'] = []
                categories[spec.definition_status] = category
            category['specs'].append(spec)
        categories = categories.values()
        return sorted(categories, key=itemgetter('definition_status'))

    def getLatestSpecifications(self, quantity=5):
        """Return <quantity> latest specs created for this target.

        Only ACCEPTED specifications are returned.  This list is used by the
        +portlet-latestspecs view.
        """
        return self.context.specifications(self.user,
            sort=SpecificationSort.DATE, quantity=quantity,
            need_people=False, need_branches=False, need_workitems=False)


class SpecificationAssignmentsView(HasSpecificationsView):
    """View for +assignments pages."""
    page_title = "Assignments"

    @property
    def label(self):
        return smartquote(
            'Blueprint assignments for "%s"' % self.context.displayname)


class SpecificationDocumentationView(HasSpecificationsView):
    """View for blueprints +documentation page."""
    page_title = "Documentation"

    @property
    def label(self):
        return smartquote('Current documentation for "%s"' %
                          self.context.displayname)


class RegisterABlueprintButtonPortlet:
    """View that renders a button to register a blueprint on its context."""

    @cachedproperty
    def target_url(self):
        """The +addspec URL for the specifiation target or None"""
        # Check if the context has an +addspec view available.
        if queryMultiAdapter(
            (self.context, self.request), name='+addspec'):
            target = self.context
        else:
            # otherwise find an adapter to ISpecificationTarget which will.
            target = ISpecificationTarget(self.context)
        if target is None:
            return None
        else:
            return canonical_url(
                target, rootsite='blueprints', view_name='+addspec')

    def __call__(self):
        if self.target_url is None:
            return ''
        return """
            <div id="involvement" class="portlet involvement">
              <ul>
                <li class="first">
                  <a class="menu-link-register_blueprint sprite blueprints"
                    href="%s">Register a blueprint</a>
                </li>
              </ul>
            </div>
            """ % self.target_url


class BlueprintsVHostBreadcrumb(Breadcrumb):
    rootsite = 'blueprints'
    text = 'Blueprints'
