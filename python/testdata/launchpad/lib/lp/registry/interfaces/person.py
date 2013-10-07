# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Person interfaces."""

__metaclass__ = type

__all__ = [
    'IAdminPeopleMergeSchema',
    'IAdminTeamMergeSchema',
    'ICanonicalSSOAPI',
    'ICanonicalSSOApplication',
    'IHasStanding',
    'IObjectReassignment',
    'IPerson',
    'IPersonClaim',
    'IPersonEditRestricted',
    'IPersonPublic',
    'IPersonSet',
    'IPersonSettings',
    'IPersonLimitedView',
    'IPersonViewRestricted',
    'IRequestPeopleMerge',
    'ISoftwareCenterAgentAPI',
    'ISoftwareCenterAgentApplication',
    'ITeam',
    'ITeamContactAddressForm',
    'ITeamReassignment',
    'ImmutableVisibilityError',
    'NoSuchPerson',
    'PersonCreationRationale',
    'PersonalStanding',
    'PRIVATE_TEAM_PREFIX',
    'TeamContactMethod',
    'TeamEmailAddressError',
    'validate_person',
    'validate_person_or_closed_team',
    'validate_public_person',
    'validate_membership_policy',
    ]

import httplib

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    EnumeratedType,
    Item,
    )
from lazr.lifecycle.snapshot import doNotSnapshot
from lazr.restful.declarations import (
    call_with,
    collection_default_content,
    error_status,
    export_as_webservice_collection,
    export_as_webservice_entry,
    export_factory_operation,
    export_read_operation,
    export_write_operation,
    exported,
    LAZR_WEBSERVICE_EXPORTED,
    mutator_for,
    operation_for_version,
    operation_parameters,
    operation_returns_collection_of,
    operation_returns_entry,
    rename_parameters_as,
    REQUEST_USER,
    )
from lazr.restful.fields import (
    CollectionField,
    Reference,
    )
from lazr.restful.interface import copy_field
from zope.component import getUtility
from zope.formlib.form import NoInputData
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.interface.exceptions import Invalid
from zope.interface.interface import invariant
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    Int,
    List,
    Object,
    Text,
    TextLine,
    )

from lp import _
from lp.answers.interfaces.questionsperson import IQuestionsPerson
from lp.app.errors import NameLookupFailed
from lp.app.interfaces.headings import IRootContext
from lp.app.interfaces.launchpad import (
    IHasIcon,
    IHasLogo,
    IHasMugshot,
    IPrivacy,
    )
from lp.app.validators import LaunchpadValidationError
from lp.app.validators.email import email_validator
from lp.app.validators.name import name_validator
from lp.blueprints.interfaces.specificationtarget import IHasSpecifications
from lp.bugs.interfaces.bugtarget import IHasBugs
from lp.code.interfaces.hasbranches import (
    IHasBranches,
    IHasMergeProposals,
    IHasRequestedReviews,
    )
from lp.code.interfaces.hasrecipes import IHasRecipes
from lp.registry.enums import (
    EXCLUSIVE_TEAM_POLICY,
    INCLUSIVE_TEAM_POLICY,
    PersonVisibility,
    TeamMembershipPolicy,
    TeamMembershipRenewalPolicy,
    )
from lp.registry.errors import (
    InclusiveTeamLinkageError,
    PrivatePersonLinkageError,
    TeamMembershipPolicyError,
    )
from lp.registry.interfaces.gpg import IGPGKey
from lp.registry.interfaces.irc import IIrcID
from lp.registry.interfaces.jabber import IJabberID
from lp.registry.interfaces.location import (
    IHasLocation,
    IObjectWithLocation,
    ISetLocation,
    )
from lp.registry.interfaces.mailinglistsubscription import (
    MailingListAutoSubscribePolicy,
    )
from lp.registry.interfaces.ssh import ISSHKey
from lp.registry.interfaces.teammembership import (
    ITeamMembership,
    ITeamParticipation,
    TeamMembershipStatus,
    )
from lp.registry.interfaces.wikiname import IWikiName
from lp.services.database.sqlbase import block_implicit_flushes
from lp.services.fields import (
    BlacklistableContentNameField,
    IconImageUpload,
    is_public_person,
    is_public_person_or_closed_team,
    LogoImageUpload,
    MugshotImageUpload,
    PersonChoice,
    PublicPersonChoice,
    StrippedTextLine,
    )
from lp.services.identity.interfaces.account import (
    AccountStatus,
    IAccount,
    )
from lp.services.identity.interfaces.emailaddress import IEmailAddress
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.interfaces import ILaunchpadApplication
from lp.services.worlddata.interfaces.language import ILanguage
from lp.translations.interfaces.hastranslationimports import (
    IHasTranslationImports,
    )


PRIVATE_TEAM_PREFIX = 'private-'


@block_implicit_flushes
def validate_person_common(obj, attr, value, validate_func,
                           error_class=PrivatePersonLinkageError):
    """Validate the person using the supplied function."""
    if value is None:
        return None
    assert isinstance(value, (int, long)), (
        "Expected int for Person foreign key reference, got %r" % type(value))

    # Importing here to avoid a cyclic import.
    from lp.registry.model.person import Person
    person = Person.get(value)
    if not validate_func(person):
        raise error_class(
            "Cannot link person (name=%s, visibility=%s) to %s (name=%s)"
            % (person.name, person.visibility.name,
               obj, getattr(obj, 'name', None)))
    return value


def validate_person(obj, attr, value):
    """Validate the person is a real person with no other restrictions."""

    def validate(person):
        return IPerson.providedBy(person)

    return validate_person_common(obj, attr, value, validate)


def validate_public_person(obj, attr, value):
    """Validate that the person identified by value is public."""

    def validate(person):
        return is_public_person(person)

    return validate_person_common(obj, attr, value, validate)


def validate_person_or_closed_team(obj, attr, value):

    def validate(person):
        return is_public_person_or_closed_team(person)

    return validate_person_common(
        obj, attr, value, validate, error_class=InclusiveTeamLinkageError)


def validate_membership_policy(obj, attr, value):
    """Validate the team membership_policy."""
    if value is None:
        return None

    # If we are just creating a new team, it can have any membership policy.
    if getattr(obj, '_SO_creating', True):
        return value

    team = obj
    existing_membership_policy = getattr(team, 'membership_policy', None)
    if value == existing_membership_policy:
        return value
    if value in INCLUSIVE_TEAM_POLICY:
        team.checkInclusiveMembershipPolicyAllowed(policy=value)
    if value in EXCLUSIVE_TEAM_POLICY:
        team.checkExclusiveMembershipPolicyAllowed(policy=value)
    return value


class PersonalStanding(DBEnumeratedType):
    """A person's standing.

    Standing is currently (just) used to determine whether a person's posts to
    a mailing list require first-post moderation or not.  Any person with good
    or excellent standing may post directly to the mailing list without
    moderation.  Any person with unknown or poor standing must have their
    first-posts moderated.
    """

    UNKNOWN = DBItem(0, """
        Unknown standing

        Nothing about this person's standing is known.
        """)

    POOR = DBItem(100, """
        Poor standing

        This person has poor standing.
        """)

    GOOD = DBItem(200, """
        Good standing

        This person has good standing and may post to a mailing list without
        being subject to first-post moderation rules.
        """)

    EXCELLENT = DBItem(300, """
        Excellent standing

        This person has excellent standing and may post to a mailing list
        without being subject to first-post moderation rules.
        """)


class PersonCreationRationale(DBEnumeratedType):
    """The rationale for the creation of a given person.

    Launchpad automatically creates user accounts under certain
    circumstances. The owners of these accounts may discover Launchpad
    at a later date and wonder why Launchpad knows about them, so we
    need to make it clear why a certain account was automatically created.
    """

    UNKNOWN = DBItem(1, """
        Unknown

        The reason for the creation of this person is unknown.
        """)

    BUGIMPORT = DBItem(2, """
        Existing user in another bugtracker from which we imported bugs.

        A bugzilla import or sf.net import, for instance. The bugtracker from
        which we were importing should be described in
        Person.creation_comment.
        """)

    SOURCEPACKAGEIMPORT = DBItem(3, """
        This person was mentioned in a source package we imported.

        When gina imports source packages, it has to create Person entries for
        the email addresses that are listed as maintainer and/or uploader of
        the package, in case they don't exist in Launchpad.
        """)

    POFILEIMPORT = DBItem(4, """
        This person was mentioned in a POFile imported into Rosetta.

        When importing POFiles into Rosetta, we need to give credit for the
        translations on that POFile to its last translator, which may not
        exist in Launchpad, so we'd need to create it.
        """)

    KEYRINGTRUSTANALYZER = DBItem(5, """
        Created by the keyring trust analyzer.

        The keyring trust analyzer is responsible for scanning GPG keys
        belonging to the strongly connected set and assign all email addresses
        registered on those keys to the people representing their owners in
        Launchpad. If any of these people doesn't exist, it creates them.
        """)

    FROMEMAILMESSAGE = DBItem(6, """
        Created when parsing an email message.

        Sometimes we parse email messages and want to associate them with the
        sender, which may not have a Launchpad account. In that case we need
        to create a Person entry to associate with the email.
        """)

    SOURCEPACKAGEUPLOAD = DBItem(7, """
        This person was mentioned in a source package uploaded.

        Some uploaded packages may be uploaded with a maintainer that is not
        registered in Launchpad, and in these cases, soyuz may decide to
        create the new Person instead of complaining.
        """)

    OWNER_CREATED_LAUNCHPAD = DBItem(8, """
        Created by the owner, coming from Launchpad.

        Somebody was navigating through Launchpad and at some point decided to
        create an account.
        """)

    OWNER_CREATED_SHIPIT = DBItem(9, """
        Created by the owner, coming from Shipit.

        Somebody went to one of the shipit sites to request Ubuntu CDs and was
        directed to Launchpad to create an account.
        """)

    OWNER_CREATED_UBUNTU_WIKI = DBItem(10, """
        Created by the owner, coming from the Ubuntu wiki.

        Somebody went to the Ubuntu wiki and was directed to Launchpad to
        create an account.
        """)

    USER_CREATED = DBItem(11, """
        Created by a user to represent a person which does not use Launchpad.

        A user wanted to reference a person which is not a Launchpad user, so
        he created this "placeholder" profile.
        """)

    OWNER_CREATED_UBUNTU_SHOP = DBItem(12, """
        Created by the owner, coming from the Ubuntu Shop.

        Somebody went to the Ubuntu Shop and was directed to Launchpad to
        create an account.
        """)

    OWNER_CREATED_UNKNOWN_TRUSTROOT = DBItem(13, """
        Created by the owner, coming from unknown OpenID consumer.

        Somebody went to an OpenID consumer we don't know about and was
        directed to Launchpad to create an account.
        """)

    OWNER_SUBMITTED_HARDWARE_TEST = DBItem(14, """
        Created by a submission to the hardware database.

        Somebody without a Launchpad account made a submission to the
        hardware database.
        """)

    BUGWATCH = DBItem(15, """
        Created by the updating of a bug watch.

        A watch was made against a remote bug that the user submitted or
        commented on.
        """)

    SOFTWARE_CENTER_PURCHASE = DBItem(16, """
        Created by purchasing commercial software through Software Center.

        A purchase of commercial software (ie. subscriptions to a private
        and commercial archive) was made via Software Center.
        """)


class PersonNameField(BlacklistableContentNameField):
    """A `Person` team name, which is unique and performs psuedo blacklisting.

    If the team name is not unique, and the clash is with a private team,
    return the blacklist message.  Also return the blacklist message if the
    private prefix is used but the user is not privileged to create private
    teams.
    """
    errormessage = _("%s is already in use by another person or team.")

    @property
    def _content_iface(self):
        """Return the interface this field belongs to."""
        return IPerson

    def _getByName(self, name):
        """Return a Person by looking up his name."""
        return getUtility(IPersonSet).getByName(name, ignore_merged=False)

    def _validate(self, input):
        """See `UniqueField`."""
        # If the name didn't change then we needn't worry about validating it.
        if self.unchanged(input):
            return

        if not check_permission('launchpad.Commercial', self.context):
            # Commercial admins can create private teams, with or without the
            # private prefix.

            if input.startswith(PRIVATE_TEAM_PREFIX):
                raise LaunchpadValidationError(self.blacklistmessage % input)

            # If a non-privileged user attempts to use an existing name AND
            # the existing project is private, then return the blacklist
            # message rather than the message indicating the project exists.
            existing_object = self._getByAttribute(input)
            if (existing_object is not None and
                existing_object.visibility != PersonVisibility.PUBLIC):
                raise LaunchpadValidationError(self.blacklistmessage % input)

        # Perform the normal validation, including the real blacklist checks.
        super(PersonNameField, self)._validate(input)


def team_membership_policy_can_transition(team, policy):
    """Can the team can change its membership policy?

    Returns True when the policy can change. or raises an error. OPEN teams
    cannot be members of MODERATED or RESTRICTED teams. OPEN teams
    cannot have PPAs. Changes from between OPEN and the two closed states
    can be blocked by team membership and team artifacts.

    We only perform the check if a membership policy is transitioning from
    open->closed or visa versa. So if a team already has a closed subscription
    policy, it is always allowed to transition to another closed policy.

    :param team: The team to change.
    :param policy: The TeamMembershipPolicy to change to.
    :raises TeamMembershipPolicyError: Raised when a membership constrain
        or a team artifact prevents the policy from being set.
    """
    if team is None or policy == team.membership_policy:
        # The team is being initialized or the policy is not changing.
        return True
    elif (policy in INCLUSIVE_TEAM_POLICY
          and team.membership_policy in EXCLUSIVE_TEAM_POLICY):
        team.checkInclusiveMembershipPolicyAllowed(policy)
    elif (policy in EXCLUSIVE_TEAM_POLICY
          and team.membership_policy in INCLUSIVE_TEAM_POLICY):
        team.checkExclusiveMembershipPolicyAllowed(policy)
    return True


class TeamMembershipPolicyChoice(Choice):
    """A valid team membership policy."""

    def _getTeam(self):
        """Return the context if it is a team or None."""
        if IPerson.providedBy(self.context):
            return self.context
        else:
            return None

    def constraint(self, value):
        """See `IField`."""
        team = self._getTeam()
        policy = value
        try:
            return team_membership_policy_can_transition(team, policy)
        except TeamMembershipPolicyError:
            return False

    def _validate(self, value):
        """Ensure the TeamMembershipPolicy is valid for state of the team.

        Returns True if the team can change its membership policy to the
        `TeamMembershipPolicy`, otherwise raise TeamMembershipPolicyError.
        """
        team = self._getTeam()
        policy = value
        team_membership_policy_can_transition(team, policy)
        super(TeamMembershipPolicyChoice, self)._validate(value)


class IPersonClaim(Interface):
    """The schema used by IPerson's +claim form."""

    emailaddress = TextLine(title=_('Email address'), required=True)


# This has to be defined here to avoid circular import problems.
class IHasStanding(Interface):
    """An object that can have personal standing."""

    personal_standing = Choice(
        title=_('Personal standing'),
        required=True,
        vocabulary=PersonalStanding,
        description=_('The standing of a person for non-member mailing list '
                      'posting privileges.'))

    personal_standing_reason = Text(
        title=_('Reason for personal standing'),
        required=False,
        description=_("The reason the person's standing is what it is."))


class IPersonSettings(Interface):
    """Settings for a person (not a team!) that are used relatively rarely.

    We store these attributes on a separate object, PersonSettings, to which
    the Person class delegates.  This makes it possible to shrink the size of
    the person record.

    In the future, perhaps we will adapt IPerson to IPersonSettings when
    we want these attributes instead of delegating, so we can shrink the
    class, too.

    We also may want TeamSettings and PersonTeamSettings in the future.
    """

    selfgenerated_bugnotifications = Bool(
        title=_("Send me bug notifications for changes I make"),
        required=False, default=False)


class IPersonPublic(IPrivacy):
    """Public attributes for a Person.

    Very few attributes on a person can be public because private teams
    are also persons. The public attributes are generally information
    needed by the system to determine if the principal in the current
    interaction can work with the object.
    """

    id = Int(title=_('ID'), required=True, readonly=True)
    # This is redefined from IPrivacy.private because the attribute is
    # read-only. It is a summary of the team's visibility.
    private = exported(Bool(
            title=_("This team is private"),
            readonly=True, required=False,
            description=_("Private teams are visible only to "
                          "their members.")))
    is_valid_person = Bool(
        title=_("This is an active user and not a team."), readonly=True)
    is_valid_person_or_team = exported(
        Bool(title=_("This is an active user or a team."), readonly=True),
        exported_as='is_valid')
    is_team = exported(
        Bool(title=_('Is this object a team?'), readonly=True))
    account_status = Choice(
        title=_("The status of this person's account"), required=False,
        readonly=True, vocabulary=AccountStatus)
    account_status_comment = Text(
        title=_("Why are you deactivating your account?"), required=False,
        readonly=True)
    visibility = exported(
        Choice(title=_("Visibility"),
               description=_(
                   "Anyone can see a public team's data. Only team members "
                   "and Launchpad admins can see private team data. "
                   "Private teams cannot become public."),
               required=True, vocabulary=PersonVisibility,
               default=PersonVisibility.PUBLIC, readonly=True))

    def anyone_can_join():
        """Quick check as to whether a team allows anyone to join."""

    def checkAllowVisibility():
        """Is the user allowed to see the visibility field.

        :param: The user.
        :return: True if they can, otherwise False.
        """

    @mutator_for(visibility)
    @call_with(user=REQUEST_USER)
    @operation_parameters(visibility=copy_field(visibility))
    @export_write_operation()
    @operation_for_version("beta")
    def transitionVisibility(visibility, user):
        """Set visibility of IPerson.

        :param visibility: The PersonVisibility to change to.
        :param user: The user requesting the change.
        :raises: `ImmutableVisibilityError` when the visibility can not
            be changed.
        :return: None.
        """

    def isMergePending():
        """Is this person due to be merged with another?"""


class IPersonLimitedView(IHasIcon, IHasLogo):
    """IPerson attributes that require launchpad.LimitedView permission."""

    name = exported(
        PersonNameField(
            title=_('Name'), required=True, readonly=False,
            constraint=name_validator,
            description=_(
                "A short unique name, beginning with a lower-case "
                "letter or number, and containing only letters, "
                "numbers, dots, hyphens, or plus signs.")))
    displayname = exported(
        StrippedTextLine(
            title=_('Display Name'), required=True, readonly=False,
            description=_(
                "Your name as you would like it displayed throughout "
                "Launchpad. Most people use their full name here.")),
        exported_as='display_name')
    unique_displayname = TextLine(
        title=_('Return a string of the form $displayname ($name).'))
    # NB at this stage we do not allow individual people to have their own
    # icon, only teams get that. People can however have a logo and mugshot
    # The icon is only used for teams; that's why we use /@@/team as the
    # default image resource.
    icon = IconImageUpload(
        title=_("Icon"), required=False,
        default_image_resource='/@@/team',
        description=_(
            "A small image of exactly 14x14 pixels and at most 5kb in size, "
            "that can be used to identify this team. The icon will be "
            "displayed whenever the team name is listed - for example "
            "in listings of bugs or on a person's membership table."))
    iconID = Int(title=_('Icon ID'), required=True, readonly=True)
    logo = exported(
        LogoImageUpload(
            title=_("Logo"), required=False,
            default_image_resource='/@@/person-logo',
            description=_(
                "An image of exactly 64x64 pixels that will be displayed in "
                "the heading of all pages related to you. Traditionally this "
                "is a logo, a small picture or a personal mascot. It should "
                "be no bigger than 50kb in size.")))
    logoID = Int(title=_('Logo ID'), required=True, readonly=True)
    # title is required for the Launchpad Page Layout main template
    title = Attribute('Person Page Title')
    is_probationary = exported(
        Bool(title=_("Is this a probationary user?"), readonly=True))

    @operation_parameters(
        name=TextLine(required=True, constraint=name_validator))
    @operation_returns_entry(Interface)  # Really IArchive.
    @export_read_operation()
    @operation_for_version("beta")
    def getPPAByName(name):
        """Return a PPA with the given name if it exists.

        :param name: A string with the exact name of the ppa being looked up.
        :raises: `NoSuchPPA` if a suitable PPA could not be found.

        :return: a PPA `IArchive` record corresponding to the name.
        """


class IPersonViewRestricted(IHasBranches, IHasSpecifications,
                    IHasMergeProposals, IHasMugshot,
                    IHasLocation, IHasRequestedReviews, IObjectWithLocation,
                    IHasBugs, IHasRecipes, IHasTranslationImports,
                    IPersonSettings, IQuestionsPerson):
    """IPerson attributes that require launchpad.View permission."""
    account = Object(schema=IAccount)
    accountID = Int(title=_('Account ID'), required=True, readonly=True)
    karma = exported(
        Int(title=_('Karma'), readonly=True,
            description=_('The cached total karma for this person.')))
    homepage_content = exported(
        Text(title=_("Homepage Content"), required=False,
            description=_("Obsolete. Use description.")))

    description = exported(
        Text(title=_("Description"), required=False,
            description=_(
                "Details about interests and goals. Use plain text, "
                "paragraphs are preserved and URLs are linked.")))

    mugshot = exported(MugshotImageUpload(
        title=_("Mugshot"), required=False,
        default_image_resource='/@@/person-mugshot',
        description=_(
            "A large image of exactly 192x192 pixels, that will be displayed "
            "on your home page in Launchpad. Traditionally this is a great "
            "big picture of your grinning face. Make the most of it! It "
            "should be no bigger than 100kb in size. ")))
    mugshotID = Int(title=_('Mugshot ID'), required=True, readonly=True)

    languages = exported(
        CollectionField(
            title=_('List of languages known by this person'),
            readonly=True, required=False,
            value_type=Reference(schema=ILanguage)))

    hide_email_addresses = exported(
        Bool(title=_("Hide my email addresses from other Launchpad users"),
             required=False, default=False))
    # This is not a date of birth, it is the date the person record was
    # created in this db
    datecreated = exported(
        Datetime(title=_('Date Created'), required=True, readonly=True),
        exported_as='date_created')
    creation_rationale = Choice(
        title=_("Rationale for this entry's creation"), required=False,
        readonly=True, values=PersonCreationRationale.items)
    creation_comment = TextLine(
        title=_("Comment for this entry's creation"),
        description=_(
            "This comment may be displayed verbatim in a web page, so it "
            "has to follow some structural constraints, that is, it must "
            "be of the form: 'when %(action_details)s' (e.g 'when the "
            "foo package was imported into Ubuntu Breezy'). The only "
            "exception to this is when we allow users to create Launchpad "
            "profiles through the /people/+newperson page."),
        required=False, readonly=True)
    # XXX Guilherme Salgado 2006-11-10:
    # We can't use a Choice field here because we don't have a vocabulary
    # which contains valid people but not teams, and we don't really need one
    # apart from here.
    registrant = Attribute('The user who created this profile.')

    oauth_access_tokens = Attribute(_("Non-expired access tokens"))

    oauth_request_tokens = Attribute(_("Non-expired request tokens"))

    sshkeys = exported(
             CollectionField(
                title=_('List of SSH keys'),
                readonly=False, required=False,
                value_type=Reference(schema=ISSHKey)))

    # Properties of the Person object.
    karma_category_caches = Attribute(
        'The caches of karma scores, by karma category.')
    is_ubuntu_coc_signer = exported(
    Bool(title=_("Signed Ubuntu Code of Conduct"),
            readonly=True))
    activesignatures = Attribute("Retrieve own Active CoC Signatures.")
    inactivesignatures = Attribute("Retrieve own Inactive CoC Signatures.")
    signedcocs = Attribute("List of Signed Code Of Conduct")
    gpg_keys = exported(
        CollectionField(
            title=_("List of valid OpenPGP keys ordered by ID"),
            readonly=False, required=False,
            value_type=Reference(schema=IGPGKey)))
    pending_gpg_keys = CollectionField(
        title=_("Set of fingerprints pending confirmation"),
        readonly=False, required=False,
        value_type=Reference(schema=IGPGKey))
    inactive_gpg_keys = Attribute(
        "List of inactive OpenPGP keys in LP Context, ordered by ID")
    wiki_names = exported(
        CollectionField(
            title=_("All WikiNames of this Person, sorted alphabetically by "
                    "URL."),
            readonly=True, required=False,
            value_type=Reference(schema=IWikiName)))
    ircnicknames = exported(
        CollectionField(title=_("List of IRC nicknames of this Person."),
                        readonly=True, required=False,
                        value_type=Reference(schema=IIrcID)),
        exported_as='irc_nicknames')
    jabberids = exported(
        CollectionField(title=_("List of Jabber IDs of this Person."),
                        readonly=True, required=False,
                        value_type=Reference(schema=IJabberID)),
        exported_as='jabber_ids')
    team_memberships = exported(
        CollectionField(
            title=_("All TeamMemberships for Teams this Team or Person is an "
                    "active member of."),
            value_type=Reference(schema=ITeamMembership),
            readonly=True, required=False),
        exported_as='memberships_details')
    open_membership_invitations = exported(
        CollectionField(
            title=_('Open membership invitations.'),
            description=_("All TeamMemberships which represent an invitation "
                          "(to join a team) sent to this person."),
            readonly=True, required=False,
            value_type=Reference(schema=ITeamMembership)))
    # XXX: salgado, 2008-08-01: Unexported because this method doesn't take
    # into account whether or not a team's memberships are private.
    # teams_participated_in = exported(
    #     CollectionField(
    #         title=_('All teams in which this person is a participant.'),
    #         readonly=True, required=False,
    #         value_type=Reference(schema=Interface)),
    #     exported_as='participations')
    teams_participated_in = CollectionField(
        title=_('All teams in which this person is a participant.'),
        readonly=True, required=False,
        value_type=Reference(schema=Interface))
    # XXX: salgado, 2008-08-01: Unexported because this method doesn't take
    # into account whether or not a team's memberships are private.
    # teams_indirectly_participated_in = exported(
    #     CollectionField(
    #         title=_(
    #             'All teams in which this person is an indirect member.'),
    #         readonly=True, required=False,
    #         value_type=Reference(schema=Interface)),
    #     exported_as='indirect_participations')
    teams_indirectly_participated_in = CollectionField(
        title=_('All teams in which this person is an indirect member.'),
        readonly=True, required=False,
        value_type=Reference(schema=Interface))
    teams_with_icons = Attribute(
        "Iterable of all Teams that this person is active in that have "
        "icons")
    guessedemails = Attribute(
        "List of emails with status NEW. These email addresses probably "
        "came from a gina or POFileImporter run.")
    validatedemails = exported(
        CollectionField(
            title=_("Confirmed e-mails of this person."),
            description=_(
                "Confirmed e-mails are the ones in the VALIDATED state"),
            readonly=True, required=False,
            value_type=Reference(schema=IEmailAddress)),
        exported_as='confirmed_email_addresses')
    unvalidatedemails = Attribute(
        "Emails this person added in Launchpad but are not yet validated.")
    specifications = Attribute(
        "Any specifications related to this person, either because the are "
        "a subscriber, or an assignee, or a drafter, or the creator. "
        "Sorted newest-first.")

    def findVisibleAssignedInProgressSpecs(user):
        """List specifications in progress assigned to this person.

        In progress means their implementation is started but not yet
        completed.  They are sorted newest first.  No more than 5
        specifications are returned.

        :param user: The use to use for determining visibility.
        """

    teamowner = exported(
        PublicPersonChoice(
            title=_('Team Owner'), required=False, readonly=False,
            vocabulary='ValidTeamOwner'),
        exported_as='team_owner')
    teamownerID = Int(title=_("The Team Owner's ID or None"), required=False,
                      readonly=True)
    preferredemail = exported(
        Reference(title=_("Preferred email address"),
               description=_("The preferred email address for this person. "
                             "The one we'll use to communicate with them."),
               readonly=True, required=False, schema=IEmailAddress),
        exported_as='preferred_email_address')

    safe_email_or_blank = TextLine(
        title=_("Safe email for display"),
        description=_("The person's preferred email if they have"
                      "one and do not choose to hide it. Otherwise"
                      "the empty string."),
        readonly=True)

    verbose_bugnotifications = Bool(
        title=_("Include bug descriptions when sending me bug notifications"),
        required=False, default=True)

    mailing_list_auto_subscribe_policy = exported(
        Choice(title=_('Mailing List Auto-subscription Policy'),
               required=True,
               vocabulary=MailingListAutoSubscribePolicy,
               default=MailingListAutoSubscribePolicy.ON_REGISTRATION,
               description=_(
                   "This attribute determines whether a person is "
                   "automatically subscribed to a team's mailing list when "
                   "the person joins said team.")))

    merged = Int(
        title=_('Merged Into'), required=False, readonly=True,
        description=_(
            "When a Person is merged into another Person, this attribute "
            "is set on the Person referencing the destination Person. If "
            "this is set to None, then this Person has not been merged "
            "into another and is still valid"))

    archive = exported(
        Reference(
            title=_("Default PPA"),
            description=_("The PPA named 'ppa' owned by this person."),
            readonly=True, required=False,
            # Really IArchive, see archive.py
            schema=Interface))

    ppas = exported(
        CollectionField(
            title=_("PPAs for this person."),
            description=_(
                "PPAs owned by the context person ordered by name."),
            readonly=True, required=False,
            # Really IArchive, see archive.py
            value_type=Reference(schema=Interface)))

    structural_subscriptions = Attribute(
        "The structural subscriptions for this person.")

    visibilityConsistencyWarning = Attribute(
        "Warning that a private team may leak membership info.")

    sub_teams = exported(
        CollectionField(
            title=_("All subteams of this team."),
            description=_("""
                A subteam is any team that is a member (either directly or
                indirectly) of this team. As an example, let's say we have
                this hierarchy of teams:

                Rosetta Translators
                    Rosetta pt Translators
                        Rosetta pt_BR Translators

                In this case, both 'Rosetta pt Translators' and 'Rosetta pt_BR
                Translators' are subteams of the 'Rosetta Translators' team,
                and all members of both subteams are considered members of
                "Rosetta Translators".
                """),
            readonly=True, required=False,
            value_type=Reference(schema=Interface)))

    super_teams = exported(
        CollectionField(
            title=_("All superteams of this team."),
            description=_("""
                A superteam is any team that this team is a member of. For
                example, let's say we have this hierarchy of teams, and we are
                the "Rosetta pt_BR Translators":

                Rosetta Translators
                    Rosetta pt Translators
                        Rosetta pt_BR Translators

                In this case, we will return both 'Rosetta pt Translators' and
                'Rosetta Translators', because we are member of both of them.
                """),
            readonly=True, required=False,
            value_type=Reference(schema=Interface)))

    hardware_submissions = exported(CollectionField(
            title=_("Hardware submissions"),
            readonly=True, required=False,
            value_type=Reference(schema=Interface)))  # HWSubmission

    administrated_teams = Attribute(
        u"the teams that this person/team is an administrator of.")

    @invariant
    def personCannotHaveIcon(person):
        """Only Persons can have icons."""
        # XXX Guilherme Salgado 2007-05-28:
        # This invariant is busted! The person parameter provided to this
        # method will always be an instance of zope.formlib.form.FormData
        # containing only the values of the fields included in the POSTed
        # form. IOW, person.inTeam() will raise a NoInputData just like
        # person.teamowner would as it's not present in most of the
        # person-related forms.
        if person.icon is not None and not person.is_team:
            raise Invalid('Only teams can have an icon.')

    def convertToTeam(team_owner):
        """Convert this person into a team owned by the given team_owner.

        Also adds the given team owner as an administrator of the team.

        Only Person entries whose account_status is NOACCOUNT and which are
        not teams can be converted into teams.
        """

    @call_with(registrant=REQUEST_USER)
    @operation_parameters(
        description=Text(),
        distroseries=List(value_type=Reference(schema=Interface)),
        name=TextLine(),
        recipe_text=Text(),
        daily_build_archive=Reference(schema=Interface),
        build_daily=Bool(),
        )
    @export_factory_operation(Interface, [])
    @operation_for_version("beta")
    def createRecipe(name, description, recipe_text, distroseries,
                     registrant, daily_build_archive=None, build_daily=False):
        """Create a SourcePackageRecipe owned by this person.

        :param name: the name to use for referring to the recipe.
        :param description: A description of the recipe.
        :param recipe_text: The text of the recipe.
        :param distroseries: The distroseries to use.
        :param registrant: The person who created this recipe.
        :param daily_build_archive: The archive to use for daily builds.
        :param build_daily: If True, build this recipe daily (if changed).
        :return: a SourcePackageRecipe.
        """

    @operation_parameters(name=TextLine(required=True))
    @operation_returns_entry(Interface)  # Really ISourcePackageRecipe.
    @export_read_operation()
    @operation_for_version("beta")
    def getRecipe(name):
        """Return the person's recipe with the given name."""

    def getMergeQueue(name):
        """Return the person's merge queue with the given name."""

    @call_with(requester=REQUEST_USER)
    @export_read_operation()
    @operation_for_version("beta")
    def getArchiveSubscriptionURLs(requester):
        """Return private archive URLs that this person can see.

        For each of the private archives (PPAs) that this person can see,
        return a URL that includes the HTTP basic auth data.  The URL
        returned is suitable for including in a sources.list file.
        """

    @call_with(requester=REQUEST_USER)
    @operation_parameters(
        archive=Reference(schema=Interface))  # Really IArchive
    @export_write_operation()
    @operation_for_version("beta")
    def getArchiveSubscriptionURL(requester, archive):
        """Get a text line that is suitable to be used for a sources.list
        entry.

        It will create a new IArchiveAuthToken if one doesn't already exist.
        """

    def getVisiblePPAs(user):
        """Return active PPAs for which user has launchpad.View permission."""

    def getInvitedMemberships():
        """Return all TeamMemberships of this team with the INVITED status.

        The results are ordered using Person.sortingColumns.
        """

    def getInactiveMemberships():
        """Return all inactive TeamMemberships of this team.

        Inactive memberships are the ones with status EXPIRED or DEACTIVATED.

        The results are ordered using Person.sortingColumns.
        """

    def getProposedMemberships():
        """Return all TeamMemberships of this team with the PROPOSED status.

        The results are ordered using Person.sortingColumns.
        """

    @operation_returns_collection_of(Interface)
    @export_read_operation()
    @operation_for_version("beta")
    def getBugSubscriberPackages():
        """Return the packages for which this person is a bug subscriber.

        Returns a list of IDistributionSourcePackage's, ordered alphabetically
        (A to Z) by name.
        """

    def setContactAddress(email):
        """Set the given email address as this team's contact address.

        This method must be used only for teams, unless the disable argument
        is True.

        If the team has a contact address its status will be changed to
        VALIDATED.

        If the given email is None the team is left without a contact address.
        """

    def setPreferredEmail(email):
        """Set the given email address as this person's preferred one.

        If ``email`` is None, the preferred email address is unset, which
        will make the person invalid.

        This method must be used only for people, not teams.
        """

    # XXX: salgado, 2008-08-01: Unexported because this method doesn't take
    # into account whether or not a team's memberships are private.
    # @operation_parameters(team=copy_field(ITeamMembership['team']))
    # @operation_returns_collection_of(Interface) # Really IPerson
    # @export_read_operation()
    def findPathToTeam(team):
        """Return the teams providing membership to the given team.

        If there is more than one path leading this person to the given team,
        only the one with the oldest teams is returned.

        This method must not be called if this person is not an indirect
        member of the given team.
        """

    # XXX BarryWarsaw 2007-11-29: I'd prefer for this to be an Object() with a
    # schema of IMailingList, but setting that up correctly causes a circular
    # import error with interfaces.mailinglists that is too difficult to
    # unfunge for this one attribute.
    mailing_list = Attribute(
        _("The team's mailing list, if it has one, otherwise None."))

    def getProjectsAndCategoriesContributedTo(user, limit=10):
        """Return a list of dicts with projects and the contributions made
        by this person on that project.

        Only entries visible to the specified user will be shown.

        The list is limited to the :limit: projects this person is most
        active.

        The dictionaries containing the following keys:
            - project:    The project, which is either an IProduct or an
                          IDistribution.
            - categories: A dictionary mapping KarmaCategory titles to
                          the icons which represent that category.
        """

    def getAffiliatedPillars(user):
        """Return the pillars that this person directly has a role with.

        Returns distributions, project groups, and projects that this person
        maintains, drives, or is the bug supervisor for.
        """

    def getOwnedProjects(match_name=None):
        """Projects owned by this person or teams to which she belongs.

        :param match_name: string optional project name to screen the results.
        """

    def isAnyPillarOwner():
        """Is this person the owner of any pillar?"""

    def getAllCommercialSubscriptionVouchers(voucher_proxy=None):
        """Return all commercial subscription vouchers.

        All of a `Person`s vouchers are returned, regardless of redemption
        status.  Even vouchers marked inactive are returned.
        The result is a dictionary, indexed by the three
        voucher statuses.
        :return: dict
        """

    def getRedeemableCommercialSubscriptionVouchers(voucher_proxy=None):
        """Return the set of redeemable vouchers.

        The `Person`s vouchers are returned if they are unredeemed and active.

        The result is a list of vouchers.
        :return: list
        """

    def hasCurrentCommercialSubscription():
        """Return if the user has a current commercial subscription."""

    def assignKarma(action_name, product=None, distribution=None,
                    sourcepackagename=None, datecreated=None):
        """Assign karma for the action named <action_name> to this person.

        This karma will be associated with the given product or distribution.
        If a distribution is given, then product must be None and an optional
        sourcepackagename may also be given. If a product is given, then
        distribution and sourcepackagename must be None.

        If a datecreated is specified, the karma will be created with that
        date.  This is how historic karma events can be created.
        """

    def latestKarma(quantity=25):
        """Return the latest karma actions for this person.

        Return no more than the number given as quantity.
        """

    # XXX: salgado, 2008-08-01: Unexported because this method doesn't take
    # into account whether or not a team's memberships are private.
    # @operation_parameters(team=copy_field(ITeamMembership['team']))
    # @export_read_operation()
    def inTeam(team):
        """Is this person is a member of `team`?

        Returns `True` when you ask if an `IPerson` (or an `ITeam`,
        since it inherits from `IPerson`) is a member of himself
        (i.e. `person1.inTeam(person1)`).

        :param team: Either an object providing `IPerson`, the string name of
            a team or `None`. If a string was supplied the team is looked up.
        :return: A bool with the result of the membership lookup. When looking
            up the team from a string finds nothing or team was `None` then
            `False` is returned.
        """

    def clearInTeamCache():
        """Clears the person's inTeam cache.

        To be used when membership changes are enacted. Only meant to be
        used between TeamMembership and Person objects.
        """

    def getLatestSynchronisedPublishings():
        """Return `SourcePackagePublishingHistory`s synchronised by this
        person.

        This method will only include the latest publishings for each source
        package name, distribution series combination.
        """

    def getLatestMaintainedPackages():
        """Return `SourcePackageRelease`s maintained by this person.

        This method will only include the latest source package release
        for each source package name, distribution series combination.
        """

    def getLatestUploadedButNotMaintainedPackages():
        """Return `SourcePackageRelease`s created by this person but
        not maintained by him.

        This method will only include the latest source package release
        for each source package name, distribution series combination.
        """

    def getLatestUploadedPPAPackages():
        """Return `SourcePackageRelease`s uploaded by this person to any PPA.

        This method will only include the latest source package release
        for each source package name, distribution series combination.
        """

    def hasSynchronisedPublishings():
        """Are there `SourcePackagePublishingHistory`s synchronised by this
        person.
        """

    def hasMaintainedPackages():
        """Are there `SourcePackageRelease`s maintained by this person."""

    def hasUploadedButNotMaintainedPackages():
        """Are there `SourcePackageRelease`s created by this person but
        not maintained by him.
        """

    def hasUploadedPPAPackages():
        """Are there `SourcePackageRelease`s uploaded by this person to any
        PPA.
        """

    def validateAndEnsurePreferredEmail(email):
        """Ensure this person has a preferred email.

        If this person doesn't have a preferred email, <email> will be set as
        this person's preferred one. Otherwise it'll be set as VALIDATED and
        this person will keep their old preferred email.

        This method is meant to be the only one to change the status of an
        email address, but as we all know the real world is far from ideal
        and we have to deal with this in one more place, which is the case
        when people explicitly want to change their preferred email address.
        On that case, though, all we have to do is use
        person.setPreferredEmail().
        """

    def hasParticipationEntryFor(team):
        """Return True when this person is a member of the given team.

        The person's membership may be direct or indirect.
        """

    @call_with(user=REQUEST_USER)
    @operation_returns_collection_of(Interface)  # Really ITeam.
    @export_read_operation()
    @operation_for_version("devel")
    def getOwnedTeams(user=None):
        """Return the teams that this person owns.

        The iterator includes the teams that the user owns, but it not
        a member of.
        """

    def getAdministratedTeams():
        """Return the teams that this person/team is an administrator of.

        This includes teams for which the person is the owner, a direct
        member with admin privilege, or member of a team with such
        privileges.  It excludes teams which have been merged.
        """
    def getTeamAdminsEmailAddresses():
        """Return a set containing the email addresses of all administrators
        of this team.
        """

    def getLatestApprovedMembershipsForPerson(limit=5):
        """Return the <limit> latest approved membrships for this person."""

    def getPathsToTeams():
        """Return the paths to all teams related to this person."""

    @operation_parameters(
        language=Reference(schema=ILanguage))
    @export_write_operation()
    @operation_for_version("devel")
    def addLanguage(language):
        """Add a language to this person's preferences.

        :param language: An object providing ILanguage.

        If the given language is one of the user's preferred languages
        already, nothing will happen.
        """

    @operation_parameters(
        language=Reference(schema=ILanguage))
    @export_write_operation()
    @operation_for_version("devel")
    def removeLanguage(language):
        """Remove a language from this person's preferences.

        :param language: An object providing ILanguage.

        If the given language is not present, nothing  will happen.
        """

    def isBugContributor(user):
        """Is the person a contributer to bugs in Launchpad?

        Return True if the user has any bugs assigned to him, either
        directly or by team participation.

        :user: The user doing the search. Private bugs that this
        user doesn't have access to won't be included in the
        count.
        """

    def isBugContributorInTarget(user, target):
        """Is the person a contributor to bugs in `target`?

        Return True if the user has any bugs assigned to him in the
        context of a specific target, either directly or by team
        participation.

        :user: The user doing the search. Private bugs that this
        user doesn't have access to won't be included in the
        count.

        :target: An object providing `IBugTarget` to search within.
        """

    def autoSubscribeToMailingList(mailinglist, requester=None):
        """Subscribe this person to a mailing list.

        This method takes the user's mailing list auto-subscription
        setting into account, and it may or may not result in a list
        subscription.  It will only subscribe the user to the mailing
        list if all of the following conditions are met:

          * The mailing list is not None.
          * The mailing list is in an unusable state.
          * The user is not already subscribed.
          * The user has a preferred address set.
          * The user's auto-subscribe preference is ALWAYS, or
          * The user's auto-subscribe preference is ON_REGISTRATION,
            and the requester is either themself or None.

        This method will not raise exceptions if any of the above are
        not true.  If you want these problems to raise exceptions
        consider using `IMailinglist.subscribe()` directly.

        :param mailinglist: The list to subscribe to.  No action is
                taken if the list is None, or in an unusable state.

        :param requester: The person requesting the list subscription,
                if not the user himself.  The default assumes the user
                themself is making the request.

        :return: True if the user was subscribed, false if they weren't.
        """

    def checkRename():
        """Check if a person or team can be renamed.

        :return: a text string of the reason, or None if the rename is
        allowed.
        """

    def canCreatePPA():
        """Check if a person or team can create a PPA.

        :return: a boolean.
        """

    def getAssignedSpecificationWorkItemsDueBefore(date, user):
        """Return SpecificationWorkItems assigned to this person (or members
        of this team) and whose milestone is due between today and the given
        date (inclusive).

        user specifies the user who is viewing the list; items they cannot see
        are filtered out.  None indicates the anonymous user who can only see
        public items.
        """

    def getAssignedBugTasksDueBefore(date, user):
        """Get all BugTasks assigned to this person (or members of this team)
        and whose milestone is due between today and the given date
        (inclusive).
        """

    participant_ids = List(
        title=_("The DB IDs of this team's participants"), value_type=Int())
    active_member_count = Attribute(
        "The number of real people who are members of this team.")
    # activemembers.value_type.schema will be set to IPerson once
    # IPerson is defined.
    activemembers = Attribute(
        'List of direct members with ADMIN or APPROVED status')
    # For the API we need eager loading
    api_activemembers = exported(
        doNotSnapshot(
            CollectionField(
                title=_(
                    "List of direct members with ADMIN or APPROVED status"),
                value_type=Reference(schema=Interface))),
        exported_as='members')
    adminmembers = exported(
        doNotSnapshot(
            CollectionField(
                title=_("List of this team's admins."),
                value_type=Reference(schema=Interface))),
        exported_as='admins')
    all_member_count = Attribute(
        "The total number of real people who are members of this team, "
        "including subteams.")
    all_members_prepopulated = exported(
        doNotSnapshot(
            CollectionField(
                title=_("All participants of this team."),
                description=_(
                    "List of all direct and indirect people and teams who, "
                    "one way or another, are a part of this team. If you "
                    "want a method to check if a given person is a member "
                    "of a team, you should probably look at "
                    "IPerson.inTeam()."),
                value_type=Reference(schema=Interface))),
        exported_as='participants')
    allmembers = doNotSnapshot(
        Attribute("List of all members, without checking karma etc."))
    approvedmembers = doNotSnapshot(
        Attribute("List of members with APPROVED status"))
    deactivated_member_count = Attribute("Number of deactivated members")
    deactivatedmembers = exported(
        doNotSnapshot(
            CollectionField(
                title=_(
                    "All members whose membership is in the "
                    "DEACTIVATED state"),
                value_type=Reference(schema=Interface))),
        exported_as='deactivated_members')
    expired_member_count = Attribute("Number of EXPIRED members.")
    expiredmembers = exported(
        doNotSnapshot(
            CollectionField(
                title=_("All members whose membership is in the "
                        "EXPIRED state"),
                value_type=Reference(schema=Interface))),
        exported_as='expired_members')
    inactivemembers = doNotSnapshot(
        Attribute(
            "List of members with EXPIRED or DEACTIVATED status"))
    inactive_member_count = Attribute("Number of inactive members")
    invited_members = exported(
        doNotSnapshot(
            CollectionField(
                title=_("All members whose membership is "
                        "in the INVITED state"),
                value_type=Reference(schema=Interface))))

    invited_member_count = Attribute("Number of members with INVITED status")
    member_memberships = exported(
        doNotSnapshot(
            CollectionField(
                title=_("Active TeamMemberships for this object's members."),
                description=_(
                    "Active TeamMemberships are the ones with the ADMIN or "
                    "APPROVED status.  The results are ordered using "
                    "Person.sortingColumns."),
                readonly=True, required=False,
                value_type=Reference(schema=ITeamMembership))),
        exported_as='members_details')
    pendingmembers = doNotSnapshot(
        Attribute(
            "List of members with INVITED or PROPOSED status"))
    proposedmembers = exported(
        doNotSnapshot(
            CollectionField(
                title=_("All members whose membership is in the "
                        "PROPOSED state"),
                value_type=Reference(schema=Interface))),
        exported_as='proposed_members')
    proposed_member_count = Attribute("Number of PROPOSED members")

    def getMembersWithPreferredEmails():
        """Returns a result set of persons with precached addresses.

        Persons or teams without preferred email addresses are not included.
        """

    def getMembersWithPreferredEmailsCount():
        """Returns the count of persons/teams with preferred emails.

        See also getMembersWithPreferredEmails.
        """

    def getDirectAdministrators():
        """Return this team's administrators.

        This includes all direct members with admin rights and also
        the team owner. Note that some other persons/teams might have admin
        privilege by virtue of being a member of a team with admin rights.
        """

    @operation_parameters(status=copy_field(ITeamMembership['status']))
    @operation_returns_collection_of(Interface)  # Really IPerson
    @export_read_operation()
    @operation_for_version("beta")
    def getMembersByStatus(status, orderby=None):
        """Return the people whose membership on this team match :status:.

        If no orderby is provided, Person.sortingColumns is used.
        """


class IPersonEditRestricted(Interface):
    """IPerson attributes that require launchpad.Edit permission."""

    @call_with(requester=REQUEST_USER)
    @operation_parameters(team=copy_field(ITeamMembership['team']))
    @export_write_operation()
    @operation_for_version("beta")
    def join(team, requester=None, may_subscribe_to_list=True):
        """Join the given team if its membership_policy is not RESTRICTED.

        Join the given team according to the policies and defaults of that
        team:

        - If the team membership_policy is OPEN, the user is added as
          an APPROVED member with a NULL TeamMembership.reviewer.
        - If the team membership_policy is MODERATED, the user is added as
          a PROPOSED member and one of the team's administrators have to
          approve the membership.

        If may_subscribe_to_list is True, then also attempt to
        subscribe to the team's mailing list, depending on the list
        status and the person's auto-subscribe settings.

        :param requester: The person who requested the membership on
            behalf of a team or None when a person requests the
            membership for himself.

        :param may_subscribe_to_list: If True, also try subscribing to
            the team mailing list.
        """

    @operation_parameters(team=copy_field(ITeamMembership['team']))
    @export_write_operation()
    @operation_for_version("beta")
    def leave(team):
        """Leave the given team.

        This is a convenience method for retractTeamMembership() that allows
        a user to leave the given team, or to cancel a PENDING membership
        request.

        :param team: The team to leave.
        """

    def setMembershipData(person, status, reviewer, expires=None,
                          comment=None):
        """Set the attributes of the person's membership on this team.

        Set the status, dateexpires, reviewer and comment, where reviewer is
        the user responsible for this status change and comment is the comment
        left by the reviewer for the change.

        This method will ensure that we only allow the status transitions
        specified in the TeamMembership spec. It's also responsible for
        filling/cleaning the TeamParticipation table when the transition
        requires it.
        """

    @call_with(reviewer=REQUEST_USER)
    @operation_parameters(
        person=copy_field(ITeamMembership['person']),
        status=copy_field(ITeamMembership['status']),
        comment=Text(required=False))
    @export_write_operation()
    @operation_for_version("beta")
    def addMember(person, reviewer, status=TeamMembershipStatus.APPROVED,
                  comment=None, force_team_add=False,
                  may_subscribe_to_list=True):
        """Add the given person as a member of this team.

        :param person: If the given person is already a member of this
            team we'll simply change its membership status. Otherwise a new
            TeamMembership is created with the given status.

        :param reviewer: The user who made the given person a member of this
            team.

        :param comment: String that will be assigned to the
            proponent_comment, reviwer_comment, or acknowledger comment.

        :param status: `TeamMembershipStatus` value must be either
            Approved, Proposed or Admin.
            If the new member is a team, the status will be changed to
            Invited unless the user is also an admin of that team.

        :param force_team_add: If the person is actually a team and
            force_team_add is False, the team will actually be invited to
            join this one. Otherwise the team is added as if it were a
            person.

        :param may_subscribe_to_list: If the person is not a team, and
            may_subscribe_to_list is True, then the person may be subscribed
            to the team's mailing list, depending on the list status and the
            person's auto-subscribe settings.

        :return: A tuple containing a boolean indicating when the
            membership status changed and the current `TeamMembershipStatus`.
            This depends on the desired status passed as an argument, the
            membership policy and the user's privileges.
        """

    @operation_parameters(
        team=copy_field(ITeamMembership['team']),
        comment=Text())
    @export_write_operation()
    @operation_for_version("beta")
    def acceptInvitationToBeMemberOf(team, comment):
        """Accept an invitation to become a member of the given team.

        There must be a TeamMembership for this person and the given team with
        the INVITED status. The status of this TeamMembership will be changed
        to APPROVED.
        """

    @operation_parameters(
        team=copy_field(ITeamMembership['team']),
        comment=Text())
    @export_write_operation()
    @operation_for_version("beta")
    def declineInvitationToBeMemberOf(team, comment):
        """Decline an invitation to become a member of the given team.

        There must be a TeamMembership for this person and the given team with
        the INVITED status. The status of this TeamMembership will be changed
        to INVITATION_DECLINED.
        """

    @call_with(user=REQUEST_USER)
    @operation_parameters(
        team=copy_field(ITeamMembership['team']),
        comment=Text(required=False))
    @export_write_operation()
    @operation_for_version("beta")
    def retractTeamMembership(team, user, comment=None):
        """Retract this team's membership in the given team.

        If there's a membership entry for this team on the given team and
        its status is either APPROVED, ADMIN, PENDING, or INVITED, the status
        is changed and the relevant entries in TeamParticipation.

        APPROVED and ADMIN status are changed to DEACTIVATED.
        PENDING status is changed to DECLINED.
        INVITED status is changes to INVITATION_DECLINED.

        :param team: The team to leave.
        :param user: The user making the retraction.
        :param comment: An optional explanation about why the change was made.
        """

    def renewTeamMembership(team):
        """Renew the TeamMembership for this person on the given team.

        The given team's renewal policy must be ONDEMAND and the membership
        must be active (APPROVED or ADMIN) and set to expire in less than
        DAYS_BEFORE_EXPIRATION_WARNING_IS_SENT days.
        """

    def security_field_changed(subject, change_description,
        recipient_emails=None):
        """Trigger email when a secured field like preferredemail changes.

        :param recipient_emails: If supplied custom email addresses to notify.
            This is used when a new preferred email address is set.
        :param subject: The subject to use.
        :param change_description: A textual description to use when notifying
            about the change.
        """

    @operation_parameters(
        name=TextLine(required=True, constraint=name_validator),
        displayname=TextLine(required=False),
        description=TextLine(required=False),
        private=Bool(required=False),
        suppress_subscription_notifications=Bool(required=False),
        )
    @export_factory_operation(Interface, [])  # Really IArchive.
    @operation_for_version("beta")
    def createPPA(name=None, displayname=None, description=None,
                  private=False, suppress_subscription_notifications=False):
        """Create a PPA.

        :param name: A string with the name of the new PPA to create. If
            not specified, defaults to 'ppa'.
        :param displayname: The displayname for the new PPA.
        :param description: The description for the new PPA.
        :param private: Whether or not to create a private PPA. Defaults to
            False, which means the PPA will be public.
        :param suppress_subscription_notifications: Whether or not to suppress
            emails to new subscribers about their subscriptions.  Only
            meaningful for private PPAs.
        :raises: `PPACreationError` if an error is encountered

        :return: a PPA `IArchive` record.
        """


class IPersonSpecialRestricted(Interface):
    """IPerson methods that require launchpad.Special permission to use."""

    def canDeactivate():
        """Verify we safely deactivate this user account.

        :return: A possibly empty list which contains error messages.
        """

    def preDeactivate(comment):
        """Perform the easy work in deactivating a user."""

    def deactivate(comment=None, validate=True, pre_deactivate=True):
        """Deactivate this person's Launchpad account.

        Deactivating an account means:
            - Removing the user from all teams they are a member of;
            - Changing all of their email addresses' status to NEW;
            - Revoking Code of Conduct signatures of that user;
            - Reassigning bugs/specs assigned to that user;
            - Changing the ownership of products/projects/teams owned by that
              user.

        :param comment: An explanation of why the account status changed.
        :param validate: Run validation checks.
        """

    def reactivate(comment, preferred_email):
        """Reactivate this person and its account.

        Set the account status to ACTIVE, and update the preferred email
        address.

        If the person's name contains a -deactivatedaccount suffix (usually
        added by `IPerson`.deactivate(), it is removed.

        :param comment: An explanation of why the account status changed.
        :param preferred_email: The `EmailAddress` to set as the account's
            preferred email address. It cannot be None.
        """

    # XXX 2011-04-20, Abel Deuring, Bug=767293: The methods canAccess()
    # and canWrite() are defined in this interface for two reasons:
    # 1. The functions zope.security.checker.canWrite() and
    #    zope.security.checker.canAccess() can at present check only
    #    permissions for the current user, and this interface is
    #    protected by the permission launchpad.Special, which
    #    allows users only access to theirs own object.
    # 2. Allowing users access to check permissions for other persons
    #    than themselves might leak information.
    def canAccess(obj, attribute):
        """True if this person can access the given attribute of the object.

        :param obj: The object to be checked.
        :param attributes: The name of an attribute to check.
        :return: True if the person can access the attribute of the given
            object, else False.
        """

    def canWrite(obj, attribute):
        """True if this person can write the given attribute of the object.

        :param obj: The object to be checked.
        :param attribute: The name an attribute to check.
        :return: True if the person can change the attribute of the given
            object, else False.
        """


class IPerson(IPersonPublic, IPersonLimitedView, IPersonViewRestricted,
              IPersonEditRestricted, IPersonSpecialRestricted, IHasStanding,
              ISetLocation, IRootContext):
    """A Person."""
    export_as_webservice_entry(plural_name='people')


# Set the schemas to the newly defined interface for classes that deferred
# doing so when defined.
PersonChoice.schema = IPerson


class ITeamPublic(Interface):
    """Public attributes of a Team."""

    @invariant
    def defaultRenewalPeriodIsRequiredForSomeTeams(person):
        """Teams may specify a default renewal period.

        The team renewal period cannot be less than 1 day, and when the
        renewal policy is is 'On Demand' or 'Automatic', it cannot be None.
        """
        # The person arg is a zope.formlib.form.FormData instance.
        # Instead of checking 'not person.is_team' or 'person.teamowner',
        # we check for a field in the schema to identify this as a team.
        try:
            renewal_policy = person.renewal_policy
        except NoInputData:
            # This is not a team.
            return

        renewal_period = person.defaultrenewalperiod
        is_required_value_missing = (
            renewal_period is None
            and renewal_policy == TeamMembershipRenewalPolicy.ONDEMAND)
        out_of_range = (
            renewal_period is not None
            and (renewal_period <= 0 or renewal_period > 3650))
        if is_required_value_missing or out_of_range:
            raise Invalid(
                'You must specify a default renewal period '
                'from 1 to 3650 days.')

    teamdescription = exported(
        Text(title=_('Team Description'), required=False, readonly=False,
             description=_("Obsolete. Use description.")),
        exported_as='team_description')

    membership_policy = exported(
        TeamMembershipPolicyChoice(title=_('Membership policy'),
            vocabulary=TeamMembershipPolicy,
            default=TeamMembershipPolicy.RESTRICTED, required=True,
            description=_(
                TeamMembershipPolicy.__doc__.split('\n\n')[1])))

    subscription_policy = exported(
        TeamMembershipPolicyChoice(title=_('Membership policy'),
            vocabulary=TeamMembershipPolicy,
            description=_("Obsolete: use membership_policy"))
        )

    renewal_policy = exported(
        Choice(title=_("When someone's membership is about to expire, "
                       "notify them and"),
               required=True, vocabulary=TeamMembershipRenewalPolicy,
               default=TeamMembershipRenewalPolicy.NONE))

    defaultmembershipperiod = exported(
        Int(title=_('Subscription period'), required=False, max=3650,
            description=_(
                "Number of days a new subscription lasts before expiring. "
                "You can customize the length of an individual subscription "
                "when approving it. Leave this empty or set to 0 for "
                "subscriptions to never expire.")),
        exported_as='default_membership_period')

    defaultrenewalperiod = exported(
        Int(title=_('Self renewal period'), required=False,
            description=_(
                "Number of days members can renew their own membership. "
                "The number can be from 1 to 3650 (10 years).")),
        exported_as='default_renewal_period')

    defaultexpirationdate = Attribute(
        "The date, according to team's default values, in which a newly "
        "approved membership will expire.")

    defaultrenewedexpirationdate = Attribute(
        "The date, according to team's default values, in "
        "which a just-renewed membership will expire.")

    def checkInclusiveMembershipPolicyAllowed(policy='open'):
        """Check whether this team's membership policy can be open.

        An inclusive membership policy is OPEN or DELEGATED.
        A exclusive membership policy is MODERATED or RESTRICTED.
        An exclusive membership policy is required when:
        - any of the team's super teams are closed.
        - the team has any active PPAs
        - it is subscribed or assigned to any private bugs
        - it owns any pillars

        :param policy: The policy that is being checked for validity. This is
            an optional parameter used in the message of the exception raised
            when an open policy is not allowed. Sometimes though, the caller
            just wants to know if any open policy is allowed without having a
            particular policy to check. In this case, the method is called
            without a policy parameter being required.
        :raises TeamMembershipPolicyError: When the membership policy is
            not allowed to be open.
        """

    def checkExclusiveMembershipPolicyAllowed(policy='closed'):
        """Return true if this team's membership policy must be open.

        An inclusive membership policy is OPEN or DELEGATED.
        A exclusive membership policy is MODERATED or RESTRICTED.
        An inclusive membership policy is required when:
        - any of the team's sub (member) teams are open.

        :param policy: The policy that is being checked for validity. This is
            an optional parameter used in the message of the exception raised
            when a closed policy is not allowed. Sometimes though, the caller
            just wants to know if any closed policy is allowed without having
            a particular policy to check. In this case, the method is called
            without a policy parameter being required.
        :raises TeamMembershipPolicyError: When the membership policy is
            not allowed to be closed.
        """


class ITeam(IPerson, ITeamPublic):
    """A group of people and other teams.

    Launchpadlib example of getting the date a user joined a team::

        def get_join_date(team, user):
            team = launchpad.people[team]
            members = team.members_details
            for member in members:
                if member.member.name == user:
                    return member.date_joined
            return None

    Implementation notes:

    - ITeam extends IPerson.
    - The teamowner should never be None.
    """
    export_as_webservice_entry('team')

    # Logo, Mugshot and displayname are here so that they can have a
    # description on a Team which is different to the description they have on
    # a Person.
    logo = copy_field(
        IPerson['logo'], default_image_resource='/@@/team-logo',
        description=_(
            "An image of exactly 64x64 pixels that will be displayed in "
            "the heading of all pages related to the team. Traditionally "
            "this is a logo, a small picture or a personal mascot. It "
            "should be no bigger than 50kb in size."))

    mugshot = copy_field(
        IPerson['mugshot'], default_image_resource='/@@/team-mugshot',
        description=_(
            "A large image of exactly 192x192 pixels, that will be displayed "
            "on the team page in Launchpad. It "
            "should be no bigger than 100kb in size. "))

    displayname = copy_field(
        IPerson['displayname'],
        description=_(
            "This team's name as you would like it displayed throughout "
            "Launchpad."))


class IPersonSet(Interface):
    """The set of Persons."""
    export_as_webservice_collection(IPerson)

    title = Attribute('Title')

    @collection_default_content()
    def getTopContributors(limit=50):
        """Return the top contributors in Launchpad, up to the given limit."""

    def isNameBlacklisted(name, user=None):
        """Is the given name blacklisted by Launchpad Administrators?

        :param name: The name to be checked.
        :param user: The `IPerson` that wants to use the name. If the user
            is an admin for the nameblacklist expression, he can use the name.
        """

    def createPersonAndEmail(
            email, rationale, comment=None, name=None, displayname=None,
            hide_email_addresses=False, registrant=None):
        """Create and return an `IPerson` and `IEmailAddress`.

        The newly created EmailAddress will have a status of NEW and will be
        linked to the newly created Person.

        An Account is also created, but this will change in the future!

        If the given name is None, we generate a unique nickname from the
        email address given.

        :param email: The email address, as text.
        :param rationale: An item of `PersonCreationRationale` to be used as
            the person's creation_rationale.
        :param comment: A comment explaining why the person record was
            created (usually used by scripts which create them automatically).
            Must be of the following form: "when %(action_details)s"
            (e.g. "when the foo package was imported into Ubuntu Breezy").
        :param name: The person's name.
        :param displayname: The person's displayname.
        :param registrant: The user who created this person, if any.
        :param hide_email_addresses: Whether or not Launchpad should hide the
            person's email addresses from other users.
        :raises InvalidName: When the given name is not valid.
        :raises InvalidEmailAddress: When the given email is not valid.
        :raises NameAlreadyTaken: When the given name is already in use.
        :raises EmailAddressAlreadyTaken: When the given email is already in
            use.
        :raises NicknameGenerationError: When no name is provided and we can't
            generate a nickname from the given email address.
        """

    def createPersonWithoutEmail(
        name, rationale, comment=None, displayname=None, registrant=None):
        """Create and return an `IPerson` without using an email address.

        :param name: The person's name.
        :param comment: A comment explaining why the person record was
            created (usually used by scripts which create them automatically).
            Must be of the following form: "when %(action_details)s"
            (e.g. "when the foo package was imported into Ubuntu Breezy").
        :param displayname: The person's displayname.
        :param registrant: The user who created this person, if any.
        :raises InvalidName: When the passed name isn't valid.
        :raises NameAlreadyTaken: When the passed name has already been
            used.
        """

    def ensurePerson(email, displayname, rationale, comment=None,
                     registrant=None):
        """Make sure that there is a person in the database with the given
        email address. If necessary, create the person, using the
        displayname given.

        The comment must be of the following form: "when %(action_details)s"
        (e.g. "when the foo package was imported into Ubuntu Breezy").

        If the email address is already registered and bound to an
        `IAccount`, the created `IPerson` will have 'hide_email_addresses'
        flag set to True.

        XXX sabdfl 2005-06-14: this should be extended to be similar or
        identical to the other person creation argument lists, so we can
        call it and create a full person if needed. Email would remain the
        deciding factor, we would not try and guess if someone existed based
        on the displayname or other arguments.
        """

    @operation_parameters(identifier=TextLine(required=True))
    @operation_returns_entry(IPerson)
    @export_read_operation()
    @operation_for_version("devel")
    def getByOpenIDIdentifier(identifier):
        """Get the person for a given OpenID identifier.

        :param openid_identifier: full OpenID identifier URL for the user.
        :return: the corresponding `IPerson` or None if the identifier is
            unknown
        """

    def getOrCreateByOpenIDIdentifier(openid_identifier, email,
                                      full_name, creation_rationale, comment):
        """Get or create a person for a given OpenID identifier.

        This is used when users login. We get the account with the given
        OpenID identifier (creating one if it doesn't already exist) and
        act according to the account's state:
          - If the account is suspended, we stop and raise an error.
          - If the account is deactivated, we reactivate it and proceed;
          - If the account is active, we just proceed.

        If there is no existing Launchpad person for the account, we
        create it.

        :param openid_identifier: OpenID identifier suffix for the user.
            This is *not* the full URL, just the unique suffix portion.
        :param email_address: the email address of the user.
        :param full_name: the full name of the user.
        :param creation_rationale: When an account or person needs to
            be created, this indicates why it was created.
        :param comment: If the account is reactivated or person created,
            this comment indicates why.
        :return: a tuple of `IPerson` and a boolean indicating whether the
            database was updated.
        :raises AccountSuspendedError: if the account associated with the
            identifier has been suspended.
        """

    @call_with(teamowner=REQUEST_USER)
    @rename_parameters_as(
        displayname='display_name', teamdescription='team_description',
        defaultmembershipperiod='default_membership_period',
        defaultrenewalperiod='default_renewal_period')
    @operation_parameters(
        membership_policy=Choice(
            title=_('Membership policy'), vocabulary=TeamMembershipPolicy,
            required=False, default=TeamMembershipPolicy.MODERATED))
    @export_factory_operation(
        ITeam, ['name', 'displayname', 'teamdescription',
                'defaultmembershipperiod', 'defaultrenewalperiod',
                'subscription_policy'])
    @operation_for_version("beta")
    def newTeam(teamowner, name, displayname, teamdescription=None,
                membership_policy=TeamMembershipPolicy.MODERATED,
                defaultmembershipperiod=None, defaultrenewalperiod=None,
                subscription_policy=None):
        """Create and return a new Team with given arguments."""

    def get(personid):
        """Return the person with the given id or None if it's not found."""

    @operation_parameters(
        email=TextLine(required=True, constraint=email_validator))
    @operation_returns_entry(IPerson)
    @export_read_operation()
    @operation_for_version("beta")
    def getByEmail(email):
        """Return the person with the given email address.

        Return None if there is no person with the given email address.
        """

    def getByEmails(emails, include_hidden=True):
        """Search for people with the given email addresses.

        :param emails: A list of email addresses.
        :param include_hidden: Include people who have opted to hide their
            email. Defaults to True.

        :return: A `ResultSet` of `IEmailAddress`, `IPerson`.
        """

    def getByName(name, ignore_merged=True):
        """Return the person with the given name, ignoring merged persons if
        ignore_merged is True.

        Return None if there is no person with the given name.
        """

    def getByAccount(account):
        """Return the `IPerson` with the given account, or None."""

    def updateStatistics():
        """Update statistics caches and commit."""

    def peopleCount():
        """Return the number of non-merged persons in the database as
           of the last statistics update.
        """

    def teamsCount():
        """Return the number of teams in the database as of the last
           statistics update.
        """

    @operation_parameters(
        text=TextLine(title=_("Search text"), default=u""))
    @operation_returns_collection_of(IPerson)
    @export_read_operation()
    @operation_for_version("beta")
    def find(text=""):
        """Return all non-merged Persons and Teams whose name, displayname or
        email address match <text>.

        The results will be ordered using the default ordering specified in
        Person._defaultOrder.

        While we don't have Full Text Indexes in the emailaddress table, we'll
        be trying to match the text only against the beginning of an email
        address.
        """

    @operation_parameters(
        text=TextLine(
            title=_("Search text"), default=u""),
        created_after=Datetime(
            title=_("Created after"), required=False),
        created_before=Datetime(
            title=_("Created before"), required=False),
        )
    @operation_returns_collection_of(IPerson)
    @export_read_operation()
    @operation_for_version("beta")
    def findPerson(text="", exclude_inactive_accounts=True,
                   must_have_email=False,
                   created_after=None, created_before=None):
        """Return all non-merged Persons with at least one email address whose
        name, displayname or email address match <text>.

        If text is an empty string, all persons with at least one email
        address will be returned.

        The results will be ordered using the default ordering specified in
        Person._defaultOrder.

        If exclude_inactive_accounts is True, any accounts whose
        account_status is any of INACTIVE_ACCOUNT_STATUSES will not be in the
        returned set.

        If must_have_email is True, only people with one or more email
        addresses are returned.

        While we don't have Full Text Indexes in the emailaddress table, we'll
        be trying to match the text only against the beginning of an email
        address.

        If created_before or created_after are not None, they are used to
        restrict the search to the dates provided.
        """

    @operation_parameters(
        text=TextLine(title=_("Search text"), default=u""))
    @operation_returns_collection_of(IPerson)
    @export_read_operation()
    @operation_for_version("beta")
    def findTeam(text=""):
        """Return all Teams whose name, displayname or email address
        match <text>.

        The results will be ordered using the default ordering specified in
        Person._defaultOrder.

        While we don't have Full Text Indexes in the emailaddress table, we'll
        be trying to match the text only against the beginning of an email
        address.
        """

    def mergeAsync(from_person, to_person, requester, reviewer=None,
                   delete=False):
        """Merge a person/team into another asynchronously.

        This schedules a call to `merge()` to happen outside of the current
        context/request. The intention is that it is called soon after this
        method is called but there is no guarantee of that, nor is that call
        guaranteed to succeed. If either user is in a pending person merge
        job, None is returned.

        :param from_person: An IPerson or ITeam that is a duplicate.
        :param to_person: An IPerson or ITeam that is a master.
        :param requester: The IPerson who requested the merge.  Should not be
            an ITeam.
        :param reviewer: An IPerson who approved the ITeam merger.
        :param delete: The merge is really a deletion.
        :return: A `PersonMergeJob` or None.
        """

    def getValidPersons(persons):
        """Get all the Persons that are valid.

        This method is more effective than looking at
        Person.is_valid_person_or_team, since it avoids issuing one DB
        query per person. It queries the ValidPersonOrTeamCache table,
        issuing one query for all the person records. This makes the
        method useful for filling the ORM cache, so that checks to
        .is_valid_person won't issue any DB queries.

        XXX: This method exists mainly to fill the ORM cache for
             ValidPersonOrTeamCache. It would be better to add a column
             to the Person table. If we do that, this method can go
             away. Bug 221901. -- Bjorn Tillenius, 2008-04-25
        """

    def getPeopleWithBranches(product=None):
        """Return the people who have branches.

        :param product: If supplied, only people who have branches in the
            specified product are returned.
        """

    def updatePersonalStandings():
        """Update the personal standings of some people.

        Personal standing controls whether a person can post to a mailing list
        they are not a member of without moderation.  A person starts out with
        Unknown standing.  Once they have at least one message approved for
        three different lists, this method will bump their standing to Good.
        If a person's standing is already Good, or Poor or Excellent, no
        change to standing is made.
        """

    def cacheBrandingForPeople(people):
        """Prefetch Librarian aliases and content for personal images."""

    def getPrecachedPersonsFromIDs(
        person_ids, need_karma=False, need_ubuntu_coc=False,
        need_location=False, need_archive=False,
        need_preferred_email=False, need_validity=False):
        """Lookup person objects from ids with optional precaching.

        :param person_ids: List of person ids.
        :param need_karma: The karma attribute will be cached.
        :param need_ubuntu_coc: The is_ubuntu_coc_signer attribute will be
            cached.
        :param need_location: The location attribute will be cached.
        :param need_archive: The archive attribute will be cached.
        :param need_preferred_email: The preferred email attribute will be
            cached.
        :param need_validity: The is_valid attribute will be cached.
        """


class IRequestPeopleMerge(Interface):
    """This schema is used only because we want a very specific vocabulary."""

    dupe_person = Choice(
        title=_('Duplicated Account'), required=True,
        vocabulary='PersonAccountToMerge',
        description=_(
            "The e-mail address or Launchpad ID of the account you want to "
            "merge into yours."))


class IAdminPeopleMergeSchema(Interface):
    """The schema used by the admin merge people page."""

    dupe_person = Choice(
        title=_('Duplicated Person'), required=True,
        vocabulary='AdminMergeablePerson',
        description=_("The duplicated person found in Launchpad."))

    target_person = Choice(
        title=_('Target Person'), required=True,
        vocabulary='AdminMergeablePerson',
        description=_("The person to be merged on."))


class IAdminTeamMergeSchema(Interface):
    """The schema used by the admin merge teams page."""

    dupe_person = Choice(
        title=_('Duplicated Team'), required=True, vocabulary='ValidTeam',
        description=_("The duplicated team found in Launchpad."))

    target_person = Choice(
        title=_('Target Team'), required=True, vocabulary='ValidTeam',
        description=_("The team to be merged on."))


class IObjectReassignment(Interface):
    """The schema used by the object reassignment page."""

    owner = PublicPersonChoice(title=_('New'), vocabulary='ValidOwner',
                               required=True)


class ITeamReassignment(Interface):
    """The schema used by the team reassignment page."""

    owner = PublicPersonChoice(
        title=_('New'), vocabulary='ValidTeamOwner', required=True)


class TeamContactMethod(EnumeratedType):
    """The method used by Launchpad to contact a given team."""

    HOSTED_LIST = Item("""
        The Launchpad mailing list for this team

        Notifications directed to this team are sent to its Launchpad-hosted
        mailing list.
        """)

    NONE = Item("""
        Each member individually

        Notifications directed to this team will be sent to each of its
        members.
        """)

    EXTERNAL_ADDRESS = Item("""
        Another e-mail address

        Notifications directed to this team are sent to the contact address
        specified.
        """)


class ITeamContactAddressForm(Interface):

    contact_address = TextLine(
        title=_("Contact Email Address"), required=False, readonly=False)

    contact_method = Choice(
        title=_("How do people contact these team's members?"),
        required=True, vocabulary=TeamContactMethod)


class ISoftwareCenterAgentAPI(Interface):
    """XMLRPC API used by the software center agent."""

    def getOrCreateSoftwareCenterCustomer(openid_identifier, email,
                                          full_name):
        """Get or create an LP person based on a given identifier.

        See the method of the same name on `IPersonSet`. This XMLRPC version
        doesn't require the creation rationale and comment.

        This is added as a private XMLRPC method instead of exposing via the
        API as it should not be needed long-term. Long term we should allow
        the software center to create subscriptions to private PPAs without
        requiring a Launchpad account.
        """


class ICanonicalSSOApplication(ILaunchpadApplication):
    """XMLRPC application root for ICanonicalSSOAPI."""


class ICanonicalSSOAPI(Interface):
    """XMLRPC API used by the software center agent."""

    def getPersonDetailsByOpenIDIdentifier(openid_identifier):
        """Get the details of an LP person based on an OpenID identifier."""


class ISoftwareCenterAgentApplication(ILaunchpadApplication):
    """XMLRPC application root for ISoftwareCenterAgentAPI."""


@error_status(httplib.FORBIDDEN)
class ImmutableVisibilityError(Exception):
    """A change in team membership visibility is not allowed."""


class NoSuchPerson(NameLookupFailed):
    """Raised when we try to look up an IPerson that doesn't exist."""

    _message_prefix = "No such person"


class TeamEmailAddressError(Exception):
    """The person cannot be created as a team owns its email address."""


# Fix value_type.schema of IPersonViewRestricted attributes.
for name in [
    'all_members_prepopulated',
    'api_activemembers',
    'adminmembers',
    'proposedmembers',
    'invited_members',
    'deactivatedmembers',
    'expiredmembers',
    ]:
    IPersonViewRestricted[name].value_type.schema = IPerson

IPersonViewRestricted['sub_teams'].value_type.schema = ITeam
IPersonViewRestricted['super_teams'].value_type.schema = ITeam
# XXX: salgado, 2008-08-01: Uncomment these when teams_*participated_in are
# exported again.
# IPersonViewRestricted['teams_participated_in'].value_type.schema = ITeam
# IPersonViewRestricted[
#   'teams_indirectly_participated_in'].value_type.schema = ITeam

# Fix schema of operation parameters. We need zope.deferredimport!
params_to_fix = [
    # XXX: salgado, 2008-08-01: Uncomment these when they are exported again.
    # (IPersonViewRestricted['findPathToTeam'], 'team'),
    # (IPersonViewRestricted['inTeam'], 'team'),
    (IPersonEditRestricted['join'], 'team'),
    (IPersonEditRestricted['leave'], 'team'),
    (IPersonEditRestricted['addMember'], 'person'),
    (IPersonEditRestricted['acceptInvitationToBeMemberOf'], 'team'),
    (IPersonEditRestricted['declineInvitationToBeMemberOf'], 'team'),
    (IPersonEditRestricted['retractTeamMembership'], 'team'),
    ]
for method, name in params_to_fix:
    method.queryTaggedValue(
        'lazr.restful.exported')['params'][name].schema = IPerson

# Fix schema of operation return values.
# XXX: salgado, 2008-08-01: Uncomment when findPathToTeam is exported again.
# IPersonPublic['findPathToTeam'].queryTaggedValue(
#     'lazr.webservice.exported')['return_type'].value_type.schema = IPerson
IPersonViewRestricted['getMembersByStatus'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)['return_type'].value_type.schema = IPerson
IPersonViewRestricted['getOwnedTeams'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)['return_type'].value_type.schema = ITeam

# Fix schema of ITeamMembership fields.  Has to be done here because of
# circular dependencies.
for name in ['team', 'person', 'last_changed_by']:
    ITeamMembership[name].schema = IPerson

# Fix schema of ITeamParticipation fields.  Has to be done here because of
# circular dependencies.
for name in ['team', 'person']:
    ITeamParticipation[name].schema = IPerson

# Thank circular dependencies once again.
IIrcID['person'].schema = IPerson
IJabberID['person'].schema = IPerson
IWikiName['person'].schema = IPerson
IEmailAddress['person'].schema = IPerson
