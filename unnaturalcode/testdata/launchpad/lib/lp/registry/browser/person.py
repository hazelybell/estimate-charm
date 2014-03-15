# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Person-related view classes."""

__metaclass__ = type
__all__ = [
    'BeginTeamClaimView',
    'CommonMenuLinks',
    'EmailToPersonView',
    'PeopleSearchView',
    'PersonAccountAdministerView',
    'PersonAdministerView',
    'PersonAnswerContactForView',
    'PersonAnswersMenu',
    'PersonBrandingView',
    'PersonCodeOfConductEditView',
    'PersonDeactivateAccountView',
    'PersonEditEmailsView',
    'PersonEditIRCNicknamesView',
    'PersonEditJabberIDsView',
    'PersonEditTimeZoneView',
    'PersonEditSSHKeysView',
    'PersonEditView',
    'PersonFacets',
    'PersonGPGView',
    'PersonIndexMenu',
    'PersonIndexView',
    'PersonKarmaView',
    'PersonLanguagesView',
    'PersonLatestQuestionsView',
    'PersonNavigation',
    'PersonOAuthTokensView',
    'PersonOverviewMenu',
    'PersonOwnedTeamsView',
    'PersonRdfContentsView',
    'PersonRdfView',
    'PersonRelatedSoftwareView',
    'PersonRenameFormMixin',
    'PersonSearchQuestionsView',
    'PersonSetActionNavigationMenu',
    'PersonSetContextMenu',
    'PersonSetNavigation',
    'PersonView',
    'PersonVouchersView',
    'PPANavigationMenuMixIn',
    'RedirectToEditLanguagesView',
    'RestrictedMembershipsPersonView',
    'SearchAnsweredQuestionsView',
    'SearchAssignedQuestionsView',
    'SearchCommentedQuestionsView',
    'SearchCreatedQuestionsView',
    'SearchNeedAttentionQuestionsView',
    'SearchSubscribedQuestionsView',
    'archive_to_person',
    ]


from datetime import datetime
import itertools
from itertools import chain
from operator import (
    attrgetter,
    itemgetter,
    )
from textwrap import dedent
import urllib

from lazr.config import as_timedelta
from lazr.delegates import delegates
from lazr.restful.interface import copy_field
from lazr.restful.interfaces import IWebServiceClientRequest
from lazr.restful.utils import smartquote
from lazr.uri import URI
import pytz
from storm.zope.interfaces import IResultSet
from z3c.ptcompat import ViewPageTemplateFile
from zope.component import (
    adapts,
    getUtility,
    queryMultiAdapter,
    )
from zope.error.interfaces import IErrorReportingUtility
from zope.formlib import form
from zope.formlib.form import FormFields
from zope.formlib.widgets import (
    TextAreaWidget,
    TextWidget,
    )
from zope.interface import (
    classImplements,
    implements,
    Interface,
    )
from zope.interface.exceptions import Invalid
from zope.interface.interface import invariant
from zope.publisher.interfaces import NotFound
from zope.schema import (
    Choice,
    Text,
    TextLine,
    )
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )
from zope.security.interfaces import Unauthorized
from zope.security.proxy import removeSecurityProxy

from lp import _
from lp.answers.browser.questiontarget import SearchQuestionsView
from lp.answers.enums import QuestionParticipation
from lp.answers.interfaces.questionsperson import IQuestionsPerson
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadEditFormView,
    LaunchpadFormView,
    )
from lp.app.browser.lazrjs import TextAreaEditorWidget
from lp.app.browser.tales import (
    DateTimeFormatterAPI,
    PersonFormatterAPI,
    )
from lp.app.errors import (
    NotFoundError,
    UnexpectedFormData,
    )
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.app.validators.email import valid_email
from lp.app.widgets.image import ImageChangeWidget
from lp.app.widgets.itemswidgets import (
    LaunchpadDropdownWidget,
    LaunchpadRadioWidget,
    LaunchpadRadioWidgetWithDescription,
    )
from lp.bugs.interfaces.bugsupervisor import IHasBugSupervisor
from lp.bugs.interfaces.bugtask import BugTaskStatus
from lp.bugs.interfaces.bugtasksearch import BugTaskSearchParams
from lp.buildmaster.enums import BuildStatus
from lp.code.browser.sourcepackagerecipelisting import HasRecipesMenuMixin
from lp.code.errors import InvalidNamespace
from lp.code.interfaces.branchnamespace import IBranchNamespaceSet
from lp.registry.browser import BaseRdfView
from lp.registry.browser.branding import BrandingChangeView
from lp.registry.browser.menu import (
    IRegistryCollectionNavigationMenu,
    RegistryCollectionActionMenuBase,
    TopLevelMenuMixin,
    )
from lp.registry.browser.teamjoin import TeamJoinMixin
from lp.registry.enums import PersonVisibility
from lp.registry.errors import VoucherAlreadyRedeemed
from lp.registry.interfaces.codeofconduct import ISignedCodeOfConductSet
from lp.registry.interfaces.gpg import IGPGKeySet
from lp.registry.interfaces.irc import IIrcIDSet
from lp.registry.interfaces.jabber import (
    IJabberID,
    IJabberIDSet,
    )
from lp.registry.interfaces.mailinglist import (
    CannotUnsubscribe,
    IMailingListSet,
    )
from lp.registry.interfaces.mailinglistsubscription import (
    MailingListAutoSubscribePolicy,
    )
from lp.registry.interfaces.person import (
    IPerson,
    IPersonClaim,
    IPersonSet,
    )
from lp.registry.interfaces.personproduct import IPersonProductFactory
from lp.registry.interfaces.persontransferjob import (
    IPersonDeactivateJobSource,
    )
from lp.registry.interfaces.pillar import IPillarNameSet
from lp.registry.interfaces.poll import IPollSubset
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.ssh import (
    ISSHKeySet,
    SSHKeyAdditionError,
    SSHKeyCompromisedError,
    SSHKeyType,
    )
from lp.registry.interfaces.teammembership import (
    ITeamMembershipSet,
    TeamMembershipStatus,
    )
from lp.registry.interfaces.wikiname import IWikiNameSet
from lp.registry.mail.notification import send_direct_contact_email
from lp.registry.model.person import get_recipients
from lp.services.config import config
from lp.services.database.sqlbase import flush_database_updates
from lp.services.feeds.browser import FeedsMixin
from lp.services.geoip.interfaces import IRequestPreferredLanguages
from lp.services.gpg.interfaces import (
    GPGKeyNotFoundError,
    IGPGHandler,
    )
from lp.services.identity.interfaces.account import (
    AccountStatus,
    IAccount,
    )
from lp.services.identity.interfaces.emailaddress import (
    EmailAddressStatus,
    IEmailAddress,
    IEmailAddressSet,
    )
from lp.services.mail.interfaces import (
    INotificationRecipientSet,
    UnknownRecipientError,
    )
from lp.services.messages.interfaces.message import (
    IDirectEmailAuthorization,
    QuotaReachedError,
    )
from lp.services.oauth.interfaces import IOAuthConsumerSet
from lp.services.openid.adapters.openid import CurrentOpenIDEndPoint
from lp.services.openid.browser.openiddiscovery import (
    XRDSContentNegotiationMixin,
    )
from lp.services.openid.interfaces.openid import IOpenIDPersistentIdentity
from lp.services.propertycache import (
    cachedproperty,
    get_property_cache,
    )
from lp.services.salesforce.interfaces import (
    ISalesforceVoucherProxy,
    REDEEMABLE_VOUCHER_STATUSES,
    SalesforceVoucherProxyException,
    )
from lp.services.verification.interfaces.authtoken import LoginTokenType
from lp.services.verification.interfaces.logintoken import ILoginTokenSet
from lp.services.webapp import (
    ApplicationMenu,
    canonical_url,
    ContextMenu,
    enabled_with_permission,
    Link,
    Navigation,
    NavigationMenu,
    StandardLaunchpadFacets,
    stepthrough,
    stepto,
    structured,
    )
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.batching import BatchNavigator
from lp.services.webapp.interfaces import (
    ILaunchBag,
    IOpenLaunchBag,
    )
from lp.services.webapp.login import (
    logoutPerson,
    require_fresh_login,
    )
from lp.services.webapp.menu import get_current_view
from lp.services.webapp.publisher import LaunchpadView
from lp.services.worlddata.interfaces.country import ICountry
from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.soyuz.browser.archivesubscription import (
    traverse_archive_subscription_for_subscriber,
    )
from lp.soyuz.interfaces.archivesubscriber import IArchiveSubscriberSet
from lp.soyuz.interfaces.binarypackagebuild import IBinaryPackageBuildSet
from lp.soyuz.interfaces.publishing import ISourcePackagePublishingHistory
from lp.soyuz.interfaces.sourcepackagerelease import ISourcePackageRelease


COMMASPACE = ', '


class RestrictedMembershipsPersonView(LaunchpadView):
    """Secure access to team membership information for a person.

    This class checks that the logged-in user has access to view
    all the teams that these attributes and functions return.
    """

    def getLatestApprovedMembershipsForPerson(self):
        """Returns a list of teams the person has recently joined.

        Private teams are filtered out if the user is not a member of them.
        """
        # This method returns a list as opposed to the database object's
        # getLatestApprovedMembershipsForPerson which returns a sqlobject
        # result set.
        membership_list = self.context.getLatestApprovedMembershipsForPerson()
        return [membership for membership in membership_list
                if check_permission('launchpad.View', membership.team)]

    @property
    def teams_with_icons(self):
        """Returns list of teams with custom icons.

        These are teams that the person is an active member of.
        Private teams are filtered out if the user is not a member of them.
        """
        # This method returns a list as opposed to the database object's
        # teams_with_icons which returns a sqlobject
        # result set.
        return [team for team in self.context.teams_with_icons
                if check_permission('launchpad.View', team)]

    @property
    def administrated_teams(self):
        """Return the list of teams administrated by the person.

        The user must be an administrator of the team, and the team must
        be public.
        """
        return [team for team in self.context.getAdministratedTeams()
                if team.visibility == PersonVisibility.PUBLIC]

    def userCanViewMembership(self):
        """Return true if the user can view a team's membership.

        Only launchpad admins and team members can view the private
        membership. Anyone can view a public team's membership.
        """
        return check_permission('launchpad.View', self.context)


class BranchTraversalMixin:
    """Logic for traversing to branches from `IPerson`s.

    Branches can be reached from
    code.launchpad.net/~person/+branch/other/path/info or from
    code.launchpad.net/~person/other/path/info.

    Most of the knowledge of how branch paths work is stored in
    `IBranchNamespaceSet`. This class simply delegates to that.
    """

    def _getSegments(self, pillar_name=None):
        base = [self.context.name]
        if pillar_name is not None:
            base.append(pillar_name)
        return itertools.chain(iter(base), iter(self.request.stepstogo))

    @stepto('+branch')
    def redirect_branch(self):
        """Redirect to canonical_url."""
        branch = getUtility(IBranchNamespaceSet).traverse(self._getSegments())
        if branch:
            return self.redirectSubTree(canonical_url(branch))
        raise NotFoundError

    def traverse(self, pillar_name):
        # If the pillar is a product, then return the PersonProduct.
        pillar = getUtility(IPillarNameSet).getByName(pillar_name)
        if IProduct.providedBy(pillar):
            person_product = getUtility(IPersonProductFactory).create(
                self.context, pillar)
            # If accessed through an alias, redirect to the proper name.
            if pillar.name != pillar_name:
                return self.redirectSubTree(canonical_url(person_product))
            getUtility(IOpenLaunchBag).add(pillar)
            return person_product
        # Otherwise look for a branch.
        try:
            branch = getUtility(IBranchNamespaceSet).traverse(
                self._getSegments(pillar_name))
        except (NotFoundError, InvalidNamespace):
            return super(BranchTraversalMixin, self).traverse(pillar_name)

        # Normally, populating the launch bag is done by the traversal
        # mechanism. However, here we short-circuit that mechanism by
        # processing multiple segments at once. Thus, we populate the launch
        # bag with information about the containers of a branch.
        branch.addToLaunchBag(getUtility(IOpenLaunchBag))

        if branch.product is not None:
            if branch.product.name != pillar_name:
                # This branch was accessed through one of its product's
                # aliases, so we must redirect to its canonical URL.
                return self.redirectSubTree(canonical_url(branch))

        if branch.distribution is not None:
            if branch.distribution.name != pillar_name:
                # This branch was accessed through one of its product's
                # aliases, so we must redirect to its canonical URL.
                return self.redirectSubTree(canonical_url(branch))

        return branch


class PersonNavigation(BranchTraversalMixin, Navigation):

    usedfor = IPerson

    @stepthrough('+expiringmembership')
    def traverse_expiring_membership(self, name):
        # Return the found membership regardless of its status as we know
        # TeamMembershipSelfRenewalView will tell users why the memembership
        # can't be renewed when necessary.
        # Circular imports
        from lp.registry.browser.team import TeamMembershipSelfRenewalView
        membership = getUtility(ITeamMembershipSet).getByPersonAndTeam(
            self.context, getUtility(IPersonSet).getByName(name))
        if membership is None:
            return None
        return TeamMembershipSelfRenewalView(membership, self.request)

    @stepto('+archive')
    def traverse_archive(self):

        if self.request.stepstogo:
            # If the URL has something that could be a PPA name in it,
            # use that, but just in case it fails, keep a copy
            # of the traversal stack so we can try using the default
            # archive afterwards:
            traversal_stack = self.request.getTraversalStack()
            ppa_name = self.request.stepstogo.consume()

            try:
                from lp.soyuz.browser.archive import traverse_named_ppa
                return traverse_named_ppa(self.context.name, ppa_name)
            except NotFoundError:
                self.request.setTraversalStack(traversal_stack)
                # and simply continue below...

        # Otherwise try to get the default PPA and if it exists redirect
        # to the new-style URL, if it doesn't, return None (to trigger a
        # NotFound error).
        default_ppa = self.context.archive
        if default_ppa is None:
            return None

        return self.redirectSubTree(canonical_url(default_ppa))

    @stepthrough('+email')
    def traverse_email(self, email):
        """Traverse to this person's emails on the webservice layer."""
        email = getUtility(IEmailAddressSet).getByEmail(email)
        if email is None or email.personID != self.context.id:
            return None
        return email

    @stepthrough('+wikiname')
    def traverse_wikiname(self, id):
        """Traverse to this person's WikiNames on the webservice layer."""
        wiki = getUtility(IWikiNameSet).get(id)
        if wiki is None or wiki.person != self.context:
            return None
        return wiki

    @stepthrough('+jabberid')
    def traverse_jabberid(self, jabber_id):
        """Traverse to this person's JabberIDs on the webservice layer."""
        jabber = getUtility(IJabberIDSet).getByJabberID(jabber_id)
        if jabber is None or jabber.person != self.context:
            return None
        return jabber

    @stepthrough('+ircnick')
    def traverse_ircnick(self, id):
        """Traverse to this person's IrcIDs on the webservice layer."""
        irc_nick = getUtility(IIrcIDSet).get(id)
        if irc_nick is None or irc_nick.person != self.context:
            return None
        return irc_nick

    @stepto('+archivesubscriptions')
    def traverse_archive_subscription(self):
        """Traverse to the archive subscription for this person."""
        if self.context.is_team:
            raise NotFoundError

        if self.request.stepstogo:
            # In which case we assume it is the archive_id (for the
            # moment, archive name will be an option soon).
            archive_id = self.request.stepstogo.consume()
            if not archive_id.isdigit():
                return None
            return traverse_archive_subscription_for_subscriber(
                self.context, archive_id)
        else:
            # Otherwise we return the normal view for a person's
            # archive subscriptions.
            return queryMultiAdapter(
                (self.context, self.request), name="+archivesubscriptions")

    @stepthrough('+recipe')
    def traverse_recipe(self, name):
        """Traverse to this person's recipes."""
        return self.context.getRecipe(name)

    @stepthrough('+merge-queues')
    def traverse_merge_queue(self, name):
        """Traverse to this person's merge queues."""
        return self.context.getMergeQueue(name)


class PersonSetNavigation(Navigation):

    usedfor = IPersonSet

    def traverse(self, name):
        # Raise a 404 on an invalid Person name
        person = self.context.getByName(name)
        if person is None:
            raise NotFoundError(name)
        # Redirect to /~name
        return self.redirectSubTree(
            canonical_url(person, request=self.request))

    @stepto('+me')
    def me(self):
        me = getUtility(ILaunchBag).user
        if me is None:
            raise Unauthorized("You need to be logged in to view this URL.")
        return self.redirectSubTree(
            canonical_url(me, request=self.request), status=303)


class PersonSetContextMenu(ContextMenu, TopLevelMenuMixin):

    usedfor = IPersonSet

    links = ['projects', 'distributions', 'people', 'meetings',
             'register_team',
             'adminpeoplemerge', 'adminteammerge', 'mergeaccounts']

    def mergeaccounts(self):
        text = 'Merge accounts'
        return Link('+requestmerge', text, icon='edit')

    @enabled_with_permission('launchpad.Admin')
    def adminpeoplemerge(self):
        text = 'Admin merge people'
        return Link('+adminpeoplemerge', text, icon='edit')

    @enabled_with_permission('launchpad.Admin')
    def adminteammerge(self):
        text = 'Admin merge teams'
        return Link('+adminteammerge', text, icon='edit')


class PersonFacets(StandardLaunchpadFacets):
    """The links that will appear in the facet menu for an IPerson."""

    usedfor = IPerson

    enable_only = ['overview', 'bugs', 'answers', 'specifications',
                   'branches', 'translations']

    def overview(self):
        text = 'Overview'
        summary = 'General information about %s' % self.context.displayname
        return Link('', text, summary)

    def bugs(self):
        text = 'Bugs'
        summary = (
            'Bug reports that %s is involved with' % self.context.displayname)
        return Link('', text, summary)

    def specifications(self):
        text = 'Blueprints'
        summary = (
            'Feature specifications that %s is involved with' %
            self.context.displayname)
        return Link('', text, summary)

    def branches(self):
        text = 'Code'
        summary = ('Bazaar Branches and revisions registered and authored '
                   'by %s' % self.context.displayname)
        return Link('', text, summary)

    def answers(self):
        text = 'Answers'
        summary = (
            'Questions that %s is involved with' % self.context.displayname)
        return Link('', text, summary)

    def translations(self):
        text = 'Translations'
        summary = (
            'Software that %s is involved in translating' %
            self.context.displayname)
        return Link('', text, summary)


class CommonMenuLinks:

    @property
    def person(self):
        """Allow subclasses that use the view as the context."""
        return self.context

    @enabled_with_permission('launchpad.Edit')
    def activate_ppa(self):
        target = "+activate-ppa"
        text = 'Create a new PPA'
        return Link(target, text, icon='add')

    def related_software_summary(self):
        target = '+related-packages'
        text = 'Related packages'
        return Link(target, text, icon='info')

    def maintained(self):
        target = '+maintained-packages'
        text = 'Maintained packages'
        enabled = self.person.hasMaintainedPackages()
        return Link(target, text, enabled=enabled, icon='info')

    def uploaded(self):
        target = '+uploaded-packages'
        text = 'Uploaded packages'
        enabled = self.person.hasUploadedButNotMaintainedPackages()
        return Link(target, text, enabled=enabled, icon='info')

    def ppa(self):
        target = '+ppa-packages'
        text = 'Related PPA packages'
        enabled = self.person.hasUploadedPPAPackages()
        return Link(target, text, enabled=enabled, icon='info')

    def synchronised(self):
        target = '+synchronised-packages'
        text = 'Synchronised packages'
        enabled = self.person.hasSynchronisedPublishings()
        return Link(target, text, enabled=enabled, icon='info')

    def projects(self):
        target = '+related-projects'
        text = 'Related projects'
        user = getUtility(ILaunchBag).user
        enabled = bool(self.person.getAffiliatedPillars(user))
        return Link(target, text, enabled=enabled, icon='info')

    def owned_teams(self):
        target = '+owned-teams'
        text = 'Owned teams'
        return Link(target, text, icon='info')

    def subscriptions(self):
        target = '+subscriptions'
        text = 'Direct subscriptions'
        return Link(target, text, icon='info')

    def structural_subscriptions(self):
        target = '+structural-subscriptions'
        text = 'Structural subscriptions'
        return Link(target, text, icon='info')


class PersonMenuMixin(CommonMenuLinks):

    @enabled_with_permission('launchpad.Edit')
    def branding(self):
        target = '+branding'
        text = 'Change branding'
        return Link(target, text, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def edit(self):
        target = '+edit'
        text = 'Change details'
        return Link(target, text, icon='edit')

    @enabled_with_permission('launchpad.Moderate')
    def administer(self):
        target = '+review'
        text = 'Administer'
        return Link(target, text, icon='edit')

    @enabled_with_permission('launchpad.Moderate')
    def administer_account(self):
        target = '+reviewaccount'
        text = 'Administer Account'
        return Link(target, text, icon='edit')


class PersonOverviewMenu(ApplicationMenu, PersonMenuMixin,
                         HasRecipesMenuMixin):

    usedfor = IPerson
    facet = 'overview'
    links = [
        'edit',
        'branding',
        'editemailaddresses',
        'editlanguages',
        'editircnicknames',
        'editjabberids',
        'editsshkeys',
        'editpgpkeys',
        'editlocation',
        'memberships',
        'codesofconduct',
        'karma',
        'administer',
        'administer_account',
        'projects',
        'activate_ppa',
        'maintained',
        'manage_vouchers',
        'owned_teams',
        'synchronised',
        'view_ppa_subscriptions',
        'ppa',
        'oauth_tokens',
        'related_software_summary',
        'view_recipes',
        'subscriptions',
        'structural_subscriptions',
        ]

    def related_software_summary(self):
        target = '+related-packages'
        text = 'Related packages'
        return Link(target, text, icon='info')

    @enabled_with_permission('launchpad.Edit')
    def oauth_tokens(self):
        target = '+oauth-tokens'
        text = 'Authorized applications'
        access_tokens = self.context.oauth_access_tokens
        request_tokens = self.context.oauth_request_tokens
        enabled = bool(access_tokens or request_tokens)
        return Link(target, text, enabled=enabled, icon='info')

    @enabled_with_permission('launchpad.Edit')
    def manage_vouchers(self):
        target = '+vouchers'
        text = 'Manage commercial subscriptions'
        summary = 'Purchase and redeem commercial subscription vouchers'
        return Link(target, text, summary, icon='info')

    @enabled_with_permission('launchpad.Edit')
    def editlanguages(self):
        target = '+editlanguages'
        text = 'Set preferred languages'
        return Link(target, text, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def editemailaddresses(self):
        target = '+editemails'
        text = 'Change e-mail settings'
        return Link(target, text, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def editircnicknames(self):
        target = '+editircnicknames'
        text = 'Update IRC nicknames'
        return Link(target, text, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def editjabberids(self):
        target = '+editjabberids'
        text = 'Update Jabber IDs'
        return Link(target, text, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def editlocation(self):
        target = '+editlocation'
        text = 'Set location and time zone'
        return Link(target, text, icon='edit')

    def karma(self):
        target = '+karma'
        text = 'Show karma summary'
        summary = (
            u'%s\N{right single quotation mark}s activities '
            u'in Launchpad' % self.context.displayname)
        return Link(target, text, summary, icon='info')

    def memberships(self):
        target = '+participation'
        text = 'Show team participation'
        return Link(target, text, icon='info')

    @enabled_with_permission('launchpad.Special')
    def editsshkeys(self):
        target = '+editsshkeys'
        if self.context.sshkeys.is_empty():
            text = 'Add an SSH key'
            icon = 'add'
        else:
            text = 'Update SSH keys'
            icon = 'edit'
        summary = 'Used when storing code on Launchpad'
        return Link(target, text, summary, icon=icon)

    @enabled_with_permission('launchpad.Edit')
    def editpgpkeys(self):
        target = '+editpgpkeys'
        text = 'Update OpenPGP keys'
        summary = 'Used when maintaining packages'
        return Link(target, text, summary, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def codesofconduct(self):
        target = '+codesofconduct'
        text = 'Codes of Conduct'
        summary = (
            'Agreements to abide by the rules of a distribution or project')
        return Link(target, text, summary, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def view_ppa_subscriptions(self):
        target = "+archivesubscriptions"
        text = "View your private PPA subscriptions"
        summary = ('View your personal PPA subscriptions and set yourself '
                   'up to download your software')

        # Only enable the link if the person has some subscriptions.
        subscriptions = getUtility(IArchiveSubscriberSet).getBySubscriber(
            self.context)
        enabled = not subscriptions.is_empty()

        return Link(target, text, summary, enabled=enabled, icon='info')


class IPersonEditMenu(Interface):
    """A marker interface for the 'Edit Profile' navigation menu."""


class IPersonRelatedSoftwareMenu(Interface):
    """A marker interface for the 'Related software' navigation menu."""


class PPANavigationMenuMixIn:
    """PPA-related navigation menu links for Person and Team pages."""

    def ppas(self):
        target = '#ppas'
        text = 'Personal Package Archives'
        view = get_current_view()
        if isinstance(view, PersonView):
            enabled = view.should_show_ppa_section
        else:
            enabled = True
        return Link(target, text, enabled=enabled)


class PersonRelatedSoftwareNavigationMenu(NavigationMenu, CommonMenuLinks):

    usedfor = IPersonRelatedSoftwareMenu
    facet = 'overview'
    links = ('related_software_summary', 'maintained', 'uploaded', 'ppa',
             'synchronised', 'projects', 'owned_teams')

    @property
    def person(self):
        """Override CommonMenuLinks since the view is the context."""
        return self.context.context


class PersonEditNavigationMenu(NavigationMenu):
    """A sub-menu for different aspects of editing a Person's profile."""

    usedfor = IPersonEditMenu
    facet = 'overview'
    links = ('personal', 'email_settings', 'sshkeys', 'gpgkeys')

    def personal(self):
        target = '+edit'
        text = 'Personal'
        return Link(target, text)

    def email_settings(self):
        target = '+editemails'
        text = 'E-mail Settings'
        return Link(target, text)

    @enabled_with_permission('launchpad.Special')
    def sshkeys(self):
        target = '+editsshkeys'
        text = 'SSH keys'
        return Link(target, text)

    def gpgkeys(self):
        target = '+editpgpkeys'
        text = 'OpenPGP Keys'
        return Link(target, text)


class PersonSetActionNavigationMenu(RegistryCollectionActionMenuBase):
    """Action menu for `PeopleSearchView`."""
    usedfor = IPersonSet
    links = ['register_team', 'register_project', 'create_account',
             'request_merge', 'admin_merge_people', 'admin_merge_teams']


class PeopleSearchView(LaunchpadView):
    """Search for people and teams on the /people page."""

    implements(IRegistryCollectionNavigationMenu)

    page_title = 'People and teams in Launchpad'

    def __init__(self, context, request):
        super(PeopleSearchView, self).__init__(context, request)
        self.results = []

    @property
    def number_of_people(self):
        return self.context.peopleCount()

    @property
    def number_of_teams(self):
        return self.context.teamsCount()

    @property
    def is_teams_only(self):
        """Is the search restricted to teams."""
        searchfor = self.request.get("searchfor", None)
        return searchfor == 'teamsonly'

    @property
    def is_people_only(self):
        """Is the search restricted to people."""
        searchfor = self.request.get("searchfor", None)
        return searchfor == 'peopleonly'

    def searchPeopleBatchNavigator(self):
        name = self.request.get("name")
        if not name:
            return None
        if self.is_people_only:
            results = self.context.findPerson(name)
        elif self.is_teams_only:
            results = self.context.findTeam(name)
        else:
            results = self.context.find(name)
        return BatchNavigator(results, self.request)


class DeactivateAccountSchema(Interface):
    comment = copy_field(
        IPerson['account_status_comment'], readonly=False, __name__='comment')


class PersonDeactivateAccountView(LaunchpadFormView):

    schema = DeactivateAccountSchema
    label = "Deactivate your Launchpad account"
    custom_widget('comment', TextAreaWidget, height=5, width=60)

    def validate(self, data):
        """See `LaunchpadFormView`."""
        [self.addError(message) for message in self.context.canDeactivate()]

    @action(_("Deactivate My Account"), name="deactivate")
    def deactivate_action(self, action, data):
        self.context.preDeactivate(data['comment'])
        getUtility(IPersonDeactivateJobSource).create(self.context)
        logoutPerson(self.request)
        self.request.response.addInfoNotification(
            _(u'Your account has been deactivated.'))
        self.next_url = self.request.getApplicationURL()


class BeginTeamClaimView(LaunchpadFormView):
    """Where you can claim an unvalidated profile turning it into a team.

    This is actually just the first step, where you enter the email address
    of the team and we email further instructions to that address.
    """
    label = 'Claim team'
    schema = IPersonClaim

    def initialize(self):
        if self.context.is_valid_person_or_team:
            # Valid teams and people aren't claimable. We pull the path
            # out of PATH_INFO to make sure that the exception looks
            # good for subclasses. We're that picky!
            name = self.request['PATH_INFO'].split("/")[-1]
            raise NotFound(self, name, request=self.request)
        LaunchpadFormView.initialize(self)

    def validate(self, data):
        emailaddress = data.get('emailaddress')
        if emailaddress is None:
            self.setFieldError(
                'emailaddress', 'Please enter the email address')
            return

        email = getUtility(IEmailAddressSet).getByEmail(emailaddress)
        error = ""
        if email is None:
            # Email not registered in launchpad, ask the user to try another
            # one.
            error = ("We couldn't find this email address. Please try "
                     "another one that could possibly be associated with "
                     "this profile. Note that this profile's name (%s) was "
                     "generated based on the email address it's "
                     "associated with."
                     % self.context.name)
        elif email.personID != self.context.id:
            error = structured(
                        "This email address is associated with yet another "
                        "Launchpad profile, which you seem to have used at "
                        "some point. If that's the case, you can "
                        '<a href="/people/+requestmerge'
                        '?field.dupe_person=%s">combine '
                        "this profile with the other one</a> (you'll "
                        "have to log in with the other profile first, "
                        "though). If that's not the case, please try with a "
                        "different email address.",
                        self.context.name)
        else:
            # Yay! You got the right email this time.
            pass
        if error:
            self.setFieldError('emailaddress', error)

    @property
    def next_url(self):
        return canonical_url(self.context)

    @action(_("Continue"), name="confirm")
    def confirm_action(self, action, data):
        email = data['emailaddress']
        token = getUtility(ILoginTokenSet).new(
            requester=self.user, requesteremail=None, email=email,
            tokentype=LoginTokenType.TEAMCLAIM)
        token.sendClaimTeamEmail()
        self.request.response.addInfoNotification(_(
            "A confirmation message has been sent to '${email}'. "
            "Follow the instructions in that message to finish claiming this "
            "team. "
            "(If the above address is from a mailing list, it may be "
            "necessary to talk with one of its admins to accept the message "
            "from Launchpad so that you can finish the process.)",
            mapping=dict(email=email)))


class RedirectToEditLanguagesView(LaunchpadView):
    """Redirect the logged in user to his +editlanguages page.

    This view should always be registered with a launchpad.AnyPerson
    permission, to make sure the user is logged in. It exists so that
    we provide a link for non logged in users that will require them to login
    and them send them straight to the page they want to go.
    """

    def initialize(self):
        self.request.response.redirect(
            '%s/+editlanguages' % canonical_url(self.user))


class PersonWithKeysAndPreferredEmail:
    """A decorated person that includes GPG keys and preferred emails."""

    # These need to be predeclared to avoid delegates taking them over.
    # Would be nice if there was a way of allowing writes to just work
    # (i.e. no proxying of __set__).
    gpgkeys = None
    sshkeys = None
    preferredemail = None
    delegates(IPerson, 'person')

    def __init__(self, person):
        self.person = person
        self.gpgkeys = []
        self.sshkeys = []

    def addGPGKey(self, key):
        self.gpgkeys.append(key)

    def addSSHKey(self, key):
        self.sshkeys.append(key)

    def setPreferredEmail(self, email):
        self.preferredemail = email


class PersonRdfView(BaseRdfView):
    """A view that embeds PersonRdfContentsView in a standalone page."""

    template = ViewPageTemplateFile(
        '../templates/person-rdf.pt')

    @property
    def filename(self):
        return '%s.rdf' % self.context.name


class PersonRdfContentsView:
    """A view for the contents of Person FOAF RDF."""

    # We need to set the content_type here explicitly in order to
    # preserve the case of the elements (which is not preserved in the
    # parsing of the default text/html content-type.)
    template = ViewPageTemplateFile(
        '../templates/person-rdf-contents.pt',
        content_type="application/rdf+xml")

    def __init__(self, context, request):
        self.context = context
        self.request = request

    def __call__(self):
        """Render RDF output.

        This is only used when rendering this to the end-user, and is
        only here to avoid us OOPSing if people access +raw-contents via
        the web. All templates should reuse this view by invoking
        +rdf-contents/template.
        """
        unicodedata = self.template()
        encodeddata = unicodedata.encode('utf-8')
        return encodeddata


class PersonRenameFormMixin(LaunchpadEditFormView):

    def setUpWidgets(self):
        """See `LaunchpadViewForm`.

        Renames are prohibited if a person/team has an active PPA or an
        active mailing list.
        """
        reason = self.context.checkRename()
        # Reason is a message about why a rename cannot happen.
        # No message means renames are permitted.
        if reason:
            # This makes the field's widget display (i.e. read) only.
            self.form_fields['name'].for_display = True
        super(PersonRenameFormMixin, self).setUpWidgets()
        if reason:
            self.widgets['name'].hint = reason


class PersonAdministerView(PersonRenameFormMixin):
    """Administer an `IPerson`."""
    schema = IPerson
    label = "Review person"
    field_names = [
        'name', 'displayname',
        'personal_standing', 'personal_standing_reason']
    custom_widget(
        'personal_standing_reason', TextAreaWidget, height=5, width=60)

    @property
    def is_viewing_person(self):
        """Is the view showing an `IPerson`?

        `PersonAdministerView` and `PersonAccountAdministerView` share a
        template. It needs to know what the context is.
        """
        return True

    @property
    def next_url(self):
        """See `LaunchpadEditFormView`."""
        return canonical_url(self.context)

    @property
    def cancel_url(self):
        """See `LaunchpadEditFormView`."""
        return canonical_url(self.context)

    @action('Change', name='change')
    def change_action(self, action, data):
        """Update the IPerson."""
        self.updateContextFromData(data)


class PersonAccountAdministerView(LaunchpadEditFormView):
    """Administer an `IAccount` belonging to an `IPerson`."""
    schema = IAccount
    label = "Review person's account"
    field_names = ['displayname', 'status', 'status_comment']
    custom_widget(
        'status_comment', TextAreaWidget, height=5, width=60)

    def __init__(self, context, request):
        """See `LaunchpadEditFormView`."""
        super(PersonAccountAdministerView, self).__init__(context, request)
        # Only the IPerson can be traversed to, so it provides the IAccount.
        # It also means that permissions are checked on IAccount, not IPerson.
        self.person = self.context
        self.context = self.person.account

    @property
    def is_viewing_person(self):
        """Is the view showing an `IPerson`?

        `PersonAdministerView` and `PersonAccountAdministerView` share a
        template. It needs to know what the context is.
        """
        return False

    @property
    def email_addresses(self):
        """A list of the user's preferred and validated email addresses."""
        emails = sorted(
            email.email for email in self.person.validatedemails)
        if self.person.preferredemail is not None:
            emails.insert(0, self.person.preferredemail.email)
        return emails

    @property
    def guessed_email_addresses(self):
        """A list of the user's new email addresses.

        This is just EmailAddressStatus.NEW addresses, not unvalidated ones
        created through the web UI. They only have LoginTokens.
        """
        return sorted(email.email for email in self.person.guessedemails)

    @property
    def next_url(self):
        """See `LaunchpadEditFormView`."""
        return canonical_url(self.person)

    @property
    def cancel_url(self):
        """See `LaunchpadEditFormView`."""
        return canonical_url(self.person)

    @action('Change', name='change')
    def change_action(self, action, data):
        """Update the IAccount."""
        if (data['status'] == AccountStatus.SUSPENDED
            and self.context.status != AccountStatus.SUSPENDED):
            # The preferred email address is removed to ensure no email
            # is sent to the user.
            self.person.setPreferredEmail(None)
            self.request.response.addInfoNotification(
                u'The account "%s" has been suspended.' % (
                    self.context.displayname))
        if (data['status'] == AccountStatus.ACTIVE
            and self.context.status != AccountStatus.ACTIVE):
            self.request.response.addInfoNotification(
                u'The user is reactivated. He must use the '
                u'"forgot password" to log in.')
        self.updateContextFromData(data)


class PersonVouchersView(LaunchpadFormView):
    """Form for displaying and redeeming commercial subscription vouchers."""

    custom_widget('voucher', LaunchpadDropdownWidget)

    @property
    def page_title(self):
        return 'Commercial subscription vouchers'

    @property
    def cancel_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(self.context)

    def setUpFields(self):
        """Set up the fields for this view."""

        self.form_fields = []
        self.form_fields = (self.createProjectField() +
                            self.createVoucherField())

    def createProjectField(self):
        """Create the project field for selection commercial projects.

        The vocabulary shows commercial projects owned by the current user.
        """
        field = FormFields(
            Choice(__name__='project',
                   title=_('Select the project you wish to subscribe'),
                   description=_('Commercial projects you administer'),
                   vocabulary="CommercialProjects",
                   required=True),
            render_context=self.render_context)
        return field

    def createVoucherField(self):
        """Create voucher field.

        Only redeemable vouchers owned by the user are shown.
        """
        terms = []
        for voucher in self.redeemable_vouchers:
            text = "%s (%d months)" % (
                voucher.voucher_id, voucher.term_months)
            terms.append(SimpleTerm(voucher, voucher.voucher_id, text))
        voucher_vocabulary = SimpleVocabulary(terms)
        field = FormFields(
            Choice(__name__='voucher',
                   title=_('Select a voucher'),
                   description=_('Choose one of these redeemable vouchers'),
                   vocabulary=voucher_vocabulary,
                   required=True),
            render_context=self.render_context)
        return field

    @cachedproperty
    def show_voucher_selection(self):
        return self.redeemable_vouchers or self.errors

    @cachedproperty
    def redeemable_vouchers(self):
        """Get the list redeemable vouchers owned by the user."""
        vouchers = [
            voucher for voucher in
            self.context.getRedeemableCommercialSubscriptionVouchers()]
        return vouchers

    def removeRedeemableVoucher(self, voucher):
        """Remove the voucher from the cached list of redeemable vouchers.

        Updated the voucher field and widget so that the form can be reused.
        """
        vouchers = get_property_cache(self).redeemable_vouchers
        vouchers.remove(voucher)
        # Setup the fields and widgets again, but withut the submitted data.
        self.form_fields = (
            self.createProjectField() + self.createVoucherField())
        self.widgets = form.setUpWidgets(
            self.form_fields.select('project', 'voucher'),
            self.prefix, self.context, self.request,
            data=self.initial_values, ignore_request=True)

    @action(_("Redeem"), name="redeem")
    def redeem_action(self, action, data):
        salesforce_proxy = getUtility(ISalesforceVoucherProxy)
        project = data['project']
        voucher = data['voucher']

        try:
            # Perform a check that the submitted voucher id is valid.
            check_voucher = salesforce_proxy.getVoucher(voucher.voucher_id)
            if not check_voucher.status in REDEEMABLE_VOUCHER_STATUSES:
                self.addError(
                    _("Voucher %s has invalid status %s"
                      % (check_voucher.voucher_id, check_voucher.status)))
                return
            # Redeem the voucher in Launchpad, marking the subscription as
            # pending. Launchpad will honour the subscription but a job will
            # still need to be run to notify Salesforce.
            try:
                project.redeemSubscriptionVoucher(
                    voucher='pending-' + voucher.voucher_id,
                    registrant=self.context,
                    purchaser=self.context,
                    subscription_months=voucher.term_months)
            except VoucherAlreadyRedeemed as error:
                self.setFieldError('voucher', _(error.message))
                return
            self.request.response.addInfoNotification(
                _("Voucher redeemed successfully"))
            self.removeRedeemableVoucher(voucher)
        except SalesforceVoucherProxyException as error:
            self.addError(
                _("The voucher could not be redeemed at this time."))
            # Log an OOPS report without raising an error.
            info = (error.__class__, error, None)
            globalErrorUtility = getUtility(IErrorReportingUtility)
            globalErrorUtility.raising(info, self.request)


class PersonLanguagesView(LaunchpadFormView):
    """Edit preferred languages for a person or team."""
    schema = Interface

    @property
    def label(self):
        """The form label."""
        if self.is_current_user:
            return "Your language preferences"
        else:
            return "%s's language preferences" % self.context.displayname

    page_title = "Language preferences"

    def requestCountry(self):
        return ICountry(self.request, None)

    def browserLanguages(self):
        return (
            IRequestPreferredLanguages(self.request).getPreferredLanguages())

    def visible_checked_languages(self):
        return self.context.languages

    def visible_unchecked_languages(self):
        common_languages = getUtility(ILanguageSet).common_languages
        person_languages = self.context.languages
        return sorted(set(common_languages) - set(person_languages),
                      key=attrgetter('englishname'))

    def getRedirectionURL(self):
        request = self.request
        referrer = request.getHeader('referer')
        if referrer and (referrer.startswith(request.getApplicationURL()) or
                         referrer.find('+languages') != -1):
            return referrer
        else:
            return ''

    @property
    def is_current_user(self):
        """Return True when the Context is also the User."""
        return self.user == self.context

    @property
    def next_url(self):
        """Redirect to the +languages page if request originated there."""
        redirection_url = self.request.get('redirection_url')
        if redirection_url:
            return redirection_url
        return canonical_url(self.context)

    @property
    def cancel_url(self):
        """Redirect to the +languages page if request originated there."""
        redirection_url = self.getRedirectionURL()
        if redirection_url:
            return redirection_url
        return canonical_url(self.context)

    @action(_("Save"), name="save")
    def submitLanguages(self, action, data):
        '''Process a POST request to the language preference form.

        This list of languages submitted is compared to the list of
        languages the user has, and the latter is matched to the former.
        '''

        all_languages = getUtility(ILanguageSet)
        old_languages = self.context.languages
        new_languages = []

        for key in all_languages.keys():
            if self.request.get(key, None) == u'on':
                new_languages.append(all_languages[key])

        if self.is_current_user:
            subject = "your"
        else:
            subject = "%s's" % self.context.displayname

        # Add languages to the user's preferences.
        messages = []
        for language in set(new_languages) - set(old_languages):
            self.context.addLanguage(language)
            messages.append(
                "Added %(language)s to %(subject)s preferred languages." %
                {'language': language.englishname, 'subject': subject})

        # Remove languages from the user's preferences.
        for language in set(old_languages) - set(new_languages):
            self.context.removeLanguage(language)
            messages.append(
                "Removed %(language)s from %(subject)s preferred languages." %
                {'language': language.englishname, 'subject': subject})
        if len(messages) > 0:
            message = structured(
                '<br />'.join(['%s'] * len(messages)), *messages)
            self.request.response.addInfoNotification(message)

    @property
    def answers_url(self):
        return canonical_url(
            getUtility(ILaunchpadCelebrities).launchpad,
            rootsite='answers')


class PersonKarmaView(LaunchpadView):
    """A view class used for ~person/+karma."""

    page_title = 'Karma'

    @property
    def label(self):
        if self.user == self.context:
            return 'Your Launchpad Karma'
        else:
            return 'Launchpad Karma'

    @cachedproperty
    def has_karma(self):
        """Does the person have karma?"""
        return bool(self.context.karma_category_caches)

    @cachedproperty
    def has_expired_karma(self):
        """Did the person have karma?"""
        return not self.context.latestKarma().is_empty()


class ContactViaWebLinksMixin:

    @cachedproperty
    def group_to_contact(self):
        """Contacting a team may contact different email addresses.

        :return: the recipients of the message.
        :rtype: `ContactViaWebNotificationRecipientSet` constant:
                TO_USER
                TO_ADMINS
                TO_MEMBERS
        """
        return ContactViaWebNotificationRecipientSet(
            self.user, self.context).primary_reason

    @property
    def contact_link_title(self):
        """Return the appropriate +contactuser link title for the tooltip."""
        ContactViaWeb = ContactViaWebNotificationRecipientSet
        if self.group_to_contact == ContactViaWeb.TO_USER:
            if self.viewing_own_page:
                return 'Send an email to yourself through Launchpad'
            else:
                return 'Send an email to this user through Launchpad'
        elif self.group_to_contact == ContactViaWeb.TO_MEMBERS:
            return "Send an email to your team's members through Launchpad"
        elif self.group_to_contact == ContactViaWeb.TO_ADMINS:
            return "Send an email to this team's admins through Launchpad"
        else:
            raise AssertionError('Unknown group to contact.')

    @property
    def specific_contact_text(self):
        """Return the appropriate link text."""
        ContactViaWeb = ContactViaWebNotificationRecipientSet
        if self.group_to_contact == ContactViaWeb.TO_USER:
            # Note that we explicitly do not change the text to "Contact
            # yourself" when viewing your own page.
            return 'Contact this user'
        elif self.group_to_contact == ContactViaWeb.TO_MEMBERS:
            return "Contact this team's members"
        elif self.group_to_contact == ContactViaWeb.TO_ADMINS:
            return "Contact this team's admins"
        else:
            raise AssertionError('Unknown group to contact.')


class PersonView(LaunchpadView, FeedsMixin, ContactViaWebLinksMixin):
    """A View class used in almost all Person's pages."""

    @property
    def should_show_ubuntu_coc_section(self):
        """Should the 'Code of Conduct' section be shown?

        It's shown when the person has signed the code of conduct or has
        rights to sign it.
        """
        return self.context.is_ubuntu_coc_signer or (
            check_permission('launchpad.Edit', self.context))

    @property
    def should_show_ircnicknames_section(self):
        """Should the 'IRC nicknames' section be shown?

        It's shown when the person has IRC nicknames registered or has rights
        to register new ones.
        """
        return bool(self.context.ircnicknames) or (
            check_permission('launchpad.Edit', self.context))

    @property
    def should_show_jabberids_section(self):
        """Should the 'Jabber IDs' section be shown?

        It's shown when the person has Jabber IDs registered or has rights
        to register new ones.
        """
        return bool(self.context.jabberids) or (
            check_permission('launchpad.Edit', self.context))

    @property
    def should_show_sshkeys_section(self):
        """Should the 'SSH keys' section be shown?

        It's shown when the person has SSH keys registered or has rights
        to register new ones.
        """
        return bool(self.context.sshkeys) or (
            check_permission('launchpad.Edit', self.context))

    @property
    def should_show_gpgkeys_section(self):
        """Should the 'OpenPGP keys' section be shown?

        It's shown when the person has OpenPGP keys registered or has rights
        to register new ones.
        """
        return bool(self.context.gpg_keys) or (
            check_permission('launchpad.Edit', self.context))

    @cachedproperty
    def is_probationary_or_invalid_user(self):
        """True when the user is not active or does not have karma.

        Some content should not be rendered when the context is not a an
        established user. For example, probationary and invalid user pages
        must not be indexed by search engines and their narrative linkified.
        """
        user = self.context
        return user.is_probationary or not user.is_valid_person_or_team

    @cachedproperty
    def recently_approved_members(self):
        members = self.context.getMembersByStatus(
            TeamMembershipStatus.APPROVED,
            orderBy='-TeamMembership.date_joined')
        return members[:5]

    @cachedproperty
    def recently_proposed_members(self):
        members = self.context.getMembersByStatus(
            TeamMembershipStatus.PROPOSED,
            orderBy='-TeamMembership.date_proposed')
        return members[:5]

    @cachedproperty
    def recently_invited_members(self):
        members = self.context.getMembersByStatus(
            TeamMembershipStatus.INVITED,
            orderBy='-TeamMembership.date_proposed')
        return members[:5]

    @property
    def recently_approved_hidden(self):
        """Optionally hide the div.

        The AJAX on the page needs the elements to be present
        but hidden in case it adds a member to the list.
        """
        if IResultSet(self.recently_approved_members).is_empty():
            return 'hidden'
        else:
            return ''

    @property
    def recently_proposed_hidden(self):
        """Optionally hide the div.

        The AJAX on the page needs the elements to be present
        but hidden in case it adds a member to the list.
        """
        if IResultSet(self.recently_proposed_members).is_empty():
            return 'hidden'
        else:
            return ''

    @property
    def recently_invited_hidden(self):
        """Optionally hide the div.

        The AJAX on the page needs the elements to be present
        but hidden in case it adds a member to the list.
        """
        if IResultSet(self.recently_invited_members).is_empty():
            return 'hidden'
        else:
            return ''

    @cachedproperty
    def openpolls(self):
        assert self.context.is_team
        return IPollSubset(self.context).getOpenPolls()

    @cachedproperty
    def closedpolls(self):
        assert self.context.is_team
        return IPollSubset(self.context).getClosedPolls()

    @cachedproperty
    def notyetopenedpolls(self):
        assert self.context.is_team
        return IPollSubset(self.context).getNotYetOpenedPolls()

    @cachedproperty
    def contributions(self):
        """Cache the results of getProjectsAndCategoriesContributedTo()."""
        return self.context.getProjectsAndCategoriesContributedTo(
            self.user, limit=5)

    @cachedproperty
    def contributed_categories(self):
        """Return all karma categories in which this person has some karma."""
        categories = set()
        for contrib in self.contributions:
            categories.update(category for category in contrib['categories'])
        sort = {'code': 0, 'bugs': 1, 'blueprints': 2, 'translations': 3,
                'answers': 4, 'specs': 5, 'soyuz': 6}
        return sorted(categories, key=lambda category: sort[category.name])

    @cachedproperty
    def context_is_probably_a_team(self):
        """Return True if we have any indication that context is a team.

        For now, all we do is check whether or not any email associated with
        our context contains the '@lists.' string as that's a very good
        indication this is a team which was automatically created.

        This can only be used when the context is an automatically created
        profile (account_status == NOACCOUNT).
        """
        assert self.context.account_status == AccountStatus.NOACCOUNT, (
            "This can only be used when the context has no account.")
        emails = getUtility(IEmailAddressSet).getByPerson(self.context)
        for email in emails:
            if '@lists.' in removeSecurityProxy(email).email:
                return True
        return False

    @cachedproperty
    def is_delegated_identity(self):
        """Should the page delegate identity to the OpenId identitier.

        We only do this if it's enabled for the vhost.
        """
        return (self.context.is_valid_person
                and config.vhost.mainsite.openid_delegate_profile)

    @cachedproperty
    def openid_identity_url(self):
        """The public OpenID identity URL. That's the profile page."""
        profile_url = URI(canonical_url(self.context))
        if not config.vhost.mainsite.openid_delegate_profile:
            # Change the host to point to the production site.
            profile_url.host = config.launchpad.non_restricted_hostname
        return str(profile_url)

    def getURLToAssignedBugsInProgress(self):
        """Return an URL to a page which lists all bugs assigned to this
        person that are In Progress.
        """
        query_string = urllib.urlencode(
            [('field.status', BugTaskStatus.INPROGRESS.title)])
        url = "%s/+assignedbugs" % canonical_url(self.context)
        return ("%(url)s?search=Search&%(query_string)s"
                % {'url': url, 'query_string': query_string})

    @cachedproperty
    def assigned_bugs_in_progress(self):
        """Return up to 5 assigned bugs that are In Progress."""
        params = BugTaskSearchParams(
            user=self.user, assignee=self.context, omit_dupes=True,
            status=BugTaskStatus.INPROGRESS, orderby='-date_last_updated')
        return list(self.context.searchTasks(params)[:5])

    @cachedproperty
    def assigned_specs_in_progress(self):
        """Return up to 5 assigned specs that are being worked on."""
        specs = self.context.findVisibleAssignedInProgressSpecs(self.user)
        return list(specs)

    @property
    def has_assigned_bugs_or_specs_in_progress(self):
        """Does the user have any bugs or specs that are being worked on?"""
        bugtasks = self.assigned_bugs_in_progress
        specs = self.assigned_specs_in_progress
        return len(bugtasks) > 0 or len(specs) > 0

    @property
    def viewing_own_page(self):
        return self.user == self.context

    @property
    def can_contact(self):
        """Can the user contact this context (this person or team)?

        Users can contact other valid users and teams. Anonymous users
        cannot contact persons or teams, and no one can contact an invalid
        person (inactive or without a preferred email address).
        """
        return (
            self.user is not None and self.context.is_valid_person_or_team)

    @property
    def should_show_polls_portlet(self):
        # Circular imports.
        from lp.registry.browser.team import TeamOverviewMenu
        menu = TeamOverviewMenu(self.context)
        return (
            self.has_current_polls or self.closedpolls
            or menu.add_poll().enabled)

    @property
    def has_current_polls(self):
        """Return True if this team has any non-closed polls."""
        assert self.context.is_team
        return bool(self.openpolls) or bool(self.notyetopenedpolls)

    def userIsOwner(self):
        """Return True if the user is the owner of this Team."""
        if self.user is None:
            return False

        return self.user.inTeam(self.context.teamowner)

    def findUserPathToTeam(self):
        assert self.user is not None
        return self.user.findPathToTeam(self.context)

    def userIsParticipant(self):
        """Return true if the user is a participant of this team.

        A person is said to be a team participant when he's a member
        of that team, either directly or indirectly via another team
        membership.
        """
        if self.user is None:
            return False
        return self.user.inTeam(self.context)

    @cachedproperty
    def email_address_visibility(self):
        """The EmailAddressVisibleState of this person or team.

        :return: The state of what a logged in user may know of a
            person or team's email addresses.
        :rtype: `EmailAddressVisibleState`
        """
        return EmailAddressVisibleState(self)

    @property
    def visible_email_addresses(self):
        """The list of email address that can be shown.

        The list contains email addresses when the EmailAddressVisibleState's
        PUBLIC or ALLOWED attributes are True. The preferred email
        address is the first in the list, the other validated email addresses
        are not ordered. When the team is the context, only the preferred
        email address is in the list.

        :return: A list of email address strings that can be seen.
        """
        visible_states = (
            EmailAddressVisibleState.PUBLIC, EmailAddressVisibleState.ALLOWED)
        if self.email_address_visibility.state in visible_states:
            emails = [self.context.preferredemail.email]
            if not self.context.is_team:
                emails.extend(sorted(
                    email.email for email in self.context.validatedemails))
            return emails
        else:
            return []

    @property
    def visible_email_address_description(self):
        """A description of who can see a user's email addresses.

        :return: A string, or None if the email addresses cannot be viewed
            by any user.
        """
        state = self.email_address_visibility.state
        if state is EmailAddressVisibleState.PUBLIC:
            return 'This email address is only visible to Launchpad users.'
        elif state is EmailAddressVisibleState.ALLOWED:
            return 'This email address is not disclosed to others.'
        else:
            return None

    def showSSHKeys(self):
        """Return a data structure used for display of raw SSH keys"""
        self.request.response.setHeader('Content-Type', 'text/plain')
        keys = []
        for key in self.context.sshkeys:
            if key.keytype == SSHKeyType.DSA:
                type_name = 'ssh-dss'
            elif key.keytype == SSHKeyType.RSA:
                type_name = 'ssh-rsa'
            else:
                type_name = 'Unknown key type'
            keys.append("%s %s %s" % (type_name, key.keytext, key.comment))
        return "\n".join(keys)

    @cachedproperty
    def archive_url(self):
        """Return a url to a mailing list archive for the team's list.

        If the person is not a team, does not have a mailing list, that
        mailing list has never been activated, or the team is private and the
        logged in user is not a team member, return None instead.  The url is
        also returned if the user is a Launchpad admin.
        """
        celebrities = getUtility(ILaunchpadCelebrities)
        mailing_list = self.context.mailing_list
        if mailing_list is None:
            return None
        elif mailing_list.is_public:
            return mailing_list.archive_url
        elif self.user is None:
            return None
        elif (self.user.inTeam(self.context) or
              self.user.inTeam(celebrities.admin)):
            return mailing_list.archive_url
        else:
            return None

    @cachedproperty
    def languages(self):
        """The user's preferred languages, or English if none are set."""
        languages = list(self.context.languages)
        if len(languages) > 0:
            englishnames = [language.englishname for language in languages]
            return ', '.join(sorted(englishnames))
        else:
            return getUtility(ILaunchpadCelebrities).english.englishname

    @cachedproperty
    def should_show_ppa_section(self):
        """Return True if "Personal package archives" is to be shown.

        We display it if:
        current_user may view at least one PPA or current_user has lp.edit
        """
        # If the current user has edit permission, show the section.
        if check_permission('launchpad.Edit', self.context):
            return True

        # If the current user can view any PPA, show the section.
        return not self.visible_ppas.is_empty()

    @cachedproperty
    def visible_ppas(self):
        return self.context.getVisiblePPAs(self.user)

    @property
    def time_zone_offset(self):
        """Return a string with offset from UTC"""
        return datetime.now(
            pytz.timezone(self.context.time_zone)).strftime("%z")


class PersonParticipationView(LaunchpadView):
    """View for the ~person/+participation page."""

    @property
    def label(self):
        return 'Team participation for ' + self.context.displayname

    def _asParticipation(self, membership=None, team=None, via=None):
        """Return a dict of participation information for the membership.

        Method requires membership or team, not both.
        :param via: The team through which the membership in the indirect
        team is established.
        """
        if ((membership is None and team is None) or
            (membership is not None and team is not None)):
            raise AssertionError(
                "The membership or team argument must be provided, not both.")

        if via is not None:
            # When showing the path, it's unnecessary to show the team in
            # question at the beginning of the path, or the user at the
            # end of the path.
            via = COMMASPACE.join(
                [via_team.displayname for via_team in via[1:-1]])

        if membership is None:
            # Membership is via an indirect team so sane defaults exist.
            # An indirect member cannot be an Owner or Admin of a team.
            role = 'Member'
            # The Person never joined, and can't have a join date.
            datejoined = None
        else:
            # The member is a direct member; use the membership data.
            team = membership.team
            datejoined = membership.datejoined
            if membership.person == team.teamowner:
                role = 'Owner'
            elif membership.status == TeamMembershipStatus.ADMIN:
                role = 'Admin'
            else:
                role = 'Member'

        if team.mailing_list is not None and team.mailing_list.is_usable:
            subscription = team.mailing_list.getSubscription(self.context)
            if subscription is None:
                subscribed = 'Not subscribed'
            else:
                subscribed = 'Subscribed'
        else:
            subscribed = '&mdash;'

        return dict(
            displayname=team.displayname, team=team, datejoined=datejoined,
            role=role, via=via, subscribed=subscribed)

    @cachedproperty
    def active_participations(self):
        """Return the participation information for active memberships."""
        paths, memberships = self.context.getPathsToTeams()
        direct_teams = [membership.team for membership in memberships]
        indirect_teams = [
            team for team in paths.keys()
            if team not in direct_teams]
        participations = []

        # First, create a participation for all direct memberships.
        for membership in memberships:
            # Add a participation record for the membership if allowed.
            if check_permission('launchpad.View', membership.team):
                participations.append(
                    self._asParticipation(membership=membership))

        # Second, create a participation for all indirect memberships,
        # using the remaining paths.
        for indirect_team in indirect_teams:
            if not check_permission('launchpad.View', indirect_team):
                continue
            participations.append(
                self._asParticipation(
                    via=paths[indirect_team],
                    team=indirect_team))
        return sorted(participations, key=itemgetter('displayname'))

    @cachedproperty
    def has_participations(self):
        return len(self.active_participations) > 0


class EmailAddressVisibleState:
    """The state of a person's email addresses w.r.t. the logged in user.

    There are five states that describe the visibility of a person or
    team's addresses to a logged in user, only one will be True:

    * LOGIN_REQUIRED: The user is anonymous; email addresses are never
      visible to anonymous users.
    * NONE_AVAILABLE: The person has no validated email addresses or the
      team has no contact address registered, so there is nothing to show.
    * PUBLIC: The person is not hiding their email addresses, or the team
      has a contact address, so any logged in user may view them.
    * HIDDEN: The person is hiding their email address, so even logged in
      users cannot view them.  Teams cannot hide their contact address.
    * ALLOWED: The person is hiding their email address, but the logged in
      user has permission to see them.  This is either because the user is
      viewing their own page or because the user is a privileged
      administrator.
    """
    LOGIN_REQUIRED = object()
    NONE_AVAILABLE = object()
    PUBLIC = object()
    HIDDEN = object()
    ALLOWED = object()

    def __init__(self, view):
        """Set the state.

        :param view: The view that provides the current user and the
            context (person or team).
        :type view: `LaunchpadView`
        """
        if view.user is None:
            self.state = EmailAddressVisibleState.LOGIN_REQUIRED
        elif view.context.preferredemail is None:
            self.state = EmailAddressVisibleState.NONE_AVAILABLE
        elif not view.context.hide_email_addresses:
            self.state = EmailAddressVisibleState.PUBLIC
        elif check_permission('launchpad.View', view.context.preferredemail):
            self.state = EmailAddressVisibleState.ALLOWED
        else:
            self.state = EmailAddressVisibleState.HIDDEN

    @property
    def is_login_required(self):
        """Is login required to see the person or team's addresses?"""
        return self.state is EmailAddressVisibleState.LOGIN_REQUIRED

    @property
    def are_none_available(self):
        """Does the person or team not have any email addresses?"""
        return self.state is EmailAddressVisibleState.NONE_AVAILABLE

    @property
    def are_public(self):
        """Are the person's or team's email addresses public to users?"""
        return self.state is EmailAddressVisibleState.PUBLIC

    @property
    def are_hidden(self):
        """Are the person's or team's email addresses hidden from the user?"""
        return self.state is EmailAddressVisibleState.HIDDEN

    @property
    def are_allowed(self):
        """Is the user allowed to see the person's or team's addresses?"""
        return self.state is EmailAddressVisibleState.ALLOWED


class PersonIndexView(XRDSContentNegotiationMixin, PersonView,
                      TeamJoinMixin):
    """View class for person +index and +xrds pages."""

    xrds_template = ViewPageTemplateFile(
        "../../services/openid/templates/person-xrds.pt")

    def initialize(self):
        super(PersonIndexView, self).initialize()
        if self.context.isMergePending():
            if self.context.is_team:
                merge_action = 'merged or deleted'
            else:
                merge_action = 'merged'
            self.request.response.addInfoNotification(
                "%s is queued to be %s in a few minutes." % (
                self.context.displayname, merge_action))
        if self.request.method == "POST":
            self.processForm()

    @property
    def page_title(self):
        context = self.context
        if context.is_valid_person_or_team:
            return '%s in Launchpad' % context.displayname
        else:
            return "%s does not use Launchpad" % context.displayname

    @property
    def description_widget(self):
        """The description as a widget."""
        non_probationary = not self.context.is_probationary
        return TextAreaEditorWidget(
            self.context, IPerson['description'], title="",
            edit_title='Edit description', hide_empty=False,
            linkify_text=non_probationary)

    @cachedproperty
    def page_description(self):
        if self.context.is_valid_person_or_team:
            return self.context.description
        else:
            return None

    @cachedproperty
    def enable_xrds_discovery(self):
        """Only enable discovery if person is OpenID enabled."""
        return self.is_delegated_identity

    @cachedproperty
    def openid_server_url(self):
        """The OpenID Server endpoint URL for Launchpad."""
        return CurrentOpenIDEndPoint.getServiceURL()

    @cachedproperty
    def openid_identity_url(self):
        return IOpenIDPersistentIdentity(self.context).openid_identity_url

    def processForm(self):
        if not self.request.form.get('unsubscribe'):
            raise UnexpectedFormData(
                "The mailing list form did not receive the expected form "
                "fields.")

        mailing_list = self.context.mailing_list
        if mailing_list is None:
            raise UnexpectedFormData(
                _("This team does not use Launchpad to host a mailing list."))
        if not self.user:
            raise Unauthorized(
                _("You must be logged in to unsubscribe."))
        try:
            mailing_list.unsubscribe(self.user)
        except CannotUnsubscribe:
            self.request.response.addErrorNotification(
                _("You could not be unsubscribed from the team mailing "
                  "list."))
        else:
            self.request.response.addInfoNotification(
                _("You have been unsubscribed from the team "
                  "mailing list."))
        self.request.response.redirect(canonical_url(self.context))


class PersonCodeOfConductEditView(LaunchpadView):
    """View for the ~person/+codesofconduct pages."""

    @property
    def label(self):
        """See `LaunchpadView`."""
        return 'Codes of Conduct for ' + self.context.displayname

    def initialize(self):
        """See `LaunchpadView`."""
        # Make changes to code-of-conduct signature records for this person.
        sig_ids = self.request.form.get("DEACTIVATE_SIGNATURE")

        if sig_ids is not None:
            sCoC_util = getUtility(ISignedCodeOfConductSet)
            # Verify that we have multiple entries to deactive.
            if not isinstance(sig_ids, list):
                sig_ids = [sig_ids]
            for sig_id in sig_ids:
                sig_id = int(sig_id)
                # Deactivating signature.
                comment = 'Deactivated by Owner'
                sCoC_util.modifySignature(sig_id, self.user, comment, False)


class PersonEditIRCNicknamesView(LaunchpadFormView):

    schema = Interface

    @property
    def page_title(self):
        return smartquote("%s's IRC nicknames" % self.context.displayname)

    label = page_title

    @property
    def cancel_url(self):
        return canonical_url(self.context)

    @action(_("Save Changes"), name="save")
    def save(self, action, data):
        """Process the IRC nicknames form."""
        # XXX: EdwinGrubbs 2009-09-01 bug=422784
        # This view should use schema and form validation.
        form = self.request.form
        for ircnick in self.context.ircnicknames:
            # XXX: GuilhermeSalgado 2005-08-25:
            # We're exposing IrcID IDs here because that's the only
            # unique column we have, so we don't have anything else that we
            # can use to make field names that allow us to uniquely identify
            # them.
            if form.get('remove_%d' % ircnick.id):
                ircnick.destroySelf()
            else:
                nick = form.get('nick_%d' % ircnick.id)
                network = form.get('network_%d' % ircnick.id)
                if not (nick and network):
                    self.request.response.addErrorNotification(
                        "Neither Nickname nor Network can be empty.")
                    return
                ircnick.nickname = nick
                ircnick.network = network

        nick = form.get('newnick')
        network = form.get('newnetwork')
        if nick or network:
            if nick and network:
                getUtility(IIrcIDSet).new(self.context, network, nick)
            else:
                self.newnick = nick
                self.newnetwork = network
                self.request.response.addErrorNotification(
                    "Neither Nickname nor Network can be empty.")


class PersonEditJabberIDsView(LaunchpadFormView):

    schema = IJabberID
    field_names = ['jabberid']

    def setUpFields(self):
        super(PersonEditJabberIDsView, self).setUpFields()
        if not self.context.jabberids.is_empty():
            # Make the jabberid entry optional on the edit page if one or more
            # ids already exist, which allows the removal of ids without
            # filling out the new jabberid field.
            jabber_field = self.form_fields['jabberid']
            # Copy the field so as not to modify the interface.
            jabber_field.field = copy_field(jabber_field.field)
            jabber_field.field.required = False

    @property
    def page_title(self):
        return smartquote("%s's Jabber IDs" % self.context.displayname)

    label = page_title

    @property
    def next_url(self):
        return canonical_url(self.context)

    cancel_url = next_url

    def validate(self, data):
        """Ensure the edited data does not already exist."""
        jabberid = data.get('jabberid')
        if jabberid is not None:
            jabberset = getUtility(IJabberIDSet)
            existingjabber = jabberset.getByJabberID(jabberid)
            if existingjabber is not None:
                if existingjabber.person != self.context:
                    self.setFieldError(
                        'jabberid',
                        structured(
                            'The Jabber ID %s is already registered by '
                            '<a href="%s">%s</a>.',
                            jabberid, canonical_url(existingjabber.person),
                            existingjabber.person.displayname))
                else:
                    self.setFieldError(
                        'jabberid',
                        'The Jabber ID %s already belongs to you.' % jabberid)

    @action(_("Save Changes"), name="save")
    def save(self, action, data):
        """Process the Jabber ID form."""
        form = self.request.form
        for jabber in self.context.jabberids:
            if form.get('remove_%s' % jabber.jabberid):
                jabber.destroySelf()
        jabberid = data.get('jabberid')
        if jabberid is not None:
            jabberset = getUtility(IJabberIDSet)
            jabberset.new(self.context, jabberid)


class PersonEditSSHKeysView(LaunchpadView):

    implements(IPersonEditMenu)

    info_message = None
    error_message = None

    def initialize(self):
        require_fresh_login(self.request, self.context, '+editsshkeys')

        if self.request.method != "POST":
            # Nothing to do
            return

        action = self.request.form.get('action')

        if action == 'add_ssh':
            self.add_ssh()
        elif action == 'remove_ssh':
            self.remove_ssh()
        else:
            raise UnexpectedFormData("Unexpected action: %s" % action)

    @property
    def label(self):
        return "Change your SSH keys"

    page_title = label

    @property
    def cancel_url(self):
        return canonical_url(self.context, view_name="+edit")

    def add_ssh(self):
        sshkey = self.request.form.get('sshkey')
        try:
            getUtility(ISSHKeySet).new(self.user, sshkey)
        except SSHKeyAdditionError:
            self.error_message = structured('Invalid public key')
        except SSHKeyCompromisedError:
            self.error_message = structured(
                'This key is known to be compromised due to a security flaw '
                'in the software used to generate it, so it will not be '
                'accepted by Launchpad. See the full '
                '<a href="http://www.ubuntu.com/usn/usn-612-2">Security '
                'Notice</a> for further information and instructions on how '
                'to generate another key.')
        else:
            self.info_message = structured('SSH public key added.')

    def remove_ssh(self):
        key_id = self.request.form.get('key')
        if not key_id:
            raise UnexpectedFormData('SSH Key was not defined')

        sshkey = getUtility(ISSHKeySet).getByID(key_id)
        if sshkey is None:
            self.error_message = structured(
                "Cannot remove a key that doesn't exist")
            return

        if sshkey.person != self.user:
            raise UnexpectedFormData("Cannot remove someone else's key")

        comment = sshkey.comment
        sshkey.destroySelf()
        self.info_message = structured('Key "%s" removed', comment)


class PersonGPGView(LaunchpadView):
    """View for the GPG-related actions for a Person

    Supports claiming (importing) a key, validating it and deactivating
    it. Also supports removing the token generated for validation (in
    the case you want to give up on importing the key).
    """

    implements(IPersonEditMenu)

    key = None
    fingerprint = None

    key_ok = False
    invalid_fingerprint = False
    key_retrieval_failed = False
    key_already_imported = False

    error_message = None
    info_message = None

    def initialize(self):
        require_fresh_login(self.request, self.context, '+editpgpkeys')
        super(PersonGPGView, self).initialize()

    @property
    def cancel_url(self):
        return canonical_url(self.context, view_name="+edit")

    @property
    def label(self):
        return "Change your OpenPGP keys"

    page_title = label

    def keyserver_url(self):
        assert self.fingerprint
        return getUtility(
            IGPGHandler).getURLForKeyInServer(self.fingerprint, public=True)

    def form_action(self):
        permitted_actions = [
            'claim_gpg',
            'deactivate_gpg',
            'remove_gpgtoken',
            'reactivate_gpg',
            ]
        if self.request.method != "POST":
            return ''
        action = self.request.form.get('action')
        if action not in permitted_actions:
            raise UnexpectedFormData("Action not permitted: %s" % action)
        getattr(self, action)()

    def claim_gpg(self):
        # XXX cprov 2005-04-01: As "Claim GPG key" takes a lot of time, we
        # should process it throught the NotificationEngine.
        gpghandler = getUtility(IGPGHandler)
        fingerprint = self.request.form.get('fingerprint')
        self.fingerprint = gpghandler.sanitizeFingerprint(fingerprint)

        if not self.fingerprint:
            self.invalid_fingerprint = True
            return

        gpgkeyset = getUtility(IGPGKeySet)
        if gpgkeyset.getByFingerprint(self.fingerprint):
            self.key_already_imported = True
            return

        try:
            key = gpghandler.retrieveKey(self.fingerprint)
        except GPGKeyNotFoundError:
            self.key_retrieval_failed = True
            return

        self.key = key
        if not key.expired and not key.revoked:
            self._validateGPG(key)
            self.key_ok = True

    def deactivate_gpg(self):
        key_ids = self.request.form.get('DEACTIVATE_GPGKEY')

        if key_ids is None:
            self.error_message = structured(
                'No key(s) selected for deactivation.')
            return

        # verify if we have multiple entries to deactive
        if not isinstance(key_ids, list):
            key_ids = [key_ids]

        gpgkeyset = getUtility(IGPGKeySet)

        deactivated_keys = []
        for key_id in key_ids:
            gpgkey = gpgkeyset.get(key_id)
            if gpgkey is None:
                continue
            if gpgkey.owner != self.user:
                self.error_message = structured(
                    "Cannot deactivate someone else's key")
                return
            gpgkey.active = False
            deactivated_keys.append(gpgkey.displayname)

        flush_database_updates()
        self.info_message = structured(
           'Deactivated key(s): %s', ", ".join(deactivated_keys))

    def remove_gpgtoken(self):
        token_fingerprints = self.request.form.get('REMOVE_GPGTOKEN')

        if token_fingerprints is None:
            self.error_message = structured(
                'No key(s) pending validation selected.')
            return

        logintokenset = getUtility(ILoginTokenSet)
        if not isinstance(token_fingerprints, list):
            token_fingerprints = [token_fingerprints]

        cancelled_fingerprints = []
        for fingerprint in token_fingerprints:
            logintokenset.deleteByFingerprintRequesterAndType(
                fingerprint, self.user, LoginTokenType.VALIDATEGPG)
            logintokenset.deleteByFingerprintRequesterAndType(
                fingerprint, self.user, LoginTokenType.VALIDATESIGNONLYGPG)
            cancelled_fingerprints.append(fingerprint)

        self.info_message = structured(
            'Cancelled validation of key(s): %s',
            ", ".join(cancelled_fingerprints))

    def reactivate_gpg(self):
        key_ids = self.request.form.get('REACTIVATE_GPGKEY')

        if key_ids is None:
            self.error_message = structured(
                'No key(s) selected for reactivation.')
            return

        found = []
        notfound = []
        # Verify if we have multiple entries to activate.
        if not isinstance(key_ids, list):
            key_ids = [key_ids]

        gpghandler = getUtility(IGPGHandler)
        keyset = getUtility(IGPGKeySet)

        for key_id in key_ids:
            gpgkey = keyset.get(key_id)
            try:
                key = gpghandler.retrieveKey(gpgkey.fingerprint)
            except GPGKeyNotFoundError:
                notfound.append(gpgkey.fingerprint)
            else:
                found.append(key.displayname)
                self._validateGPG(key)

        comments = []
        if len(found) > 0:
            comments.append(
                'A message has been sent to %s with instructions to '
                'reactivate these key(s): %s'
                % (self.context.preferredemail.email, ', '.join(found)))
        if len(notfound) > 0:
            if len(notfound) == 1:
                comments.append(
                    'Launchpad failed to retrieve this key from '
                    'the keyserver: %s. Please make sure the key is '
                    'published in a keyserver (such as '
                    '<a href="http://pgp.mit.edu">pgp.mit.edu</a>) before '
                    'trying to reactivate it again.' % (', '.join(notfound)))
            else:
                comments.append(
                    'Launchpad failed to retrieve these keys from '
                    'the keyserver: %s. Please make sure the keys '
                    'are published in a keyserver (such as '
                    '<a href="http://pgp.mit.edu">pgp.mit.edu</a>) '
                    'before trying to reactivate them '
                    'again.' % (', '.join(notfound)))

        self.info_message = structured('\n<br />\n'.join(comments))

    def _validateGPG(self, key):
        bag = getUtility(ILaunchBag)
        preferredemail = bag.user.preferredemail.email
        login = bag.login

        if key.can_encrypt:
            tokentype = LoginTokenType.VALIDATEGPG
        else:
            tokentype = LoginTokenType.VALIDATESIGNONLYGPG

        token = getUtility(ILoginTokenSet).new(
            self.context, login, preferredemail, tokentype,
            fingerprint=key.fingerprint)

        token.sendGPGValidationRequest(key)


class BasePersonEditView(LaunchpadEditFormView):

    schema = IPerson
    field_names = []

    @action(_("Save"), name="save")
    def action_save(self, action, data):
        self.updateContextFromData(data)

    @property
    def next_url(self):
        return canonical_url(self.context)

    cancel_url = next_url


class PersonEditView(PersonRenameFormMixin, BasePersonEditView):
    """The Person 'Edit' page."""

    field_names = ['displayname', 'name', 'mugshot', 'description',
                   'hide_email_addresses', 'verbose_bugnotifications',
                   'selfgenerated_bugnotifications']
    custom_widget('mugshot', ImageChangeWidget, ImageChangeWidget.EDIT_STYLE)

    implements(IPersonEditMenu)

    label = 'Change your personal details'
    page_title = label

    # Will contain an hidden input when the user is renaming his
    # account with full knowledge of the consequences.
    i_know_this_is_an_openid_security_issue_input = None

    def validate(self, data):
        """If the name changed, warn the user about the implications."""
        new_name = data.get('name')
        bypass_check = self.request.form_ng.getOne(
            'i_know_this_is_an_openid_security_issue', 0)
        if (new_name and new_name != self.context.name and not bypass_check):
            # Warn the user that they might shoot themselves in the foot.
            self.setFieldError('name', structured(dedent('''
            <div class="inline-warning">
              <p>Changing your name will change your
                  public OpenID identifier. This means that you might be
                  locked out of certain sites where you used it, or that
                  somebody could create a new profile with the same name and
                  log in as you on these third-party sites. See
                  <a href="https://help.launchpad.net/OpenID#rename-account"
                    >https://help.launchpad.net/OpenID#rename-account</a>
                  for more information.
              </p>
              <p>If you click 'Save' again, we will rename your account
                 anyway.
              </p>
            </div>'''),))
            self.i_know_this_is_an_openid_security_issue_input = dedent("""\
                <input type="hidden"
                       id="i_know_this_is_an_openid_security_issue"
                       name="i_know_this_is_an_openid_security_issue"
                       value="1">""")

    @action(_("Save Changes"), name="save")
    def action_save(self, action, data):
        # XXX: BradCrittenden 2010-09-10 bug=634878: Find a cleaner solution
        # to the permissions problem for 'name'.  Users should be able to
        # change their name, but the permission setting for the attribute is
        # launchpad.Moderate, which only allows admins and registry.  A user
        # must have launchpad.Edit to access this page.
        if 'name' in data:
            new_name = data['name']
            removeSecurityProxy(self.context).name = new_name
            del data['name']
        self.updateContextFromData(data)
        self.request.response.addInfoNotification(
            'The changes to your personal details have been saved.')


class PersonBrandingView(BrandingChangeView):

    field_names = ['logo', 'mugshot']
    schema = IPerson


class PersonEditEmailsView(LaunchpadFormView):
    """A view for editing a person's email settings.

    The user can associate emails with their account, verify emails
    the system associated with their account, and remove associated
    emails.
    """

    implements(IPersonEditMenu)

    schema = IEmailAddress

    custom_widget('VALIDATED_SELECTED', LaunchpadRadioWidget,
                  orientation='vertical')
    custom_widget('UNVALIDATED_SELECTED', LaunchpadRadioWidget,
                  orientation='vertical')
    custom_widget('mailing_list_auto_subscribe_policy',
                  LaunchpadRadioWidgetWithDescription)

    label = 'Change your e-mail settings'

    def initialize(self):
        require_fresh_login(self.request, self.context, '+editemails')
        if self.context.is_team:
            # +editemails is not available on teams.
            name = self.request['PATH_INFO'].split('/')[-1]
            raise NotFound(self, name, request=self.request)
        super(PersonEditEmailsView, self).initialize()

    def setUpFields(self):
        """Set up fields for this view.

        The main fields of interest are the selection fields with custom
        vocabularies for the lists of validated and unvalidated email
        addresses.
        """
        super(PersonEditEmailsView, self).setUpFields()
        self.form_fields = (self._validated_emails_field() +
                            self._unvalidated_emails_field() +
                            FormFields(TextLine(__name__='newemail',
                                                title=u'Add a new address'))
                            + self._mailing_list_fields()
                            + self._autosubscribe_policy_fields())

    @property
    def initial_values(self):
        """Set up default values for the radio widgets.

        A radio widget must have a selected value, so we select the
        first unvalidated and validated email addresses in the lists
        to be the default for the corresponding widgets.

        The only exception is if the user has a preferred email
        address: then, that address is used as the default validated
        email address.
        """
        # Defaults for the user's email addresses.
        validated = self.context.preferredemail
        if validated is None and not self.context.validatedemails.is_empty():
            validated = self.context.validatedemails[0]
        unvalidated = self.unvalidated_addresses
        if len(unvalidated) > 0:
            unvalidated = unvalidated.pop()
        initial = dict(VALIDATED_SELECTED=validated,
                       UNVALIDATED_SELECTED=unvalidated)

        # Defaults for the mailing list autosubscribe buttons.
        policy = self.context.mailing_list_auto_subscribe_policy
        initial.update(mailing_list_auto_subscribe_policy=policy)

        return initial

    def setUpWidgets(self, context=None):
        """See `LaunchpadFormView`."""
        super(PersonEditEmailsView, self).setUpWidgets(context)
        widget = self.widgets['mailing_list_auto_subscribe_policy']
        widget.display_label = False

    def _validated_emails_field(self):
        """Create a field with a vocabulary of validated emails.

        :return: A Choice field containing the list of validated emails
        """
        terms = [SimpleTerm(term, term.email)
                 for term in self.context.validatedemails]
        preferred = self.context.preferredemail
        if preferred:
            terms.insert(0, SimpleTerm(preferred, preferred.email))

        return FormFields(
            Choice(__name__='VALIDATED_SELECTED',
                   title=_('These addresses are confirmed as being yours'),
                   source=SimpleVocabulary(terms),
                   ),
            custom_widget=self.custom_widgets['VALIDATED_SELECTED'])

    def _unvalidated_emails_field(self):
        """Create a field with a vocabulary of unvalidated and guessed emails.

        :return: A Choice field containing the list of emails
        """
        terms = []
        for term in self.unvalidated_addresses:
            if isinstance(term, unicode):
                term = SimpleTerm(term)
            else:
                term = SimpleTerm(term, term.email)
            terms.append(term)
        if self.validated_addresses:
            title = _('These addresses may also be yours')
        else:
            title = _('These addresses may be yours')

        return FormFields(
            Choice(__name__='UNVALIDATED_SELECTED', title=title,
                   source=SimpleVocabulary(terms)),
            custom_widget=self.custom_widgets['UNVALIDATED_SELECTED'])

    def _mailing_list_subscription_type(self, mailing_list):
        """Return the context user's subscription type for the given list.

        This is 'Preferred address' if the user is subscribed using her
        preferred address and 'Don't subscribe' if the user is not
        subscribed at all. Otherwise it's the EmailAddress under
        which the user is subscribed to this mailing list.
        """
        subscription = mailing_list.getSubscription(self.context)
        if subscription is None:
            return "Don't subscribe"
        elif subscription.email_address is None:
            return 'Preferred address'
        else:
            return subscription.email_address

    def _mailing_list_fields(self):
        """Creates a field for each mailing list the user can subscribe to.

        If a team doesn't have a mailing list, or the mailing list
        isn't usable, it's not included.
        """
        mailing_list_set = getUtility(IMailingListSet)
        fields = []
        terms = [
            SimpleTerm("Preferred address"),
            SimpleTerm("Don't subscribe"),
            ]
        for email in self.validated_addresses:
            terms.append(SimpleTerm(email, email.email))
        for team in self.context.teams_participated_in:
            mailing_list = mailing_list_set.get(team.name)
            if mailing_list is not None and mailing_list.is_usable:
                name = 'subscription.%s' % team.name
                value = self._mailing_list_subscription_type(mailing_list)
                field = Choice(__name__=name,
                               title=team.name,
                               source=SimpleVocabulary(terms), default=value)
                fields.append(field)
        return FormFields(*fields)

    def _autosubscribe_policy_fields(self):
        """Create a field for each mailing list auto-subscription option."""
        return FormFields(
            Choice(__name__='mailing_list_auto_subscribe_policy',
                   title=_('When should Launchpad automatically subscribe '
                           'you to a team&#x2019;s mailing list?'),
                   source=MailingListAutoSubscribePolicy))

    @property
    def mailing_list_widgets(self):
        """Return all the mailing list subscription widgets."""
        mailing_list_set = getUtility(IMailingListSet)
        widgets = []
        for widget in self.widgets:
            if widget.name.startswith('field.subscription.'):
                team_name = widget.label
                mailing_list = mailing_list_set.get(team_name)
                assert mailing_list is not None, 'Missing mailing list'
                widget_dict = dict(
                    team=mailing_list.team,
                    widget=widget,
                    )
                widgets.append(widget_dict)
                # We'll put the label in the first column, so don't include it
                # in the second column.
                widget.display_label = False
        return widgets

    def _validate_selected_address(self, data, field='VALIDATED_SELECTED'):
        """A generic validator for this view's actions.

        Makes sure one (and only one) email address is selected and that
        the selected address belongs to the context person. The address may
        be represented by an EmailAddress object or (for unvalidated
        addresses) a LoginToken object.
        """
        self.validate_widgets(data, [field])

        email = data.get(field)
        if email is None:
            return None
        elif isinstance(data[field], list):
            self.addError("You must not select more than one address.")
            return None

        # Make sure the selected address or login token actually
        # belongs to this person.
        if IEmailAddress.providedBy(email):
            person = email.person

            assert person == self.context, (
                "differing ids in emailaddress.person.id(%s,%d) == "
                "self.context.id(%s,%d) (%s)"
                % (person.name, person.id, self.context.name, self.context.id,
                   email.email))
        elif isinstance(email, unicode):
            tokenset = getUtility(ILoginTokenSet)
            email = tokenset.searchByEmailRequesterAndType(
                email, self.context, LoginTokenType.VALIDATEEMAIL)
            assert email is not None, "Couldn't find login token!"
        else:
            raise AssertionError("Selected address was not EmailAddress "
                                 "or unicode string!")

        # Return the EmailAddress/LoginToken object for use in any
        # further validation.
        return email

    @property
    def validated_addresses(self):
        """All of this person's validated email addresses, including
        their preferred address (if any).
        """
        addresses = []
        if self.context.preferredemail:
            addresses.append(self.context.preferredemail)
        addresses += [email for email in self.context.validatedemails]
        return addresses

    @property
    def unvalidated_addresses(self):
        """All of this person's unvalidated and guessed emails.

        The guessed emails will be EmailAddress objects, and the
        unvalidated emails will be unicode strings.
        """
        emailset = set(self.context.unvalidatedemails)
        emailset = emailset.union(
            [guessed for guessed in self.context.guessedemails
             if not guessed.email in emailset])
        return emailset

    def validate_action_remove_validated(self, action, data):
        """Make sure the user selected an email address to remove."""
        emailaddress = self._validate_selected_address(data,
                                                       'VALIDATED_SELECTED')
        if emailaddress is None:
            return self.errors

        if self.context.preferredemail == emailaddress:
            self.addError(
                "You can't remove %s because it's your contact email "
                "address." % self.context.preferredemail.email)
            return self.errors
        return self.errors

    @action(_("Remove"), name="remove_validated",
            validator=validate_action_remove_validated)
    def action_remove_validated(self, action, data):
        """Delete the selected (validated) email address."""
        emailaddress = data['VALIDATED_SELECTED']
        emailaddress.destroySelf()
        self.request.response.addInfoNotification(
            "The email address '%s' has been removed." % emailaddress.email)
        self.next_url = self.action_url

    def validate_action_set_preferred(self, action, data):
        """Make sure the user selected an address."""
        emailaddress = self._validate_selected_address(data,
                                                       'VALIDATED_SELECTED')
        if emailaddress is None:
            return self.errors

        if emailaddress.status == EmailAddressStatus.PREFERRED:
            self.request.response.addInfoNotification(
                "%s is already set as your contact address." % (
                    emailaddress.email))
        return self.errors

    @action(_("Set as Contact Address"), name="set_preferred",
            validator=validate_action_set_preferred)
    def action_set_preferred(self, action, data):
        """Set the selected email as preferred for the person in context."""
        emailaddress = data['VALIDATED_SELECTED']
        if emailaddress.status != EmailAddressStatus.PREFERRED:
            self.context.setPreferredEmail(emailaddress)
            self.request.response.addInfoNotification(
                "Your contact address has been changed to: %s" % (
                    emailaddress.email))
        self.next_url = self.action_url

    def validate_action_confirm(self, action, data):
        """Make sure the user selected an email address to confirm."""
        self._validate_selected_address(data, 'UNVALIDATED_SELECTED')
        return self.errors

    @action(_('Confirm'), name='validate', validator=validate_action_confirm)
    def action_confirm(self, action, data):
        """Mail a validation URL to the selected email address."""
        email = data['UNVALIDATED_SELECTED']
        if IEmailAddress.providedBy(email):
            email = email.email
        token = getUtility(ILoginTokenSet).new(
            self.context, getUtility(ILaunchBag).login, email,
            LoginTokenType.VALIDATEEMAIL)
        token.sendEmailValidationRequest()
        self.request.response.addInfoNotification(
            "An e-mail message was sent to '%s' with "
            "instructions on how to confirm that "
            "it belongs to you." % email)
        self.next_url = self.action_url

    def validate_action_remove_unvalidated(self, action, data):
        """Make sure the user selected an email address to remove."""
        email = self._validate_selected_address(data, 'UNVALIDATED_SELECTED')
        if email is not None and IEmailAddress.providedBy(email):
            assert self.context.preferredemail.id != email.id
        return self.errors

    @action(_("Remove"), name="remove_unvalidated",
            validator=validate_action_remove_unvalidated)
    def action_remove_unvalidated(self, action, data):
        """Delete the selected (un-validated) email address.

        This selected address can be either on the EmailAddress table
        marked with status NEW, or in the LoginToken table.
        """
        emailaddress = data['UNVALIDATED_SELECTED']
        if IEmailAddress.providedBy(emailaddress):
            emailaddress.destroySelf()
            email = emailaddress.email
        elif isinstance(emailaddress, unicode):
            logintokenset = getUtility(ILoginTokenSet)
            logintokenset.deleteByEmailRequesterAndType(
                emailaddress, self.context, LoginTokenType.VALIDATEEMAIL)
            email = emailaddress
        else:
            raise AssertionError("Selected address was not EmailAddress "
                                 "or Unicode string!")

        self.request.response.addInfoNotification(
            "The email address '%s' has been removed." % email)
        self.next_url = self.action_url

    def validate_action_add_email(self, action, data):
        """Make sure the user entered a valid email address.

        The email address must be syntactically valid and must not already
        be in use.
        """
        has_errors = bool(self.validate_widgets(data, ['newemail']))
        if has_errors:
            # We know that 'newemail' is empty.
            return self.errors

        newemail = data['newemail']
        if not valid_email(newemail):
            self.addError(
                "'%s' doesn't seem to be a valid email address." % newemail)
            return self.errors

        # XXX j.c.sackett 2010-09-15 bug=628247, 576757 There is a validation
        # system set up for this that is almost identical in
        # lp.app.validators.validation, called
        # _check_email_available or similar. It would be really nice if we
        # could merge that code somehow with this.
        email = getUtility(IEmailAddressSet).getByEmail(newemail)
        person = self.context
        if email is not None:
            if email.person == person:
                self.addError(
                    "The email address '%s' is already registered as your "
                    "email address. This can be either because you already "
                    "added this email address before or because our system "
                    "detected it as being yours. If it was detected by our "
                    "system, it's probably shown on this page and is waiting "
                    "to be confirmed as yours." % newemail)
            else:
                owner = email.person
                owner_name = urllib.quote(owner.name)
                merge_url = (
                    '%s/+requestmerge?field.dupe_person=%s'
                    % (canonical_url(getUtility(IPersonSet)), owner_name))
                self.addError(structured(
                    "The email address '%s' is already registered to "
                    '<a href="%s">%s</a>. If you think that is a '
                    'duplicated account, you can <a href="%s">merge it'
                    "</a> into your account.",
                    newemail, canonical_url(owner), owner.displayname,
                    merge_url))
        return self.errors

    @action(_("Add"), name="add_email", validator=validate_action_add_email)
    def action_add_email(self, action, data):
        """Register a new email for the person in context."""
        newemail = data['newemail']
        token = getUtility(ILoginTokenSet).new(
            self.context, getUtility(ILaunchBag).login, newemail,
            LoginTokenType.VALIDATEEMAIL)
        token.sendEmailValidationRequest()

        self.request.response.addInfoNotification(
                "A confirmation message has been sent to '%s'. "
                "Follow the instructions in that message to confirm that the "
                "address is yours. "
                "(If the message doesn't arrive in a few minutes, your mail "
                "provider might use 'greylisting', which could delay the "
                "message for up to an hour or two.)" % newemail)
        self.next_url = self.action_url

    def validate_action_update_subscriptions(self, action, data):
        """Make sure the user is subscribing using a valid address.

        Valid addresses are the ones presented as options for the mailing
        list widgets.
        """
        names = [widget_dict['widget'].context.getName()
                 for widget_dict in self.mailing_list_widgets]
        self.validate_widgets(data, names)
        return self.errors

    @action(_("Update Subscriptions"), name="update_subscriptions",
            validator=validate_action_update_subscriptions)
    def action_update_subscriptions(self, action, data):
        """Change the user's mailing list subscriptions."""
        mailing_list_set = getUtility(IMailingListSet)
        dirty = False
        prefix_length = len('subscription.')
        for widget_dict in self.mailing_list_widgets:
            widget = widget_dict['widget']
            mailing_list_name = widget.context.getName()[prefix_length:]
            mailing_list = mailing_list_set.get(mailing_list_name)
            new_value = data[widget.context.getName()]
            old_value = self._mailing_list_subscription_type(mailing_list)
            if IEmailAddress.providedBy(new_value):
                new_value_string = new_value.email
            else:
                new_value_string = new_value
            if new_value_string != old_value:
                dirty = True
                if new_value == "Don't subscribe":
                    # Delete the subscription.
                    mailing_list.unsubscribe(self.context)
                else:
                    if new_value == "Preferred address":
                        # If the user is subscribed but not under any
                        # particular address, her current preferred
                        # address will always be used.
                        new_value = None
                    subscription = mailing_list.getSubscription(self.context)
                    if subscription is None:
                        mailing_list.subscribe(self.context, new_value)
                    else:
                        mailing_list.changeAddress(self.context, new_value)
        if dirty:
            self.request.response.addInfoNotification(
                "Subscriptions updated.")
        self.next_url = self.action_url

    def validate_action_update_autosubscribe_policy(self, action, data):
        """Ensure that the requested auto-subscribe setting is valid."""
        # XXX mars 2008-04-27 bug=223303:
        # This validator appears pointless and untestable, but it is
        # required for LaunchpadFormView to tell apart the three <form>
        # elements on the page.

        widget = self.widgets['mailing_list_auto_subscribe_policy']
        self.validate_widgets(data, widget.name)
        return self.errors

    @action(
        _('Update Policy'),
        name="update_autosubscribe_policy",
        validator=validate_action_update_autosubscribe_policy)
    def action_update_autosubscribe_policy(self, action, data):
        newpolicy = data['mailing_list_auto_subscribe_policy']
        self.context.mailing_list_auto_subscribe_policy = newpolicy
        self.request.response.addInfoNotification(
            'Your auto-subscribe policy has been updated.')
        self.next_url = self.action_url


class PersonLatestQuestionsView(LaunchpadFormView):
    """View used by the porlet displaying the latest questions made by
    a person.
    """

    @cachedproperty
    def getLatestQuestions(self, quantity=5):
        """Return <quantity> latest questions created for this target. """
        return IQuestionsPerson(self.context).searchQuestions(
            participation=QuestionParticipation.OWNER)[:quantity]


class PersonSearchQuestionsView(SearchQuestionsView):
    """View to search and display questions that involve an `IPerson`."""

    display_target_column = True

    @property
    def template(self):
        # Persons always show the default template.
        return self.default_template

    @property
    def pageheading(self):
        """See `SearchQuestionsView`."""
        return _('Questions involving $name',
                 mapping=dict(name=self.context.displayname))

    @property
    def empty_listing_message(self):
        """See `SearchQuestionsView`."""
        return _('No questions  involving $name found with the '
                 'requested statuses.',
                 mapping=dict(name=self.context.displayname))


class SearchAnsweredQuestionsView(PersonSearchQuestionsView):
    """View used to search and display questions answered by an IPerson."""

    def getDefaultFilter(self):
        """See `SearchQuestionsView`."""
        return dict(participation=QuestionParticipation.ANSWERER)

    @property
    def pageheading(self):
        """See `SearchQuestionsView`."""
        return _('Questions answered by $name',
                 mapping=dict(name=self.context.displayname))

    @property
    def empty_listing_message(self):
        """See `SearchQuestionsView`."""
        return _('No questions answered by $name found with the '
                 'requested statuses.',
                 mapping=dict(name=self.context.displayname))


class SearchAssignedQuestionsView(PersonSearchQuestionsView):
    """View used to search and display questions assigned to an IPerson."""

    def getDefaultFilter(self):
        """See `SearchQuestionsView`."""
        return dict(participation=QuestionParticipation.ASSIGNEE)

    @property
    def pageheading(self):
        """See `SearchQuestionsView`."""
        return _('Questions assigned to $name',
                 mapping=dict(name=self.context.displayname))

    @property
    def empty_listing_message(self):
        """See `SearchQuestionsView`."""
        return _('No questions assigned to $name found with the '
                 'requested statuses.',
                 mapping=dict(name=self.context.displayname))


class SearchCommentedQuestionsView(PersonSearchQuestionsView):
    """View used to search and show questions commented on by an IPerson."""

    def getDefaultFilter(self):
        """See `SearchQuestionsView`."""
        return dict(participation=QuestionParticipation.COMMENTER)

    @property
    def pageheading(self):
        """See `SearchQuestionsView`."""
        return _('Questions commented on by $name ',
                 mapping=dict(name=self.context.displayname))

    @property
    def empty_listing_message(self):
        """See `SearchQuestionsView`."""
        return _('No questions commented on by $name found with the '
                 'requested statuses.',
                 mapping=dict(name=self.context.displayname))


class SearchCreatedQuestionsView(PersonSearchQuestionsView):
    """View used to search and display questions created by an IPerson."""

    def getDefaultFilter(self):
        """See `SearchQuestionsView`."""
        return dict(participation=QuestionParticipation.OWNER)

    @property
    def pageheading(self):
        """See `SearchQuestionsView`."""
        return _('Questions asked by $name',
                 mapping=dict(name=self.context.displayname))

    @property
    def empty_listing_message(self):
        """See `SearchQuestionsView`."""
        return _('No questions asked by $name found with the '
                 'requested statuses.',
                 mapping=dict(name=self.context.displayname))


class SearchNeedAttentionQuestionsView(PersonSearchQuestionsView):
    """View used to search and show questions needing an IPerson attention."""

    def getDefaultFilter(self):
        """See `SearchQuestionsView`."""
        return dict(needs_attention=True)

    @property
    def pageheading(self):
        """See `SearchQuestionsView`."""
        return _("Questions needing $name's attention",
                 mapping=dict(name=self.context.displayname))

    @property
    def empty_listing_message(self):
        """See `SearchQuestionsView`."""
        return _("No questions need $name's attention.",
                 mapping=dict(name=self.context.displayname))


class SearchSubscribedQuestionsView(PersonSearchQuestionsView):
    """View used to search and show questions subscribed to by an IPerson."""

    def getDefaultFilter(self):
        """See `SearchQuestionsView`."""
        return dict(participation=QuestionParticipation.SUBSCRIBER)

    @property
    def pageheading(self):
        """See `SearchQuestionsView`."""
        return _('Questions $name is subscribed to',
                 mapping=dict(name=self.context.displayname))

    @property
    def empty_listing_message(self):
        """See `SearchQuestionsView`."""
        return _('No questions subscribed to by $name found with the '
                 'requested statuses.',
                 mapping=dict(name=self.context.displayname))


class PersonAnswerContactForView(LaunchpadView):
    """View used to show all the IQuestionTargets that an IPerson is an answer
    contact for.
    """

    @property
    def label(self):
        return 'Projects for which %s is an answer contact' % (
            self.context.displayname)

    page_title = label

    @cachedproperty
    def direct_question_targets(self):
        """List of targets that the IPerson is a direct answer contact.

        Return a list of IQuestionTargets sorted alphabetically by title.
        """
        return sorted(
            IQuestionsPerson(self.context).getDirectAnswerQuestionTargets(),
            key=attrgetter('title'))

    @cachedproperty
    def team_question_targets(self):
        """List of IQuestionTargets for the context's team membership.

        Sorted alphabetically by title.
        """
        return sorted(
            IQuestionsPerson(self.context).getTeamAnswerQuestionTargets(),
            key=attrgetter('title'))

    def showRemoveYourselfLink(self):
        """The link is shown when the page is in the user's own profile."""
        return self.user == self.context


class PersonAnswersMenu(NavigationMenu):

    usedfor = IPerson
    facet = 'answers'
    links = ['answered', 'assigned', 'created', 'commented', 'need_attention',
             'subscribed', 'answer_contact_for']

    def answer_contact_for(self):
        summary = "Projects for which %s is an answer contact" % (
            self.context.displayname)
        return Link(
            '+answer-contact-for', 'Answer contact for', summary, icon='edit')

    def answered(self):
        summary = 'Questions answered by %s' % self.context.displayname
        return Link(
            '+answeredquestions', 'Answered', summary, icon='question')

    def assigned(self):
        summary = 'Questions assigned to %s' % self.context.displayname
        return Link(
            '+assignedquestions', 'Assigned', summary, icon='question')

    def created(self):
        summary = 'Questions asked by %s' % self.context.displayname
        return Link('+createdquestions', 'Asked', summary, icon='question')

    def commented(self):
        summary = 'Questions commented on by %s' % (
            self.context.displayname)
        return Link(
            '+commentedquestions', 'Commented', summary, icon='question')

    def need_attention(self):
        summary = 'Questions needing %s attention' % (
            self.context.displayname)
        return Link('+needattentionquestions', 'Need attention', summary,
                    icon='question')

    def subscribed(self):
        text = 'Subscribed'
        summary = 'Questions subscribed to by %s' % (
                self.context.displayname)
        return Link('+subscribedquestions', text, summary, icon='question')


class BaseWithStats:
    """An ISourcePackageRelease or a ISourcePackagePublishingHistory,
    with extra stats added.

    """

    failed_builds = None
    needs_building = None

    def __init__(self, object, failed_builds, needs_building):
        self.context = object
        self.failed_builds = failed_builds
        self.needs_building = needs_building


class SourcePackageReleaseWithStats(BaseWithStats):
    """An ISourcePackageRelease, with extra stats added."""

    implements(ISourcePackageRelease)
    delegates(ISourcePackageRelease)


class SourcePackagePublishingHistoryWithStats(BaseWithStats):
    """An ISourcePackagePublishingHistory, with extra stats added."""

    implements(ISourcePackagePublishingHistory)
    delegates(ISourcePackagePublishingHistory)


class PersonRelatedSoftwareView(LaunchpadView):
    """View for +related-packages."""
    implements(IPersonRelatedSoftwareMenu)
    _max_results_key = 'summary_list_size'

    @property
    def max_results_to_display(self):
        return config.launchpad[self._max_results_key]

    @property
    def page_title(self):
        return 'Related packages'

    @cachedproperty
    def related_projects(self):
        """Return a list of project dicts owned or driven by this person.

        The number of projects returned is limited by max_results_to_display.
        A project dict has the following keys: title, url, is_owner,
        is_driver, is_bugsupervisor.
        """
        projects = []
        max_projects = self.max_results_to_display
        pillarnames = self._related_projects[:max_projects]
        for pillarname in pillarnames:
            pillar = pillarname.pillar
            project = {}
            project['title'] = pillar.title
            project['url'] = canonical_url(pillar)
            person = self.context
            project['is_owner'] = person.inTeam(pillar.owner)
            project['is_driver'] = person.inTeam(pillar.driver)
            project['is_bug_supervisor'] = False
            if IHasBugSupervisor.providedBy(pillar):
                project['is_bug_supervisor'] = (
                    person.inTeam(pillar.bug_supervisor))
            projects.append(project)
        return projects

    @cachedproperty
    def first_five_related_projects(self):
        """Return first five projects owned or driven by this person."""
        return self._related_projects[:5]

    @cachedproperty
    def related_projects_count(self):
        """The number of project owned or driven by this person."""
        return self._related_projects.count()

    @cachedproperty
    def has_more_related_projects(self):
        """Does this person have more than five related projects?"""
        return self.related_projects_count > 5

    @cachedproperty
    def projects_header_message(self):
        return self._tableHeaderMessage(
            self.related_projects_count, label='project')

    @cachedproperty
    def _related_projects(self):
        """Return all projects owned or driven by this person."""
        user = getUtility(ILaunchBag).user
        return self.context.getAffiliatedPillars(user)

    def _tableHeaderMessage(self, count, label='package'):
        """Format a header message for the tables on the summary page."""
        if count > 1:
            label += 's'
        if count > self.max_results_to_display:
            header_message = (
                "Displaying first %d %s out of %d total" % (
                    self.max_results_to_display, label, count))
        else:
            header_message = "%d %s" % (count, label)

        return header_message

    def filterPPAPackageList(self, packages):
        """Remove packages that the user is not allowed to see.

        Given a list of PPA packages, some might be in a PPA that the
        user is not allowed to see, so they are filtered out of the list.
        """
        # For each package we find out which archives it was published in.
        # If the user has permission to see any of those archives then
        # the user is permitted to see the package.
        #
        # Ideally this check should be done in
        # IPerson.getLatestUploadedPPAPackages() but formulating the SQL
        # query is virtually impossible!
        results = []
        for package in packages:
            # Make a shallow copy to remove the Zope security.
            archives = set(package.published_archives)
            # Ensure the SPR.upload_archive is also considered.
            archives.add(package.upload_archive)
            for archive in archives:
                if check_permission('launchpad.View', archive):
                    results.append(package)
                    break

        return results

    def _getDecoratedPackagesSummary(self, packages):
        """Helper returning decorated packages for the summary page.

        :param packages: A SelectResults that contains the query
        :return: A tuple of (packages, header_message).

        The packages returned are limited to self.max_results_to_display
        and decorated with the stats required in the page template.
        The header_message is the text to be displayed at the top of the
        results table in the template.
        """
        # This code causes two SQL queries to be generated.
        results = self._addStatsToPackages(
            packages[:self.max_results_to_display])
        header_message = self._tableHeaderMessage(packages.count())
        return results, header_message

    def _getDecoratedPublishingsSummary(self, publishings):
        """Helper returning decorated publishings for the summary page.

        :param publishings: A SelectResults that contains the query
        :return: A tuple of (publishings, header_message).

        The publishings returned are limited to self.max_results_to_display
        and decorated with the stats required in the page template.
        The header_message is the text to be displayed at the top of the
        results table in the template.
        """
        # This code causes two SQL queries to be generated.
        results = self._addStatsToPublishings(
            publishings[:self.max_results_to_display])
        header_message = self._tableHeaderMessage(publishings.count())
        return results, header_message

    @property
    def latest_uploaded_ppa_packages_with_stats(self):
        """Return the sourcepackagereleases uploaded to PPAs by this person.

        Results are filtered according to the permission of the requesting
        user to see private archives.
        """
        packages = self.context.getLatestUploadedPPAPackages()
        results, header_message = self._getDecoratedPackagesSummary(packages)
        self.ppa_packages_header_message = header_message
        return self.filterPPAPackageList(results)

    @property
    def latest_maintained_packages_with_stats(self):
        """Return the latest maintained packages, including stats."""
        packages = self.context.getLatestMaintainedPackages()
        results, header_message = self._getDecoratedPackagesSummary(packages)
        self.maintained_packages_header_message = header_message
        return results

    @property
    def latest_uploaded_but_not_maintained_packages_with_stats(self):
        """Return the latest uploaded packages, including stats.

        Don't include packages that are maintained by the user.
        """
        packages = self.context.getLatestUploadedButNotMaintainedPackages()
        results, header_message = self._getDecoratedPackagesSummary(packages)
        self.uploaded_packages_header_message = header_message
        return results

    @property
    def latest_synchronised_publishings_with_stats(self):
        """Return the latest synchronised publishings, including stats.

        """
        publishings = self.context.getLatestSynchronisedPublishings()
        results, header_message = self._getDecoratedPublishingsSummary(
            publishings)
        self.synchronised_packages_header_message = header_message
        return results

    def _calculateBuildStats(self, package_releases):
        """Calculate failed builds and needs_build state.

        For each of the package_releases, calculate the failed builds
        and the needs_build state, and return a tuple of two dictionaries,
        one containing the failed builds and the other containing
        True or False according to the needs_build state, both keyed by
        the source package release.
        """
        # Calculate all the failed builds with one query.
        build_set = getUtility(IBinaryPackageBuildSet)
        package_release_ids = [
            package_release.id for package_release in package_releases]
        all_builds = build_set.getBuildsBySourcePackageRelease(
            package_release_ids)
        # Make a dictionary of lists of builds keyed by SourcePackageRelease
        # and a dictionary of "needs build" state keyed by the same.
        builds_by_package = {}
        needs_build_by_package = {}
        for package in package_releases:
            builds_by_package[package.id] = []
            needs_build_by_package[package.id] = False
        for build in all_builds:
            if build.status == BuildStatus.FAILEDTOBUILD:
                builds_by_package[
                    build.source_package_release.id].append(build)
            needs_build = build.status in [
                BuildStatus.NEEDSBUILD,
                BuildStatus.MANUALDEPWAIT,
                BuildStatus.CHROOTWAIT,
                ]
            needs_build_by_package[
                build.source_package_release.id] = needs_build

        return (builds_by_package, needs_build_by_package)

    def _addStatsToPackages(self, package_releases):
        """Add stats to the given package releases, and return them."""
        builds_by_package, needs_build_by_package = self._calculateBuildStats(
            package_releases)

        return [
            SourcePackageReleaseWithStats(
                package, builds_by_package[package.id],
                needs_build_by_package[package.id])
            for package in package_releases]

    def _addStatsToPublishings(self, publishings):
        """Add stats to the given publishings, and return them."""
        filtered_spphs = [
            spph for spph in publishings if
            check_permission('launchpad.View', spph)]
        builds_by_package, needs_build_by_package = self._calculateBuildStats(
            [spph.sourcepackagerelease for spph in filtered_spphs])

        return [
            SourcePackagePublishingHistoryWithStats(
                spph, builds_by_package[spph.sourcepackagerelease.id],
                needs_build_by_package[spph.sourcepackagerelease.id])
            for spph in filtered_spphs]

    def setUpBatch(self, packages):
        """Set up the batch navigation for the page being viewed.

        This method creates the BatchNavigator and converts its
        results batch into a list of decorated sourcepackagereleases.
        """
        self.batchnav = BatchNavigator(packages, self.request)
        packages_batch = list(self.batchnav.currentBatch())
        self.batch = self._addStatsToPackages(packages_batch)


class PersonMaintainedPackagesView(PersonRelatedSoftwareView):
    """View for +maintained-packages."""
    _max_results_key = 'default_batch_size'

    def initialize(self):
        """Set up the batch navigation."""
        packages = self.context.getLatestMaintainedPackages()
        self.setUpBatch(packages)

    @property
    def page_title(self):
        return "Maintained Packages"


class PersonUploadedPackagesView(PersonRelatedSoftwareView):
    """View for +uploaded-packages."""
    _max_results_key = 'default_batch_size'

    def initialize(self):
        """Set up the batch navigation."""
        packages = self.context.getLatestUploadedButNotMaintainedPackages()
        self.setUpBatch(packages)

    @property
    def page_title(self):
        return "Uploaded packages"


class PersonPPAPackagesView(PersonRelatedSoftwareView):
    """View for +ppa-packages."""
    _max_results_key = 'default_batch_size'

    def initialize(self):
        """Set up the batch navigation."""
        # We can't use the base class's setUpBatch() here because
        # the batch needs to be filtered.  It would be nice to not have
        # to filter like this, but as the comment in filterPPAPackage() says,
        # it's very hard to write the SQL for the original query.
        packages = self.context.getLatestUploadedPPAPackages()
        self.batchnav = BatchNavigator(packages, self.request)
        packages_batch = list(self.batchnav.currentBatch())
        packages_batch = self.filterPPAPackageList(packages_batch)
        self.batch = self._addStatsToPackages(packages_batch)

    @property
    def page_title(self):
        return "PPA packages"


class PersonSynchronisedPackagesView(PersonRelatedSoftwareView):
    """View for +synchronised-packages."""
    _max_results_key = 'default_batch_size'

    def initialize(self):
        """Set up the batch navigation."""
        publishings = self.context.getLatestSynchronisedPublishings()
        self.setUpBatch(publishings)

    def setUpBatch(self, publishings):
        """Set up the batch navigation for the page being viewed.

        This method creates the BatchNavigator and converts its
        results batch into a list of decorated sourcepackagepublishinghistory.
        """
        self.batchnav = BatchNavigator(publishings, self.request)
        publishings_batch = list(self.batchnav.currentBatch())
        self.batch = self._addStatsToPublishings(publishings_batch)

    @property
    def page_title(self):
        return "Synchronised packages"


class PersonRelatedProjectsView(PersonRelatedSoftwareView):
    """View for +related-projects."""
    _max_results_key = 'default_batch_size'

    def initialize(self):
        """Set up the batch navigation."""
        self.batchnav = BatchNavigator(
            self.related_projects, self.request)
        self.batch = list(self.batchnav.currentBatch())

    @property
    def page_title(self):
        return "Related projects"


class PersonOwnedTeamsView(PersonRelatedSoftwareView):
    """View for +owned-teams."""
    page_title = "Owned teams"

    def initialize(self):
        """Set up the batch navigation."""
        self.batchnav = BatchNavigator(
            self.context.getOwnedTeams(self.user), self.request)
        self.batchnav.setHeadings('team', 'teams')
        self.batch = list(self.batchnav.currentBatch())


class PersonOAuthTokensView(LaunchpadView):
    """Where users can see/revoke their non-expired access tokens."""

    label = 'Authorized applications'

    def initialize(self):
        if self.request.method == 'POST':
            self.expireToken()

    @property
    def access_tokens(self):
        return sorted(
            self.context.oauth_access_tokens,
            key=lambda token: token.consumer.key)

    @property
    def request_tokens(self):
        return sorted(
            self.context.oauth_request_tokens,
            key=lambda token: token.consumer.key)

    def expireToken(self):
        """Expire the token with the key contained in the request's form."""
        form = self.request.form
        consumer = getUtility(IOAuthConsumerSet).getByKey(
            form.get('consumer_key'))
        token_key = form.get('token_key')
        token_type = form.get('token_type')
        if token_type == 'access_token':
            token = consumer.getAccessToken(token_key)
        elif token_type == 'request_token':
            token = consumer.getRequestToken(token_key)
        else:
            raise UnexpectedFormData("Invalid form value for token_type: %r"
                                     % token_type)
        if token is not None:
            token.date_expires = datetime.now(pytz.timezone('UTC'))
            self.request.response.addInfoNotification(
                "Authorization revoked successfully.")
            self.request.response.redirect(canonical_url(self.user))
        else:
            self.request.response.addInfoNotification(
                "Couldn't find authorization given to %s. Maybe it has been "
                "revoked already?" % consumer.key)
        self.request.response.redirect(
            canonical_url(self.context, view_name='+oauth-tokens'))


class PersonTimeZoneForm(Interface):

    time_zone = Choice(
        vocabulary='TimezoneName', title=_('Time zone'), required=True,
        description=_(
            'Once the time zone is correctly set, events '
            'in Launchpad will be displayed in local time.'))


class PersonEditTimeZoneView(LaunchpadFormView):
    """Edit a person's time zone."""

    schema = PersonTimeZoneForm
    page_title = label = 'Set timezone'

    @property
    def initial_values(self):
        if self.context.time_zone is None:
            return {}
        else:
            return dict(time_zone=self.context.time_zone)

    @property
    def next_url(self):
        return canonical_url(self.context)

    cancel_url = next_url

    @action(_("Update"), name="update")
    def action_update(self, action, data):
        """Set the time zone for the person."""
        timezone = data.get('time_zone')
        if timezone is None:
            raise UnexpectedFormData('No location received.')
        # XXX salgado, 2012-02-16, bug=933699: Use setLocation() because it's
        # the cheaper way to set the timezone of a person. Once the bug is
        # fixed we'll be able to get rid of this hack.
        self.context.setLocation(None, None, timezone, self.user)


def archive_to_person(archive):
    """Adapts an `IArchive` to an `IPerson`."""
    return IPerson(archive.owner)


class IEmailToPerson(Interface):
    """Schema for contacting a user via email through Launchpad."""

    from_ = TextLine(
        title=_('From'), required=True, readonly=False)

    subject = TextLine(
        title=_('Subject'), required=True, readonly=False)

    message = Text(
        title=_('Message'), required=True, readonly=False)

    @invariant
    def subject_and_message_are_not_empty(data):
        """Raise an Invalid error if the message or subject is empty."""
        if '' in (data.message.strip(), data.subject.strip()):
            raise Invalid('You must provide a subject and a message.')


class ContactViaWebNotificationRecipientSet:
    """A set of notification recipients and rationales from ContactViaWeb."""
    implements(INotificationRecipientSet)

    # Primary reason enumerations.
    TO_USER = object()
    TO_MEMBERS = object()
    TO_ADMINS = object()

    def __init__(self, user, person_or_team):
        """Initialize the state based on the context and the user.

        The recipients are determined by the relationship between the user
        and the context that he is contacting: another user, himself, his
        team, another team.

        :param user: The person doing the contacting.
        :type user: an `IPerson`.
        :param person_or_team: The party that is the context of the email.
        :type person_or_team: `IPerson`.
        """
        self.user = user
        self.description = None
        self.primary_reason = None
        self._primary_recipient = None
        self._reason = None
        self._header = None
        self._count_recipients = None
        self.add(person_or_team, None, None)

    def _reset_state(self):
        """Reset the cache because the recipients changed."""
        self._count_recipients = None
        del get_property_cache(self)._all_recipients

    def _getPrimaryReason(self, person_or_team):
        """Return the primary reason enumeration.

        :param person_or_team: The party that is the context of the email.
        :type person_or_team: `IPerson`.
        """
        if person_or_team.is_team:
            if person_or_team in self.user.getAdministratedTeams():
                # Team admins can broadcast messages to all members.
                return self.TO_MEMBERS
            else:
                # A non-team-admins can make inquiries to the people who
                # lead the team.
                return self.TO_ADMINS
        else:
            # Send to the user
            return self.TO_USER

    def _getReasonAndHeader(self, person_or_team):
        """Return the reason and header why the email was received.

        :param person_or_team: The party that is the context of the email.
        :type person_or_team: `IPerson`.
        """
        if self.primary_reason is self.TO_USER:
            reason = (
                'using the "Contact this user" link on your profile page\n'
                '(%s)' % canonical_url(person_or_team))
            header = 'ContactViaWeb user'
        elif self.primary_reason is self.TO_ADMINS:
            reason = (
                'using the "Contact this team\'s admins" link on the '
                '%s team page\n(%s)' % (
                    person_or_team.displayname,
                    canonical_url(person_or_team)))
            header = 'ContactViaWeb owner (%s team)' % person_or_team.name
        else:
            # self.primary_reason is self.TO_MEMBERS.
            reason = (
                'to each member of the %s team using the '
                '"Contact this team" link on the %s team page\n(%s)' % (
                    person_or_team.displayname,
                    person_or_team.displayname,
                    canonical_url(person_or_team)))
            header = 'ContactViaWeb member (%s team)' % person_or_team.name
        return (reason, header)

    def _getDescription(self, person_or_team):
        """Return the description of the recipients being contacted.

        :param person_or_team: The party that is the context of the email.
        :type person_or_team: `IPerson`.
        """
        if self.primary_reason is self.TO_USER:
            return (
                'You are contacting %s (%s).' %
                (person_or_team.displayname, person_or_team.name))
        elif self.primary_reason is self.TO_ADMINS:
            return (
                'You are contacting the %s (%s) team admins.' %
                (person_or_team.displayname, person_or_team.name))
        else:
            # This is a team without a contact address (self.TO_MEMBERS).
            recipients_count = len(self)
            if recipients_count == 1:
                plural_suffix = ''
            else:
                plural_suffix = 's'
            text = '%d member%s' % (recipients_count, plural_suffix)
            return (
                'You are contacting %s of the %s (%s) team directly.'
                % (text, person_or_team.displayname, person_or_team.name))

    @cachedproperty
    def _all_recipients(self):
        """Set the cache of all recipients."""
        all_recipients = {}
        if self.primary_reason is self.TO_MEMBERS:
            team = self._primary_recipient
            for recipient in team.getMembersWithPreferredEmails():
                email = removeSecurityProxy(recipient).preferredemail.email
                all_recipients[email] = recipient
        elif self.primary_reason is self.TO_ADMINS:
            team = self._primary_recipient
            for admin in team.adminmembers:
                # This method is similar to getTeamAdminsEmailAddresses, but
                # this case needs to know the user. Since both methods
                # ultimately iterate over get_recipients, this case is not
                # in a different performance class.
                for recipient in get_recipients(admin):
                    email = removeSecurityProxy(recipient).preferredemail.email
                    all_recipients[email] = recipient
        elif self._primary_recipient.is_valid_person_or_team:
            email = removeSecurityProxy(
                self._primary_recipient).preferredemail.email
            all_recipients[email] = self._primary_recipient
        else:
            # The user or team owner is not active.
            pass
        return all_recipients

    def getEmails(self):
        """See `INotificationRecipientSet`."""
        for email in sorted(self._all_recipients.keys()):
            yield email

    def getRecipients(self):
        """See `INotificationRecipientSet`."""
        for recipient in sorted(
            self._all_recipients.values(), key=attrgetter('displayname')):
            yield recipient

    def getRecipientPersons(self):
        """See `INotificationRecipientSet`."""
        for email, person in self._all_recipients.items():
            yield (email, person)

    def __iter__(self):
        """See `INotificationRecipientSet`."""
        return iter(self.getRecipients())

    def __contains__(self, person_or_email):
        """See `INotificationRecipientSet`."""
        if IPerson.implementedBy(person_or_email):
            return person_or_email in self._all_recipients.values()
        else:
            return person_or_email in self._all_recipients.keys()

    def __len__(self):
        """The number of recipients in the set."""
        if self._count_recipients is None:
            recipient = self._primary_recipient
            if self.primary_reason is self.TO_MEMBERS:
                # Get the count without loading all the members.
                self._count_recipients = (
                    recipient.getMembersWithPreferredEmailsCount())
            elif self.primary_reason is self.TO_ADMINS:
                self._count_recipients = len(self._all_recipients)
            elif recipient.is_valid_person_or_team:
                self._count_recipients = 1
            else:
                # The user is deactivated.
                self._count_recipients = 0
        return self._count_recipients

    def __nonzero__(self):
        """See `INotificationRecipientSet`."""
        return len(self) > 0

    def getReason(self, person_or_email):
        """See `INotificationRecipientSet`."""
        if person_or_email not in self:
            raise UnknownRecipientError(
                '%s in not in the recipients' % person_or_email)
        # All users have the same reason based on the primary recipient.
        return (self._reason, self._header)

    def add(self, person, reason, header):
        """See `INotificationRecipientSet`.

        This method sets the primary recipient of the email. If the primary
        recipient is a team without a contact address, all the members will
        be recipients. Calling this method more than once resets the
        recipients.
        """
        self._reset_state()
        self.primary_reason = self._getPrimaryReason(person)
        self._primary_recipient = person
        if reason is None:
            reason, header = self._getReasonAndHeader(person)
        self._reason = reason
        self._header = header
        self.description = self._getDescription(person)

    def update(self, recipient_set):
        """See `INotificationRecipientSet`.

        This method is is not relevant to this implementation because the
        set is generated based on the primary recipient. use the add() to
        set the primary recipient.
        """
        pass


class EmailToPersonView(LaunchpadFormView):
    """The 'Contact this user' page."""

    schema = IEmailToPerson
    field_names = ['subject', 'message']
    custom_widget('subject', TextWidget, displayWidth=60)

    def initialize(self):
        """See `ILaunchpadFormView`."""
        # Send the user to the profile page if contact is not possible.
        if self.user is None or not self.context.is_valid_person_or_team:
            return self.request.response.redirect(canonical_url(self.context))
        LaunchpadFormView.initialize(self)

    def setUpFields(self):
        """Set up fields for this view.

        The field needing special set up is the 'From' fields, which contains
        a vocabulary of the user's preferred (first) and validated
        (subsequent) email addresses.
        """
        super(EmailToPersonView, self).setUpFields()
        usable_addresses = [self.user.preferredemail]
        usable_addresses.extend(self.user.validatedemails)
        terms = [SimpleTerm(email, email.email) for email in usable_addresses]
        field = Choice(__name__='field.from_',
                       title=_('From'),
                       source=SimpleVocabulary(terms),
                       default=terms[0].value)
        # Get the order right; the From field should be first, followed by the
        # Subject and then Message fields.
        self.form_fields = FormFields(*chain((field, ), self.form_fields))

    label = 'Contact user'

    @cachedproperty
    def recipients(self):
        """The recipients of the email message.

        :return: the recipients of the message.
        :rtype: `ContactViaWebNotificationRecipientSet`.
        """
        return ContactViaWebNotificationRecipientSet(self.user, self.context)

    @action(_('Send'), name='send')
    def action_send(self, action, data):
        """Send an email to the user."""
        sender_email = data['field.from_'].email
        subject = data['subject']
        message = data['message']

        if not self.recipients:
            self.request.response.addErrorNotification(
                _('Your message was not sent because the recipient '
                  'does not have a preferred email address.'))
            self.next_url = canonical_url(self.context)
            return
        try:
            send_direct_contact_email(
                sender_email, self.recipients, subject, message)
        except QuotaReachedError as error:
            fmt_date = DateTimeFormatterAPI(self.next_try)
            self.request.response.addErrorNotification(
                _('Your message was not sent because you have exceeded your '
                  'daily quota of $quota messages to contact users. '
                  'Try again $when.', mapping=dict(
                      quota=error.authorization.message_quota,
                      when=fmt_date.approximatedate(),
                      )))
        else:
            self.request.response.addInfoNotification(
                _('Message sent to $name',
                  mapping=dict(name=self.context.displayname)))
        self.next_url = canonical_url(self.context)

    @property
    def cancel_url(self):
        """The return URL."""
        return canonical_url(self.context)

    @property
    def contact_is_allowed(self):
        """Whether the sender is allowed to send this email or not."""
        return IDirectEmailAuthorization(self.user).is_allowed

    @property
    def has_valid_email_address(self):
        """Whether there is a contact address."""
        return len(self.recipients) > 0

    @property
    def contact_is_possible(self):
        """Whether there is a contact address and the user can send email."""
        return self.contact_is_allowed and self.has_valid_email_address

    @property
    def next_try(self):
        """When can the user try again?"""
        throttle_date = IDirectEmailAuthorization(self.user).throttle_date
        interval = as_timedelta(
            config.launchpad.user_to_user_throttle_interval)
        return throttle_date + interval

    @property
    def contact_not_possible_reason(self):
        """The reason the person cannot be contacted."""
        if self.has_valid_email_address:
            return None
        elif self.recipients.primary_reason is self.recipients.TO_USER:
            return "The user is not active."
        elif self.recipients.primary_reason is self.recipients.TO_ADMINS:
            return "The team has no admins. Contact the team owner instead."
        else:
            return "The team has no members."

    @property
    def page_title(self):
        """Return the appropriate pagetitle."""
        if self.context.is_team:
            if self.user.inTeam(self.context):
                return 'Contact your team'
            else:
                return 'Contact this team'
        elif self.context == self.user:
            return 'Contact yourself'
        else:
            return 'Contact this user'


class IPersonIndexMenu(Interface):
    """A marker interface for the +index navigation menu."""


class PersonIndexMenu(NavigationMenu, PersonMenuMixin):
    usedfor = IPersonIndexMenu
    facet = 'overview'
    title = 'Change person'
    links = ('edit', 'administer', 'administer_account', 'branding')


classImplements(PersonIndexView, IPersonIndexMenu)


class PersonXHTMLRepresentation:
    adapts(IPerson, IWebServiceClientRequest)
    implements(Interface)

    def __init__(self, person, request):
        self.person = person
        self.request = request

    def __call__(self):
        """Render `Person` as XHTML using the webservice."""
        return PersonFormatterAPI(self.person).link(None)
