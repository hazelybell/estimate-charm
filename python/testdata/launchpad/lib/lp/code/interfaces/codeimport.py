# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Code import interfaces."""

__metaclass__ = type

__all__ = [
    'ICodeImport',
    'ICodeImportSet',
    ]

import re

from CVS.protocol import (
    CVSRoot,
    CvsRootError,
    )
from lazr.restful.declarations import (
    call_with,
    export_as_webservice_entry,
    export_write_operation,
    exported,
    REQUEST_USER,
    )
from lazr.restful.fields import ReferenceChoice
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Choice,
    Datetime,
    Int,
    TextLine,
    Timedelta,
    )

from lp import _
from lp.app.validators import LaunchpadValidationError
from lp.code.enums import (
    CodeImportReviewStatus,
    RevisionControlSystems,
    )
from lp.code.interfaces.branch import IBranch
from lp.services.fields import (
    PublicPersonChoice,
    URIField,
    )


def validate_cvs_root(cvsroot):
    try:
        root = CVSRoot(cvsroot)
    except CvsRootError as e:
        raise LaunchpadValidationError(e)
    if root.method == 'local':
        raise LaunchpadValidationError('Local CVS roots are not allowed.')
    if not root.hostname:
        raise LaunchpadValidationError('CVS root is invalid.')
    if root.hostname.count('.') == 0:
        raise LaunchpadValidationError(
            'Please use a fully qualified host name.')
    return True


def validate_cvs_module(cvsmodule):
    valid_module = re.compile('^[a-zA-Z][a-zA-Z0-9_/.+-]*$')
    if not valid_module.match(cvsmodule):
        raise LaunchpadValidationError(
            'The CVS module contains illegal characters.')
    if cvsmodule == 'CVS':
        raise LaunchpadValidationError(
            'A CVS module can not be called "CVS".')
    return True


def validate_cvs_branch(branch):
    if branch and re.match('^[a-zA-Z][a-zA-Z0-9_-]*$', branch):
        return True
    else:
        raise LaunchpadValidationError('Your CVS branch name is invalid.')


class ICodeImport(Interface):
    """A code import to a Bazaar Branch."""

    export_as_webservice_entry()

    id = Int(readonly=True, required=True)
    date_created = Datetime(
        title=_("Date Created"), required=True, readonly=True)

    branch = exported(
        ReferenceChoice(
            title=_('Branch'), required=True, readonly=True,
            vocabulary='Branch', schema=IBranch,
            description=_("The Bazaar branch produced by the "
                "import system.")))

    registrant = PublicPersonChoice(
        title=_('Registrant'), required=True, readonly=True,
        vocabulary='ValidPersonOrTeam',
        description=_("The person who initially requested this import."))

    review_status = exported(
        Choice(
            title=_("Review Status"), vocabulary=CodeImportReviewStatus,
            default=CodeImportReviewStatus.REVIEWED, readonly=True,
            description=_("Only reviewed imports are processed.")))

    rcs_type = exported(
        Choice(title=_("Type of RCS"), readonly=True,
            required=True, vocabulary=RevisionControlSystems,
            description=_(
                "The version control system to import from. "
                "Can be CVS or Subversion.")))

    url = exported(
        URIField(title=_("URL"), required=False, readonly=True,
            description=_("The URL of the VCS branch."),
            allowed_schemes=["http", "https", "svn", "git", "bzr", "ftp"],
            allow_userinfo=True,
            allow_port=True,
            allow_query=False,      # Query makes no sense in Subversion.
            allow_fragment=False,   # Fragment makes no sense in Subversion.
            trailing_slash=False))  # See http://launchpad.net/bugs/56357.

    cvs_root = exported(
        TextLine(title=_("Repository"), required=False, readonly=True,
            constraint=validate_cvs_root,
            description=_("The CVSROOT. "
                "Example: :pserver:anonymous@anoncvs.gnome.org:/cvs/gnome")))

    cvs_module = exported(
        TextLine(title=_("Module"), required=False, readonly=True,
            constraint=validate_cvs_module,
            description=_("The path to import within the repository."
                " Usually, it is the name of the project.")))

    date_last_successful = exported(
        Datetime(title=_("Last successful"), required=False, readonly=True))

    update_interval = Timedelta(
        title=_("Update interval"), required=False, description=_(
        "The user-specified time between automatic updates of this import. "
        "If this is unspecified, the effective update interval is a default "
        "value selected by Launchpad administrators."))

    effective_update_interval = Timedelta(
        title=_("Effective update interval"), required=True, readonly=True,
        description=_(
        "The effective time between automatic updates of this import. "
        "If the user did not specify an update interval, this is a default "
        "value selected by Launchpad administrators."))

    def getImportDetailsForDisplay():
        """Get a one-line summary of the location this import is from."""

    import_job = Choice(
        title=_("Current job"),
        readonly=True, vocabulary='CodeImportJob',
        description=_(
            "The current job for this import, either pending or running."))

    results = Attribute("The results for this code import.")

    consecutive_failure_count = Attribute(
        "How many times in a row this import has failed.")

    def updateFromData(data, user):
        """Modify attributes of the `CodeImport`.

        Creates and returns a MODIFY `CodeImportEvent` if changes were made.

        This method preserves the invariant that a `CodeImportJob` exists for
        a given import if and only if its review_status is REVIEWED, creating
        and deleting jobs as necessary.

        :param data: dictionary whose keys are attribute names and values are
            attribute values.
        :param user: user who made the change, to record in the
            `CodeImportEvent`.  May be ``None``.
        :return: The MODIFY `CodeImportEvent`, if any changes were made, or
            None if no changes were made.
        """

    def tryFailingImportAgain(user):
        """Try a failing import again.

        This method sets the review_status back to REVIEWED and requests the
        import be attempted as soon as possible.

        The import must be in the FAILING state.

        :param user: the user who is requesting the import be tried again.
        """

    @call_with(requester=REQUEST_USER)
    @export_write_operation()
    def requestImport(requester, error_if_already_requested=False):
        """Request that an import be tried soon.

        This method will schedule an import to happen soon for this branch.

        The import must be in the Reviewed state, if not then a
        CodeImportNotInReviewedState error will be thrown. If using the
        API then a status code of 400 will result.

        If the import is already running then a CodeImportAlreadyRunning
        error will be thrown. If using the API then a status code of
        400 will result.

        The two cases can be distinguished over the API by seeing if the
        exception names appear in the body of the response.

        If used over the API and the request has already been made then this
        method will silently do nothing.
        If called internally then the error_if_already_requested parameter
        controls whether a CodeImportAlreadyRequested exception will be
        thrown in that situation.

        :return: None
        """


class ICodeImportSet(Interface):
    """Interface representing the set of code imports."""

    def new(registrant, target, branch_name, rcs_type, url=None,
            cvs_root=None, cvs_module=None, review_status=None,
            owner=None):
        """Create a new CodeImport.

        :param target: An `IBranchTarget` that the code is associated with.
        :param owner: The `IPerson` to set as the owner of the branch, or
            None to use registrant. registrant must be a member of owner to
            do this.
        """

    def get(id):
        """Get a CodeImport by its id.

        Raises `NotFoundError` if no such import exists.
        """

    def getByBranch(branch):
        """Get the CodeImport, if any, associated to a Branch."""

    def getByCVSDetails(cvs_root, cvs_module):
        """Get the CodeImport with the specified CVS details."""

    def getByURL(url):
        """Get the CodeImport with the url."""

    def delete(id):
        """Delete a CodeImport given its id."""

    def search(review_status=None, rcs_type=None):
        """Find the CodeImports of the given status and type.

        :param review_status: An entry from the `CodeImportReviewStatus`
            schema, or None, which signifies 'any status'.
        :param rcs_type: An entry from the `RevisionControlSystems`
            schema, or None, which signifies 'any type'.
        """
