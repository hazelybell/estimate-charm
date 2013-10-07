# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Launchpad XMLRPC faults."""

# Note: When you add a fault to this file, be sure to add it to configure.zcml
# in this directory.

__metaclass__ = type

__all__ = [
    'BadStatus',
    'BranchAlreadyRegistered',
    'BranchCreationForbidden',
    'BranchNameInUse',
    'BranchUniqueNameConflict',
    'CannotHaveLinkedBranch',
    'FileBugGotProductAndDistro',
    'FileBugMissingProductOrDistribution',
    'InvalidBranchIdentifier',
    'InvalidBranchName',
    'InvalidBranchUniqueName',
    'InvalidProductName',
    'InvalidBranchUrl',
    'InvalidSourcePackageName',
    'OopsOccurred',
    'NoBranchWithID',
    'NoLinkedBranch',
    'NoSuchBranch',
    'NoSuchBug',
    'NoSuchCodeImportJob',
    'NoSuchDistribution',
    'NoSuchPackage',
    'NoSuchPerson',
    'NoSuchPersonWithName',
    'NoSuchProduct',
    'NoSuchProductSeries',
    'NoSuchTeamMailingList',
    'NotInTeam',
    'NoUrlForBranch',
    'RequiredParameterMissing',
    'TeamEmailAddress',
    'UnexpectedStatusReport',
    ]


from lp.registry.interfaces.projectgroup import IProjectGroup
from lp.services.xmlrpc import LaunchpadFault


class NoSuchProduct(LaunchpadFault):
    """There's no such product registered in Launchpad."""

    error_code = 10
    msg_template = "No such project: %(product_name)s"

    def __init__(self, product_name):
        LaunchpadFault.__init__(self, product_name=product_name)
        self.product_name = product_name


class NoSuchPerson(LaunchpadFault):
    """There's no Person with the specified email registered in Launchpad."""

    error_code = 20
    msg_template = (
        'Invalid %(type)s: No user with the email address '
        '"%(email_address)s" was found')

    def __init__(self, email_address, type="user"):
        LaunchpadFault.__init__(self, type=type, email_address=email_address)


class NoSuchBranch(LaunchpadFault):
    """There's no Branch with the specified URL registered in Launchpad."""

    error_code = 30
    msg_template = "No such branch: %(branch_url)s"

    def __init__(self, branch_url):
        LaunchpadFault.__init__(self, branch_url=branch_url)


class NoSuchBug(LaunchpadFault):
    """There's no Bug with the specified id registered in Launchpad."""

    error_code = 40
    msg_template = "No such bug: %(bug_id)s"

    def __init__(self, bug_id):
        LaunchpadFault.__init__(self, bug_id=bug_id)


class BranchAlreadyRegistered(LaunchpadFault):
    """A branch with the same URL is already registered in Launchpad."""

    error_code = 50
    msg_template = "%(branch_url)s is already registered."

    def __init__(self, branch_url):
        LaunchpadFault.__init__(self, branch_url=branch_url)


class FileBugMissingProductOrDistribution(LaunchpadFault):
    """No product or distribution specified when filing a bug."""

    error_code = 60
    msg_template = (
        "Required arguments missing. You must specify either a product or "
        "distribution in which the bug exists.")


class FileBugGotProductAndDistro(LaunchpadFault):
    """A distribution and product were specified when filing a bug.

    Only one is allowed.
    """

    error_code = 70
    msg_template = (
        "Too many arguments. You may specify either a product or a "
        "distribution, but not both.")


class NoSuchDistribution(LaunchpadFault):
    """There's no such distribution registered in Launchpad."""

    error_code = 80
    msg_template = "No such distribution: %(distro_name)s"

    def __init__(self, distro_name):
        LaunchpadFault.__init__(self, distro_name=distro_name)


class NoSuchPackage(LaunchpadFault):
    """There's no source or binary package with the name provided."""

    error_code = 90
    msg_template = "No such package: %(package_name)s"

    def __init__(self, package_name):
        LaunchpadFault.__init__(self, package_name=package_name)


class RequiredParameterMissing(LaunchpadFault):
    """A required parameter was not provided."""

    error_code = 100
    msg_template = "Required parameter missing: %(parameter_name)s"

    def __init__(self, parameter_name):
        LaunchpadFault.__init__(self, parameter_name=parameter_name)


class BranchCreationForbidden(LaunchpadFault):
    """The user was not permitted to create a branch."""

    error_code = 110
    msg_template = (
        "You are not allowed to create a branch for project: "
        "%(parameter_name)s")

    def __init__(self, parameter_name):
        LaunchpadFault.__init__(self, parameter_name=parameter_name)


class InvalidBranchUrl(LaunchpadFault):
    """The provided branch URL is not valid."""

    error_code = 120
    msg_template = "Invalid URL: %(branch_url)s\n%(message)s"

    def __init__(self, branch_url, message):
        LaunchpadFault.__init__(self, branch_url=branch_url, message=message)


class BranchUniqueNameConflict(LaunchpadFault):
    """There is already a branch with this unique name."""

    error_code = 130
    msg_template = "Unique name already in use: %(unique_name)s"

    def __init__(self, unique_name):
        LaunchpadFault.__init__(self, unique_name=unique_name)


class NoSuchTeamMailingList(LaunchpadFault):
    """There is no such team mailing list with the given name."""

    error_code = 140
    msg_template = 'No such team mailing list: %(team_name)s'

    def __init__(self, team_name):
        LaunchpadFault.__init__(self, team_name=team_name)


class UnexpectedStatusReport(LaunchpadFault):
    """A team mailing list received an unexpected status report.

    In other words, the mailing list was not in a state that was awaiting such
    a status report.
    """

    error_code = 150
    msg_template = ('Unexpected status report "%(status)s" '
                    'for team: %(team_name)s')

    def __init__(self, team_name, status):
        LaunchpadFault.__init__(self, team_name=team_name, status=status)


class BadStatus(LaunchpadFault):
    """A bad status string was received."""

    error_code = 160
    msg_template = 'Bad status string "%(status)s" for team: %(team_name)s'

    def __init__(self, team_name, status):
        LaunchpadFault.__init__(self, team_name=team_name, status=status)


class NoLinkedBranch(LaunchpadFault):
    """The object has no branch registered with it."""

    error_code = 170
    msg_template = ('%(object_name)s has no default branch.')

    def __init__(self, component):
        LaunchpadFault.__init__(self, object_name=component.displayname)


class NoSuchProductSeries(LaunchpadFault):
    """There is no such series on a particular project."""

    error_code = 180
    msg_template = (
        'Project %(product_name)s has no series called "%(series_name)s"')

    def __init__(self, series_name, product):
        LaunchpadFault.__init__(
            self, series_name=series_name, product_name=product.name)


class InvalidBranchIdentifier(LaunchpadFault):
    """The branch identifier didn't begin with a tilde."""

    error_code = 190
    msg_template = (
        'Invalid branch identifier: %(branch_path)r')

    def __init__(self, branch_path):
        LaunchpadFault.__init__(self, branch_path=branch_path)


class NoSuchPersonWithName(LaunchpadFault):
    """There's no Person with the specified name registered in Launchpad."""

    error_code = 200
    msg_template = 'No such person or team: %(person_name)s'

    def __init__(self, person_name):
        LaunchpadFault.__init__(self, person_name=person_name)


class BranchNameInUse(LaunchpadFault):
    """There is already a branch with this name for this product."""

    error_code = 220
    msg_template = "Branch name already in use: %(error)s"

    def __init__(self, error):
        LaunchpadFault.__init__(self, error=error)


class CannotHaveLinkedBranch(LaunchpadFault):
    """Raised when we get a linked branch for a thing that can't have any.

    An example of this is trying to get lp:bazaar, where 'bazaar' is a project
    group, or lp:ubuntu, where 'ubuntu' is a distro.
    """

    error_code = 230
    msg_template = (
        "%(component_name)s is a %(component_type)s, and a "
        "%(component_type)s cannot have a default branch.")

    def __init__(self, component):
        if IProjectGroup.providedBy(component):
            component_type = 'project group'
        else:
            component_type = component.__class__.__name__.lower()
        LaunchpadFault.__init__(
            self, component_name=component.displayname,
            component_type=component_type)


class InvalidProductName(LaunchpadFault):
    """Raised when we are passed an invalid name for a product.

    This is for when users try to specify a product using a silly name
    like 'flop$y,mop$y&cott0ntail'.
    """

    error_code = 240
    msg_template = "%(name)s cannot be the name for a project."

    def __init__(self, name):
        LaunchpadFault.__init__(self, name=name)


class NotInTeam(LaunchpadFault):
    """Raised when a person needs to be a member of a team, but is not.

    In particular, this is used when a user tries to register a branch as
    being owned by a team that they themselves are not a member of.
    """

    error_code = 250
    msg_template = '%(person_name)s is not a member of %(team_name)s.'

    def __init__(self, person_name, team_name):
        LaunchpadFault.__init__(
            self, person_name=person_name, team_name=team_name)


class InvalidBranchName(LaunchpadFault):
    """The branch name is not allowed by Launchpad.

    Raised when the user tries to register a branch with forbidden characters
    in it.
    """

    error_code = 260
    # The actual exception is rather friendly, so we just wrap it in a Fault.
    msg_template = '%(error)s'

    def __init__(self, error):
        error_message = error.args[0].encode('utf-8', 'replace')
        LaunchpadFault.__init__(self, error=error_message)


class NoBranchWithID(LaunchpadFault):
    """There's no branch with the given ID."""

    error_code = 270
    msg_template = 'No branch with ID %(branch_id)s'

    def __init__(self, branch_id):
        LaunchpadFault.__init__(self, branch_id=branch_id)


class NoUrlForBranch(LaunchpadFault):
    """resolve_lp_path resolved to a remote branch with no URL."""

    error_code = 280
    msg_template = (
        'The remote branch at %(unique_name)s has no URL specified.')

    def __init__(self, unique_name):
        LaunchpadFault.__init__(self, unique_name=unique_name)


class PathTranslationError(LaunchpadFault):
    """Raised when a virtual path cannot be translated to a real one.

    This can be raised when the path is utterly unrecognizable, or when the
    path looks sensible, but points to a resource we can't find.
    """

    error_code = 290
    msg_template = "Could not translate '%(path)s'."

    def __init__(self, path):
        LaunchpadFault.__init__(self, path=path)


class InvalidPath(LaunchpadFault):
    """Raised when `translatePath` is passed something that's not a path."""

    error_code = 300
    msg_template = (
        "Could not translate '%(path)s'. Can only translate absolute paths.")

    def __init__(self, path):
        LaunchpadFault.__init__(self, path=path)


class PermissionDenied(LaunchpadFault):
    """Raised when a user is denied access to some resource."""

    error_code = 310
    msg_template = (
        "%(message)s")

    def __init__(self, message="Permission denied."):
        LaunchpadFault.__init__(self, message=message)


class NotFound(LaunchpadFault):
    """Raised when a resource is not found."""

    error_code = 320
    msg_template = (
        "%(message)s")

    def __init__(self, message="Not found."):
        LaunchpadFault.__init__(self, message=message)


class InvalidBranchUniqueName(LaunchpadFault):
    """Raised when a user tries to resolve a unique name that's incomplete.
    """

    error_code = 330
    msg_template = (
        "~%(path)s is too short to be a branch name. Try "
        "'~<owner>/+junk/<branch>', '~<owner>/<product>/<branch> or "
        "'~<owner>/<distribution>/<series>/<sourcepackage>/<branch>'.")

    def __init__(self, path):
        self.path = path
        LaunchpadFault.__init__(self, path=path)


class NoSuchDistroSeries(LaunchpadFault):
    """Raised when the user tries to get a distroseries that doesn't exist."""

    error_code = 340
    msg_template = "No such distribution series %(distroseries_name)s."

    def __init__(self, distroseries_name):
        self.distroseries_name = distroseries_name
        LaunchpadFault.__init__(self, distroseries_name=distroseries_name)


class NoSuchSourcePackageName(LaunchpadFault):
    """Raised when the user tries to get a sourcepackage that doesn't exist.
    """

    error_code = 350
    msg_template = "No such source package %(sourcepackagename)s."

    def __init__(self, sourcepackagename):
        self.sourcepackagename = sourcepackagename
        LaunchpadFault.__init__(self, sourcepackagename=sourcepackagename)


class NoSuchCodeImportJob(LaunchpadFault):
    """Raised by `ICodeImportScheduler` methods when a job is not found."""

    error_code = 360
    msg_template = 'Job %(job_id)d not found.'

    def __init__(self, job_id):
        LaunchpadFault.__init__(self, job_id=job_id)


class AccountSuspended(LaunchpadFault):
    """Raised by `ISoftwareCenterAgentAPI` when an account is suspended."""

    error_code = 370
    msg_template = (
        'The openid_identifier \'%(openid_identifier)s\''
        ' is linked to a suspended account.')

    def __init__(self, openid_identifier):
        LaunchpadFault.__init__(self, openid_identifier=openid_identifier)


class OopsOccurred(LaunchpadFault):
    """An oops has occurred performing the requested operation."""

    error_code = 380
    msg_template = (
        'An unexpected error has occurred while %(server_op)s. '
        'Please report a Launchpad bug and quote: %(oopsid)s.')

    def __init__(self, server_op, oopsid):
        LaunchpadFault.__init__(self, server_op=server_op, oopsid=oopsid)
        self.oopsid = oopsid


class InvalidSourcePackageName(LaunchpadFault):

    error_code = 390
    msg_template = ("%(name)s is not a valid source package name.")

    def __init__(self, name):
        self.name = name
        LaunchpadFault.__init__(self, name=name)


class TeamEmailAddress(LaunchpadFault):
    """Raised by `ISoftwareCenterAgentAPI` when an email address is a team."""

    error_code = 400
    msg_template = (
        'The email address \'%(email)s\' '
        '(openid_identifier \'%(openid_identifier)s\') '
        'is linked to a Launchpad team.')

    def __init__(self, email, openid_identifier):
        LaunchpadFault.__init__(
            self, email=email, openid_identifier=openid_identifier)
