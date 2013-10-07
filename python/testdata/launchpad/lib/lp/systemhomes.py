# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Content classes for the 'home pages' of the subsystems of Launchpad."""

__all__ = [
    'BazaarApplication',
    'CodeImportSchedulerApplication',
    'FeedsApplication',
    'MailingListApplication',
    'MaloneApplication',
    'PrivateMaloneApplication',
    'RosettaApplication',
    'TestOpenIDApplication',
    ]

__metaclass__ = type

import codecs
import os

from lazr.restful import ServiceRootResource
from lazr.restful.interfaces import ITopLevelEntryLink
from storm.expr import Max
from zope.component import getUtility
from zope.interface import implements

from lp.app.enums import PRIVATE_INFORMATION_TYPES
from lp.bugs.adapters.bug import convert_to_information_type
from lp.bugs.interfaces.bug import (
    CreateBugParams,
    IBugSet,
    )
from lp.bugs.interfaces.bugtask import IBugTaskSet
from lp.bugs.interfaces.bugtasksearch import BugTaskSearchParams
from lp.bugs.interfaces.bugtracker import IBugTrackerSet
from lp.bugs.interfaces.bugwatch import IBugWatchSet
from lp.bugs.interfaces.malone import (
    IMaloneApplication,
    IPrivateMaloneApplication,
    )
from lp.bugs.model.bug import Bug
from lp.code.interfaces.codehosting import (
    IBazaarApplication,
    ICodehostingApplication,
    )
from lp.code.interfaces.codeimportscheduler import (
    ICodeImportSchedulerApplication,
    )
from lp.hardwaredb.interfaces.hwdb import (
    IHWDBApplication,
    IHWDeviceSet,
    IHWDriverSet,
    IHWSubmissionDeviceSet,
    IHWSubmissionSet,
    IHWVendorIDSet,
    ParameterError,
    )
from lp.registry.interfaces.distroseries import IDistroSeriesSet
from lp.registry.interfaces.mailinglist import IMailingListApplication
from lp.registry.interfaces.product import IProductSet
from lp.services.config import config
from lp.services.database.interfaces import IStore
from lp.services.feeds.interfaces.application import IFeedsApplication
from lp.services.statistics.interfaces.statistic import ILaunchpadStatisticSet
from lp.services.webapp.interfaces import (
    ICanonicalUrlData,
    ILaunchBag,
    )
from lp.services.webapp.publisher import canonical_url
from lp.services.webservice.interfaces import IWebServiceApplication
from lp.services.worlddata.interfaces.language import ILanguageSet
from lp.testopenid.interfaces.server import ITestOpenIDApplication
from lp.translations.interfaces.translationgroup import ITranslationGroupSet
from lp.translations.interfaces.translations import IRosettaApplication
from lp.translations.interfaces.translationsoverview import (
    ITranslationsOverview,
    )


class CodehostingApplication:
    """Codehosting End-Point."""
    implements(ICodehostingApplication)

    title = "Codehosting API"


class CodeImportSchedulerApplication:
    """CodeImportScheduler End-Point."""
    implements(ICodeImportSchedulerApplication)

    title = "Code Import Scheduler"


class PrivateMaloneApplication:
    """ExternalBugTracker authentication token end-point."""
    implements(IPrivateMaloneApplication)

    title = "Launchpad Bugs."


class MailingListApplication:
    implements(IMailingListApplication)


class FeedsApplication:
    implements(IFeedsApplication)


class MaloneApplication:
    implements(IMaloneApplication)

    def __init__(self):
        self.title = 'Malone: the Launchpad bug tracker'

    def searchTasks(self, search_params):
        """See `IMaloneApplication`."""
        return getUtility(IBugTaskSet).search(search_params)

    def getBugData(self, user, bug_id, related_bug=None):
        """See `IMaloneApplication`."""
        search_params = BugTaskSearchParams(user, bug=bug_id)
        bugtasks = getUtility(IBugTaskSet).search(search_params)
        if not bugtasks:
            return []
        bugs = [task.bug for task in bugtasks]
        data = []
        for bug in bugs:
            bugtask = bug.default_bugtask
            different_pillars = related_bug and (
                set(bug.affected_pillars).isdisjoint(
                    related_bug.affected_pillars)) or False
            data.append({
                'id': bug_id,
                'information_type': bug.information_type.title,
                'is_private':
                    bug.information_type in PRIVATE_INFORMATION_TYPES,
                'importance': bugtask.importance.title,
                'importance_class': 'importance' + bugtask.importance.name,
                'status': bugtask.status.title,
                'status_class': 'status' + bugtask.status.name,
                'bug_summary': bug.title,
                'description': bug.description,
                'bug_url': canonical_url(bugtask),
                'different_pillars': different_pillars})
        return data

    def createBug(self, owner, title, description, target,
                  information_type=None, tags=None,
                  security_related=None, private=None):
        """See `IMaloneApplication`."""
        if (information_type is None
            and (security_related is not None or private is not None)):
            # Adapt the deprecated args to information_type.
            information_type = convert_to_information_type(
                private, security_related)
        params = CreateBugParams(
            title=title, comment=description, owner=owner,
            information_type=information_type, tags=tags, target=target)
        return getUtility(IBugSet).createBug(params)

    @property
    def bug_count(self):
        return IStore(Bug).find(Max(Bug.id)).one()

    @property
    def bugwatch_count(self):
        return getUtility(IBugWatchSet).search().count()

    @property
    def bugtask_count(self):
        user = getUtility(ILaunchBag).user
        search_params = BugTaskSearchParams(user=user)
        return getUtility(IBugTaskSet).search(search_params).count()

    @property
    def bugtracker_count(self):
        return getUtility(IBugTrackerSet).count

    @property
    def projects_with_bugs_count(self):
        return getUtility(ILaunchpadStatisticSet).value('projects_with_bugs')

    @property
    def shared_bug_count(self):
        return getUtility(ILaunchpadStatisticSet).value('shared_bug_count')

    @property
    def top_bugtrackers(self):
        return getUtility(IBugTrackerSet).getMostActiveBugTrackers(limit=5)

    def empty_list(self):
        """See `IMaloneApplication`."""
        return []


class BazaarApplication:
    implements(IBazaarApplication)

    def __init__(self):
        self.title = 'The Open Source Bazaar'


class RosettaApplication:
    implements(IRosettaApplication)

    def __init__(self):
        self.title = 'Rosetta: Translations in the Launchpad'
        self.name = 'Rosetta'

    @property
    def languages(self):
        """See `IRosettaApplication`."""
        return getUtility(ILanguageSet)

    @property
    def language_count(self):
        """See `IRosettaApplication`."""
        stats = getUtility(ILaunchpadStatisticSet)
        return stats.value('language_count')

    @property
    def statsdate(self):
        stats = getUtility(ILaunchpadStatisticSet)
        return stats.dateupdated('potemplate_count')

    @property
    def translation_groups(self):
        """See `IRosettaApplication`."""
        return getUtility(ITranslationGroupSet)

    def translatable_products(self):
        """See `IRosettaApplication`."""
        products = getUtility(IProductSet)
        return products.getTranslatables()

    def featured_products(self):
        """See `IRosettaApplication`."""
        projects = getUtility(ITranslationsOverview)
        for project in projects.getMostTranslatedPillars():
            yield {
                'pillar': project['pillar'],
                'font_size': project['weight'] * 10,
                }

    def translatable_distroseriess(self):
        """See `IRosettaApplication`."""
        distroseriess = getUtility(IDistroSeriesSet)
        return distroseriess.translatables()

    def potemplate_count(self):
        """See `IRosettaApplication`."""
        stats = getUtility(ILaunchpadStatisticSet)
        return stats.value('potemplate_count')

    def pofile_count(self):
        """See `IRosettaApplication`."""
        stats = getUtility(ILaunchpadStatisticSet)
        return stats.value('pofile_count')

    def pomsgid_count(self):
        """See `IRosettaApplication`."""
        stats = getUtility(ILaunchpadStatisticSet)
        return stats.value('pomsgid_count')

    def translator_count(self):
        """See `IRosettaApplication`."""
        stats = getUtility(ILaunchpadStatisticSet)
        return stats.value('translator_count')


class HWDBApplication:
    """See `IHWDBApplication`."""
    implements(IHWDBApplication, ITopLevelEntryLink)

    link_name = 'hwdb'
    entry_type = IHWDBApplication

    def devices(self, bus, vendor_id, product_id=None):
        """See `IHWDBApplication`."""
        return getUtility(IHWDeviceSet).search(bus, vendor_id, product_id)

    def drivers(self, package_name=None, name=None):
        """See `IHWDBApplication`."""
        return getUtility(IHWDriverSet).search(package_name, name)

    def vendorIDs(self, bus):
        """See `IHWDBApplication`."""
        return getUtility(IHWVendorIDSet).idsForBus(bus)

    @property
    def driver_names(self):
        """See `IHWDBApplication`."""
        return getUtility(IHWDriverSet).all_driver_names()

    @property
    def package_names(self):
        """See `IHWDBApplication`."""
        return getUtility(IHWDriverSet).all_package_names()

    def search(self, user=None, device=None, driver=None, distribution=None,
               distroseries=None, architecture=None, owner=None,
               created_before=None, created_after=None,
               submitted_before=None, submitted_after=None):
        """See `IHWDBApplication`."""
        return getUtility(IHWSubmissionSet).search(
            user=user, device=device, driver=driver,
            distribution=distribution, distroseries=distroseries,
            architecture=architecture, owner=owner,
            created_before=created_before, created_after=created_after,
            submitted_before=submitted_before,
            submitted_after=submitted_after)

    def getDistroTarget(self, distribution, distroseries, distroarchseries):
        distro_targets = [
            target for target in (
                distribution, distroseries, distroarchseries)
            if target is not None]
        if len(distro_targets) == 0:
            return None
        elif len(distro_targets) == 1:
            return distro_targets[0]
        else:
            raise ParameterError(
                'Only one of `distribution`, `distroseries` or '
                '`distroarchseries` can be present.')

    def numSubmissionsWithDevice(
        self, bus=None, vendor_id=None, product_id=None, driver_name=None,
        package_name=None, distribution=None, distroseries=None,
        distroarchseries=None):
        """See `IHWDBApplication`."""
        submissions_with_device, all_submissions = (
            getUtility(IHWSubmissionSet).numSubmissionsWithDevice(
                bus, vendor_id, product_id, driver_name, package_name,
                distro_target=self.getDistroTarget(
                    distribution, distroseries, distroarchseries)))
        return {
            'submissions_with_device': submissions_with_device,
            'all_submissions': all_submissions,
            }

    def numOwnersOfDevice(
        self, bus=None, vendor_id=None, product_id=None, driver_name=None,
        package_name=None, distribution=None, distroseries=None,
        distroarchseries=None):
        """See `IHWDBApplication`."""
        owners, all_submitters = (
            getUtility(IHWSubmissionSet).numOwnersOfDevice(
                bus, vendor_id, product_id, driver_name, package_name,
                distro_target=self.getDistroTarget(
                    distribution, distroseries, distroarchseries)))
        return {
            'owners': owners,
            'all_submitters': all_submitters,
            }

    def numDevicesInSubmissions(
        self, bus=None, vendor_id=None, product_id=None, driver_name=None,
        package_name=None, distribution=None, distroseries=None,
        distroarchseries=None):
        """See `IHWDBApplication`."""
        return getUtility(IHWSubmissionDeviceSet).numDevicesInSubmissions(
                bus, vendor_id, product_id, driver_name, package_name,
                distro_target=self.getDistroTarget(
                    distribution, distroseries, distroarchseries))

    def deviceDriverOwnersAffectedByBugs(
        self, bus=None, vendor_id=None, product_id=None, driver_name=None,
        package_name=None, bug_ids=None, bug_tags=None, affected_by_bug=False,
        subscribed_to_bug=False, user=None):
        """See `IHWDBApplication`."""
        return getUtility(IHWSubmissionSet).deviceDriverOwnersAffectedByBugs(
            bus, vendor_id, product_id, driver_name, package_name, bug_ids,
            bug_tags, affected_by_bug, subscribed_to_bug, user)

    def hwInfoByBugRelatedUsers(
        self, bug_ids=None, bug_tags=None, affected_by_bug=False,
        subscribed_to_bug=False, user=None):
        """See `IHWDBApplication`."""
        return getUtility(IHWSubmissionSet).hwInfoByBugRelatedUsers(
            bug_ids, bug_tags, affected_by_bug, subscribed_to_bug, user)


class WebServiceApplication(ServiceRootResource):
    """See `IWebServiceApplication`.

    This implementation adds a 'cached_wadl' attribute, which starts
    out as an empty dict and is populated as needed.
    """
    implements(IWebServiceApplication, ICanonicalUrlData)

    inside = None
    path = ''
    rootsite = None

    cached_wadl = {}

    # This should only be used by devel instances: production serves root
    # WADL (and JSON) from the filesystem.

    @classmethod
    def cachedWADLPath(cls, instance_name, version):
        """Helper method to calculate the path to a cached WADL file."""
        return os.path.join(
            config.root, 'lib', 'canonical', 'launchpad',
            'apidoc', version, '%s.wadl' % (instance_name,))

    def toWADL(self):
        """See `IWebServiceApplication`.

        Look for a cached WADL file for the request version at the
        location used by the script
        utilities/create-launchpad-wadl.py. If the file is present,
        load the file and cache its contents rather than generating
        new WADL. Otherwise, generate new WADL and cache it.
        """
        version = self.request.version
        if self.__class__.cached_wadl is None:
            # The cache has been disabled for testing
            # purposes. Generate the WADL.
            return super(WebServiceApplication, self).toWADL()
        if  version not in self.__class__.cached_wadl:
            # It's not cached. Look for it on disk.
            _wadl_filename = self.cachedWADLPath(
                config.instance_name, version)
            _wadl_fd = None
            try:
                _wadl_fd = codecs.open(_wadl_filename, encoding='UTF-8')
                try:
                    wadl = _wadl_fd.read()
                finally:
                    _wadl_fd.close()
            except IOError:
                # It's not on disk; generate it.
                wadl = super(WebServiceApplication, self).toWADL()
            del _wadl_fd
            self.__class__.cached_wadl[version] = wadl
        return self.__class__.cached_wadl[version]


class TestOpenIDApplication:
    implements(ITestOpenIDApplication)
