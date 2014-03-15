# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'BasePollView',
    'PollAddView',
    'PollEditNavigationMenu',
    'PollEditView',
    'PollNavigation',
    'PollOptionAddView',
    'PollOptionEditView',
    'PollOverviewMenu',
    'PollView',
    'PollVoteView',
    'PollBreadcrumb',
    'TeamPollsView',
    ]

from z3c.ptcompat import ViewPageTemplateFile
from zope.component import getUtility
from zope.event import notify
from zope.formlib.widgets import TextWidget
from zope.interface import (
    implements,
    Interface,
    )
from zope.lifecycleevent import ObjectCreatedEvent

from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadEditFormView,
    LaunchpadFormView,
    )
from lp.registry.browser.person import PersonView
from lp.registry.interfaces.poll import (
    IPoll,
    IPollOption,
    IPollOptionSet,
    IPollSubset,
    IVoteSet,
    PollAlgorithm,
    PollSecrecy,
    )
from lp.services.helpers import shortlist
from lp.services.webapp import (
    ApplicationMenu,
    canonical_url,
    enabled_with_permission,
    LaunchpadView,
    Link,
    Navigation,
    NavigationMenu,
    stepthrough,
    )
from lp.services.webapp.breadcrumb import TitleBreadcrumb


class PollEditLinksMixin:

    @enabled_with_permission('launchpad.Edit')
    def addnew(self):
        text = 'Add new option'
        return Link('+newoption', text, icon='add')

    @enabled_with_permission('launchpad.Edit')
    def edit(self):
        text = 'Change details'
        return Link('+edit', text, icon='edit')


class PollOverviewMenu(ApplicationMenu, PollEditLinksMixin):
    usedfor = IPoll
    facet = 'overview'
    links = ['addnew']


class IPollEditMenu(Interface):
    """A marker interface for the edit navigation menu."""


class PollEditNavigationMenu(NavigationMenu, PollEditLinksMixin):
    usedfor = IPollEditMenu
    facet = 'overview'
    links = ['addnew', 'edit']


class IPollActionMenu(Interface):
    """A marker interface for the action menu."""


class PollActionNavigationMenu(PollEditNavigationMenu):
    usedfor = IPollActionMenu
    links = ['edit']


class PollNavigation(Navigation):

    usedfor = IPoll

    @stepthrough('+option')
    def traverse_option(self, name):
        return getUtility(IPollOptionSet).getByPollAndId(
            self.context, int(name))


class BasePollView(LaunchpadView):
    """A base view class to be used in other poll views."""

    token = None
    gotTokenAndVotes = False
    feedback = ""

    def setUpTokenAndVotes(self):
        """Set up the token and votes to be displayed."""
        if not self.userVoted():
            return

        # For secret polls we can only display the votes after the token
        # is submitted.
        if self.request.method == 'POST' and self.isSecret():
            self.setUpTokenAndVotesForSecretPolls()
        elif not self.isSecret():
            self.setUpTokenAndVotesForNonSecretPolls()

    def setUpTokenAndVotesForNonSecretPolls(self):
        """Get the votes of the logged in user in this poll.

        Set the votes in instance variables and also set self.gotTokenAndVotes
        to True, so the templates know they can display the vote.

        This method should be used only on non-secret polls and if the logged
        in user has voted on this poll.
        """
        assert not self.isSecret() and self.userVoted()
        votes = self.context.getVotesByPerson(self.user)
        assert votes, (
            "User %r hasn't voted on poll %r" % (self.user, self.context))
        if self.isSimple():
            # Here we have only one vote.
            self.currentVote = votes[0]
            self.token = self.currentVote.token
        elif self.isCondorcet():
            # Here we have multiple votes, and the token is the same in
            # all of them.
            self.currentVotes = sorted(votes, key=lambda v: v.preference)
            self.token = self.currentVotes[0].token
        self.gotTokenAndVotes = True

    def setUpTokenAndVotesForSecretPolls(self):
        """Get the votes with the token provided in the form.

        Set the votes, together with the token in instance variables. Also
        set self.gotTokenAndVotes to True, so the templates know they can
        display the vote.

        Return True if there's any vote with the given token and the votes
        are on this poll.

        This method should be used only on secret polls and if the logged
        in user has voted on this poll.
        """
        assert self.isSecret() and self.userVoted()
        token = self.request.form.get('token')
        # Only overwrite self.token if the request contains a 'token'
        # variable.
        if token is not None:
            self.token = token
        votes = getUtility(IVoteSet).getByToken(self.token)
        if not votes:
            self.feedback = ("There's no vote associated with the token %s"
                             % self.token)
            return False

        # All votes with a given token must be on the same poll. That means
        # checking the poll of the first vote is enough.
        if votes[0].poll != self.context:
            self.feedback = ("The vote associated with the token %s is not "
                             "a vote on this poll." % self.token)
            return False

        if self.isSimple():
            # A simple poll has only one vote, because you can choose only one
            # option.
            self.currentVote = votes[0]
        elif self.isCondorcet():
            self.currentVotes = sorted(votes, key=lambda v: v.preference)
        self.gotTokenAndVotes = True
        return True

    def userCanVote(self):
        """Return True if the user is/was eligible to vote on this poll."""
        return (self.user and self.user.inTeam(self.context.team))

    def userVoted(self):
        """Return True if the user voted on this poll."""
        return (self.user and self.context.personVoted(self.user))

    def isCondorcet(self):
        """Return True if this poll's type is Condorcet."""
        return self.context.type == PollAlgorithm.CONDORCET

    def isSimple(self):
        """Return True if this poll's type is Simple."""
        return self.context.type == PollAlgorithm.SIMPLE

    def isSecret(self):
        """Return True if this is a secret poll."""
        return self.context.secrecy == PollSecrecy.SECRET


class PollBreadcrumb(TitleBreadcrumb):
    """Breadcrumb for polls."""


class PollView(BasePollView):
    """A view class to display the results of a poll."""
    implements(IPollActionMenu)

    def initialize(self):
        super(PollView, self).initialize()
        request = self.request
        if (self.userCanVote() and self.context.isOpen() and
            self.context.getActiveOptions()):
            vote_url = canonical_url(self.context, view_name='+vote')
            request.response.redirect(vote_url)

    def getVotesByOption(self, option):
        """Return the number of votes the given option received."""
        return getUtility(IVoteSet).getVotesByOption(option)

    def getPairwiseMatrixWithHeaders(self):
        """Return the pairwise matrix, with headers being the option's
        names.
        """
        # XXX: kiko 2006-03-13:
        # The list() call here is necessary because, lo and behold,
        # it gives us a non-security-proxied list object! Someone come
        # in and fix this!
        pairwise_matrix = list(self.context.getPairwiseMatrix())
        headers = [None]
        for idx, option in enumerate(self.context.getAllOptions()):
            headers.append(option.title)
            # Get a mutable row.
            row = list(pairwise_matrix[idx])
            row.insert(0, option.title)
            pairwise_matrix[idx] = row
        pairwise_matrix.insert(0, headers)
        return pairwise_matrix


class PollVoteView(BasePollView):
    """A view class to where the user can vote on a poll.

    If the user already voted, the current vote is displayed and the user can
    change it. Otherwise he can register his vote.
    """

    default_template = ViewPageTemplateFile(
        '../templates/poll-vote-simple.pt')
    condorcet_template = ViewPageTemplateFile(
        '../templates/poll-vote-condorcet.pt')

    page_title = 'Vote'

    @property
    def template(self):
        if self.isCondorcet():
            return self.condorcet_template
        else:
            return self.default_template

    def initialize(self):
        """Process the form, if it was submitted."""
        super(PollVoteView, self).initialize()
        if not self.isSecret() and self.userVoted():
            # For non-secret polls, the user's vote is always displayed
            self.setUpTokenAndVotesForNonSecretPolls()

        if self.request.method != 'POST':
            return

        if self.isSecret() and self.userVoted():
            if not self.setUpTokenAndVotesForSecretPolls():
                # Not possible to get the votes. Probably the token was wrong.
                return

        if 'showvote' in self.request.form:
            # The user only wants to see the vote.
            return

        if not self.context.isOpen():
            self.feedback = "This poll is not open."
            return

        if self.isSimple():
            self.processSimpleVotingForm()
        else:
            self.processCondorcetVotingForm()

        # User may have voted, so we need to setup the vote to display again.
        self.setUpTokenAndVotes()

    def processSimpleVotingForm(self):
        """Process the simple-voting form to change a user's vote or register
        a new one.

        This method must not be called if the poll is not open.
        """
        assert self.context.isOpen()
        context = self.context
        newoption_id = self.request.form.get('newoption')
        if newoption_id == 'donotchange':
            self.feedback = "Your vote was not changed."
            return
        elif newoption_id == 'donotvote':
            self.feedback = "You chose not to vote yet."
            return
        elif newoption_id == 'none':
            newoption = None
        else:
            newoption = getUtility(IPollOptionSet).getByPollAndId(
                context, int(newoption_id))

        if self.userVoted():
            self.currentVote.option = newoption
            self.feedback = "Your vote was changed successfully."
        else:
            self.currentVote = context.storeSimpleVote(self.user, newoption)
            self.token = self.currentVote.token
            self.currentVote = self.currentVote
            if self.isSecret():
                self.feedback = (
                    "Your vote has been recorded. If you want to view or "
                    "change it later you must write down this key: %s"
                    % self.token)
            else:
                self.feedback = (
                    "Your vote was stored successfully. You can come back to "
                    "this page at any time before this poll closes to view "
                    "or change your vote, if you want.")

    def processCondorcetVotingForm(self):
        """Process the condorcet-voting form to change a user's vote or
        register a new one.

        This method must not be called if the poll is not open.
        """
        assert self.context.isOpen()
        form = self.request.form
        activeoptions = shortlist(self.context.getActiveOptions())
        newvotes = {}
        for option in activeoptions:
            try:
                preference = int(form.get('option_%d' % option.id))
            except ValueError:
                # XXX: Guilherme Salgado 2005-09-14:
                # User tried to specify a value which we can't convert to
                # an integer. Better thing to do would be to notify the user
                # and ask him to fix it.
                preference = None
            newvotes[option] = preference

        if self.userVoted():
            # This is a vote change.
            # For now it's not possible to have votes in an inactive option,
            # but it'll be in the future as we'll allow people to make options
            # inactive after a poll opens.
            assert len(activeoptions) == len(self.currentVotes)
            for vote in self.currentVotes:
                vote.preference = newvotes.get(vote.option)
            self.currentVotes.sort(key=lambda v: v.preference)
            self.feedback = "Your vote was changed successfully."
        else:
            # This is a new vote.
            votes = self.context.storeCondorcetVote(self.user, newvotes)
            self.token = votes[0].token
            self.currentVotes = sorted(votes, key=lambda v: v.preference)
            if self.isSecret():
                self.feedback = (
                    "Your vote has been recorded. If you want to view or "
                    "change it later you must write down this key: %s"
                    % self.token)
            else:
                self.feedback = (
                    "Your vote was stored successfully. You can come back to "
                    "this page at any time before this poll closes to view "
                    "or change your vote, if you want.")


class PollAddView(LaunchpadFormView):
    """The view class to create a new poll in a given team."""

    schema = IPoll
    field_names = ["name", "title", "proposition", "allowspoilt", "dateopens",
                   "datecloses"]

    page_title = 'New poll'

    @property
    def cancel_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(self.context)

    @action("Continue", name="continue")
    def continue_action(self, action, data):
        # XXX: salgado, 2008-10-08: Only secret polls can be created until we
        # fix https://launchpad.net/bugs/80596.
        secrecy = PollSecrecy.SECRET
        poll = IPollSubset(self.context).new(
            data['name'], data['title'], data['proposition'],
            data['dateopens'], data['datecloses'], secrecy,
            data['allowspoilt'])
        self.next_url = canonical_url(poll)
        notify(ObjectCreatedEvent(poll))


class PollEditView(LaunchpadEditFormView):

    implements(IPollEditMenu)
    schema = IPoll
    label = "Edit poll details"
    page_title = 'Edit'
    field_names = ["name", "title", "proposition", "allowspoilt", "dateopens",
                   "datecloses"]

    @property
    def cancel_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(self.context)

    @action("Save", name="save")
    def save_action(self, action, data):
        self.updateContextFromData(data)
        self.next_url = canonical_url(self.context)


class PollOptionEditView(LaunchpadEditFormView):
    """Edit one of a poll's options."""

    schema = IPollOption
    label = "Edit option details"
    page_title = 'Edit option'
    field_names = ["name", "title"]
    custom_widget("title", TextWidget, displayWidth=30)

    @property
    def cancel_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(self.context.poll)

    @action("Save", name="save")
    def save_action(self, action, data):
        self.updateContextFromData(data)
        self.next_url = canonical_url(self.context.poll)


class PollOptionAddView(LaunchpadFormView):
    """Create a new option in a given poll."""

    schema = IPollOption
    label = "Create new poll option"
    page_title = "New option"
    field_names = ["name", "title"]
    custom_widget("title", TextWidget, displayWidth=30)

    @property
    def cancel_url(self):
        """See `LaunchpadFormView`."""
        return canonical_url(self.context)

    @action("Create", name="create")
    def create_action(self, action, data):
        polloption = self.context.newOption(data['name'], data['title'])
        self.next_url = canonical_url(self.context)
        notify(ObjectCreatedEvent(polloption))


class TeamPollsView(PersonView):

    page_title = 'Polls'
