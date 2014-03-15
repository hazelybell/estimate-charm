# -*- coding: utf-8 -*-
# NOTE: The first line above must stay first; do not move the copyright
# notice to the top.  See http://www.python.org/dev/peps/pep-0263/.
#
# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Testing infrastructure for the Launchpad application.

This module should not contain tests (but it should be tested).
"""

__metaclass__ = type
__all__ = [
    'GPGSigningContext',
    'is_security_proxied_or_harmless',
    'LaunchpadObjectFactory',
    'ObjectFactory',
    'remove_security_proxy_and_shout_at_engineer',
    ]

from datetime import (
    datetime,
    timedelta,
    )
from email.encoders import encode_base64
from email.message import Message as EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import (
    formatdate,
    make_msgid,
    )
import hashlib
from itertools import count
from operator import (
    isMappingType,
    isSequenceType,
    )
import os
from StringIO import StringIO
import sys
from textwrap import dedent
from types import InstanceType
import uuid
import warnings

from bzrlib.plugins.builder.recipe import BaseRecipeBranch
from bzrlib.revision import Revision as BzrRevision
from lazr.jobrunner.jobrunner import SuspendJobException
import pytz
from pytz import UTC
import simplejson
from twisted.python.util import mergeFunctionMetadata
from zope.component import (
    ComponentLookupError,
    getUtility,
    )
from zope.security.proxy import (
    builtin_isinstance,
    Proxy,
    ProxyFactory,
    removeSecurityProxy,
    )

from lp.app.enums import (
    InformationType,
    PROPRIETARY_INFORMATION_TYPES,
    PUBLIC_INFORMATION_TYPES,
    ServiceUsage,
    )
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.archivepublisher.interfaces.publisherconfig import IPublisherConfigSet
from lp.archiveuploader.dscfile import DSCFile
from lp.blueprints.enums import (
    NewSpecificationDefinitionStatus,
    SpecificationDefinitionStatus,
    SpecificationPriority,
    SpecificationWorkItemStatus,
    )
from lp.blueprints.interfaces.specification import ISpecificationSet
from lp.blueprints.interfaces.sprint import ISprintSet
from lp.bugs.interfaces.apportjob import IProcessApportBlobJobSource
from lp.bugs.interfaces.bug import (
    CreateBugParams,
    IBugSet,
    )
from lp.bugs.interfaces.bugtask import BugTaskStatus
from lp.bugs.interfaces.bugtracker import (
    BugTrackerType,
    IBugTrackerSet,
    )
from lp.bugs.interfaces.bugwatch import IBugWatchSet
from lp.bugs.interfaces.cve import (
    CveStatus,
    ICveSet,
    )
from lp.bugs.model.bug import FileBugData
from lp.buildmaster.enums import (
    BuildFarmJobType,
    BuildStatus,
    )
from lp.buildmaster.interfaces.builder import IBuilderSet
from lp.buildmaster.model.buildqueue import BuildQueue
from lp.code.enums import (
    BranchMergeProposalStatus,
    BranchSubscriptionNotificationLevel,
    BranchType,
    CodeImportMachineState,
    CodeImportResultStatus,
    CodeImportReviewStatus,
    CodeReviewNotificationLevel,
    RevisionControlSystems,
    )
from lp.code.errors import UnknownBranchTypeError
from lp.code.interfaces.branchmergequeue import IBranchMergeQueueSource
from lp.code.interfaces.branchnamespace import get_branch_namespace
from lp.code.interfaces.branchtarget import IBranchTarget
from lp.code.interfaces.codeimport import ICodeImportSet
from lp.code.interfaces.codeimportevent import ICodeImportEventSet
from lp.code.interfaces.codeimportmachine import ICodeImportMachineSet
from lp.code.interfaces.codeimportresult import ICodeImportResultSet
from lp.code.interfaces.linkedbranch import ICanHasLinkedBranch
from lp.code.interfaces.revision import IRevisionSet
from lp.code.interfaces.sourcepackagerecipe import (
    ISourcePackageRecipeSource,
    MINIMAL_RECIPE_TEXT,
    )
from lp.code.interfaces.sourcepackagerecipebuild import (
    ISourcePackageRecipeBuildSource,
    )
from lp.code.model.diff import (
    Diff,
    PreviewDiff,
    )
from lp.codehosting.codeimport.worker import CodeImportSourceDetails
from lp.hardwaredb.interfaces.hwdb import (
    HWSubmissionFormat,
    IHWDeviceDriverLinkSet,
    IHWSubmissionDeviceSet,
    IHWSubmissionSet,
    )
from lp.registry.enums import (
    BranchSharingPolicy,
    BugSharingPolicy,
    DistroSeriesDifferenceStatus,
    DistroSeriesDifferenceType,
    SpecificationSharingPolicy,
    TeamMembershipPolicy,
    )
from lp.registry.interfaces.accesspolicy import (
    IAccessArtifactGrantSource,
    IAccessArtifactSource,
    IAccessPolicyArtifactSource,
    IAccessPolicyGrantSource,
    IAccessPolicySource,
    )
from lp.registry.interfaces.distribution import (
    IDistribution,
    IDistributionSet,
    )
from lp.registry.interfaces.distributionmirror import (
    MirrorContent,
    MirrorSpeed,
    )
from lp.registry.interfaces.distributionsourcepackage import (
    IDistributionSourcePackage,
    )
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.distroseriesdifference import (
    IDistroSeriesDifferenceSource,
    )
from lp.registry.interfaces.distroseriesdifferencecomment import (
    IDistroSeriesDifferenceCommentSource,
    )
from lp.registry.interfaces.distroseriesparent import IDistroSeriesParentSet
from lp.registry.interfaces.gpg import IGPGKeySet
from lp.registry.interfaces.mailinglist import (
    IMailingListSet,
    MailingListStatus,
    )
from lp.registry.interfaces.mailinglistsubscription import (
    MailingListAutoSubscribePolicy,
    )
from lp.registry.interfaces.packaging import (
    IPackagingUtil,
    PackagingType,
    )
from lp.registry.interfaces.person import (
    IPerson,
    IPersonSet,
    PersonCreationRationale,
    )
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.poll import (
    IPollSet,
    PollAlgorithm,
    PollSecrecy,
    )
from lp.registry.interfaces.product import (
    IProduct,
    IProductSet,
    License,
    )
from lp.registry.interfaces.productseries import IProductSeries
from lp.registry.interfaces.projectgroup import IProjectGroupSet
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.interfaces.sourcepackage import (
    ISourcePackage,
    SourcePackageFileType,
    SourcePackageUrgency,
    )
from lp.registry.interfaces.sourcepackagename import ISourcePackageNameSet
from lp.registry.interfaces.ssh import ISSHKeySet
from lp.registry.model.commercialsubscription import CommercialSubscription
from lp.registry.model.karma import KarmaTotalCache
from lp.registry.model.milestone import Milestone
from lp.registry.model.suitesourcepackage import SuiteSourcePackage
from lp.services.config import config
from lp.services.database.constants import (
    DEFAULT,
    UTC_NOW,
    )
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    IStoreSelector,
    )
from lp.services.database.policy import MasterDatabasePolicy
from lp.services.database.sqlbase import flush_database_updates
from lp.services.gpg.interfaces import (
    GPGKeyAlgorithm,
    IGPGHandler,
    )
from lp.services.identity.interfaces.account import (
    AccountCreationRationale,
    AccountStatus,
    IAccountSet,
    )
from lp.services.identity.interfaces.emailaddress import (
    EmailAddressStatus,
    IEmailAddressSet,
    )
from lp.services.identity.model.account import Account
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.librarian.model import (
    LibraryFileAlias,
    LibraryFileContent,
    )
from lp.services.mail.signedmessage import SignedMessage
from lp.services.messages.model.message import (
    Message,
    MessageChunk,
    )
from lp.services.oauth.interfaces import IOAuthConsumerSet
from lp.services.openid.model.openididentifier import OpenIdIdentifier
from lp.services.propertycache import clear_property_cache
from lp.services.temporaryblobstorage.interfaces import (
    ITemporaryStorageManager,
    )
from lp.services.temporaryblobstorage.model import TemporaryBlobStorage
from lp.services.utils import AutoDecorate
from lp.services.webapp.interfaces import OAuthPermission
from lp.services.webapp.sorting import sorted_version_numbers
from lp.services.worlddata.interfaces.country import ICountrySet
from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.soyuz.adapters.overrides import SourceOverride
from lp.soyuz.adapters.packagelocation import PackageLocation
from lp.soyuz.enums import (
    ArchivePurpose,
    BinaryPackageFileType,
    BinaryPackageFormat,
    PackageDiffStatus,
    PackagePublishingPriority,
    PackagePublishingStatus,
    PackageUploadCustomFormat,
    PackageUploadStatus,
    )
from lp.soyuz.interfaces.archive import (
    default_name_by_purpose,
    IArchiveSet,
    )
from lp.soyuz.interfaces.archivepermission import IArchivePermissionSet
from lp.soyuz.interfaces.binarypackagebuild import IBinaryPackageBuildSet
from lp.soyuz.interfaces.binarypackagename import IBinaryPackageNameSet
from lp.soyuz.interfaces.component import (
    IComponent,
    IComponentSet,
    )
from lp.soyuz.interfaces.packagecopyjob import IPlainPackageCopyJobSource
from lp.soyuz.interfaces.packageset import IPackagesetSet
from lp.soyuz.interfaces.processor import IProcessorSet
from lp.soyuz.interfaces.publishing import IPublishingSet
from lp.soyuz.interfaces.queue import IPackageUploadSet
from lp.soyuz.interfaces.section import ISectionSet
from lp.soyuz.model.component import ComponentSelection
from lp.soyuz.model.distributionsourcepackagecache import (
    DistributionSourcePackageCache,
    )
from lp.soyuz.model.files import (
    BinaryPackageFile,
    SourcePackageReleaseFile,
    )
from lp.soyuz.model.packagediff import PackageDiff
from lp.testing import (
    admin_logged_in,
    ANONYMOUS,
    celebrity_logged_in,
    launchpadlib_for,
    login,
    login_as,
    login_person,
    person_logged_in,
    run_with_login,
    time_counter,
    with_celebrity_logged_in,
    )
from lp.testing.dbuser import dbuser
from lp.translations.enums import (
    LanguagePackType,
    RosettaImportStatus,
    )
from lp.translations.interfaces.languagepack import ILanguagePackSet
from lp.translations.interfaces.potemplate import IPOTemplateSet
from lp.translations.interfaces.side import TranslationSide
from lp.translations.interfaces.translationfileformat import (
    TranslationFileFormat,
    )
from lp.translations.interfaces.translationgroup import ITranslationGroupSet
from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    )
from lp.translations.interfaces.translationmessage import (
    RosettaTranslationOrigin,
    )
from lp.translations.interfaces.translationsperson import ITranslationsPerson
from lp.translations.interfaces.translationtemplatesbuildjob import (
    ITranslationTemplatesBuildJobSource,
    )
from lp.translations.interfaces.translator import ITranslatorSet
from lp.translations.model.translationtemplateitem import (
    TranslationTemplateItem,
    )
from lp.translations.utilities.sanitize import (
    sanitize_translations_from_webui,
    )


SPACE = ' '

DIFF = """\
=== zbqvsvrq svyr 'yvo/yc/pbqr/vagresnprf/qvss.cl'
--- yvo/yc/pbqr/vagresnprf/qvss.cl      2009-10-01 13:25:12 +0000
+++ yvo/yc/pbqr/vagresnprf/qvss.cl      2010-02-02 15:48:56 +0000
@@ -121,6 +121,10 @@
                 'Gur pbasyvpgf grkg qrfpevovat nal cngu be grkg pbasyvpgf.'),
              ernqbayl=Gehr))

+    unf_pbasyvpgf = Obby(
+        gvgyr=_('Unf pbasyvpgf'), ernqbayl=Gehr,
+        qrfpevcgvba=_('Gur cerivrjrq zretr cebqhprf pbasyvpgf.'))
+
     # Gur fpurzn sbe gur Ersrerapr trgf cngpurq va _fpurzn_pvephyne_vzcbegf.
     oenapu_zretr_cebcbfny = rkcbegrq(
         Ersrerapr(
"""


def default_master_store(func):
    """Decorator to temporarily set the default Store to the master.

    In some cases, such as in the middle of a page test story,
    we might be calling factory methods with the default Store set
    to the slave which breaks stuff. For instance, if we set an account's
    password that needs to happen on the master store and this is forced.
    However, if we then read it back the default Store has to be used.
    """

    def with_default_master_store(*args, **kw):
        try:
            store_selector = getUtility(IStoreSelector)
        except ComponentLookupError:
            # Utilities not registered. No policies.
            return func(*args, **kw)
        store_selector.push(MasterDatabasePolicy())
        try:
            return func(*args, **kw)
        finally:
            store_selector.pop()
    return mergeFunctionMetadata(func, with_default_master_store)


# We use this for default parameters where None has a specific meaning. For
# example, makeBranch(product=None) means "make a junk branch". None, because
# None means "junk branch".
_DEFAULT = object()


class GPGSigningContext:
    """A helper object to hold the fingerprint, password and mode."""

    def __init__(self, fingerprint, password='', mode=None):
        self.fingerprint = fingerprint
        self.password = password
        self.mode = mode


class ObjectFactory:
    """Factory methods for creating basic Python objects."""

    __metaclass__ = AutoDecorate(default_master_store)

    # This allocates process-wide unique integers.  We count on Python doing
    # only cooperative threading to make this safe across threads.
    _unique_int_counter = count(100000)

    def getUniqueEmailAddress(self):
        return "%s@example.com" % self.getUniqueString('email')

    def getUniqueInteger(self):
        """Return an integer unique to this factory instance.

        For each thread, this will be a series of increasing numbers, but the
        starting point will be unique per thread.
        """
        return ObjectFactory._unique_int_counter.next()

    def getUniqueHexString(self, digits=None):
        """Return a unique hexadecimal string.

        :param digits: The number of digits in the string. 'None' means you
            don't care.
        :return: A hexadecimal string, with 'a'-'f' in lower case.
        """
        hex_number = '%x' % self.getUniqueInteger()
        if digits is not None:
            hex_number = hex_number.zfill(digits)
        return hex_number

    def getUniqueString(self, prefix=None):
        """Return a string unique to this factory instance.

        The string returned will always be a valid name that can be used in
        Launchpad URLs.

        :param prefix: Used as a prefix for the unique string. If
            unspecified, generates a name starting with 'unique' and
            mentioning the calling source location.
        """
        if prefix is None:
            frame = sys._getframe(2)
            source_filename = frame.f_code.co_filename
            # Dots and dashes cause trouble with some consumers of these
            # names.
            source = (
                os.path.basename(source_filename)
                .replace('_', '-')
                .replace('.', '-'))
            if source.startswith(
                    '<doctest '):
                # Like '-<doctest xx-build-summary-txt[10]>'.
                source = (source
                    .replace('<doctest ', '')
                    .replace('[', '')
                    .replace(']>', ''))
            prefix = 'unique-from-%s-line%d' % (
                source, frame.f_lineno)
        string = "%s-%s" % (prefix, self.getUniqueInteger())
        return string

    def getUniqueUnicode(self):
        return self.getUniqueString().decode('latin-1')

    def getUniqueURL(self, scheme=None, host=None):
        """Return a URL unique to this run of the test case."""
        if scheme is None:
            scheme = 'http'
        if host is None:
            host = "%s.domain.com" % self.getUniqueString('domain')
        return '%s://%s/%s' % (scheme, host, self.getUniqueString('path'))

    def getUniqueDate(self):
        """Return a unique date since January 1 2009.

        Each date returned by this function will more recent (or further into
        the future) than the previous one.
        """
        epoch = datetime(2009, 1, 1, tzinfo=pytz.UTC)
        return epoch + timedelta(minutes=self.getUniqueInteger())

    def makeCodeImportSourceDetails(self, branch_id=None, rcstype=None,
                                    url=None, cvs_root=None, cvs_module=None,
                                    stacked_on_url=None):
        if branch_id is None:
            branch_id = self.getUniqueInteger()
        if rcstype is None:
            rcstype = 'svn'
        if rcstype in ['svn', 'bzr-svn', 'bzr']:
            assert cvs_root is cvs_module is None
            if url is None:
                url = self.getUniqueURL()
        elif rcstype == 'cvs':
            assert url is None
            if cvs_root is None:
                cvs_root = self.getUniqueString()
            if cvs_module is None:
                cvs_module = self.getUniqueString()
        elif rcstype == 'git':
            assert cvs_root is cvs_module is None
            if url is None:
                url = self.getUniqueURL(scheme='git')
        else:
            raise AssertionError("Unknown rcstype %r." % rcstype)
        return CodeImportSourceDetails(
            branch_id, rcstype, url, cvs_root, cvs_module,
            stacked_on_url=stacked_on_url)


class BareLaunchpadObjectFactory(ObjectFactory):
    """Factory methods for creating Launchpad objects.

    All the factory methods should be callable with no parameters.
    When this is done, the returned object should have unique references
    for any other required objects.
    """

    def loginAsAnyone(self, participation=None):
        """Log in as an arbitrary person.

        If you want to log in as a celebrity, including admins, see
        `lp.testing.login_celebrity`.
        """
        login(ANONYMOUS)
        person = self.makePerson()
        login_as(person, participation)
        return person

    @with_celebrity_logged_in('admin')
    def makeAdministrator(self, name=None, email=None):
        return self.makePerson(
            name=name, email=email,
            member_of=[getUtility(ILaunchpadCelebrities).admin])

    @with_celebrity_logged_in('admin')
    def makeRegistryExpert(self, name=None, email='expert@example.com'):
        return self.makePerson(
            name=name, email=email,
            member_of=[getUtility(ILaunchpadCelebrities).registry_experts])

    @with_celebrity_logged_in('admin')
    def makeCommercialAdmin(self, name=None, email=None):
        return self.makePerson(
            name=name, email=email,
            member_of=[getUtility(ILaunchpadCelebrities).commercial_admin])

    def makeCopyArchiveLocation(self, distribution=None, owner=None,
        name=None, enabled=True):
        """Create and return a new arbitrary location for copy packages."""
        copy_archive = self.makeArchive(distribution, owner, name,
                                        ArchivePurpose.COPY, enabled)

        distribution = copy_archive.distribution
        distroseries = distribution.currentseries
        pocket = PackagePublishingPocket.RELEASE

        location = PackageLocation(copy_archive, distribution, distroseries,
            pocket)
        return ProxyFactory(location)

    def makeAccount(self, displayname=None, status=AccountStatus.ACTIVE,
                    rationale=AccountCreationRationale.UNKNOWN):
        """Create and return a new Account."""
        if displayname is None:
            displayname = self.getUniqueString('displayname')
        account = getUtility(IAccountSet).new(rationale, displayname)
        removeSecurityProxy(account).status = status
        self.makeOpenIdIdentifier(account)
        return account

    def makeOpenIdIdentifier(self, account, identifier=None):
        """Attach an OpenIdIdentifier to an Account."""
        # Unfortunately, there are many tests connecting as many
        # different database users that expect to be able to create
        # working accounts using these factory methods. The stored
        # procedure provides a work around and avoids us having to
        # grant INSERT rights to these database users and avoids the
        # security problems that would cause. The stored procedure
        # ensures that there is at least one OpenId Identifier attached
        # to the account that can be used to login. If the OpenId
        # Identifier needed to be created, it will not be usable in the
        # production environments so access to execute this stored
        # procedure cannot be used to compromise accounts.
        IMasterStore(OpenIdIdentifier).execute(
            "SELECT add_test_openid_identifier(%s)", (account.id, ))

    def makeGPGKey(self, owner):
        """Give 'owner' a crappy GPG key for the purposes of testing."""
        key_id = self.getUniqueHexString(digits=8).upper()
        fingerprint = key_id + 'A' * 32
        return getUtility(IGPGKeySet).new(
            owner.id,
            keyid=key_id,
            fingerprint=fingerprint,
            keysize=self.getUniqueInteger(),
            algorithm=GPGKeyAlgorithm.R,
            active=True,
            can_encrypt=False)

    def makePerson(
        self, email=None, name=None, displayname=None, account_status=None,
        email_address_status=None, hide_email_addresses=False,
        time_zone=None, latitude=None, longitude=None, description=None,
        selfgenerated_bugnotifications=False, member_of=(), karma=None):
        """Create and return a new, arbitrary Person.

        :param email: The email address for the new person.
        :param name: The name for the new person.
        :param email_address_status: If specified, the status of the email
            address is set to the email_address_status.
        :param displayname: The display name to use for the person.
        :param hide_email_addresses: Whether or not to hide the person's email
            address(es) from other users.
        :param time_zone: This person's time zone, as a string.
        :param latitude: This person's latitude, as a float.
        :param longitude: This person's longitude, as a float.
        :param selfgenerated_bugnotifications: Receive own bugmail.
        """
        if email is None:
            email = self.getUniqueEmailAddress()
        if name is None:
            name = self.getUniqueString('person-name')
        # By default, make the email address preferred.
        if (email_address_status is None
                or email_address_status == EmailAddressStatus.VALIDATED):
            email_address_status = EmailAddressStatus.PREFERRED
        if account_status == AccountStatus.NOACCOUNT:
            email_address_status = EmailAddressStatus.NEW
        person, email = getUtility(IPersonSet).createPersonAndEmail(
            email, rationale=PersonCreationRationale.UNKNOWN, name=name,
            displayname=displayname,
            hide_email_addresses=hide_email_addresses)
        naked_person = removeSecurityProxy(person)
        if description is not None:
            naked_person.description = description

        if (time_zone is not None or latitude is not None or
            longitude is not None):
            naked_person.setLocation(latitude, longitude, time_zone, person)

        # Make sure the non-security-proxied object is not returned.
        del naked_person

        if selfgenerated_bugnotifications:
            # Set it explicitely only when True because the default
            # is False.
            person.selfgenerated_bugnotifications = True

        # To make the person someone valid in Launchpad, validate the
        # email.
        if email_address_status == EmailAddressStatus.PREFERRED:
            account = IMasterStore(Account).get(
                Account, person.accountID)
            account.status = AccountStatus.ACTIVE
            person.validateAndEnsurePreferredEmail(email)

        removeSecurityProxy(email).status = email_address_status

        once_active = (AccountStatus.DEACTIVATED, AccountStatus.SUSPENDED)
        if account_status:
            if account_status in once_active:
                removeSecurityProxy(person.account).status = (
                    AccountStatus.ACTIVE)
            removeSecurityProxy(person.account).status = account_status
        self.makeOpenIdIdentifier(person.account)

        for team in member_of:
            with person_logged_in(team.teamowner):
                team.addMember(person, team.teamowner)

        if karma is not None:
            with dbuser('karma'):
                # Give the user karma to make the user non-probationary.
                KarmaTotalCache(person=person.id, karma_total=karma)
        # Ensure updated ValidPersonCache
        flush_database_updates()
        return person

    def makePersonByName(self, first_name, set_preferred_email=True,
                         use_default_autosubscribe_policy=False):
        """Create a new person with the given first name.

        The person will be given two email addresses, with the 'long form'
        (e.g. anne.person@example.com) as the preferred address.  Return
        the new person object.

        The person will also have their mailing list auto-subscription
        policy set to 'NEVER' unless 'use_default_autosubscribe_policy' is
        set to True. (This requires the Launchpad.Edit permission).  This
        is useful for testing, where we often want precise control over
        when a person gets subscribed to a mailing list.

        :param first_name: First name of the person, capitalized.
        :type first_name: string
        :param set_preferred_email: Flag specifying whether
            <name>.person@example.com should be set as the user's
            preferred email address.
        :type set_preferred_email: bool
        :param use_default_autosubscribe_policy: Flag specifying whether
            the person's `mailing_list_auto_subscribe_policy` should be set.
        :type use_default_autosubscribe_policy: bool
        :return: The newly created person.
        :rtype: `IPerson`
        """
        variable_name = first_name.lower()
        full_name = first_name + ' Person'
        # E.g. firstname.person@example.com will be an alternative address.
        preferred_address = variable_name + '.person@example.com'
        # E.g. aperson@example.org will be the preferred address.
        alternative_address = variable_name[0] + 'person@example.org'
        person, email = getUtility(IPersonSet).createPersonAndEmail(
            preferred_address,
            PersonCreationRationale.OWNER_CREATED_LAUNCHPAD,
            name=variable_name, displayname=full_name)
        if set_preferred_email:
            # setPreferredEmail no longer activates the account
            # automatically.
            account = IMasterStore(Account).get(Account, person.accountID)
            account.reactivate("Activated by factory.makePersonByName")
            person.setPreferredEmail(email)

        if not use_default_autosubscribe_policy:
            # Shut off list auto-subscription so that we have direct control
            # over subscriptions in the doctests.
            with person_logged_in(person):
                person.mailing_list_auto_subscribe_policy = (
                    MailingListAutoSubscribePolicy.NEVER)
        account = IMasterStore(Account).get(Account, person.accountID)
        getUtility(IEmailAddressSet).new(
            alternative_address, person, EmailAddressStatus.VALIDATED)
        return person

    def makeEmail(self, address, person, email_status=None):
        """Create a new email address for a person.

        :param address: The email address to create.
        :type address: string
        :param person: The person to assign the email address to.
        :type person: `IPerson`
        :param email_status: The default status of the email address,
            if given.  If not given, `EmailAddressStatus.VALIDATED`
            will be used.
        :type email_status: `EmailAddressStatus`
        :return: The newly created email address.
        :rtype: `IEmailAddress`
        """
        if email_status is None:
            email_status = EmailAddressStatus.VALIDATED
        return getUtility(IEmailAddressSet).new(
            address, person, email_status)

    def makeTeam(self, owner=None, displayname=None, email=None, name=None,
                 description=None, icon=None, logo=None,
                 membership_policy=TeamMembershipPolicy.OPEN,
                 visibility=None, members=None):
        """Create and return a new, arbitrary Team.

        :param owner: The person or person name to use as the team's owner.
            If not given, a person will be auto-generated.
        :type owner: `IPerson` or string
        :param displayname: The team's display name.  If not given we'll use
            the auto-generated name.
        :param description: Team team's description.
        :type description string:
        :param email: The email address to use as the team's contact address.
        :type email: string
        :param icon: The team's icon.
        :param logo: The team's logo.
        :param membership_policy: The membership policy of the team.
        :type membership_policy: `TeamMembershipPolicy`
        :param visibility: The team's visibility. If it's None, the default
            (public) will be used.
        :type visibility: `PersonVisibility`
        :param members: People or teams to be added to the new team
        :type members: An iterable of objects implementing IPerson
        :return: The new team
        :rtype: `ITeam`
        """
        if owner is None:
            owner = self.makePerson()
        elif isinstance(owner, basestring):
            owner = getUtility(IPersonSet).getByName(owner)
        else:
            pass
        if name is None:
            name = self.getUniqueString('team-name')
        if displayname is None:
            displayname = SPACE.join(
                word.capitalize() for word in name.split('-'))
        team = getUtility(IPersonSet).newTeam(
            owner, name, displayname, description,
            membership_policy=membership_policy)
        naked_team = removeSecurityProxy(team)
        if visibility is not None:
            # Visibility is normally restricted to launchpad.Commercial, so
            # removing the security proxy as we don't care here.
            naked_team.visibility = visibility
            naked_team._ensurePolicies()
        if email is not None:
            removeSecurityProxy(team).setContactAddress(
                getUtility(IEmailAddressSet).new(email, team))
        if icon is not None:
            naked_team.icon = icon
        if logo is not None:
            naked_team.logo = logo
        if members is not None:
            for member in members:
                naked_team.addMember(member, owner)
        return team

    def makePoll(self, team, name, title, proposition,
                 poll_type=PollAlgorithm.SIMPLE):
        """Create a new poll which starts tomorrow and lasts for a week."""
        dateopens = datetime.now(pytz.UTC) + timedelta(days=1)
        datecloses = dateopens + timedelta(days=7)
        return getUtility(IPollSet).new(
            team, name, title, proposition, dateopens, datecloses,
            PollSecrecy.SECRET, allowspoilt=True,
            poll_type=poll_type)

    def makeTranslationGroup(self, owner=None, name=None, title=None,
                             summary=None, url=None):
        """Create a new, arbitrary `TranslationGroup`."""
        if owner is None:
            owner = self.makePerson()
        if name is None:
            name = self.getUniqueString("translationgroup")
        if title is None:
            title = self.getUniqueString("title")
        if summary is None:
            summary = self.getUniqueString("summary")
        return getUtility(ITranslationGroupSet).new(
            name, title, summary, url, owner)

    def makeTranslator(self, language_code=None, group=None, person=None,
                       license=True, language=None):
        """Create a new, arbitrary `Translator`."""
        assert language_code is None or language is None, (
            "Please specifiy only one of language_code and language.")
        if language_code is None:
            if language is None:
                language = self.makeLanguage()
            language_code = language.code
        else:
            language = getUtility(ILanguageSet).getLanguageByCode(
                language_code)
            if language is None:
                language = self.makeLanguage(language_code=language_code)

        if group is None:
            group = self.makeTranslationGroup()
        if person is None:
            person = self.makePerson()
        tx_person = ITranslationsPerson(person)
        insecure_tx_person = removeSecurityProxy(tx_person)
        insecure_tx_person.translations_relicensing_agreement = license
        return getUtility(ITranslatorSet).new(group, language, person)

    def makeMilestone(self, product=None, distribution=None,
                      productseries=None, name=None, active=True,
                      dateexpected=None, distroseries=None):
        if (product is None and distribution is None and productseries is None
            and distroseries is None):
            product = self.makeProduct()
        if distribution is None and distroseries is None:
            if productseries is not None:
                product = productseries.product
            else:
                productseries = self.makeProductSeries(product=product)
        elif distroseries is None:
            distroseries = self.makeDistroSeries(distribution=distribution)
        else:
            distribution = distroseries.distribution
        if name is None:
            name = self.getUniqueString()
        return ProxyFactory(
            Milestone(product=product, distribution=distribution,
                      productseries=productseries, distroseries=distroseries,
                      name=name, active=active, dateexpected=dateexpected))

    def makeProcessor(self, name=None, title=None, description=None,
                      restricted=False):
        """Create a new processor.

        :param name: Name of the processor
        :param title: Optional title
        :param description: Optional description
        :param restricted: If the processor is restricted.
        :return: A `IProcessor`
        """
        if name is None:
            name = self.getUniqueString()
        if title is None:
            title = "The %s processor" % name
        if description is None:
            description = "The %s processor and compatible processors" % name
        return getUtility(IProcessorSet).new(
            name, title, description, restricted)

    def makeProductRelease(self, milestone=None, product=None,
                           productseries=None):
        if milestone is None:
            milestone = self.makeMilestone(product=product,
                                           productseries=productseries)
        with person_logged_in(milestone.productseries.product.owner):
            release = milestone.createProductRelease(
                milestone.product.owner, datetime.now(pytz.UTC))
        return release

    def makeProductReleaseFile(self, signed=True,
                               product=None, productseries=None,
                               milestone=None,
                               release=None,
                               description="test file",
                               filename='test.txt'):
        signature_filename = None
        signature_content = None
        if signed:
            signature_filename = '%s.asc' % filename
            signature_content = '123'
        if release is None:
            release = self.makeProductRelease(product=product,
                                              productseries=productseries,
                                              milestone=milestone)
        with person_logged_in(release.milestone.product.owner):
            release_file = release.addReleaseFile(
                filename, 'test', 'text/plain',
                uploader=release.milestone.product.owner,
                signature_filename=signature_filename,
                signature_content=signature_content,
                description=description)
        IStore(release).flush()
        return release_file

    def makeProduct(
        self, name=None, project=None, displayname=None,
        licenses=None, owner=None, registrant=None,
        title=None, summary=None, official_malone=None,
        translations_usage=None, bug_supervisor=None, driver=None, icon=None,
        bug_sharing_policy=None, branch_sharing_policy=None,
        specification_sharing_policy=None, information_type=None,
        answers_usage=None):
        """Create and return a new, arbitrary Product."""
        if owner is None:
            owner = self.makePerson()
        if name is None:
            name = self.getUniqueString('product-name')
        if displayname is None:
            if name is None:
                displayname = self.getUniqueString('displayname')
            else:
                displayname = name.capitalize()
        if licenses is None:
            if (information_type in PROPRIETARY_INFORMATION_TYPES or
                (bug_sharing_policy is not None and
                 bug_sharing_policy != BugSharingPolicy.PUBLIC) or
                (branch_sharing_policy is not None and
                 branch_sharing_policy != BranchSharingPolicy.PUBLIC) or
                (specification_sharing_policy is not None and
                 specification_sharing_policy !=
                 SpecificationSharingPolicy.PUBLIC)
                ):
                licenses = [License.OTHER_PROPRIETARY]
            else:
                licenses = [License.GNU_GPL_V2]
        if title is None:
            title = self.getUniqueString('title')
        if summary is None:
            summary = self.getUniqueString('summary')
        admins = getUtility(ILaunchpadCelebrities).admin
        with person_logged_in(admins.teamowner):
            product = getUtility(IProductSet).createProduct(
                owner,
                name,
                displayname,
                title,
                summary,
                self.getUniqueString('description'),
                licenses=licenses,
                project=project,
                registrant=registrant,
                icon=icon,
                information_type=information_type)
        naked_product = removeSecurityProxy(product)
        if official_malone is not None:
            naked_product.official_malone = official_malone
        if translations_usage is not None:
            naked_product.translations_usage = translations_usage
        if answers_usage is not None:
            naked_product.answers_usage = answers_usage
        if bug_supervisor is not None:
            naked_product.bug_supervisor = bug_supervisor
        if driver is not None:
            naked_product.driver = driver
        if branch_sharing_policy:
            naked_product.setBranchSharingPolicy(branch_sharing_policy)
        if bug_sharing_policy:
            naked_product.setBugSharingPolicy(bug_sharing_policy)
        if specification_sharing_policy:
            naked_product.setSpecificationSharingPolicy(
                specification_sharing_policy)
        return product

    def makeProductSeries(self, product=None, name=None, owner=None,
                          summary=None, date_created=None, branch=None):
        """Create a new, arbitrary ProductSeries.

        :param branch: If supplied, the branch to set as
            ProductSeries.branch.
        :param date_created: If supplied, the date the series is created.
        :param name: If supplied, the name of the series.
        :param owner: If supplied, the owner of the series.
        :param product: If supplied, the series is created for this product.
            Otherwise, a new product is created.
        :param summary: If supplied, the product series summary.
        """
        if product is None:
            product = self.makeProduct()
        if owner is None:
            owner = removeSecurityProxy(product).owner
        if name is None:
            name = self.getUniqueString()
        if summary is None:
            summary = self.getUniqueString()
        # We don't want to login() as the person used to create the product,
        # so we remove the security proxy before creating the series.
        naked_product = removeSecurityProxy(product)
        series = naked_product.newSeries(
            owner=owner, name=name, summary=summary, branch=branch)
        if date_created is not None:
            series.datecreated = date_created
        return ProxyFactory(series)

    def makeProject(self, name=None, displayname=None, title=None,
                    homepageurl=None, summary=None, owner=None, driver=None,
                    description=None):
        """Create and return a new, arbitrary ProjectGroup."""
        if owner is None:
            owner = self.makePerson()
        if name is None:
            name = self.getUniqueString('project-name')
        if displayname is None:
            displayname = self.getUniqueString('displayname')
        if summary is None:
            summary = self.getUniqueString('summary')
        if description is None:
            description = self.getUniqueString('description')
        if title is None:
            title = self.getUniqueString('title')
        project = getUtility(IProjectGroupSet).new(
            name=name,
            displayname=displayname,
            title=title,
            homepageurl=homepageurl,
            summary=summary,
            description=description,
            owner=owner)
        if driver is not None:
            removeSecurityProxy(project).driver = driver
        return project

    def makeSprint(self, title=None, name=None):
        """Make a sprint."""
        if title is None:
            title = self.getUniqueString('title')
        owner = self.makePerson()
        if name is None:
            name = self.getUniqueString('name')
        time_starts = datetime(2009, 1, 1, tzinfo=pytz.UTC)
        time_ends = datetime(2009, 1, 2, tzinfo=pytz.UTC)
        time_zone = 'UTC'
        summary = self.getUniqueString('summary')
        return getUtility(ISprintSet).new(
            owner=owner, name=name, title=title, time_zone=time_zone,
            time_starts=time_starts, time_ends=time_ends, summary=summary)

    def makeStackedOnBranchChain(self, depth=5, **kwargs):
        branch = None
        for i in xrange(depth):
            branch = self.makeAnyBranch(stacked_on=branch, **kwargs)
        return branch

    def makeBranch(self, branch_type=None, owner=None,
                   name=None, product=_DEFAULT, url=_DEFAULT, registrant=None,
                   information_type=None, stacked_on=None,
                   sourcepackage=None, reviewer=None, **optional_branch_args):
        """Create and return a new, arbitrary Branch of the given type.

        Any parameters for `IBranchNamespace.createBranch` can be specified to
        override the default ones.
        """
        if branch_type is None:
            branch_type = BranchType.HOSTED
        if owner is None:
            owner = self.makePerson()
        if name is None:
            name = self.getUniqueString('branch')

        if sourcepackage is None:
            if product is _DEFAULT:
                product = self.makeProduct()
            sourcepackagename = None
            distroseries = None
        else:
            assert product is _DEFAULT, (
                "Passed source package AND product details")
            product = None
            sourcepackagename = sourcepackage.sourcepackagename
            distroseries = sourcepackage.distroseries

        if registrant is None:
            if owner.is_team:
                registrant = removeSecurityProxy(owner).teamowner
            else:
                registrant = owner

        if branch_type in (BranchType.HOSTED, BranchType.IMPORTED):
            url = None
        elif branch_type in (BranchType.MIRRORED, BranchType.REMOTE):
            if url is _DEFAULT:
                url = self.getUniqueURL()
        else:
            raise UnknownBranchTypeError(
                'Unrecognized branch type: %r' % (branch_type, ))

        namespace = get_branch_namespace(
            owner, product=product, distroseries=distroseries,
            sourcepackagename=sourcepackagename)
        branch = namespace.createBranch(
            branch_type=branch_type, name=name, registrant=registrant,
            url=url, **optional_branch_args)
        naked_branch = removeSecurityProxy(branch)
        if information_type is not None:
            naked_branch.transitionToInformationType(
                information_type, registrant, verify_policy=False)
        if stacked_on is not None:
            naked_branch.branchChanged(
                removeSecurityProxy(stacked_on).unique_name, 'rev1', None,
                None, None)
        if reviewer is not None:
            naked_branch.reviewer = reviewer
        return branch

    def makePackagingLink(self, productseries=None, sourcepackagename=None,
                          distroseries=None, packaging_type=None, owner=None,
                          sourcepackage=None, in_ubuntu=False):
        assert sourcepackage is None or (
            distroseries is None and sourcepackagename is None), (
            "Specify either a sourcepackage or a "
            "distroseries/sourcepackagename pair")
        if productseries is None:
            productseries = self.makeProduct().development_focus
        if sourcepackage is not None:
            distroseries = sourcepackage.distroseries
            sourcepackagename = sourcepackage.sourcepackagename
        else:
            make_sourcepackagename = (
                sourcepackagename is None or
                isinstance(sourcepackagename, str))
            if make_sourcepackagename:
                sourcepackagename = self.makeSourcePackageName(
                    sourcepackagename)
            if distroseries is None:
                if in_ubuntu:
                    distroseries = self.makeUbuntuDistroSeries()
                else:
                    distroseries = self.makeDistroSeries()
        if packaging_type is None:
            packaging_type = PackagingType.PRIME
        if owner is None:
            owner = self.makePerson()
        return getUtility(IPackagingUtil).createPackaging(
            productseries=productseries,
            sourcepackagename=sourcepackagename,
            distroseries=distroseries,
            packaging=packaging_type,
            owner=owner)

    def makePackageBranch(self, sourcepackage=None, distroseries=None,
                          sourcepackagename=None, **kwargs):
        """Make a package branch on an arbitrary package.

        See `makeBranch` for more information on arguments.

        You can pass in either `sourcepackage` or one or both of
        `distroseries` and `sourcepackagename`, but not combinations or all of
        them.
        """
        assert not(sourcepackage is not None and distroseries is not None), (
            "Don't pass in both sourcepackage and distroseries")
        assert not(sourcepackage is not None
                   and sourcepackagename is not None), (
            "Don't pass in both sourcepackage and sourcepackagename")
        if sourcepackage is None:
            sourcepackage = self.makeSourcePackage(
                sourcepackagename=sourcepackagename,
                distroseries=distroseries)
        return self.makeBranch(sourcepackage=sourcepackage, **kwargs)

    def makePersonalBranch(self, owner=None, **kwargs):
        """Make a personal branch on an arbitrary person.

        See `makeBranch` for more information on arguments.
        """
        if owner is None:
            owner = self.makePerson()
        return self.makeBranch(
            owner=owner, product=None, sourcepackage=None, **kwargs)

    def makeProductBranch(self, product=None, **kwargs):
        """Make a product branch on an arbitrary product.

        See `makeBranch` for more information on arguments.
        """
        if product is None:
            product = self.makeProduct()
        return self.makeBranch(product=product, **kwargs)

    def makeAnyBranch(self, **kwargs):
        """Make a branch without caring about its container.

        See `makeBranch` for more information on arguments.
        """
        return self.makeProductBranch(**kwargs)

    def makeBranchTargetBranch(self, target, branch_type=BranchType.HOSTED,
                               name=None, owner=None, creator=None):
        """Create a branch in a BranchTarget."""
        if name is None:
            name = self.getUniqueString('branch')
        if owner is None:
            owner = self.makePerson()
        if creator is None:
            creator = owner
        namespace = target.getNamespace(owner)
        return namespace.createBranch(branch_type, name, creator)

    def makeBranchMergeQueue(self, registrant=None, owner=None, name=None,
                             description=None, configuration=None,
                             branches=None):
        """Create a BranchMergeQueue."""
        if name is None:
            name = unicode(self.getUniqueString('queue'))
        if owner is None:
            owner = self.makePerson()
        if registrant is None:
            registrant = self.makePerson()
        if description is None:
            description = unicode(self.getUniqueString('queue-description'))
        if configuration is None:
            configuration = unicode(simplejson.dumps({
                self.getUniqueString('key'): self.getUniqueString('value')}))

        queue = getUtility(IBranchMergeQueueSource).new(
            name, owner, registrant, description, configuration, branches)
        return queue

    def makeRelatedBranchesForSourcePackage(self, sourcepackage=None,
                                            **kwargs):
        """Create some branches associated with a sourcepackage."""

        reference_branch = self.makePackageBranch(sourcepackage=sourcepackage)
        return self.makeRelatedBranches(
                reference_branch=reference_branch, **kwargs)

    def makeRelatedBranchesForProduct(self, product=None, **kwargs):
        """Create some branches associated with a product."""

        reference_branch = self.makeProductBranch(product=product)
        return self.makeRelatedBranches(
                reference_branch=reference_branch, **kwargs)

    def makeRelatedBranches(self, reference_branch=None,
                            with_series_branches=True,
                            with_package_branches=True,
                            with_private_branches=False):
        """Create some branches associated with a reference branch.
        The other branches are:
          - series branches: a set of branches associated with product
            series of the same product as the reference branch.
          - package branches: a set of branches associated with packagesource
            entities of the same product as the reference branch or the same
            sourcepackage depending on what type of branch it is.

        If no reference branch is supplied, create one.

        Returns: a tuple consisting of
        (reference_branch, related_series_branches, related_package_branches)

        """
        related_series_branch_info = []
        related_package_branch_info = []
        # Make the base_branch if required and find the product if one exists.
        naked_product = None
        if reference_branch is None:
            naked_product = removeSecurityProxy(self.makeProduct())
            # Create the 'source' branch ie the base branch of a recipe.
            reference_branch = self.makeProductBranch(
                                            name="reference_branch",
                                            product=naked_product)
        elif reference_branch.product is not None:
            naked_product = removeSecurityProxy(reference_branch.product)

        related_branch_owner = self.makePerson()
        # Only branches related to products have related series branches.
        if with_series_branches and naked_product is not None:
            series_branch_info = []

            # Add some product series
            def makeSeriesBranch(name, information_type):
                branch = self.makeBranch(
                    name=name,
                    product=naked_product, owner=related_branch_owner,
                    information_type=information_type)
                series = self.makeProductSeries(
                    product=naked_product, branch=branch)
                return branch, series
            for x in range(4):
                information_type = InformationType.PUBLIC
                if x == 0 and with_private_branches:
                    information_type = InformationType.USERDATA
                (branch, series) = makeSeriesBranch(
                        ("series_branch_%s" % x), information_type)
                if information_type == InformationType.PUBLIC:
                    series_branch_info.append((branch, series))

            # Sort them
            related_series_branch_info = sorted_version_numbers(
                    series_branch_info, key=lambda branch_info: (
                        getattr(branch_info[1], 'name')))

            # Add a development branch at the start of the list.
            naked_product.development_focus.name = 'trunk'
            devel_branch = self.makeProductBranch(
                product=naked_product, name='trunk_branch',
                owner=related_branch_owner)
            linked_branch = ICanHasLinkedBranch(naked_product)
            linked_branch.setBranch(devel_branch)
            related_series_branch_info.insert(0,
                    (devel_branch, naked_product.development_focus))

        if with_package_branches:
            # Create related package branches if the base_branch is
            # associated with a product.
            if naked_product is not None:

                def makePackageBranch(name, information_type):
                    distro = self.makeDistribution()
                    distroseries = self.makeDistroSeries(
                        distribution=distro)
                    sourcepackagename = self.makeSourcePackageName()

                    suitesourcepackage = self.makeSuiteSourcePackage(
                        sourcepackagename=sourcepackagename,
                        distroseries=distroseries,
                        pocket=PackagePublishingPocket.RELEASE)
                    naked_sourcepackage = removeSecurityProxy(
                        suitesourcepackage)

                    branch = self.makePackageBranch(
                        name=name, owner=related_branch_owner,
                        sourcepackagename=sourcepackagename,
                        distroseries=distroseries,
                        information_type=information_type)
                    linked_branch = ICanHasLinkedBranch(naked_sourcepackage)
                    with celebrity_logged_in('admin'):
                        linked_branch.setBranch(branch, related_branch_owner)

                    series = self.makeProductSeries(product=naked_product)
                    self.makePackagingLink(
                        distroseries=distroseries, productseries=series,
                        sourcepackagename=sourcepackagename)
                    return branch, distroseries

                for x in range(5):
                    information_type = InformationType.PUBLIC
                    if x == 0 and with_private_branches:
                        information_type = InformationType.USERDATA
                    branch, distroseries = makePackageBranch(
                            ("product_package_branch_%s" % x),
                            information_type)
                    if information_type == InformationType.PUBLIC:
                        related_package_branch_info.append(
                                (branch, distroseries))

            # Create related package branches if the base_branch is
            # associated with a sourcepackage.
            if reference_branch.sourcepackage is not None:
                distroseries = reference_branch.sourcepackage.distroseries
                for pocket in [
                        PackagePublishingPocket.RELEASE,
                        PackagePublishingPocket.UPDATES,
                        ]:
                    branch = self.makePackageBranch(
                            name="package_branch_%s" % pocket.name,
                            distroseries=distroseries)
                    with celebrity_logged_in('admin'):
                        reference_branch.sourcepackage.setBranch(
                            pocket, branch,
                            related_branch_owner)

                    related_package_branch_info.append(
                            (branch, distroseries))

            related_package_branch_info = sorted_version_numbers(
                    related_package_branch_info, key=lambda branch_info: (
                        getattr(branch_info[1], 'name')))

        return (
            reference_branch,
            related_series_branch_info,
            related_package_branch_info)

    def enableDefaultStackingForProduct(self, product, branch=None):
        """Give 'product' a default stacked-on branch.

        :param product: The product to give a default stacked-on branch to.
        :param branch: The branch that should be the default stacked-on
            branch.  If not supplied, a fresh branch will be created.
        """
        if branch is None:
            branch = self.makeBranch(product=product)
        # We just remove the security proxies to be able to change the objects
        # here.
        removeSecurityProxy(branch).branchChanged(
            '', 'rev1', None, None, None)
        naked_series = removeSecurityProxy(product.development_focus)
        naked_series.branch = branch
        return branch

    def enableDefaultStackingForPackage(self, package, branch):
        """Give 'package' a default stacked-on branch.

        :param package: The package to give a default stacked-on branch to.
        :param branch: The branch that should be the default stacked-on
            branch.
        """
        # We just remove the security proxies to be able to change the branch
        # here.
        removeSecurityProxy(branch).branchChanged(
            '', 'rev1', None, None, None)
        with person_logged_in(package.distribution.owner):
            package.development_version.setBranch(
                PackagePublishingPocket.RELEASE, branch,
                package.distribution.owner)
        return branch

    def makeBranchMergeProposal(self, target_branch=None, registrant=None,
                                set_state=None, prerequisite_branch=None,
                                product=None, initial_comment=None,
                                source_branch=None, date_created=None,
                                description=None, reviewer=None,
                                merged_revno=None):
        """Create a proposal to merge based on anonymous branches."""
        if target_branch is not None:
            target_branch = removeSecurityProxy(target_branch)
            target = target_branch.target
        elif source_branch is not None:
            target = source_branch.target
        elif prerequisite_branch is not None:
            target = prerequisite_branch.target
        else:
            # Create a target product branch, and use that target.  This is
            # needed to make sure we get a branch target that has the needed
            # security proxy.
            target_branch = self.makeProductBranch(product)
            target = target_branch.target

        # Fall back to initial_comment for description.
        if description is None:
            description = initial_comment

        if target_branch is None:
            target_branch = self.makeBranchTargetBranch(target)
        if source_branch is None:
            source_branch = self.makeBranchTargetBranch(target)
        if registrant is None:
            registrant = self.makePerson()
        review_requests = []
        if reviewer is not None:
            review_requests.append((reviewer, None))
        proposal = source_branch.addLandingTarget(
            registrant, target_branch, review_requests=review_requests,
            prerequisite_branch=prerequisite_branch, description=description,
            date_created=date_created)

        unsafe_proposal = removeSecurityProxy(proposal)
        unsafe_proposal.merged_revno = merged_revno
        if (set_state is None or
            set_state == BranchMergeProposalStatus.WORK_IN_PROGRESS):
            # The initial state is work in progress, so do nothing.
            pass
        elif set_state == BranchMergeProposalStatus.NEEDS_REVIEW:
            unsafe_proposal.requestReview()
        elif set_state == BranchMergeProposalStatus.CODE_APPROVED:
            unsafe_proposal.approveBranch(
                proposal.target_branch.owner, 'some_revision')
        elif set_state == BranchMergeProposalStatus.REJECTED:
            unsafe_proposal.rejectBranch(
                proposal.target_branch.owner, 'some_revision')
        elif set_state == BranchMergeProposalStatus.MERGED:
            unsafe_proposal.markAsMerged()
        elif set_state == BranchMergeProposalStatus.MERGE_FAILED:
            unsafe_proposal.setStatus(set_state, proposal.target_branch.owner)
        elif set_state == BranchMergeProposalStatus.QUEUED:
            unsafe_proposal.commit_message = self.getUniqueString(
                'commit message')
            unsafe_proposal.enqueue(
                proposal.target_branch.owner, 'some_revision')
        elif set_state == BranchMergeProposalStatus.SUPERSEDED:
            unsafe_proposal.resubmit(proposal.registrant)
        else:
            raise AssertionError('Unknown status: %s' % set_state)

        return proposal

    def makeBranchSubscription(self, branch=None, person=None,
                               subscribed_by=None):
        """Create a BranchSubscription."""
        if branch is None:
            branch = self.makeBranch()
        if person is None:
            person = self.makePerson()
        if subscribed_by is None:
            subscribed_by = person
        return branch.subscribe(removeSecurityProxy(person),
            BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.NOEMAIL, subscribed_by)

    def makeDiff(self, diff_text=DIFF):
        return ProxyFactory(
            Diff.fromFile(StringIO(diff_text), len(diff_text)))

    def makePreviewDiff(self, conflicts=u'', merge_proposal=None,
                        date_created=None):
        diff = self.makeDiff()
        if merge_proposal is None:
            merge_proposal = self.makeBranchMergeProposal()
        preview_diff = PreviewDiff()
        preview_diff.branch_merge_proposal = merge_proposal
        preview_diff.conflicts = conflicts
        preview_diff.diff = diff
        preview_diff.source_revision_id = self.getUniqueUnicode()
        preview_diff.target_revision_id = self.getUniqueUnicode()
        if date_created:
            preview_diff.date_created = date_created
        return preview_diff

    def makeIncrementalDiff(self, merge_proposal=None, old_revision=None,
                            new_revision=None):
        diff = self.makeDiff()
        if merge_proposal is None:
            source_branch = self.makeBranch()
        else:
            source_branch = merge_proposal.source_branch

        def make_revision(parent=None):
            sequence = source_branch.revision_history.count() + 1
            if parent is None:
                parent_ids = []
            else:
                parent_ids = [parent.revision_id]
            branch_revision = self.makeBranchRevision(
                source_branch, sequence=sequence,
                revision_date=self.getUniqueDate(), parent_ids=parent_ids)
            return branch_revision.revision
        if old_revision is None:
            old_revision = make_revision()
        if merge_proposal is None:
            merge_proposal = self.makeBranchMergeProposal(
                date_created=self.getUniqueDate(),
                source_branch=source_branch)
        if new_revision is None:
            new_revision = make_revision(old_revision)
        return merge_proposal.generateIncrementalDiff(
            old_revision, new_revision, diff)

    def makeBzrRevision(self, revision_id=None, parent_ids=None, props=None):
        if revision_id is None:
            revision_id = self.getUniqueString('revision-id')
        if parent_ids is None:
            parent_ids = []
        return BzrRevision(
            message=self.getUniqueString('message'),
            revision_id=revision_id,
            committer=self.getUniqueString('committer'),
            parent_ids=parent_ids,
            timestamp=0, timezone=0, properties=props)

    def makeRevision(self, author=None, revision_date=None, parent_ids=None,
                     rev_id=None, log_body=None, date_created=None):
        """Create a single `Revision`."""
        if author is None:
            author = self.getUniqueString('author')
        elif IPerson.providedBy(author):
            author = removeSecurityProxy(author).preferredemail.email
        if revision_date is None:
            revision_date = datetime.now(pytz.UTC)
        if parent_ids is None:
            parent_ids = []
        if rev_id is None:
            rev_id = self.getUniqueString('revision-id')
        if log_body is None:
            log_body = self.getUniqueString('log-body')
        return getUtility(IRevisionSet).new(
            revision_id=rev_id, log_body=log_body,
            revision_date=revision_date, revision_author=author,
            parent_ids=parent_ids, properties={},
            _date_created=date_created)

    def makeRevisionsForBranch(self, branch, count=5, author=None,
                               date_generator=None):
        """Add `count` revisions to the revision history of `branch`.

        :param branch: The branch to add the revisions to.
        :param count: The number of revisions to add.
        :param author: A string for the author name.
        :param date_generator: A `time_counter` instance, defaults to starting
                               from 1-Jan-2007 if not set.
        """
        if date_generator is None:
            date_generator = time_counter(
                datetime(2007, 1, 1, tzinfo=pytz.UTC),
                delta=timedelta(days=1))
        sequence = branch.revision_count
        parent = branch.getTipRevision()
        if parent is None:
            parent_ids = []
        else:
            parent_ids = [parent.revision_id]

        revision_set = getUtility(IRevisionSet)
        if author is None:
            author = self.getUniqueString('author')
        for index in range(count):
            revision = revision_set.new(
                revision_id=self.getUniqueString('revision-id'),
                log_body=self.getUniqueString('log-body'),
                revision_date=date_generator.next(),
                revision_author=author,
                parent_ids=parent_ids,
                properties={})
            sequence += 1
            branch.createBranchRevision(sequence, revision)
            parent = revision
            parent_ids = [parent.revision_id]
        if branch.branch_type not in (BranchType.REMOTE, BranchType.HOSTED):
            branch.startMirroring()
        removeSecurityProxy(branch).branchChanged(
            '', parent.revision_id, None, None, None)
        branch.updateScannedDetails(parent, sequence)

    def makeBranchRevision(self, branch=None, revision_id=None, sequence=None,
                           parent_ids=None, revision_date=None):
        if branch is None:
            branch = self.makeBranch()
        else:
            branch = removeSecurityProxy(branch)
        revision = self.makeRevision(
            rev_id=revision_id, parent_ids=parent_ids,
            revision_date=revision_date)
        return branch.createBranchRevision(sequence, revision)

    def makeBug(self, target=None, owner=None, bug_watch_url=None,
                information_type=None, date_closed=None, title=None,
                date_created=None, description=None, comment=None,
                status=None, milestone=None, series=None, tags=None):
        """Create and return a new, arbitrary Bug.

        The bug returned uses default values where possible. See
        `IBugSet.new` for more information.

        :param target: The initial bug target. If not specified, falls
            back to the milestone target, then the series target, then a
            new product.
        :param owner: The reporter of the bug. If not set, one is created.
        :param bug_watch_url: If specified, create a bug watch pointing
            to this URL.
        :param milestone: If set, the milestone.target must match the
            target parameter's pillar.
        :param series: If set, the series's pillar must match the target
            parameter's.
        :param tags: If set, the tags to be added with the bug.
        """
        if target is None:
            if milestone is not None:
                target = milestone.target
            elif series is not None:
                target = series.pillar
            else:
                target = self.makeProduct()
                if information_type == InformationType.PROPRIETARY:
                    self.makeAccessPolicy(pillar=target)
        if IDistributionSourcePackage.providedBy(target):
            self.makeSourcePackagePublishingHistory(
                distroseries=target.distribution.currentseries,
                sourcepackagename=target.sourcepackagename)
        if owner is None:
            owner = self.makePerson()
        if title is None:
            title = self.getUniqueString('bug-title')
        if comment is None:
            comment = self.getUniqueString()
        create_bug_params = CreateBugParams(
            owner, title, comment=comment, information_type=information_type,
            datecreated=date_created, description=description,
            status=status, tags=tags, target=target)
        bug = getUtility(IBugSet).createBug(create_bug_params)
        if bug_watch_url is not None:
            # fromText() creates a bug watch associated with the bug.
            with person_logged_in(owner):
                getUtility(IBugWatchSet).fromText(bug_watch_url, bug, owner)
        bugtask = removeSecurityProxy(bug).default_bugtask
        if date_closed is not None:
            with person_logged_in(owner):
                bugtask.transitionToStatus(
                    BugTaskStatus.FIXRELEASED, owner, when=date_closed)
        if milestone is not None:
            with person_logged_in(owner):
                bugtask.transitionToMilestone(
                    milestone, milestone.target.owner)
        if series is not None:
            with person_logged_in(owner):
                task = bug.addTask(owner, series)
                task.transitionToStatus(status, owner)

        return bug

    def makeBugTask(self, bug=None, target=None, owner=None, publish=True):
        """Create and return a bug task.

        If the bug is already targeted to the given target, the existing
        bug task is returned.

        Private (and soon all) bugs cannot affect multiple projects
        so we ensure that if a bug has not been specified and one is
        created, it is for the same pillar as that of the specified target.

        :param bug: The `IBug` the bug tasks should be part of. If None,
            one will be created.
        :param target: The `IBugTarget`, to which the bug will be
            targeted to.
        """

        # Find and return the existing target if one exists.
        if bug is not None and target is not None:
            existing_bugtask = removeSecurityProxy(bug).getBugTask(target)
            if existing_bugtask is not None:
                return existing_bugtask

        # If we are adding a task to an existing bug, and no target is
        # is specified, we use the same pillar as already exists to ensure
        # that we don't end up with a bug affecting multiple projects.
        if target is None:
            default_bugtask = bug and removeSecurityProxy(bug.default_bugtask)
            if default_bugtask is not None:
                existing_pillar = default_bugtask.pillar
                if IProduct.providedBy(existing_pillar):
                    target = self.makeProductSeries(product=existing_pillar)
                elif IDistribution.providedBy(existing_pillar):
                    target = self.makeDistroSeries(
                        distribution=existing_pillar)
            if target is None:
                target = self.makeProduct()

        prerequisite_target = None
        if IProductSeries.providedBy(target):
            # We can't have a series task without a product task.
            prerequisite_target = target.product
        if IDistroSeries.providedBy(target):
            # We can't have a series task without a distribution task.
            prerequisite_target = target.distribution
        if ISourcePackage.providedBy(target):
            # We can't have a series task without a distribution task.
            prerequisite_target = target.distribution_sourcepackage
            if publish:
                self.makeSourcePackagePublishingHistory(
                    distroseries=target.distroseries,
                    sourcepackagename=target.sourcepackagename)
        if IDistributionSourcePackage.providedBy(target):
            if publish:
                self.makeSourcePackagePublishingHistory(
                    distroseries=target.distribution.currentseries,
                    sourcepackagename=target.sourcepackagename)
        if prerequisite_target is not None:
            prerequisite = bug and removeSecurityProxy(bug).getBugTask(
                prerequisite_target)
            if prerequisite is None:
                prerequisite = self.makeBugTask(
                    bug, prerequisite_target, publish=publish)
                bug = prerequisite.bug

        if bug is None:
            bug = self.makeBug()

        if owner is None:
            owner = self.makePerson()
        return removeSecurityProxy(bug).addTask(
            owner, removeSecurityProxy(target))

    def makeBugNomination(self, bug=None, target=None):
        """Create and return a BugNomination.

        Will create a non-series task if it does not already exist.

        :param bug: The `IBug` the nomination should be for. If None,
            one will be created.
        :param target: The `IProductSeries`, `IDistroSeries` or
            `ISourcePackage` to nominate for.
        """
        if ISourcePackage.providedBy(target):
            non_series = target.distribution_sourcepackage
            series = target.distroseries
        else:
            non_series = target.parent
            series = target
        with celebrity_logged_in('admin'):
            bug = self.makeBugTask(bug=bug, target=non_series).bug
            nomination = bug.addNomination(
                getUtility(ILaunchpadCelebrities).admin, series)
        return nomination

    def makeBugTracker(self, base_url=None, bugtrackertype=None, title=None,
                       name=None):
        """Make a new bug tracker."""
        owner = self.makePerson()

        if base_url is None:
            base_url = 'http://%s.example.com/' % self.getUniqueString()
        if bugtrackertype is None:
            bugtrackertype = BugTrackerType.BUGZILLA

        return getUtility(IBugTrackerSet).ensureBugTracker(
            base_url, owner, bugtrackertype, title=title, name=name)

    def makeBugTrackerWithWatches(self, base_url=None, count=2):
        """Make a new bug tracker with some watches."""
        bug_tracker = self.makeBugTracker(base_url=base_url)
        bug_watches = [
            self.makeBugWatch(bugtracker=bug_tracker)
            for i in range(count)]
        return (bug_tracker, bug_watches)

    def makeBugTrackerComponentGroup(self, name=None, bug_tracker=None):
        """Make a new bug tracker component group."""
        if name is None:
            name = self.getUniqueUnicode()
        if bug_tracker is None:
            bug_tracker = self.makeBugTracker()

        component_group = bug_tracker.addRemoteComponentGroup(name)
        return component_group

    def makeBugTrackerComponent(self, name=None, component_group=None,
                                custom=None):
        """Make a new bug tracker component."""
        if name is None:
            name = self.getUniqueUnicode()
        if component_group is None:
            component_group = self.makeBugTrackerComponentGroup()
        if custom is None:
            custom = False
        if custom:
            component = component_group.addCustomComponent(name)
        else:
            component = component_group.addComponent(name)
        return component

    def makeBugWatch(self, remote_bug=None, bugtracker=None, bug=None,
                     owner=None, bug_task=None):
        """Make a new bug watch."""
        if remote_bug is None:
            remote_bug = self.getUniqueInteger()

        if bugtracker is None:
            bugtracker = self.makeBugTracker()

        if bug_task is not None:
            # If someone passes a value for bug *and* a value for
            # bug_task then the bug value will get clobbered, but that
            # doesn't matter since the bug should be the one that the
            # bug task belongs to anyway (unless they're having a crazy
            # moment, in which case we're saving them from themselves).
            bug = bug_task.bug
        elif bug is None:
            bug = self.makeBug()

        if owner is None:
            owner = self.makePerson()

        bug_watch = getUtility(IBugWatchSet).createBugWatch(
            bug, owner, bugtracker, str(remote_bug))
        if bug_task is not None:
            bug_task.bugwatch = bug_watch
        removeSecurityProxy(bug_watch).next_check = (
            datetime.now(pytz.timezone('UTC')))
        return bug_watch

    def makeBugComment(self, bug=None, owner=None, subject=None, body=None,
                       bug_watch=None):
        """Create and return a new bug comment.

        :param bug: An `IBug` or a bug ID or name, or None, in which
            case a new bug is created.
        :param owner: An `IPerson`, or None, in which case a new
            person is created.
        :param subject: An `IMessage` or a string, or None, in which
            case a new message will be generated.
        :param body: An `IMessage` or a string, or None, in which
            case a new message will be generated.
        :param bug_watch: An `IBugWatch`, which will be used to set the
            new comment's bugwatch attribute.
        :return: An `IBugMessage`.
        """
        if bug is None:
            bug = self.makeBug()
        elif isinstance(bug, (int, long, basestring)):
            bug = getUtility(IBugSet).getByNameOrID(str(bug))
        if owner is None:
            owner = self.makePerson()
        if subject is None:
            subject = self.getUniqueString()
        if body is None:
            body = self.getUniqueString()
        with person_logged_in(owner):
            return bug.newMessage(owner=owner, subject=subject, content=body,
                                  parent=None, bugwatch=bug_watch,
                                  remote_comment_id=None)

    def makeBugAttachment(self, bug=None, owner=None, data=None,
                          comment=None, filename=None, content_type=None,
                          description=None, is_patch=_DEFAULT):
        """Create and return a new bug attachment.

        :param bug: An `IBug` or a bug ID or name, or None, in which
            case a new bug is created.
        :param owner: An `IPerson`, or None, in which case a new
            person is created.
        :param data: A file-like object or a string, or None, in which
            case a unique string will be used.
        :param comment: An `IMessage` or a string, or None, in which
            case a new message will be generated.
        :param filename: A string, or None, in which case a unique
            string will be used.
        :param content_type: The MIME-type of this file.
        :param description: The description of the attachment.
        :param is_patch: If true, this attachment is a patch.
        :return: An `IBugAttachment`.
        """
        if bug is None:
            bug = self.makeBug()
        elif isinstance(bug, (int, long, basestring)):
            bug = getUtility(IBugSet).getByNameOrID(str(bug))
        if owner is None:
            owner = self.makePerson()
        if data is None:
            data = self.getUniqueString()
        if description is None:
            description = self.getUniqueString()
        if comment is None:
            comment = self.getUniqueString()
        if filename is None:
            filename = self.getUniqueString()
        # If the default value of is_patch when creating a new
        # BugAttachment should ever change, we don't want to interfere
        # with that.  So, we only override it if our caller explicitly
        # passed it.
        other_params = {}
        if is_patch is not _DEFAULT:
            other_params['is_patch'] = is_patch
        return bug.addAttachment(
            owner, data, comment, filename, content_type=content_type,
            description=description, **other_params)

    def makeSignedMessage(self, msgid=None, body=None, subject=None,
            attachment_contents=None, force_transfer_encoding=False,
            email_address=None, signing_context=None, to_address=None):
        """Return an ISignedMessage.

        :param msgid: An rfc2822 message-id.
        :param body: The body of the message.
        :param attachment_contents: The contents of an attachment.
        :param force_transfer_encoding: If True, ensure a transfer encoding is
            used.
        :param email_address: The address the mail is from.
        :param signing_context: A GPGSigningContext instance containing the
            gpg key to sign with.  If None, the message is unsigned.  The
            context also contains the password and gpg signing mode.
        """
        mail = SignedMessage()
        if email_address is None:
            person = self.makePerson()
            email_address = removeSecurityProxy(person).preferredemail.email
        mail['From'] = email_address
        if to_address is None:
            to_address = removeSecurityProxy(
                self.makePerson()).preferredemail.email
        mail['To'] = to_address
        if subject is None:
            subject = self.getUniqueString('subject')
        mail['Subject'] = subject
        if msgid is None:
            msgid = self.makeUniqueRFC822MsgId()
        if body is None:
            body = self.getUniqueString('body')
        charset = 'ascii'
        try:
            body = body.encode(charset)
        except UnicodeEncodeError:
            charset = 'utf-8'
            body = body.encode(charset)
        mail['Message-Id'] = msgid
        mail['Date'] = formatdate()
        if signing_context is not None:
            gpghandler = getUtility(IGPGHandler)
            body = gpghandler.signContent(
                body, signing_context.fingerprint,
                signing_context.password, signing_context.mode)
            assert body is not None
        if attachment_contents is None:
            mail.set_payload(body)
            body_part = mail
        else:
            body_part = EmailMessage()
            body_part.set_payload(body)
            mail.attach(body_part)
            attach_part = EmailMessage()
            attach_part.set_payload(attachment_contents)
            attach_part['Content-type'] = 'application/octet-stream'
            if force_transfer_encoding:
                encode_base64(attach_part)
            mail.attach(attach_part)
            mail['Content-type'] = 'multipart/mixed'
        body_part['Content-type'] = 'text/plain'
        if force_transfer_encoding:
            encode_base64(body_part)
        body_part.set_charset(charset)
        mail.parsed_string = mail.as_string()
        return mail

    def makeSpecification(self, product=None, title=None, distribution=None,
                          name=None, summary=None, owner=None,
                          status=NewSpecificationDefinitionStatus.NEW,
                          implementation_status=None, goal=None, specurl=None,
                          assignee=None, drafter=None, approver=None,
                          priority=None, whiteboard=None, milestone=None,
                          information_type=None):
        """Create and return a new, arbitrary Blueprint.

        :param product: The product to make the blueprint on.  If one is
            not specified, an arbitrary product is created.
        """
        proprietary = (information_type not in PUBLIC_INFORMATION_TYPES and
            information_type is not None)
        if (product is None and milestone is not None and
            milestone.productseries is not None):
            product = milestone.productseries.product
        if distribution is None and product is None:
            if proprietary:
                specification_sharing_policy = (
                    SpecificationSharingPolicy.EMBARGOED_OR_PROPRIETARY)
            else:
                specification_sharing_policy = None
            product = self.makeProduct(
                specification_sharing_policy=specification_sharing_policy)
        if name is None:
            name = self.getUniqueString('name')
        if summary is None:
            summary = self.getUniqueString('summary')
        if title is None:
            title = self.getUniqueString('title')
        if owner is None:
            owner = self.makePerson()
        if priority is None:
            priority = SpecificationPriority.UNDEFINED
        status_names = NewSpecificationDefinitionStatus.items.mapping.keys()
        if status.name in status_names:
            definition_status = status
        else:
            # This is to satisfy life cycle requirements.
            definition_status = NewSpecificationDefinitionStatus.NEW
        spec = getUtility(ISpecificationSet).new(
            name=name,
            title=title,
            specurl=None,
            summary=summary,
            definition_status=definition_status,
            whiteboard=whiteboard,
            owner=owner,
            assignee=assignee,
            drafter=drafter,
            approver=approver,
            product=product,
            distribution=distribution,
            priority=priority)
        naked_spec = removeSecurityProxy(spec)
        if status.name not in status_names:
            # Set the closed status after the status has a sane initial state.
            naked_spec.definition_status = status
        if status in (SpecificationDefinitionStatus.OBSOLETE,
                      SpecificationDefinitionStatus.SUPERSEDED):
            # This is to satisfy a DB constraint of obsolete specs.
            naked_spec.completer = owner
            naked_spec.date_completed = datetime.now(pytz.UTC)
        naked_spec.specurl = specurl
        naked_spec.milestone = milestone
        if goal is not None:
            naked_spec.proposeGoal(goal, spec.target.owner)
        if implementation_status is not None:
            naked_spec.implementation_status = implementation_status
            naked_spec.updateLifecycleStatus(owner)
        if information_type is not None:
            if proprietary:
                naked_spec.target._ensurePolicies([information_type])
            naked_spec.transitionToInformationType(
                information_type, removeSecurityProxy(spec.target).owner)
        return spec

    makeBlueprint = makeSpecification

    def makeSpecificationWorkItem(self, title=None, specification=None,
                                  assignee=None, milestone=None, deleted=False,
                                  status=SpecificationWorkItemStatus.TODO,
                                  sequence=None):
        if title is None:
            title = self.getUniqueString(u'title')
        if specification is None:
            product = None
            distribution = None
            if milestone is not None:
                product = milestone.product
                distribution = milestone.distribution
            specification = self.makeSpecification(
                product=product, distribution=distribution)
        if sequence is None:
            sequence = self.getUniqueInteger()
        work_item = removeSecurityProxy(specification).newWorkItem(
            title=title, sequence=sequence, status=status, assignee=assignee,
            milestone=milestone)
        work_item.deleted = deleted
        return work_item

    def makeQuestion(self, target=None, title=None,
                     owner=None, description=None, language=None):
        """Create and return a new, arbitrary Question.

        :param target: The IQuestionTarget to make the question on. If one is
            not specified, an arbitrary product is created.
        :param title: The question title. If one is not provided, an
            arbitrary title is created.
        :param owner: The owner of the question. If one is not provided, the
            question target owner will be used.
        :param description: The question description.
        :param language: The question language. If one is not provided, then
            English will be used.
        """
        if target is None:
            target = self.makeProduct()
        if title is None:
            title = self.getUniqueString('title')
        if owner is None:
            owner = target.owner
        if description is None:
            description = self.getUniqueString('description')
        with person_logged_in(owner):
            question = target.newQuestion(
                owner=owner, title=title, description=description,
                language=language)
        return question

    def makeQuestionSubscription(self, question=None, person=None):
        """Create a QuestionSubscription."""
        if question is None:
            question = self.makeQuestion()
        if person is None:
            person = self.makePerson()
        with person_logged_in(person):
            return question.subscribe(person)

    def makeFAQ(self, target=None, title=None):
        """Create and return a new, arbitrary FAQ.

        :param target: The IFAQTarget to make the FAQ on. If one is
            not specified, an arbitrary product is created.
        :param title: The FAQ title. If one is not provided, an
            arbitrary title is created.
        """
        if target is None:
            target = self.makeProduct()
        if title is None:
            title = self.getUniqueString('title')
        return target.newFAQ(
            owner=target.owner, title=title, content='content')

    def makePackageCodeImport(self, sourcepackage=None, **kwargs):
        """Make a code import targetting a sourcepackage."""
        if sourcepackage is None:
            sourcepackage = self.makeSourcePackage()
        target = IBranchTarget(sourcepackage)
        return self.makeCodeImport(target=target, **kwargs)

    def makeProductCodeImport(self, product=None, **kwargs):
        """Make a code import targetting a product."""
        if product is None:
            product = self.makeProduct()
        target = IBranchTarget(product)
        return self.makeCodeImport(target=target, **kwargs)

    def makeCodeImport(self, svn_branch_url=None, cvs_root=None,
                       cvs_module=None, target=None, branch_name=None,
                       git_repo_url=None,
                       bzr_branch_url=None, registrant=None,
                       rcs_type=None, review_status=None):
        """Create and return a new, arbitrary code import.

        The type of code import will be inferred from the source details
        passed in, but defaults to a Subversion import from an arbitrary
        unique URL.
        """
        if (svn_branch_url is cvs_root is cvs_module is git_repo_url is
            bzr_branch_url is None):
            svn_branch_url = self.getUniqueURL()

        if target is None:
            target = IBranchTarget(self.makeProduct())
        if branch_name is None:
            branch_name = self.getUniqueString('name')
        if registrant is None:
            registrant = self.makePerson()

        code_import_set = getUtility(ICodeImportSet)
        if svn_branch_url is not None:
            if rcs_type is None:
                rcs_type = RevisionControlSystems.SVN
            else:
                assert rcs_type in (RevisionControlSystems.SVN,
                                    RevisionControlSystems.BZR_SVN)
            return code_import_set.new(
                registrant, target, branch_name, rcs_type=rcs_type,
                url=svn_branch_url, review_status=review_status)
        elif git_repo_url is not None:
            assert rcs_type in (None, RevisionControlSystems.GIT)
            return code_import_set.new(
                registrant, target, branch_name,
                rcs_type=RevisionControlSystems.GIT,
                url=git_repo_url, review_status=review_status)
        elif bzr_branch_url is not None:
            return code_import_set.new(
                registrant, target, branch_name,
                rcs_type=RevisionControlSystems.BZR,
                url=bzr_branch_url, review_status=review_status)
        else:
            assert rcs_type in (None, RevisionControlSystems.CVS)
            return code_import_set.new(
                registrant, target, branch_name,
                rcs_type=RevisionControlSystems.CVS,
                cvs_root=cvs_root, cvs_module=cvs_module,
                review_status=review_status)

    def makeChangelog(self, spn=None, versions=[]):
        """Create and return a LFA of a valid Debian-style changelog.

        Note that the changelog returned is unicode - this is deliberate
        so that code is forced to cope with it as utf-8 changelogs are
        normal.
        """
        if spn is None:
            spn = self.getUniqueString()
        changelog = ''
        for version in versions:
            entry = dedent(u'''\
            %s (%s) unstable; urgency=low

              * %s.

             -- Føo Bær <foo@example.com>  Tue, 01 Jan 1970 01:50:41 +0000

            ''' % (spn, version, version))
            changelog += entry
        return self.makeLibraryFileAlias(content=changelog.encode("utf-8"))

    def makeCodeImportEvent(self):
        """Create and return a CodeImportEvent."""
        code_import = self.makeCodeImport()
        person = self.makePerson()
        code_import_event_set = getUtility(ICodeImportEventSet)
        return code_import_event_set.newCreate(code_import, person)

    def makeCodeImportJob(self, code_import=None):
        """Create and return a new code import job for the given import.

        This implies setting the import's review_status to REVIEWED.
        """
        if code_import is None:
            code_import = self.makeCodeImport()
        code_import.updateFromData(
            {'review_status': CodeImportReviewStatus.REVIEWED},
            code_import.registrant)
        return code_import.import_job

    def makeCodeImportMachine(self, set_online=False, hostname=None):
        """Return a new CodeImportMachine.

        The machine will be in the OFFLINE state."""
        if hostname is None:
            hostname = self.getUniqueString('machine-')
        if set_online:
            state = CodeImportMachineState.ONLINE
        else:
            state = CodeImportMachineState.OFFLINE
        machine = getUtility(ICodeImportMachineSet).new(hostname, state)
        return machine

    def makeCodeImportResult(self, code_import=None, result_status=None,
                             date_started=None, date_finished=None,
                             log_excerpt=None, log_alias=None, machine=None):
        """Create and return a new CodeImportResult."""
        if code_import is None:
            code_import = self.makeCodeImport()
        if machine is None:
            machine = self.makeCodeImportMachine()
        requesting_user = None
        if log_excerpt is None:
            log_excerpt = self.getUniqueString()
        if result_status is None:
            result_status = CodeImportResultStatus.FAILURE
        if date_finished is None:
            # If a date_started is specified, then base the finish time
            # on that.
            if date_started is None:
                date_finished = time_counter().next()
            else:
                date_finished = date_started + timedelta(hours=4)
        if date_started is None:
            date_started = date_finished - timedelta(hours=4)
        if log_alias is None:
            log_alias = self.makeLibraryFileAlias()
        return getUtility(ICodeImportResultSet).new(
            code_import, machine, requesting_user, log_excerpt, log_alias,
            result_status, date_started, date_finished)

    def makeCodeReviewComment(self, sender=None, subject=None, body=None,
                              vote=None, vote_tag=None, parent=None,
                              merge_proposal=None, date_created=DEFAULT):
        if sender is None:
            sender = self.makePerson()
        if subject is None:
            subject = self.getUniqueString('subject')
        if body is None:
            body = self.getUniqueString('content')
        if merge_proposal is None:
            if parent:
                merge_proposal = parent.branch_merge_proposal
            else:
                merge_proposal = self.makeBranchMergeProposal(
                    registrant=sender)
        with person_logged_in(sender):
            return merge_proposal.createComment(
                sender, subject, body, vote, vote_tag, parent,
                _date_created=date_created)

    def makeCodeReviewVoteReference(self):
        bmp = removeSecurityProxy(self.makeBranchMergeProposal())
        candidate = self.makePerson()
        return bmp.nominateReviewer(candidate, bmp.registrant)

    def makeMessage(self, subject=None, content=None, parent=None,
                    owner=None, datecreated=None):
        if subject is None:
            subject = self.getUniqueString()
        if content is None:
            content = self.getUniqueString()
        if owner is None:
            owner = self.makePerson()
        if datecreated is None:
            datecreated = datetime.now(UTC)
        rfc822msgid = self.makeUniqueRFC822MsgId()
        message = Message(rfc822msgid=rfc822msgid, subject=subject,
            owner=owner, parent=parent, datecreated=datecreated)
        MessageChunk(message=message, sequence=1, content=content)
        return message

    def makeLanguage(self, language_code=None, name=None, pluralforms=None,
                     plural_expression=None):
        """Makes a language given the language_code and name."""
        if language_code is None:
            language_code = self.getUniqueString('lang')
        if name is None:
            name = "Language %s" % language_code
        if plural_expression is None and pluralforms is not None:
            # If the number of plural forms is known, the language
            # should also have a plural expression and vice versa.
            plural_expression = 'n %% %d' % pluralforms

        language_set = getUtility(ILanguageSet)
        return language_set.createLanguage(
            language_code, name, pluralforms=pluralforms,
            pluralexpression=plural_expression)

    def makeLanguagePack(self, distroseries=None, languagepack_type=None):
        """Create a language pack."""
        if distroseries is None:
            distroseries = self.makeUbuntuDistroSeries()
        if languagepack_type is None:
            languagepack_type = LanguagePackType.FULL
        return getUtility(ILanguagePackSet).addLanguagePack(
            distroseries, self.makeLibraryFileAlias(), languagepack_type)

    def makeLibraryFileAlias(self, filename=None, content=None,
                             content_type='text/plain', restricted=False,
                             expires=None, db_only=False):
        """Make a library file, and return the alias."""
        if filename is None:
            filename = self.getUniqueString('filename')
        if content is None:
            content = self.getUniqueString()

        if db_only:
            # Often we don't actually care if the file exists on disk.
            # This lets us run tests without a librarian server.
            lfc = LibraryFileContent(
                filesize=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                sha1=hashlib.sha1(content).hexdigest(),
                md5=hashlib.md5(content).hexdigest())
            lfa = LibraryFileAlias(
                content=lfc, filename=filename, mimetype=content_type)
        else:
            lfa = getUtility(ILibraryFileAliasSet).create(
                filename, len(content), StringIO(content), content_type,
                expires=expires, restricted=restricted)
        return lfa

    def makeDistribution(self, name=None, displayname=None, owner=None,
                         registrant=None, members=None, title=None,
                         aliases=None, bug_supervisor=None, driver=None,
                         publish_root_dir=None, publish_base_url=None,
                         publish_copy_base_url=None, no_pubconf=False,
                         icon=None, summary=None):
        """Make a new distribution."""
        if name is None:
            name = self.getUniqueString(prefix="distribution")
        if displayname is None:
            displayname = name.capitalize()
        if title is None:
            title = self.getUniqueString()
        description = self.getUniqueString()
        if summary is None:
            summary = self.getUniqueString()
        domainname = self.getUniqueString()
        if registrant is None:
            registrant = self.makePerson()
        if owner is None:
            owner = self.makePerson()
        if members is None:
            members = self.makeTeam(owner)
        distro = getUtility(IDistributionSet).new(
            name, displayname, title, description, summary, domainname,
            members, owner, registrant, icon=icon)
        naked_distro = removeSecurityProxy(distro)
        if aliases is not None:
            naked_distro.setAliases(aliases)
        if driver is not None:
            naked_distro.driver = driver
        if bug_supervisor is not None:
            naked_distro.bug_supervisor = bug_supervisor
        if not no_pubconf:
            self.makePublisherConfig(
                distro, publish_root_dir, publish_base_url,
                publish_copy_base_url)
        return distro

    def makeDistroSeries(self, distribution=None, version=None,
                         status=SeriesStatus.DEVELOPMENT,
                         previous_series=None, name=None, displayname=None,
                         registrant=None):
        """Make a new `DistroSeries`."""
        if distribution is None:
            distribution = self.makeDistribution()
        if name is None:
            name = self.getUniqueString(prefix="distroseries")
        if displayname is None:
            displayname = name.capitalize()
        if version is None:
            version = "%s.0" % self.getUniqueInteger()
        if registrant is None:
            registrant = distribution.owner

        # We don't want to login() as the person used to create the product,
        # so we remove the security proxy before creating the series.
        naked_distribution = removeSecurityProxy(distribution)
        series = naked_distribution.newSeries(
            version=version,
            name=name,
            displayname=displayname,
            title=self.getUniqueString(), summary=self.getUniqueString(),
            description=self.getUniqueString(),
            previous_series=previous_series, registrant=registrant)
        series.status = status

        return ProxyFactory(series)

    def makeUbuntuDistroSeries(self, version=None,
                               status=SeriesStatus.DEVELOPMENT,
                               previous_series=None, name=None,
                               displayname=None):
        """Short cut to use the celebrity 'ubuntu' as the distribution."""
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        return self.makeDistroSeries(
            ubuntu, version, status, previous_series, name, displayname)

    def makeDistroSeriesDifference(
        self, derived_series=None, source_package_name_str=None,
        versions=None,
        difference_type=DistroSeriesDifferenceType.DIFFERENT_VERSIONS,
        status=DistroSeriesDifferenceStatus.NEEDS_ATTENTION,
        changelogs=None, set_base_version=False, parent_series=None):
        """Create a new distro series source package difference."""
        if derived_series is None:
            dsp = self.makeDistroSeriesParent(
                parent_series=parent_series)
            derived_series = dsp.derived_series
            parent_series = dsp.parent_series
        else:
            if parent_series is None:
                dsp = getUtility(IDistroSeriesParentSet).getByDerivedSeries(
                    derived_series)
                if dsp.is_empty():
                    new_dsp = self.makeDistroSeriesParent(
                        derived_series=derived_series,
                        parent_series=parent_series)
                    parent_series = new_dsp.parent_series
                else:
                    parent_series = dsp[0].parent_series

        if source_package_name_str is None:
            source_package_name_str = self.getUniqueString('src-name')

        source_package_name = self.getOrMakeSourcePackageName(
            source_package_name_str)

        if versions is None:
            versions = {}
        if changelogs is None:
            changelogs = {}

        base_version = versions.get('base')
        if base_version is not None:
            for series in [derived_series, parent_series]:
                spr = self.makeSourcePackageRelease(
                    sourcepackagename=source_package_name,
                    version=base_version)
                self.makeSourcePackagePublishingHistory(
                    distroseries=series, sourcepackagerelease=spr,
                    status=PackagePublishingStatus.SUPERSEDED)

        if difference_type is not (
            DistroSeriesDifferenceType.MISSING_FROM_DERIVED_SERIES):
            spr = self.makeSourcePackageRelease(
                sourcepackagename=source_package_name,
                version=versions.get('derived'),
                changelog=changelogs.get('derived'))
            self.makeSourcePackagePublishingHistory(
                distroseries=derived_series, sourcepackagerelease=spr,
                status=PackagePublishingStatus.PUBLISHED)

        if difference_type is not (
            DistroSeriesDifferenceType.UNIQUE_TO_DERIVED_SERIES):
            spr = self.makeSourcePackageRelease(
                sourcepackagename=source_package_name,
                version=versions.get('parent'),
                changelog=changelogs.get('parent'))
            self.makeSourcePackagePublishingHistory(
                distroseries=parent_series,
                sourcepackagerelease=spr,
                status=PackagePublishingStatus.PUBLISHED)

        diff = getUtility(IDistroSeriesDifferenceSource).new(
            derived_series, source_package_name, parent_series)

        removeSecurityProxy(diff).status = status

        if set_base_version:
            version = versions.get('base', "%s.0" % self.getUniqueInteger())
            removeSecurityProxy(diff).base_version = version

        # We clear the cache on the diff, returning the object as if it
        # was just loaded from the store.
        clear_property_cache(diff)
        return diff

    def makeDistroSeriesDifferenceComment(
        self, distro_series_difference=None, owner=None, comment=None):
        """Create a new distro series difference comment."""
        if distro_series_difference is None:
            distro_series_difference = self.makeDistroSeriesDifference()
        if owner is None:
            owner = self.makePerson()
        if comment is None:
            comment = self.getUniqueString('dsdcomment')

        return getUtility(IDistroSeriesDifferenceCommentSource).new(
            distro_series_difference, owner, comment)

    def makeDistroSeriesParent(self, derived_series=None, parent_series=None,
                               initialized=False, is_overlay=False,
                               pocket=None, component=None):
        if parent_series is None:
            parent_series = self.makeDistroSeries()
        if derived_series is None:
            derived_series = self.makeDistroSeries()
        return getUtility(IDistroSeriesParentSet).new(
            derived_series, parent_series, initialized, is_overlay, pocket,
            component)

    def makeDistroArchSeries(self, distroseries=None,
                             architecturetag=None, processor=None,
                             official=True, owner=None,
                             supports_virtualized=False, enabled=True):
        """Create a new distroarchseries"""

        if distroseries is None:
            distroseries = self.makeDistroSeries()
        if processor is None:
            processor = self.makeProcessor()
        if owner is None:
            owner = self.makePerson()
        # XXX: architecturetag & processor are tightly coupled. It's
        # wrong to just make a fresh architecture tag without also making a
        # processor to go with it.
        if architecturetag is None:
            architecturetag = self.getUniqueString('arch')
        return distroseries.newArch(
            architecturetag, processor, official, owner,
            supports_virtualized, enabled)

    def makeComponent(self, name=None):
        """Make a new `IComponent`."""
        if name is None:
            name = self.getUniqueString()
        return getUtility(IComponentSet).ensure(name)

    def makeComponentSelection(self, distroseries=None, component=None):
        """Make a new `ComponentSelection`.

        :param distroseries: Optional `DistroSeries`.  If none is given,
            one will be created.
        :param component: Optional `Component` or a component name.  If
            none is given, one will be created.
        """
        if distroseries is None:
            distroseries = self.makeDistroSeries()

        if not IComponent.providedBy(component):
            component = self.makeComponent(component)

        return ComponentSelection(
            distroseries=distroseries, component=component)

    def makeArchive(self, distribution=None, owner=None, name=None,
                    purpose=None, enabled=True, private=False,
                    virtualized=True, description=None, displayname=None,
                    suppress_subscription_notifications=False):
        """Create and return a new arbitrary archive.

        :param distribution: Supply IDistribution, defaults to a new one
            made with makeDistribution() for non-PPAs and ubuntu for PPAs.
        :param owner: Supply IPerson, defaults to a new one made with
            makePerson().
        :param name: Name of the archive, defaults to a random string.
        :param purpose: Supply ArchivePurpose, defaults to PPA.
        :param enabled: Whether the archive is enabled.
        :param private: Whether the archive is created private.
        :param virtualized: Whether the archive is virtualized.
        :param description: A description of the archive.
        :param suppress_subscription_notifications: Whether to suppress
            subscription notifications, defaults to False.  Only useful
            for private archives.
        """
        if purpose is None:
            purpose = ArchivePurpose.PPA
        elif isinstance(purpose, basestring):
            purpose = ArchivePurpose.items[purpose.upper()]

        if distribution is None:
            # See bug #568769
            if purpose == ArchivePurpose.PPA:
                distribution = getUtility(ILaunchpadCelebrities).ubuntu
            else:
                distribution = self.makeDistribution()
        if owner is None:
            owner = self.makePerson()
        if name is None:
            if purpose != ArchivePurpose.PPA:
                name = default_name_by_purpose.get(purpose)
            if name is None:
                name = self.getUniqueString()

        # Making a distribution makes an archive, and there can be only one
        # per distribution.
        if purpose == ArchivePurpose.PRIMARY:
            return distribution.main_archive

        admins = getUtility(ILaunchpadCelebrities).admin
        with person_logged_in(admins.teamowner):
            archive = getUtility(IArchiveSet).new(
                owner=owner, purpose=purpose,
                distribution=distribution, name=name, displayname=displayname,
                enabled=enabled, require_virtualized=virtualized,
                description=description)

        if private:
            naked_archive = removeSecurityProxy(archive)
            naked_archive.private = True
            naked_archive.buildd_secret = "sekrit"

        if suppress_subscription_notifications:
            naked_archive = removeSecurityProxy(archive)
            naked_archive.suppress_subscription_notifications = True

        return archive

    def makeArchiveAdmin(self, archive=None):
        """Make an Archive Admin.

        :param archive: The `IArchive`, will be auto-created if None.

        Make and return an `IPerson` who has an `ArchivePermission` to admin
        the distroseries queue.
        """
        if archive is None:
            archive = self.makeArchive()

        person = self.makePerson()
        permission_set = getUtility(IArchivePermissionSet)
        permission_set.newQueueAdmin(archive, person, 'main')
        return person

    def makeBuilder(self, processor=None, url=None, name=None, title=None,
                    owner=None, active=True, virtualized=True, vm_host=None,
                    manual=False):
        """Make a new builder for i386 virtualized builds by default.

        Note: the builder returned will not be able to actually build -
        we currently have a build slave setup for 'bob' only in the
        test environment.
        """
        if processor is None:
            processor = getUtility(IProcessorSet).getByName('386')
        if url is None:
            url = 'http://%s:8221/' % self.getUniqueString()
        if name is None:
            name = self.getUniqueString('builder-name')
        if title is None:
            title = self.getUniqueString('builder-title')
        if owner is None:
            owner = self.makePerson()

        return getUtility(IBuilderSet).new(
            processor, url, name, title, owner, active, virtualized, vm_host,
            manual=manual)

    def makeRecipeText(self, *branches):
        if len(branches) == 0:
            branches = (self.makeAnyBranch(), )
        base_branch = branches[0]
        other_branches = branches[1:]
        text = MINIMAL_RECIPE_TEXT % base_branch.bzr_identity
        for i, branch in enumerate(other_branches):
            text += 'merge dummy-%s %s\n' % (i, branch.bzr_identity)
        return text

    def makeRecipe(self, *branches):
        """Make a builder recipe that references `branches`.

        If no branches are passed, return a recipe text that references an
        arbitrary branch.
        """
        from bzrlib.plugins.builder.recipe import RecipeParser
        parser = RecipeParser(self.makeRecipeText(*branches))
        return parser.parse()

    def makeSourcePackageRecipeDistroseries(self, name="warty"):
        """Return a supported Distroseries to use with Source Package Recipes.

        Ew.  This uses sampledata currently, which is the ONLY reason this
        method exists: it gives us a migration path away from sampledata.
        """
        ubuntu = getUtility(IDistributionSet).getByName('ubuntu')
        return ubuntu.getSeries(name)

    def makeSourcePackageRecipe(self, registrant=None, owner=None,
                                distroseries=None, name=None,
                                description=None, branches=(),
                                build_daily=False, daily_build_archive=None,
                                is_stale=None, recipe=None,
                                date_created=DEFAULT):
        """Make a `SourcePackageRecipe`."""
        if registrant is None:
            registrant = self.makePerson()
        if owner is None:
            owner = self.makePerson()
        if distroseries is None:
            distroseries = self.makeSourcePackageRecipeDistroseries()

        if name is None:
            name = self.getUniqueString('spr-name').decode('utf8')
        if description is None:
            description = self.getUniqueString(
                'spr-description').decode('utf8')
        if daily_build_archive is None:
            daily_build_archive = self.makeArchive(
                distribution=distroseries.distribution, owner=owner)
        if recipe is None:
            recipe = self.makeRecipeText(*branches)
        else:
            assert branches == ()
        source_package_recipe = getUtility(ISourcePackageRecipeSource).new(
            registrant, owner, name, recipe, description, [distroseries],
            daily_build_archive, build_daily, date_created)
        if is_stale is not None:
            removeSecurityProxy(source_package_recipe).is_stale = is_stale
        IStore(source_package_recipe).flush()
        return source_package_recipe

    def makeSourcePackageRecipeBuild(self, sourcepackage=None, recipe=None,
                                     requester=None, archive=None,
                                     sourcename=None, distroseries=None,
                                     pocket=None, date_created=None,
                                     status=BuildStatus.NEEDSBUILD,
                                     duration=None):
        """Make a new SourcePackageRecipeBuild."""
        if recipe is None:
            recipe = self.makeSourcePackageRecipe(name=sourcename)
        if archive is None:
            archive = self.makeArchive()
        if distroseries is None:
            distroseries = self.makeDistroSeries(
                distribution=archive.distribution)
            arch = self.makeDistroArchSeries(distroseries=distroseries)
            removeSecurityProxy(distroseries).nominatedarchindep = arch
        if requester is None:
            requester = self.makePerson()
        spr_build = getUtility(ISourcePackageRecipeBuildSource).new(
            distroseries=distroseries,
            recipe=recipe,
            archive=archive,
            requester=requester,
            pocket=pocket,
            date_created=date_created)
        if duration is not None:
            removeSecurityProxy(spr_build).updateStatus(
                BuildStatus.BUILDING, date_started=spr_build.date_created)
            removeSecurityProxy(spr_build).updateStatus(
                status, date_finished=spr_build.date_started + duration)
        else:
            removeSecurityProxy(spr_build).updateStatus(status)
        IStore(spr_build).flush()
        return spr_build

    def makeSourcePackageRecipeBuildJob(
        self, score=9876, virtualized=True, estimated_duration=64,
        sourcename=None, recipe_build=None):
        """Create a `SourcePackageRecipeBuildJob` and a `BuildQueue` for
        testing."""
        if recipe_build is None:
            recipe_build = self.makeSourcePackageRecipeBuild(
                sourcename=sourcename)
        recipe_build_job = recipe_build.makeJob()

        bq = BuildQueue(
            job=recipe_build_job.job, lastscore=score,
            job_type=BuildFarmJobType.RECIPEBRANCHBUILD,
            estimated_duration=timedelta(seconds=estimated_duration),
            virtualized=virtualized)
        IStore(BuildQueue).add(bq)
        return bq

    def makeTranslationTemplatesBuildJob(self, branch=None):
        """Make a new `TranslationTemplatesBuildJob`.

        :param branch: The branch that the job should be for.  If none
            is given, one will be created.
        """
        if branch is None:
            branch = self.makeBranch()

        jobset = getUtility(ITranslationTemplatesBuildJobSource)
        return jobset.create(branch)

    def makePOTemplate(self, productseries=None, distroseries=None,
                       sourcepackagename=None, owner=None, name=None,
                       translation_domain=None, path=None,
                       copy_pofiles=True, side=None, sourcepackage=None,
                       iscurrent=True):
        """Make a new translation template."""
        if sourcepackage is not None:
            assert distroseries is None, (
                'Cannot specify sourcepackage and distroseries')
            distroseries = sourcepackage.distroseries
            assert sourcepackagename is None, (
                'Cannot specify sourcepackage and sourcepackagename')
            sourcepackagename = sourcepackage.sourcepackagename
        if productseries is None and distroseries is None:
            if side != TranslationSide.UBUNTU:
                # No context for this template; set up a productseries.
                productseries = self.makeProductSeries(owner=owner)
                # Make it use Translations, otherwise there's little point
                # to us creating a template for it.
                naked_series = removeSecurityProxy(productseries)
                naked_series.product.translations_usage = (
                    ServiceUsage.LAUNCHPAD)
            else:
                distroseries = self.makeUbuntuDistroSeries()
        if distroseries is not None and sourcepackagename is None:
            sourcepackagename = self.makeSourcePackageName()

        templateset = getUtility(IPOTemplateSet)
        subset = templateset.getSubset(
            distroseries, sourcepackagename, productseries)

        if name is None:
            name = self.getUniqueString()
        if translation_domain is None:
            translation_domain = self.getUniqueString()

        if owner is None:
            if productseries is None:
                owner = distroseries.owner
            else:
                owner = productseries.owner

        if path is None:
            path = 'messages.pot'

        pot = subset.new(name, translation_domain, path, owner, copy_pofiles)
        removeSecurityProxy(pot).iscurrent = iscurrent
        return pot

    def makePOTemplateAndPOFiles(self, language_codes, **kwargs):
        """Create a POTemplate and associated POFiles.

        Create a POTemplate for the given distroseries/sourcepackagename or
        productseries and create a POFile for each language. Returns the
        template.
        """
        template = self.makePOTemplate(**kwargs)
        for language_code in language_codes:
            self.makePOFile(language_code, template, template.owner)
        return template

    def makePOFile(self, language_code=None, potemplate=None, owner=None,
                   create_sharing=False, language=None, side=None):
        """Make a new translation file."""
        assert language_code is None or language is None, (
            "Please specifiy only one of language_code and language.")
        if language_code is None:
            if language is None:
                language = self.makeLanguage()
            language_code = language.code
        if potemplate is None:
            potemplate = self.makePOTemplate(owner=owner, side=side)
        else:
            assert side is None, 'Cannot specify both side and potemplate.'
        return potemplate.newPOFile(language_code,
                                    create_sharing=create_sharing)

    def makePOTMsgSet(self, potemplate=None, singular=None, plural=None,
                      context=None, sequence=None, commenttext=None,
                      filereferences=None, sourcecomment=None,
                      flagscomment=None):
        """Make a new `POTMsgSet` in the given template."""
        if potemplate is None:
            potemplate = self.makePOTemplate()
        if singular is None and plural is None:
            singular = self.getUniqueString()
        if sequence is None:
            sequence = self.getUniqueInteger()
        potmsgset = potemplate.createMessageSetFromText(
            singular, plural, context, sequence)
        if commenttext is not None:
            potmsgset.commenttext = commenttext
        if filereferences is not None:
            potmsgset.filereferences = filereferences
        if sourcecomment is not None:
            potmsgset.sourcecomment = sourcecomment
        if flagscomment is not None:
            potmsgset.flagscomment = flagscomment
        removeSecurityProxy(potmsgset).sync()
        return potmsgset

    def makePOFileAndPOTMsgSet(self, language_code=None, msgid=None,
                               with_plural=False, side=None):
        """Make a `POFile` with a `POTMsgSet`."""
        pofile = self.makePOFile(language_code, side=side)

        if with_plural:
            if msgid is None:
                msgid = self.getUniqueString()
            plural = self.getUniqueString()
        else:
            plural = None

        potmsgset = self.makePOTMsgSet(
            pofile.potemplate, singular=msgid, plural=plural)

        return pofile, potmsgset

    def makeTranslationsDict(self, translations=None):
        """Make sure translations are stored in a dict, e.g. {0: "foo"}.

        If translations is already dict, it is returned unchanged.
        If translations is a sequence, it is enumerated into a dict.
        If translations is None, an arbitrary single translation is created.
        """
        translations = removeSecurityProxy(translations)
        if translations is None:
            return {0: self.getUniqueString()}
        if isinstance(translations, dict):
            return translations
        assert isinstance(translations, (list, tuple)), (
                "Expecting either a dict or a sequence.")
        return dict(enumerate(translations))

    def makeSuggestion(self, pofile=None, potmsgset=None, translator=None,
                       translations=None, date_created=None):
        """Make a new suggested `TranslationMessage` in the given PO file."""
        if pofile is None:
            pofile = self.makePOFile('sr')
        if potmsgset is None:
            potmsgset = self.makePOTMsgSet(pofile.potemplate)
        if translator is None:
            translator = self.makePerson()
        translations = self.makeTranslationsDict(translations)
        translation_message = potmsgset.submitSuggestion(
            pofile, translator, translations)
        assert translation_message is not None, (
            "Cannot make suggestion on translation credits POTMsgSet.")
        if date_created is not None:
            naked_translation_message = removeSecurityProxy(
                translation_message)
            naked_translation_message.date_created = date_created
            naked_translation_message.sync()
        return translation_message

    def makeCurrentTranslationMessage(self, pofile=None, potmsgset=None,
                                      translator=None, reviewer=None,
                                      translations=None, diverged=False,
                                      current_other=False,
                                      date_created=None, date_reviewed=None,
                                      language=None, side=None,
                                      potemplate=None):
        """Create a `TranslationMessage` and make it current.

        By default the message will only be current on the side (Ubuntu
        or upstream) that `pofile` is on.

        Be careful: if the message is already translated, calling this
        method may violate database unique constraints.

        :param pofile: `POFile` to put translation in; if omitted, one
            will be created.
        :param potmsgset: `POTMsgSet` to translate; if omitted, one will
            be created (with sequence number 1).
        :param translator: `Person` who created the translation.  If
            omitted, one will be created.
        :param reviewer: `Person` who reviewed the translation.  If
            omitted, one will be created.
        :param translations: Strings to translate the `POTMsgSet`
            to.  Can be either a list, or a dict mapping plural form
            numbers to the forms' respective translations.
            If omitted, will translate to a single random string.
        :param diverged: Create a diverged message?
        :param current_other: Should the message also be current on the
            other translation side?  (Cannot be combined with `diverged`).
        :param date_created: Force a specific creation date instead of 'now'.
        :param date_reviewed: Force a specific review date instead of 'now'.
        :param language: `Language` to use for the POFile
        :param side: The `TranslationSide` this translation should be for.
        :param potemplate: If provided, the POTemplate to use when creating
            the POFile.
        """
        assert not (diverged and current_other), (
            "A diverged message can't be current on the other side.")
        assert None in (language, pofile), (
            'Cannot specify both language and pofile.')
        assert None in (side, pofile), (
            'Cannot specify both side and pofile.')
        link_potmsgset_with_potemplate = (
            (pofile is None and potemplate is None) or potmsgset is None)
        if pofile is None:
            pofile = self.makePOFile(
                language=language, side=side, potemplate=potemplate)
        else:
            assert potemplate is None, (
                'Cannot specify both pofile and potemplate')
        potemplate = pofile.potemplate
        if potmsgset is None:
            potmsgset = self.makePOTMsgSet(potemplate)
        if link_potmsgset_with_potemplate:
            # If we have a new pofile or a new potmsgset, we must link
            # the potmsgset to the pofile's potemplate.
            potmsgset.setSequence(
                pofile.potemplate, self.getUniqueInteger())
        else:
            # Otherwise it is the duty of the callsite to ensure
            # consistency.
            store = IStore(TranslationTemplateItem)
            tti_for_message_in_template = store.find(
                TranslationTemplateItem.potmsgset == potmsgset,
                TranslationTemplateItem.potemplate == pofile.potemplate).any()
            assert tti_for_message_in_template is not None
        if translator is None:
            translator = self.makePerson()
        if reviewer is None:
            reviewer = self.makePerson()
        translations = sanitize_translations_from_webui(
            potmsgset.singular_text,
            self.makeTranslationsDict(translations),
            pofile.language.pluralforms)

        if diverged:
            message = self.makeDivergedTranslationMessage(
                pofile, potmsgset, translator, reviewer,
                translations, date_created)
        else:
            message = potmsgset.setCurrentTranslation(
                pofile, translator, translations,
                RosettaTranslationOrigin.ROSETTAWEB,
                share_with_other_side=current_other)
            if date_created is not None:
                removeSecurityProxy(message).date_created = date_created

        message.markReviewed(reviewer, date_reviewed)

        return message

    def makeDivergedTranslationMessage(self, pofile=None, potmsgset=None,
                                       translator=None, reviewer=None,
                                       translations=None, date_created=None):
        """Create a diverged, current `TranslationMessage`."""
        if pofile is None:
            pofile = self.makePOFile('lt')
        if reviewer is None:
            reviewer = self.makePerson()

        message = self.makeSuggestion(
            pofile=pofile, potmsgset=potmsgset, translator=translator,
            translations=translations, date_created=date_created)
        return message.approveAsDiverged(pofile, reviewer)

    def makeTranslationImportQueueEntry(self, path=None, productseries=None,
                                        distroseries=None,
                                        sourcepackagename=None,
                                        potemplate=None, content=None,
                                        uploader=None, pofile=None,
                                        format=None, status=None,
                                        by_maintainer=False):
        """Create a `TranslationImportQueueEntry`."""
        if path is None:
            path = self.getUniqueString() + '.pot'

        for_distro = not (distroseries is None and sourcepackagename is None)
        for_project = productseries is not None
        has_template = (potemplate is not None)
        if has_template and not for_distro and not for_project:
            # Copy target from template.
            distroseries = potemplate.distroseries
            sourcepackagename = potemplate.sourcepackagename
            productseries = potemplate.productseries

        if sourcepackagename is None and distroseries is None:
            if productseries is None:
                productseries = self.makeProductSeries()
        else:
            if sourcepackagename is None:
                sourcepackagename = self.makeSourcePackageName()
            if distroseries is None:
                distroseries = self.makeDistroSeries()

        if uploader is None:
            uploader = self.makePerson()

        if content is None:
            content = self.getUniqueString()

        if format is None:
            format = TranslationFileFormat.PO

        if status is None:
            status = RosettaImportStatus.NEEDS_REVIEW

        if type(content) == unicode:
            content = content.encode('utf-8')

        entry = getUtility(ITranslationImportQueue).addOrUpdateEntry(
            path=path, content=content, by_maintainer=by_maintainer,
            importer=uploader, productseries=productseries,
            distroseries=distroseries, sourcepackagename=sourcepackagename,
            potemplate=potemplate, pofile=pofile, format=format)
        entry.setStatus(
            status, getUtility(ILaunchpadCelebrities).rosetta_experts)
        return entry

    def makeMailingList(self, team, owner):
        """Create a mailing list for the team."""
        team_list = getUtility(IMailingListSet).new(team, owner)
        team_list.startConstructing()
        team_list.transitionToStatus(MailingListStatus.ACTIVE)
        return team_list

    def makeTeamAndMailingList(
        self, team_name, owner_name,
        visibility=None,
        membership_policy=TeamMembershipPolicy.OPEN):
        """Make a new active mailing list for the named team.

        :param team_name: The new team's name.
        :type team_name: string
        :param owner_name: The name of the team's owner.
        :type owner: string
        :param visibility: The team's visibility. If it's None, the default
            (public) will be used.
        :type visibility: `PersonVisibility`
        :param membership_policy: The membership policy of the team.
        :type membership_policy: `TeamMembershipPolicy`
        :return: The new team and mailing list.
        :rtype: (`ITeam`, `IMailingList`)
        """
        owner = getUtility(IPersonSet).getByName(owner_name)
        display_name = SPACE.join(
            word.capitalize() for word in team_name.split('-'))
        team = getUtility(IPersonSet).getByName(team_name)
        if team is None:
            team = self.makeTeam(
                owner, displayname=display_name, name=team_name,
                visibility=visibility,
                membership_policy=membership_policy)
        team_list = self.makeMailingList(team, owner)
        return team, team_list

    def makeTeamWithMailingListSubscribers(self, team_name, super_team=None,
                                           auto_subscribe=True):
        """Create a team, mailing list, and subscribers.

        :param team_name: The name of the team to create.
        :param super_team: Make the team a member of the super_team.
        :param auto_subscribe: Automatically subscribe members to the
            mailing list.
        :return: A tuple of team and the member user.
        """
        team = self.makeTeam(name=team_name)
        member = self.makePerson()
        with celebrity_logged_in('admin'):
            if super_team is None:
                mailing_list = self.makeMailingList(team, team.teamowner)
            else:
                super_team.addMember(
                    team, reviewer=team.teamowner, force_team_add=True)
                mailing_list = super_team.mailing_list
            team.addMember(member, reviewer=team.teamowner)
            if auto_subscribe:
                mailing_list.subscribe(member)
        return team, member

    def makeMirrorProbeRecord(self, mirror):
        """Create a probe record for a mirror of a distribution."""
        log_file = StringIO()
        log_file.write("Fake probe, nothing useful here.")
        log_file.seek(0)

        library_alias = getUtility(ILibraryFileAliasSet).create(
            name='foo', size=len(log_file.getvalue()),
            file=log_file, contentType='text/plain')

        proberecord = mirror.newProbeRecord(library_alias)
        return proberecord

    def makeMirror(self, distribution, displayname=None, country=None,
                   http_url=None, ftp_url=None, rsync_url=None,
                   official_candidate=False):
        """Create a mirror for the distribution."""
        if displayname is None:
            displayname = self.getUniqueString("mirror")
        # If no URL is specified create an HTTP URL.
        if http_url is None and ftp_url is None and rsync_url is None:
            http_url = self.getUniqueURL()
        # If no country is given use Argentina.
        if country is None:
            country = getUtility(ICountrySet)['AR']

        mirror = distribution.newMirror(
            owner=distribution.owner,
            speed=MirrorSpeed.S256K,
            country=country,
            content=MirrorContent.ARCHIVE,
            displayname=displayname,
            description=None,
            http_base_url=http_url,
            ftp_base_url=ftp_url,
            rsync_base_url=rsync_url,
            official_candidate=official_candidate)
        return mirror

    def makeUniqueRFC822MsgId(self):
        """Make a unique RFC 822 message id.

        The created message id is guaranteed not to exist in the
        `Message` table already.
        """
        msg_id = make_msgid('launchpad')
        while not Message.selectBy(rfc822msgid=msg_id).is_empty():
            msg_id = make_msgid('launchpad')
        return msg_id

    def makeSourcePackageName(self, name=None):
        """Make an `ISourcePackageName`."""
        if name is None:
            name = self.getUniqueString()
        return getUtility(ISourcePackageNameSet).new(name)

    def getOrMakeSourcePackageName(self, name=None):
        """Get an existing`ISourcePackageName` or make a new one.

        This method encapsulates getOrCreateByName so that tests can be kept
        free of the getUtility(ISourcePackageNameSet) noise.
        """
        if name is None:
            return self.makeSourcePackageName()
        return getUtility(ISourcePackageNameSet).getOrCreateByName(name)

    def makeSourcePackage(self, sourcepackagename=None, distroseries=None,
                          publish=False):
        """Make an `ISourcePackage`.

        :param publish: if true, create a corresponding
            SourcePackagePublishingHistory.
        """
        # Make sure we have a real sourcepackagename object.
        if (sourcepackagename is None or
            isinstance(sourcepackagename, basestring)):
            sourcepackagename = self.getOrMakeSourcePackageName(
                sourcepackagename)
        if distroseries is None:
            distroseries = self.makeDistroSeries()
        if publish:
            self.makeSourcePackagePublishingHistory(
                distroseries=distroseries,
                sourcepackagename=sourcepackagename)
        return distroseries.getSourcePackage(sourcepackagename)

    def getAnySourcePackageUrgency(self):
        return SourcePackageUrgency.MEDIUM

    def makePackageUpload(self, distroseries=None, archive=None,
                          pocket=None, changes_filename=None,
                          changes_file_content=None,
                          signing_key=None, status=None,
                          package_copy_job=None):
        if archive is None:
            archive = self.makeArchive()
        if distroseries is None:
            distroseries = self.makeDistroSeries(
                distribution=archive.distribution)
        if changes_filename is None:
            changes_filename = self.getUniqueString("changesfilename")
        if changes_file_content is None:
            changes_file_content = self.getUniqueString("changesfilecontent")
        if pocket is None:
            pocket = PackagePublishingPocket.RELEASE
        package_upload = distroseries.createQueueEntry(
            pocket, archive, changes_filename, changes_file_content,
            signing_key=signing_key, package_copy_job=package_copy_job)
        if status is not None:
            if status is not PackageUploadStatus.NEW:
                naked_package_upload = removeSecurityProxy(package_upload)
                status_changers = {
                    PackageUploadStatus.UNAPPROVED:
                        naked_package_upload.setUnapproved,
                    PackageUploadStatus.REJECTED:
                        naked_package_upload.setRejected,
                    PackageUploadStatus.DONE: naked_package_upload.setDone,
                    PackageUploadStatus.ACCEPTED:
                        naked_package_upload.setAccepted,
                    }
                status_changers[status]()
        return package_upload

    def makeSourcePackageUpload(self, distroseries=None,
                                sourcepackagename=None, component=None):
        """Make a `PackageUpload` with a `PackageUploadSource` attached."""
        if distroseries is None:
            distroseries = self.makeDistroSeries()
        upload = self.makePackageUpload(
            distroseries=distroseries, archive=distroseries.main_archive)
        upload.addSource(self.makeSourcePackageRelease(
            sourcepackagename=sourcepackagename, component=component))
        return upload

    def makeBuildPackageUpload(self, distroseries=None, pocket=None,
                               binarypackagename=None,
                               source_package_release=None, component=None):
        """Make a `PackageUpload` with a `PackageUploadBuild` attached."""
        if distroseries is None:
            distroseries = self.makeDistroSeries()
        upload = self.makePackageUpload(
            distroseries=distroseries, archive=distroseries.main_archive,
            pocket=pocket)
        build = self.makeBinaryPackageBuild(
            source_package_release=source_package_release, pocket=pocket)
        self.makeBinaryPackageRelease(
            binarypackagename=binarypackagename, build=build,
            component=component)
        upload.addBuild(build)
        return upload

    def makeCustomPackageUpload(self, distroseries=None, archive=None,
                                pocket=None, custom_type=None, filename=None):
        """Make a `PackageUpload` with a `PackageUploadCustom` attached."""
        if distroseries is None:
            distroseries = self.makeDistroSeries()
        if archive is None:
            archive = distroseries.main_archive
        if custom_type is None:
            custom_type = PackageUploadCustomFormat.DEBIAN_INSTALLER
        upload = self.makePackageUpload(
            distroseries=distroseries, archive=archive, pocket=pocket)
        file_alias = self.makeLibraryFileAlias(filename=filename)
        upload.addCustom(file_alias, custom_type)
        return upload

    def makeCopyJobPackageUpload(self, distroseries=None,
                                 sourcepackagename=None, source_archive=None,
                                 target_pocket=None):
        """Make a `PackageUpload` with a `PackageCopyJob` attached."""
        if distroseries is None:
            distroseries = self.makeDistroSeries()
        spph = self.makeSourcePackagePublishingHistory(
            archive=source_archive, sourcepackagename=sourcepackagename)
        spr = spph.sourcepackagerelease
        job = self.makePlainPackageCopyJob(
            package_name=spr.sourcepackagename.name,
            package_version=spr.version,
            source_archive=spph.archive,
            target_pocket=target_pocket,
            target_archive=distroseries.main_archive,
            target_distroseries=distroseries)
        job.addSourceOverride(SourceOverride(
            spr.sourcepackagename, spr.component, spr.section))
        try:
            job.run()
        except SuspendJobException:
            # Expected exception.
            job.suspend()
        upload_set = getUtility(IPackageUploadSet)
        return upload_set.getByPackageCopyJobIDs([job.id]).one()

    def makeSourcePackageRelease(self, archive=None, sourcepackagename=None,
                                 distroseries=None, maintainer=None,
                                 creator=None, component=None,
                                 section_name=None, urgency=None,
                                 version=None, builddepends=None,
                                 builddependsindep=None,
                                 build_conflicts=None,
                                 build_conflicts_indep=None,
                                 architecturehintlist='all',
                                 dsc_maintainer_rfc822=None,
                                 dsc_standards_version='3.6.2',
                                 dsc_format='1.0', dsc_binaries='foo-bin',
                                 date_uploaded=UTC_NOW,
                                 source_package_recipe_build=None,
                                 dscsigningkey=None,
                                 user_defined_fields=None,
                                 changelog_entry=None,
                                 homepage=None,
                                 changelog=None):
        """Make a `SourcePackageRelease`."""
        if distroseries is None:
            if source_package_recipe_build is not None:
                distroseries = source_package_recipe_build.distroseries
            else:
                if archive is None:
                    distribution = None
                else:
                    distribution = archive.distribution
                distroseries = self.makeDistroSeries(
                    distribution=distribution)

        if archive is None:
            archive = distroseries.main_archive

        if (sourcepackagename is None or
            isinstance(sourcepackagename, basestring)):
            sourcepackagename = self.getOrMakeSourcePackageName(
                sourcepackagename)

        if (component is None or isinstance(component, basestring)):
            component = self.makeComponent(component)

        if urgency is None:
            urgency = self.getAnySourcePackageUrgency()
        elif isinstance(urgency, basestring):
            urgency = SourcePackageUrgency.items[urgency.upper()]

        section = self.makeSection(name=section_name)

        if maintainer is None:
            maintainer = self.makePerson()

        if dsc_maintainer_rfc822 is None:
            dsc_maintainer_rfc822 = '%s <%s>' % (
                maintainer.displayname,
                removeSecurityProxy(maintainer).preferredemail.email)

        if creator is None:
            creator = self.makePerson()

        if version is None:
            version = unicode(self.getUniqueInteger()) + 'version'

        return distroseries.createUploadedSourcePackageRelease(
            sourcepackagename=sourcepackagename,
            maintainer=maintainer,
            creator=creator,
            component=component,
            section=section,
            urgency=urgency,
            version=version,
            builddepends=builddepends,
            builddependsindep=builddependsindep,
            build_conflicts=build_conflicts,
            build_conflicts_indep=build_conflicts_indep,
            architecturehintlist=architecturehintlist,
            changelog=changelog,
            changelog_entry=changelog_entry,
            dsc=None,
            copyright=self.getUniqueString(),
            dscsigningkey=dscsigningkey,
            dsc_maintainer_rfc822=dsc_maintainer_rfc822,
            dsc_standards_version=dsc_standards_version,
            dsc_format=dsc_format,
            dsc_binaries=dsc_binaries,
            archive=archive,
            dateuploaded=date_uploaded,
            source_package_recipe_build=source_package_recipe_build,
            user_defined_fields=user_defined_fields,
            homepage=homepage)

    def makeSourcePackageReleaseFile(self, sourcepackagerelease=None,
                                     library_file=None, filetype=None):
        if sourcepackagerelease is None:
            sourcepackagerelease = self.makeSourcePackageRelease()
        if library_file is None:
            library_file = self.makeLibraryFileAlias()
        if filetype is None:
            filetype = SourcePackageFileType.DSC
        return ProxyFactory(
            SourcePackageReleaseFile(
                sourcepackagerelease=sourcepackagerelease,
                libraryfile=library_file, filetype=filetype))

    def makeBinaryPackageBuild(self, source_package_release=None,
            distroarchseries=None, archive=None, builder=None,
            status=None, pocket=None, date_created=None, processor=None,
            sourcepackagename=None):
        """Create a BinaryPackageBuild.

        If archive is not supplied, the source_package_release is used
        to determine archive.
        :param source_package_release: The SourcePackageRelease this binary
            build uses as its source.
        :param sourcepackagename: when source_package_release is None, the
            sourcepackagename from which the build will come.
        :param distroarchseries: The DistroArchSeries to use. Defaults to the
            one from the source_package_release, or a new one if not provided.
        :param archive: The Archive to use. Defaults to the one from the
            source_package_release, or the distro arch series main archive
            otherwise.
        :param builder: An optional builder to assign.
        :param status: The BuildStatus for the build.
        """
        if processor is None:
            processor = self.makeProcessor()
        if distroarchseries is None:
            if source_package_release is not None:
                distroseries = source_package_release.upload_distroseries
            else:
                distroseries = self.makeDistroSeries()
            distroarchseries = self.makeDistroArchSeries(
                distroseries=distroseries, processor=processor)
        if archive is None:
            if source_package_release is None:
                archive = distroarchseries.main_archive
            else:
                archive = source_package_release.upload_archive
        if pocket is None:
            pocket = PackagePublishingPocket.RELEASE
        elif isinstance(pocket, basestring):
            pocket = PackagePublishingPocket.items[pocket.upper()]

        if source_package_release is None:
            multiverse = self.makeComponent(name='multiverse')
            source_package_release = self.makeSourcePackageRelease(
                archive, component=multiverse,
                distroseries=distroarchseries.distroseries,
                sourcepackagename=sourcepackagename)
            self.makeSourcePackagePublishingHistory(
                distroseries=source_package_release.upload_distroseries,
                archive=archive, sourcepackagerelease=source_package_release,
                pocket=pocket)
        if status is None:
            status = BuildStatus.NEEDSBUILD
        if date_created is None:
            date_created = self.getUniqueDate()
        admins = getUtility(ILaunchpadCelebrities).admin
        with person_logged_in(admins.teamowner):
            binary_package_build = getUtility(IBinaryPackageBuildSet).new(
                source_package_release=source_package_release,
                processor=processor,
                distro_arch_series=distroarchseries,
                status=status,
                archive=archive,
                pocket=pocket,
                date_created=date_created,
                builder=builder)
        IStore(binary_package_build).flush()
        return binary_package_build

    def makeSourcePackagePublishingHistory(self,
                                           distroseries=None,
                                           archive=None,
                                           sourcepackagerelease=None,
                                           pocket=None,
                                           status=None,
                                           dateremoved=None,
                                           date_uploaded=UTC_NOW,
                                           scheduleddeletiondate=None,
                                           ancestor=None,
                                           **kwargs):
        """Make a `SourcePackagePublishingHistory`.

        :param sourcepackagerelease: The source package release to publish
            If not provided, a new one will be created.
        :param distroseries: The distro series in which to publish.
            Default to the source package release one, or a new one will
            be created when not provided.
        :param archive: The archive to publish into. Default to the
            initial source package release  upload archive, or to the
            distro series main archive.
        :param pocket: The pocket to publish into. Can be specified as a
            string. Defaults to the BACKPORTS pocket.
        :param status: The publication status. Defaults to PENDING. If
            set to PUBLISHED, the publisheddate will be set to now.
        :param dateremoved: The removal date.
        :param date_uploaded: The upload date. Defaults to now.
        :param scheduleddeletiondate: The date where the publication
            is scheduled to be removed.
        :param ancestor: The publication ancestor parameter.
        :param **kwargs: All other parameters are passed through to the
            makeSourcePackageRelease call if needed.
        """
        if distroseries is None:
            if sourcepackagerelease is not None:
                distroseries = sourcepackagerelease.upload_distroseries
            else:
                if archive is None:
                    distribution = None
                else:
                    distribution = archive.distribution
                distroseries = self.makeDistroSeries(
                    distribution=distribution)
        if archive is None:
            archive = distroseries.main_archive

        if pocket is None:
            pocket = self.getAnyPocket()
        elif isinstance(pocket, basestring):
            pocket = PackagePublishingPocket.items[pocket.upper()]

        if status is None:
            status = PackagePublishingStatus.PENDING
        elif isinstance(status, basestring):
            status = PackagePublishingStatus.items[status.upper()]

        if sourcepackagerelease is None:
            sourcepackagerelease = self.makeSourcePackageRelease(
                archive=archive, distroseries=distroseries,
                date_uploaded=date_uploaded, **kwargs)

        admins = getUtility(ILaunchpadCelebrities).admin
        with person_logged_in(admins.teamowner):
            spph = getUtility(IPublishingSet).newSourcePublication(
                archive, sourcepackagerelease, distroseries,
                sourcepackagerelease.component, sourcepackagerelease.section,
                pocket, ancestor)

        naked_spph = removeSecurityProxy(spph)
        naked_spph.status = status
        naked_spph.datecreated = date_uploaded
        naked_spph.dateremoved = dateremoved
        naked_spph.scheduleddeletiondate = scheduleddeletiondate
        if status == PackagePublishingStatus.PUBLISHED:
            naked_spph.datepublished = UTC_NOW
        return spph

    def makeBinaryPackagePublishingHistory(self, binarypackagerelease=None,
                                           binarypackagename=None,
                                           distroarchseries=None,
                                           component=None, section_name=None,
                                           priority=None, status=None,
                                           scheduleddeletiondate=None,
                                           dateremoved=None,
                                           datecreated=None,
                                           pocket=None, archive=None,
                                           source_package_release=None,
                                           binpackageformat=None,
                                           sourcepackagename=None,
                                           version=None,
                                           architecturespecific=False,
                                           with_debug=False, with_file=False):
        """Make a `BinaryPackagePublishingHistory`."""
        if distroarchseries is None:
            if archive is None:
                distribution = None
            else:
                distribution = archive.distribution
            distroseries = self.makeDistroSeries(distribution=distribution)
            distroarchseries = self.makeDistroArchSeries(
                distroseries=distroseries)

        if archive is None:
            archive = self.makeArchive(
                distribution=distroarchseries.distroseries.distribution,
                purpose=ArchivePurpose.PRIMARY)
            # XXX wgrant 2013-05-23: We need to set build_debug_symbols
            # until the guard in publishBinaries is gone.
            need_debug = (
                with_debug or binpackageformat == BinaryPackageFormat.DDEB)
            if archive.purpose == ArchivePurpose.PRIMARY and need_debug:
                with admin_logged_in():
                    archive.build_debug_symbols = True

        if pocket is None:
            pocket = self.getAnyPocket()
        if status is None:
            status = PackagePublishingStatus.PENDING

        if priority is None:
            priority = PackagePublishingPriority.OPTIONAL
        if binpackageformat is None:
            binpackageformat = BinaryPackageFormat.DEB

        if binarypackagerelease is None:
            # Create a new BinaryPackageBuild and BinaryPackageRelease
            # in the same archive and suite.
            binarypackagebuild = self.makeBinaryPackageBuild(
                archive=archive, distroarchseries=distroarchseries,
                pocket=pocket, source_package_release=source_package_release,
                sourcepackagename=sourcepackagename)
            binarypackagerelease = self.makeBinaryPackageRelease(
                binarypackagename=binarypackagename, version=version,
                build=binarypackagebuild,
                component=component, binpackageformat=binpackageformat,
                section_name=section_name, priority=priority,
                architecturespecific=architecturespecific)
            if with_file:
                ext = {
                    BinaryPackageFormat.DEB: 'deb',
                    BinaryPackageFormat.UDEB: 'udeb',
                    BinaryPackageFormat.DDEB: 'ddeb',
                    }[binarypackagerelease.binpackageformat]
                lfa = self.makeLibraryFileAlias(
                    filename='%s_%s_%s.%s' % (
                        binarypackagerelease.binarypackagename.name,
                        binarypackagerelease.version,
                        binarypackagebuild.distro_arch_series.architecturetag,
                        ext))
                self.makeBinaryPackageFile(
                    binarypackagerelease=binarypackagerelease,
                    library_file=lfa)

        if datecreated is None:
            datecreated = self.getUniqueDate()

        bpphs = getUtility(IPublishingSet).publishBinaries(
            archive, distroarchseries.distroseries, pocket,
            {binarypackagerelease: (
                binarypackagerelease.component, binarypackagerelease.section,
                priority, None)})
        for bpph in bpphs:
            naked_bpph = removeSecurityProxy(bpph)
            naked_bpph.status = status
            naked_bpph.dateremoved = dateremoved
            naked_bpph.datecreated = datecreated
            naked_bpph.scheduleddeletiondate = scheduleddeletiondate
            naked_bpph.priority = priority
            if status == PackagePublishingStatus.PUBLISHED:
                naked_bpph.datepublished = UTC_NOW
        if with_debug:
            debug_bpph = self.makeBinaryPackagePublishingHistory(
                binarypackagename=(
                    binarypackagerelease.binarypackagename.name + '-dbgsym'),
                version=version, distroarchseries=distroarchseries,
                component=component, section_name=binarypackagerelease.section,
                priority=priority, status=status,
                scheduleddeletiondate=scheduleddeletiondate,
                dateremoved=dateremoved, datecreated=datecreated,
                pocket=pocket, archive=archive,
                source_package_release=source_package_release,
                binpackageformat=BinaryPackageFormat.DDEB,
                sourcepackagename=sourcepackagename,
                architecturespecific=architecturespecific,
                with_file=with_file)
            removeSecurityProxy(bpph.binarypackagerelease).debug_package = (
                debug_bpph.binarypackagerelease)
            return bpphs[0], debug_bpph
        return bpphs[0]

    def makeSPPHForBPPH(self, bpph):
        """Produce a `SourcePackagePublishingHistory` to match `bpph`.

        :param bpph: A `BinaryPackagePublishingHistory`.
        :return: A `SourcePackagePublishingHistory` stemming from the same
            source package as `bpph`, published into the same distroseries,
            pocket, and archive.
        """
        bpr = bpph.binarypackagerelease
        return self.makeSourcePackagePublishingHistory(
            distroseries=bpph.distroarchseries.distroseries,
            sourcepackagerelease=bpr.build.source_package_release,
            pocket=bpph.pocket, archive=bpph.archive)

    def makeBinaryPackageName(self, name=None):
        """Make an `IBinaryPackageName`."""
        if name is None:
            name = self.getUniqueString("binarypackage")
        return getUtility(IBinaryPackageNameSet).new(name)

    def getOrMakeBinaryPackageName(self, name=None):
        """Get an existing `IBinaryPackageName` or make a new one.

        This method encapsulates getOrCreateByName so that tests can be kept
        free of the getUtility(IBinaryPackageNameSet) noise.
        """
        if name is None:
            return self.makeBinaryPackageName()
        return getUtility(IBinaryPackageNameSet).getOrCreateByName(name)

    def makeBinaryPackageFile(self, binarypackagerelease=None,
                              library_file=None, filetype=None):
        if binarypackagerelease is None:
            binarypackagerelease = self.makeBinaryPackageRelease()
        if library_file is None:
            library_file = self.makeLibraryFileAlias()
        if filetype is None:
            filetype = BinaryPackageFileType.DEB
        return ProxyFactory(BinaryPackageFile(
            binarypackagerelease=binarypackagerelease,
            libraryfile=library_file, filetype=filetype))

    def makeBinaryPackageRelease(self, binarypackagename=None,
                                 version=None, build=None,
                                 binpackageformat=None, component=None,
                                 section_name=None, priority=None,
                                 architecturespecific=False,
                                 summary=None, description=None,
                                 shlibdeps=None, depends=None,
                                 recommends=None, suggests=None,
                                 conflicts=None, replaces=None,
                                 provides=None, pre_depends=None,
                                 enhances=None, breaks=None,
                                 essential=False, installed_size=None,
                                 date_created=None, debug_package=None,
                                 homepage=None):
        """Make a `BinaryPackageRelease`."""
        if build is None:
            build = self.makeBinaryPackageBuild()
        if (binarypackagename is None or
            isinstance(binarypackagename, basestring)):
            binarypackagename = self.getOrMakeBinaryPackageName(
                binarypackagename)
        if version is None:
            version = build.source_package_release.version
        if binpackageformat is None:
            binpackageformat = BinaryPackageFormat.DEB
        if component is None:
            component = build.source_package_release.component
        elif isinstance(component, unicode):
            component = getUtility(IComponentSet)[component]
        if isinstance(section_name, basestring):
            section_name = self.makeSection(section_name)
        section = section_name or build.source_package_release.section
        if priority is None:
            priority = PackagePublishingPriority.OPTIONAL
        if summary is None:
            summary = self.getUniqueString("summary")
        if description is None:
            description = self.getUniqueString("description")
        if installed_size is None:
            installed_size = self.getUniqueInteger()
        bpr = build.createBinaryPackageRelease(
                binarypackagename=binarypackagename, version=version,
                binpackageformat=binpackageformat,
                component=component, section=section, priority=priority,
                summary=summary, description=description,
                architecturespecific=architecturespecific,
                shlibdeps=shlibdeps, depends=depends, recommends=recommends,
                suggests=suggests, conflicts=conflicts, replaces=replaces,
                provides=provides, pre_depends=pre_depends,
                enhances=enhances, breaks=breaks, essential=essential,
                installedsize=installed_size, debug_package=debug_package,
                homepage=homepage)
        if date_created is not None:
            removeSecurityProxy(bpr).datecreated = date_created
        return bpr

    def makeSection(self, name=None):
        """Make a `Section`."""
        if name is None:
            name = self.getUniqueString('section')
        return getUtility(ISectionSet).ensure(name)

    def makePackageset(self, name=None, description=None, owner=None,
                       packages=(), distroseries=None, related_set=None):
        """Make an `IPackageset`."""
        if name is None:
            name = self.getUniqueString(u'package-set-name')
        if description is None:
            description = self.getUniqueString(u'package-set-description')
        if owner is None:
            person = self.getUniqueString(u'package-set-owner')
            owner = self.makePerson(name=person)
        techboard = getUtility(ILaunchpadCelebrities).ubuntu_techboard
        ps_set = getUtility(IPackagesetSet)
        package_set = run_with_login(
            techboard.teamowner,
            lambda: ps_set.new(
                name, description, owner, distroseries, related_set))
        run_with_login(owner, lambda: package_set.add(packages))
        return package_set

    def getAnyPocket(self):
        return PackagePublishingPocket.BACKPORTS

    def makeSuiteSourcePackage(self, distroseries=None,
                               sourcepackagename=None, pocket=None):
        if distroseries is None:
            distroseries = self.makeDistroSeries()
        if pocket is None:
            pocket = self.getAnyPocket()
        # Make sure we have a real sourcepackagename object.
        if (sourcepackagename is None or
            isinstance(sourcepackagename, basestring)):
            sourcepackagename = self.getOrMakeSourcePackageName(
                sourcepackagename)
        return ProxyFactory(
            SuiteSourcePackage(distroseries, pocket, sourcepackagename))

    def makeDistributionSourcePackage(self, sourcepackagename=None,
                                      distribution=None, with_db=False):
        # Make sure we have a real sourcepackagename object.
        if (sourcepackagename is None or
            isinstance(sourcepackagename, basestring)):
            sourcepackagename = self.getOrMakeSourcePackageName(
                sourcepackagename)
        if distribution is None:
            distribution = self.makeDistribution()
        package = distribution.getSourcePackage(sourcepackagename)
        if with_db:
            # Create an instance with a database record, that is normally
            # done by secondary process.
            removeSecurityProxy(package)._new(
                distribution, sourcepackagename, False)
        return package

    def makeDSPCache(self, distro_name, package_name, make_distro=True,
                     official=True, binary_names=None, archive=None):
        if make_distro:
            distribution = self.makeDistribution(name=distro_name)
        else:
            distribution = getUtility(IDistributionSet).getByName(distro_name)
        dsp = self.makeDistributionSourcePackage(
            distribution=distribution, sourcepackagename=package_name,
            with_db=official)
        if archive is None:
            archive = dsp.distribution.main_archive
        else:
            archive = self.makeArchive(
                distribution=distribution, purpose=archive)
        if official:
            self.makeSourcePackagePublishingHistory(
                distroseries=distribution.currentseries,
                sourcepackagename=dsp.sourcepackagename,
                archive=archive)
        with dbuser('statistician'):
            DistributionSourcePackageCache(
                distribution=dsp.distribution,
                sourcepackagename=dsp.sourcepackagename,
                archive=archive,
                name=package_name,
                binpkgnames=binary_names)
        return distribution, dsp

    def makeEmailMessage(self, body=None, sender=None, to=None,
                         attachments=None, encode_attachments=False):
        """Make an email message with possible attachments.

        :param attachments: Should be an interable of tuples containing
           (filename, content-type, payload)
        """
        if sender is None:
            sender = self.makePerson()
        if body is None:
            body = self.getUniqueString('body')
        if to is None:
            to = self.getUniqueEmailAddress()

        msg = MIMEMultipart()
        msg['Message-Id'] = make_msgid('launchpad')
        msg['Date'] = formatdate()
        msg['To'] = to
        msg['From'] = removeSecurityProxy(sender).preferredemail.email
        msg['Subject'] = 'Sample'

        if attachments is None:
            msg.set_payload(body)
        else:
            msg.attach(MIMEText(body))
            for filename, content_type, payload in attachments:
                attachment = EmailMessage()
                attachment.set_payload(payload)
                attachment['Content-Type'] = content_type
                attachment['Content-Disposition'] = (
                    'attachment; filename="%s"' % filename)
                if encode_attachments:
                    encode_base64(attachment)
                msg.attach(attachment)
        return msg

    def makeHWSubmission(self, date_created=None, submission_key=None,
                         emailaddress=u'test@canonical.com',
                         distroarchseries=None, private=False,
                         contactable=False, system=None,
                         submission_data=None, status=None):
        """Create a new HWSubmission."""
        if date_created is None:
            date_created = datetime.now(pytz.UTC)
        if submission_key is None:
            submission_key = self.getUniqueString('submission-key')
        if distroarchseries is None:
            distroarchseries = self.makeDistroArchSeries()
        if system is None:
            system = self.getUniqueString('system-fingerprint')
        if submission_data is None:
            sample_data_path = os.path.join(
                config.root, 'lib', 'lp', 'hardwaredb', 'scripts',
                'tests', 'simple_valid_hwdb_submission.xml')
            submission_data = open(sample_data_path).read()
        filename = self.getUniqueString('submission-file')
        filesize = len(submission_data)
        raw_submission = StringIO(submission_data)
        format = HWSubmissionFormat.VERSION_1
        submission_set = getUtility(IHWSubmissionSet)

        submission = submission_set.createSubmission(
            date_created, format, private, contactable,
            submission_key, emailaddress, distroarchseries,
            raw_submission, filename, filesize, system)

        if status is not None:
            removeSecurityProxy(submission).status = status
        return submission

    def makeHWSubmissionDevice(self, submission, device, driver, parent,
                               hal_device_id):
        """Create a new HWSubmissionDevice."""
        device_driver_link_set = getUtility(IHWDeviceDriverLinkSet)
        device_driver_link = device_driver_link_set.getOrCreate(
            device, driver)
        return getUtility(IHWSubmissionDeviceSet).create(
            device_driver_link, submission, parent, hal_device_id)

    def makeSSHKey(self, person=None):
        """Create a new SSHKey."""
        if person is None:
            person = self.makePerson()
        public_key = "ssh-rsa %s %s" % (
            self.getUniqueString(), self.getUniqueString())
        return getUtility(ISSHKeySet).new(person, public_key)

    def makeBlob(self, blob=None, expires=None, blob_file=None):
        """Create a new TemporaryFileStorage BLOB."""
        if blob_file is not None:
            blob_path = os.path.join(
                config.root, 'lib/lp/bugs/tests/testfiles', blob_file)
            blob = open(blob_path).read()
        if blob is None:
            blob = self.getUniqueString()
        new_uuid = getUtility(ITemporaryStorageManager).new(blob, expires)

        return getUtility(ITemporaryStorageManager).fetch(new_uuid)

    def makeProcessedApportBlob(self, metadata):
        """Create a processed ApportJob with the specified metadata dict.

        It doesn't actually run the job. It fakes it, and uses a fake
        librarian file so as to work without the librarian.
        """
        blob = TemporaryBlobStorage(uuid=str(uuid.uuid1()), file_alias=1)
        job = getUtility(IProcessApportBlobJobSource).create(blob)
        job.job.start()
        removeSecurityProxy(job).metadata = {
            'processed_data': FileBugData(**metadata).asDict()}
        job.job.complete()
        return blob

    def makeLaunchpadService(self, person=None, version="devel"):
        if person is None:
            person = self.makePerson()
        from lp.testing.layers import BaseLayer
        launchpad = launchpadlib_for(
            "test", person, service_root=BaseLayer.appserver_root_url("api"),
            version=version)
        login_person(person)
        return launchpad

    def makePackageDiff(self, from_source=None, to_source=None,
                        requester=None, status=None, date_fulfilled=None,
                        diff_content=None, diff_filename=None):
        """Create a new `PackageDiff`."""
        if from_source is None:
            from_source = self.makeSourcePackageRelease()
        if to_source is None:
            to_source = self.makeSourcePackageRelease()
        if requester is None:
            requester = self.makePerson()
        if status is None:
            status = PackageDiffStatus.COMPLETED
        if date_fulfilled is None:
            date_fulfilled = UTC_NOW
        if diff_content is None:
            diff_content = self.getUniqueString("packagediff")
        lfa = self.makeLibraryFileAlias(
            filename=diff_filename, content=diff_content)
        return ProxyFactory(
            PackageDiff(
                requester=requester, from_source=from_source,
                to_source=to_source, date_fulfilled=date_fulfilled,
                status=status, diff_content=lfa))

    # Factory methods for OAuth tokens.
    def makeOAuthConsumer(self, key=None, secret=None):
        if key is None:
            key = self.getUniqueString("oauthconsumerkey")
        if secret is None:
            secret = ''
        return getUtility(IOAuthConsumerSet).new(key, secret)

    def makeOAuthRequestToken(self, consumer=None, date_created=None,
                              reviewed_by=None,
                              access_level=OAuthPermission.READ_PUBLIC):
        """Create a (possibly reviewed) OAuth request token."""
        if consumer is None:
            consumer = self.makeOAuthConsumer()
        token = consumer.newRequestToken()

        if reviewed_by is not None:
            # Review the token before modifying the date_created,
            # since the date_created can be used to simulate an
            # expired token.
            token.review(reviewed_by, access_level)

        if date_created is not None:
            unwrapped_token = removeSecurityProxy(token)
            unwrapped_token.date_created = date_created
        return token

    def makeOAuthAccessToken(self, consumer=None, owner=None,
                             access_level=OAuthPermission.READ_PUBLIC):
        """Create an OAuth access token."""
        if owner is None:
            owner = self.makePerson()
        request_token = self.makeOAuthRequestToken(
            consumer, reviewed_by=owner, access_level=access_level)
        return request_token.createAccessToken()

    def makeCVE(self, sequence, description=None,
                cvestate=CveStatus.CANDIDATE):
        """Create a new CVE record."""
        if description is None:
            description = self.getUniqueString()
        return getUtility(ICveSet).new(sequence, description, cvestate)

    def makePublisherConfig(self, distribution=None, root_dir=None,
                            base_url=None, copy_base_url=None):
        """Create a new `PublisherConfig` record."""
        if distribution is None:
            distribution = self.makeDistribution()
        if root_dir is None:
            root_dir = self.getUniqueUnicode()
        if base_url is None:
            base_url = self.getUniqueUnicode()
        if copy_base_url is None:
            copy_base_url = self.getUniqueUnicode()
        return getUtility(IPublisherConfigSet).new(
            distribution, root_dir, base_url, copy_base_url)

    def makePlainPackageCopyJob(
        self, package_name=None, package_version=None, source_archive=None,
        target_archive=None, target_distroseries=None, target_pocket=None,
        requester=None):
        """Create a new `PlainPackageCopyJob`."""
        if package_name is None and package_version is None:
            package_name = self.makeSourcePackageName().name
            package_version = unicode(self.getUniqueInteger()) + 'version'
        if source_archive is None:
            source_archive = self.makeArchive()
        if target_archive is None:
            target_archive = self.makeArchive()
        if target_distroseries is None:
            target_distroseries = self.makeDistroSeries()
        if target_pocket is None:
            target_pocket = self.getAnyPocket()
        if requester is None:
            requester = self.makePerson()
        return getUtility(IPlainPackageCopyJobSource).create(
            package_name, source_archive, target_archive,
            target_distroseries, target_pocket,
            package_version=package_version, requester=requester)

    def makeAccessPolicy(self, pillar=None,
                         type=InformationType.PROPRIETARY,
                         check_existing=False):
        if pillar is None:
            pillar = self.makeProduct()
        policy_source = getUtility(IAccessPolicySource)
        if check_existing:
            policy = policy_source.find([(pillar, type)]).one()
            if policy is not None:
                return policy
        policies = policy_source.create([(pillar, type)])
        return policies[0]

    def makeAccessArtifact(self, concrete=None):
        if concrete is None:
            concrete = self.makeBranch()
        artifacts = getUtility(IAccessArtifactSource).ensure([concrete])
        return artifacts[0]

    def makeAccessPolicyArtifact(self, artifact=None, policy=None):
        if artifact is None:
            artifact = self.makeAccessArtifact()
        if policy is None:
            policy = self.makeAccessPolicy()
        [link] = getUtility(IAccessPolicyArtifactSource).create(
            [(artifact, policy)])
        return link

    def makeAccessArtifactGrant(self, artifact=None, grantee=None,
                                grantor=None, concrete_artifact=None):
        if artifact is None:
            artifact = self.makeAccessArtifact(concrete_artifact)
        if grantee is None:
            grantee = self.makePerson()
        if grantor is None:
            grantor = self.makePerson()
        [grant] = getUtility(IAccessArtifactGrantSource).grant(
            [(artifact, grantee, grantor)])
        return grant

    def makeAccessPolicyGrant(self, policy=None, grantee=None, grantor=None):
        if policy is None:
            policy = self.makeAccessPolicy()
        if grantee is None:
            grantee = self.makePerson()
        if grantor is None:
            grantor = self.makePerson()
        [grant] = getUtility(IAccessPolicyGrantSource).grant(
            [(policy, grantee, grantor)])
        return grant

    def makeFakeFileUpload(self, filename=None, content=None):
        """Return a zope.publisher.browser.FileUpload like object.

        This can be useful while testing multipart form submission.
        """
        if filename is None:
            filename = self.getUniqueString()
        if content is None:
            content = self.getUniqueString()
        fileupload = StringIO(content)
        fileupload.filename = filename
        fileupload.headers = {
            'Content-Type': 'text/plain; charset=utf-8',
            'Content-Disposition': 'attachment; filename="%s"' % filename
            }
        return fileupload

    def makeCommercialSubscription(self, product, expired=False,
                                   voucher_id='new'):
        """Create a commercial subscription for the given product."""
        if CommercialSubscription.selectOneBy(product=product) is not None:
            raise AssertionError(
                "The product under test already has a CommercialSubscription.")
        if expired:
            expiry = datetime.now(pytz.UTC) - timedelta(days=1)
        else:
            expiry = datetime.now(pytz.UTC) + timedelta(days=30)
        CommercialSubscription(
            product=product,
            date_starts=datetime.now(pytz.UTC) - timedelta(days=90),
            date_expires=expiry,
            registrant=product.owner,
            purchaser=product.owner,
            sales_system_id=voucher_id,
            whiteboard='')

    def grantCommercialSubscription(self, person, months=12):
        """Give 'person' a commercial subscription."""
        product = self.makeProduct(owner=person)
        product.redeemSubscriptionVoucher(
            self.getUniqueString(), person, person, months)


# Some factory methods return simple Python types. We don't add
# security wrappers for them, as well as for objects created by
# other Python libraries.
unwrapped_types = frozenset((
        BaseRecipeBranch,
        DSCFile,
        InstanceType,
        Message,
        datetime,
        int,
        str,
        unicode,
        ))


def is_security_proxied_or_harmless(obj):
    """Check that the object is security wrapped or a harmless object."""
    if obj is None:
        return True
    if builtin_isinstance(obj, Proxy):
        return True
    if type(obj) in unwrapped_types:
        return True
    if isSequenceType(obj) or isinstance(obj, (set, frozenset)):
        return all(
            is_security_proxied_or_harmless(element)
            for element in obj)
    if isMappingType(obj):
        return all(
            (is_security_proxied_or_harmless(key) and
             is_security_proxied_or_harmless(obj[key]))
            for key in obj)
    return False


class UnproxiedFactoryMethodWarning(UserWarning):
    """Raised when someone calls an unproxied factory method."""

    def __init__(self, method_name):
        super(UnproxiedFactoryMethodWarning, self).__init__(
            "PLEASE FIX: LaunchpadObjectFactory.%s returns an "
            "unproxied object." % (method_name, ))


class ShouldThisBeUsingRemoveSecurityProxy(UserWarning):
    """Raised when there is a potentially bad call to removeSecurityProxy."""

    def __init__(self, obj):
        message = (
            "removeSecurityProxy(%r) called. Is this correct? "
            "Either call it directly or fix the test." % obj)
        super(ShouldThisBeUsingRemoveSecurityProxy, self).__init__(message)


class LaunchpadObjectFactory:
    """A wrapper around `BareLaunchpadObjectFactory`.

    Ensure that each object created by a `BareLaunchpadObjectFactory` method
    is either of a simple Python type or is security proxied.

    A warning message is printed to stderr if a factory method creates
    an object without a security proxy.

    Whereever you see such a warning: fix it!
    """

    def __init__(self):
        self._factory = BareLaunchpadObjectFactory()

    def __getattr__(self, name):
        attr = getattr(self._factory, name)
        if os.environ.get('LP_PROXY_WARNINGS') == '1' and callable(attr):

            def guarded_method(*args, **kw):
                result = attr(*args, **kw)
                if not is_security_proxied_or_harmless(result):
                    warnings.warn(
                        UnproxiedFactoryMethodWarning(name), stacklevel=1)
                return result
            return guarded_method
        else:
            return attr

    def __dir__(self):
        """Enumerate the attributes and methods of the wrapped object factory.

        This is especially useful for interactive users."""
        return dir(self._factory)


def remove_security_proxy_and_shout_at_engineer(obj):
    """Remove an object's security proxy and print a warning.

    A number of LaunchpadObjectFactory methods returned objects without
    a security proxy. This is now no longer possible, but a number of
    tests rely on unrestricted access to object attributes.

    This function should only be used in legacy tests which fail because
    they expect unproxied objects.
    """
    if os.environ.get('LP_PROXY_WARNINGS') == '1':
        warnings.warn(ShouldThisBeUsingRemoveSecurityProxy(obj), stacklevel=2)
    return removeSecurityProxy(obj)
