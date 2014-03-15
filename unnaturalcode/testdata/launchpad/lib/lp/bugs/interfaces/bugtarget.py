# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces related to bugs."""

__metaclass__ = type

__all__ = [
    'BugDistroSeriesTargetDetails',
    'IBugTarget',
    'IHasBugs',
    'IHasExpirableBugs',
    'IHasOfficialBugTags',
    'IOfficialBugTag',
    'IOfficialBugTagTarget',
    'IOfficialBugTagTargetPublic',
    'IOfficialBugTagTargetRestricted',
    'ISeriesBugTarget',
    'BUG_POLICY_ALLOWED_TYPES',
    'BUG_POLICY_DEFAULT_TYPES',
    ]


from lazr.enum import DBEnumeratedType
from lazr.restful.declarations import (
    call_with,
    export_as_webservice_entry,
    export_read_operation,
    export_write_operation,
    exported,
    LAZR_WEBSERVICE_EXPORTED,
    operation_for_version,
    operation_parameters,
    operation_removed_in_version,
    operation_returns_collection_of,
    REQUEST_USER,
    )
from lazr.restful.fields import Reference
from lazr.restful.interface import copy_field
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    List,
    Object,
    Text,
    TextLine,
    )

from lp import _
from lp.app.enums import (
    FREE_INFORMATION_TYPES,
    InformationType,
    NON_EMBARGOED_INFORMATION_TYPES,
    PROPRIETARY_INFORMATION_TYPES,
    )
from lp.bugs.interfaces.bugtask import IBugTask
from lp.bugs.interfaces.bugtasksearch import (
    BugBlueprintSearch,
    BugBranchSearch,
    BugTagsSearchCombinator,
    IBugTaskSearch,
    )
from lp.registry.enums import BugSharingPolicy
from lp.services.fields import Tag


search_tasks_params_common = {
    "order_by": List(
        title=_('List of fields by which the results are ordered.'),
        value_type=Text(),
        required=False),
    "search_text": copy_field(IBugTaskSearch['searchtext']),
    "status": copy_field(IBugTaskSearch['status']),
    "importance": copy_field(IBugTaskSearch['importance']),
    "information_type": copy_field(IBugTaskSearch['information_type']),
    "assignee": Reference(schema=Interface),
    "bug_reporter": Reference(schema=Interface),
    "bug_supervisor": Reference(schema=Interface),
    "bug_commenter": Reference(schema=Interface),
    "bug_subscriber": Reference(schema=Interface),
    "structural_subscriber": Reference(schema=Interface),
    "owner": Reference(schema=Interface),
    "affected_user": Reference(schema=Interface),
    "has_patch": copy_field(IBugTaskSearch['has_patch']),
    "has_cve": copy_field(IBugTaskSearch['has_cve']),
    "tags": copy_field(IBugTaskSearch['tag']),
    "tags_combinator": copy_field(IBugTaskSearch['tags_combinator']),
    "omit_duplicates": copy_field(IBugTaskSearch['omit_dupes']),
    "status_upstream": copy_field(IBugTaskSearch['status_upstream']),
    "milestone": copy_field(IBugTaskSearch['milestone']),
    "component": copy_field(IBugTaskSearch['component']),
    "nominated_for": Reference(schema=Interface),
    "has_no_package": copy_field(IBugTaskSearch['has_no_package']),
    "hardware_bus": Choice(
        title=_(u"The bus of a hardware device related to a bug"),
        # The vocabulary should be HWBus; this is fixed in
        # _schema_circular_imports to avoid circular imports.
        vocabulary=DBEnumeratedType, required=False),
    "hardware_vendor_id": TextLine(
        title=_(
            u"The vendor ID of a hardware device related to a bug."),
        description=_(
            u"Allowed values of the vendor ID depend on the bus of the "
            "device.\n\n"
            "Vendor IDs of PCI, PCCard and USB devices are hexadecimal "
            "string representations of 16 bit integers in the format "
            "'0x01ab': The prefix '0x', followed by exactly 4 digits; "
            "where a digit is one of the characters 0..9, a..f. The "
            "characters A..F are not allowed.\n\n"
            "SCSI vendor IDs are strings with exactly 8 characters. "
            "Shorter names are right-padded with space (0x20) characters."
            "\n\n"
            "IDs for other buses may be arbitrary strings."),
        required=False),
    "hardware_product_id": TextLine(
        title=_(
            u"The product ID of a hardware device related to a bug."),
        description=_(
            u"Allowed values of the product ID depend on the bus of the "
            "device.\n\n"
            "Product IDs of PCI, PCCard and USB devices are hexadecimal "
            "string representations of 16 bit integers in the format "
            "'0x01ab': The prefix '0x', followed by exactly 4 digits; "
            "where a digit is one of the characters 0..9, a..f. The "
            "characters A..F are not allowed.\n\n"
            "SCSI product IDs are strings with exactly 16 characters. "
            "Shorter names are right-padded with space (0x20) characters."
            "\n\n"
            "IDs for other buses may be arbitrary strings."),
        required=False),
    "hardware_driver_name": TextLine(
        title=_(
            u"The driver controlling a hardware device related to a "
            "bug."),
        required=False),
    "hardware_driver_package_name": TextLine(
        title=_(
            u"The package of the driver which controls a hardware "
            "device related to a bug."),
        required=False),
    "hardware_owner_is_bug_reporter": Bool(
        title=_(
            u"Search for bugs reported by people who own the given "
            "device or who use the given hardware driver."),
        required=False),
    "hardware_owner_is_affected_by_bug": Bool(
        title=_(
            u"Search for bugs where people affected by a bug own the "
            "given device or use the given hardware driver."),
        required=False),
    "hardware_owner_is_subscribed_to_bug": Bool(
        title=_(
            u"Search for bugs where a bug subscriber owns the "
            "given device or uses the given hardware driver."),
        required=False),
    "hardware_is_linked_to_bug": Bool(
        title=_(
            u"Search for bugs which are linked to hardware reports "
            "which contain the given device or whcih contain a device"
            "controlled by the given driver."),
        required=False),
    "linked_branches": Choice(
        title=_(
            u"Search for bugs that are linked to branches or for bugs "
            "that are not linked to branches."),
        vocabulary=BugBranchSearch, required=False),
    "modified_since": Datetime(
        title=_(
            u"Search for bugs that have been modified since the given "
            "date."),
        required=False),
    "created_since": Datetime(
        title=_(
            u"Search for bugs that have been created since the given "
            "date."),
        required=False),
    "created_before": Datetime(
        title=_(
            u"Search for bugs that were created before the given "
            "date."),
        required=False),
    }

search_tasks_params_for_api_default = dict(
    search_tasks_params_common,
    omit_targeted=copy_field(
        IBugTaskSearch['omit_targeted']))

search_tasks_params_for_api_devel = dict(
    search_tasks_params_common,
    omit_targeted=copy_field(
        IBugTaskSearch['omit_targeted'], default=False),
    linked_blueprints=Choice(
        title=_(
            u"Search for bugs that are linked to blueprints or for "
            u"bugs that are not linked to blueprints."),
        vocabulary=BugBlueprintSearch, required=False))


BUG_POLICY_ALLOWED_TYPES = {
    BugSharingPolicy.PUBLIC: FREE_INFORMATION_TYPES,
    BugSharingPolicy.PUBLIC_OR_PROPRIETARY: NON_EMBARGOED_INFORMATION_TYPES,
    BugSharingPolicy.PROPRIETARY_OR_PUBLIC: NON_EMBARGOED_INFORMATION_TYPES,
    BugSharingPolicy.PROPRIETARY: (InformationType.PROPRIETARY,),
    BugSharingPolicy.FORBIDDEN: [],
    BugSharingPolicy.EMBARGOED_OR_PROPRIETARY: PROPRIETARY_INFORMATION_TYPES,
    }

BUG_POLICY_DEFAULT_TYPES = {
    BugSharingPolicy.PUBLIC: InformationType.PUBLIC,
    BugSharingPolicy.PUBLIC_OR_PROPRIETARY: InformationType.PUBLIC,
    BugSharingPolicy.PROPRIETARY_OR_PUBLIC: InformationType.PROPRIETARY,
    BugSharingPolicy.PROPRIETARY: InformationType.PROPRIETARY,
    BugSharingPolicy.FORBIDDEN: None,
    BugSharingPolicy.EMBARGOED_OR_PROPRIETARY: InformationType.EMBARGOED,
    }


class IHasBugs(Interface):
    """An entity which has a collection of bug tasks."""

    export_as_webservice_entry()

    # searchTasks devel API declaration.
    @call_with(search_params=None, user=REQUEST_USER)
    @operation_parameters(**search_tasks_params_for_api_devel)
    @operation_returns_collection_of(IBugTask)
    @export_read_operation()
    #
    # Pop the *default* version (decorators are run last to first).
    @operation_removed_in_version('devel')
    #
    # searchTasks default API declaration.
    @call_with(search_params=None, user=REQUEST_USER)
    @operation_parameters(**search_tasks_params_for_api_default)
    @operation_returns_collection_of(IBugTask)
    @export_read_operation()
    @operation_for_version('beta')
    def searchTasks(search_params, user=None,
                    order_by=None, search_text=None,
                    status=None, importance=None,
                    assignee=None, bug_reporter=None, bug_supervisor=None,
                    bug_commenter=None, bug_subscriber=None, owner=None,
                    affected_user=None, has_patch=None, has_cve=None,
                    distribution=None, tags=None,
                    tags_combinator=BugTagsSearchCombinator.ALL,
                    omit_duplicates=True, omit_targeted=None,
                    status_upstream=None, milestone=None, component=None,
                    nominated_for=None, sourcepackagename=None,
                    has_no_package=None, hardware_bus=None,
                    hardware_vendor_id=None, hardware_product_id=None,
                    hardware_driver_name=None,
                    hardware_driver_package_name=None,
                    hardware_owner_is_bug_reporter=None,
                    hardware_owner_is_affected_by_bug=False,
                    hardware_owner_is_subscribed_to_bug=False,
                    hardware_is_linked_to_bug=False, linked_branches=None,
                    linked_blueprints=None, structural_subscriber=None,
                    modified_since=None, created_since=None,
                    created_before=None, information_type=None):
        """Search the IBugTasks reported on this entity.

        :search_params: a BugTaskSearchParams object

        Return an iterable of matching results.

        Note: milestone is currently ignored for all IBugTargets
        except IProduct.

        In order to search bugs that are related to a given hardware
        device, you must specify the bus, the vendor ID, the product
        ID of the device and set at least one of
        hardware_owner_is_bug_reporter,
        hardware_owner_is_affected_by_bug,
        hardware_owner_is_subscribed_to_bug,
        hardware_is_linked_to_bug to True.
        """

    def getBugTaskWeightFunction():
        """Return a function that is used to weight the bug tasks.

        The function should take a bug task as a parameter and return
        an OrderedBugTask.

        The ordered bug tasks are used to choose the most relevant bug task
        for any particular context.
        """


class IHasExpirableBugs(Interface):
    """Marker interface for entities supporting querying expirable bugs"""


class IBugTarget(IHasBugs):
    """An entity on which a bug can be reported.

    Examples include an IDistribution, an IDistroSeries and an
    IProduct.
    """

    export_as_webservice_entry()

    # XXX Brad Bollenbach 2006-08-02 bug=54974: This attribute name smells.
    bugtargetdisplayname = Attribute("A display name for this bug target")
    bugtargetname = Attribute("The target as shown in mail notifications.")

    pillar = Attribute("The pillar containing this target.")

    bug_reporting_guidelines = exported(
        Text(
            title=(
                u"Helpful guidelines for reporting a bug"),
            description=(
                u"These guidelines will be shown to "
                "everyone reporting a bug and should be "
                "text or a bulleted list with your particular "
                "requirements, if any."),
            required=False,
            max_length=50000))

    bug_reported_acknowledgement = exported(
        Text(
            title=(
                u"After reporting a bug, I can expect the following."),
            description=(
                u"This message of acknowledgement will be displayed "
                "to anyone after reporting a bug."),
            required=False,
            max_length=50000))

    enable_bugfiling_duplicate_search = Bool(
        title=u"Search for possible duplicate bugs when a new bug is filed",
        description=(
            u"If enabled, Launchpad searches the project for bugs which "
            u"could match the summary given by the bug reporter. However, "
            u"this can lead users to mistake an existing bug as the one "
            u"they want to report. This can happen for example for hardware "
            u"related bugs where the one symptom can be caused by "
            u"completely different hardware and drivers."),
        required=False)

    def createBug(bug_params):
        """Create a new bug on this target.

        bug_params is an instance of `CreateBugParams`.
        """

# We assign the schema for an `IBugTask` attribute here
# in order to avoid circular dependencies.
IBugTask['target'].schema = IBugTarget
IBugTask['transitionToTarget'].getTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)['params']['target'].schema = IBugTarget


class BugDistroSeriesTargetDetails:
    """The details of a bug targeted to a specific IDistroSeries.

    The following attributes are provided:

    :series: The IDistroSeries.
    :istargeted: Is there a fix targeted to this series?
    :sourcepackage: The sourcepackage to which the fix would be targeted.
    :assignee: An IPerson, or None if no assignee.
    :status: A BugTaskStatus dbschema item, or None, if series is not
        targeted.
    """

    def __init__(self, series, istargeted=False, sourcepackage=None,
                 assignee=None, status=None):
        self.series = series
        self.istargeted = istargeted
        self.sourcepackage = sourcepackage
        self.assignee = assignee
        self.status = status


class IHasOfficialBugTags(Interface):
    """An entity that exposes a set of official bug tags."""

    official_bug_tags = exported(List(
        title=_("Official Bug Tags"),
        description=_("The list of bug tags defined as official."),
        value_type=Tag(),
        readonly=True))

    def getUsedBugTagsWithOpenCounts(user, tag_limit=0, include_tags=None):
        """Return name and bug count of tags having open bugs.

        :param user: The user who wants the report.
        :param tag_limit: The number of tags to return (excludes those found
            by matching include_tags). If 0 then all tags are returned. If
            non-zero then the most frequently used tags are returned.
        :param include_tags: A list of string tags to return irrespective of
            usage. Tags in this list that have no open bugs are returned with
            a count of 0. May be None if there are tags to require inclusion
            of.
        :return: A dict from tag -> count.
        """

    def _getOfficialTagClause():
        """Get the storm clause for finding this targets tags."""


class IOfficialBugTagTargetPublic(IHasOfficialBugTags):
    """Public attributes for `IOfficialBugTagTarget`."""

    official_bug_tags = copy_field(
        IHasOfficialBugTags['official_bug_tags'], readonly=False)


class IOfficialBugTagTargetRestricted(Interface):
    """Restricted methods for `IOfficialBugTagTarget`."""

    @operation_parameters(
        tag=Tag(title=u'The official bug tag', required=True))
    @export_write_operation()
    @operation_for_version('beta')
    def addOfficialBugTag(tag):
        """Add tag to the official bug tags of this target."""

    @operation_parameters(
        tag=Tag(title=u'The official bug tag', required=True))
    @export_write_operation()
    @operation_for_version('beta')
    def removeOfficialBugTag(tag):
        """Remove tag from the official bug tags of this target."""


class IOfficialBugTagTarget(IOfficialBugTagTargetPublic,
                            IOfficialBugTagTargetRestricted):
    """An entity for which official bug tags can be defined."""
    # XXX intellectronica 2009-03-16 bug=342413
    # We can start using straight inheritance once it becomes possible
    # to export objects implementing multiple interfaces in the
    # webservice API.


class IOfficialBugTag(Interface):
    """Official bug tags for a product, a project or a distribution."""
    tag = Tag(
        title=u'The official bug tag', required=True)

    target = Object(
        title=u'The target of this bug tag.',
        schema=IOfficialBugTagTarget,
        description=(
            u'The distribution or product having this official bug tag.'))


class ISeriesBugTarget(Interface):
    """An `IBugTarget` which is a series."""

    series = Attribute(
        "The product or distribution series of this series bug target.")
    bugtarget_parent = Attribute(
        "Non-series parent of this series bug target.")
