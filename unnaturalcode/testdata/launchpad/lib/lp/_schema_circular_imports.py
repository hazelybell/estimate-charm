# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Update the interface schema values due to circular imports.

There are situations where there would normally be circular imports to define
the necessary schema values in some interface fields.  To avoid this the
schema is initially set to `Interface`, but this needs to be updated once the
types are defined.
"""

__metaclass__ = type


__all__ = []


from lazr.restful.declarations import LAZR_WEBSERVICE_EXPORTED
from lazr.restful.fields import Reference

from lp.blueprints.interfaces.specification import ISpecification
from lp.blueprints.interfaces.specificationbranch import ISpecificationBranch
from lp.blueprints.interfaces.specificationtarget import (
    IHasSpecifications,
    ISpecificationTarget,
    )
from lp.bugs.enums import BugNotificationLevel
from lp.bugs.interfaces.bug import (
    IBug,
    IFrontPageBugAddForm,
    )
from lp.bugs.interfaces.bugactivity import IBugActivity
from lp.bugs.interfaces.bugattachment import IBugAttachment
from lp.bugs.interfaces.bugbranch import IBugBranch
from lp.bugs.interfaces.bugnomination import IBugNomination
from lp.bugs.interfaces.bugsubscriptionfilter import IBugSubscriptionFilter
from lp.bugs.interfaces.bugtarget import (
    IBugTarget,
    IHasBugs,
    )
from lp.bugs.interfaces.bugtask import IBugTask
from lp.bugs.interfaces.bugtracker import (
    IBugTracker,
    IBugTrackerComponent,
    IBugTrackerComponentGroup,
    IBugTrackerSet,
    )
from lp.bugs.interfaces.bugwatch import IBugWatch
from lp.bugs.interfaces.cve import ICve
from lp.bugs.interfaces.malone import IMaloneApplication
from lp.bugs.interfaces.structuralsubscription import (
    IStructuralSubscription,
    IStructuralSubscriptionTarget,
    )
from lp.buildmaster.enums import BuildStatus
from lp.buildmaster.interfaces.builder import (
    IBuilder,
    IBuilderSet,
    )
from lp.buildmaster.interfaces.buildfarmjob import IBuildFarmJob
from lp.buildmaster.interfaces.buildqueue import IBuildQueue
from lp.code.interfaces.branch import (
    IBranch,
    IBranchSet,
    )
from lp.code.interfaces.branchmergeproposal import IBranchMergeProposal
from lp.code.interfaces.branchmergequeue import IBranchMergeQueue
from lp.code.interfaces.branchsubscription import IBranchSubscription
from lp.code.interfaces.codeimport import ICodeImport
from lp.code.interfaces.codereviewcomment import ICodeReviewComment
from lp.code.interfaces.codereviewvote import ICodeReviewVoteReference
from lp.code.interfaces.diff import IPreviewDiff
from lp.code.interfaces.hasbranches import (
    IHasBranches,
    IHasCodeImports,
    IHasMergeProposals,
    IHasRequestedReviews,
    )
from lp.code.interfaces.hasrecipes import IHasRecipes
from lp.code.interfaces.sourcepackagerecipe import ISourcePackageRecipe
from lp.code.interfaces.sourcepackagerecipebuild import (
    ISourcePackageRecipeBuild,
    )
from lp.hardwaredb.interfaces.hwdb import (
    HWBus,
    IHWDBApplication,
    IHWDevice,
    IHWDeviceClass,
    IHWDriver,
    IHWDriverName,
    IHWDriverPackageName,
    IHWSubmission,
    IHWSubmissionDevice,
    IHWVendorID,
    )
from lp.registry.enums import (
    DistroSeriesDifferenceStatus,
    DistroSeriesDifferenceType,
    )
from lp.registry.interfaces.commercialsubscription import (
    ICommercialSubscription,
    )
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.distributionmirror import IDistributionMirror
from lp.registry.interfaces.distributionsourcepackage import (
    IDistributionSourcePackage,
    )
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.distroseriesdifference import (
    IDistroSeriesDifference,
    )
from lp.registry.interfaces.distroseriesdifferencecomment import (
    IDistroSeriesDifferenceComment,
    )
from lp.registry.interfaces.gpg import IGPGKey
from lp.registry.interfaces.irc import IIrcID
from lp.registry.interfaces.jabber import IJabberID
from lp.registry.interfaces.milestone import (
    IHasMilestones,
    IMilestone,
    )
from lp.registry.interfaces.person import (
    IPerson,
    IPersonEditRestricted,
    IPersonLimitedView,
    IPersonViewRestricted,
    ITeam,
    )
from lp.registry.interfaces.pillar import (
    IPillar,
    IPillarNameSet,
    )
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.product import (
    IProduct,
    IProductSet,
    )
from lp.registry.interfaces.productrelease import (
    IProductRelease,
    IProductReleaseFile,
    )
from lp.registry.interfaces.productseries import (
    IProductSeries,
    ITimelineProductSeries,
    )
from lp.registry.interfaces.projectgroup import (
    IProjectGroup,
    IProjectGroupSet,
    )
from lp.registry.interfaces.sourcepackage import (
    ISourcePackage,
    ISourcePackageEdit,
    ISourcePackagePublic,
    )
from lp.registry.interfaces.ssh import ISSHKey
from lp.registry.interfaces.teammembership import ITeamMembership
from lp.registry.interfaces.wikiname import IWikiName
from lp.services.comments.interfaces.conversation import IComment
from lp.services.messages.interfaces.message import (
    IIndexedMessage,
    IMessage,
    IUserToUserEmail,
    )
from lp.services.webservice.apihelpers import (
    patch_choice_parameter_type,
    patch_choice_vocabulary,
    patch_collection_property,
    patch_collection_return_type,
    patch_entry_explicit_version,
    patch_entry_return_type,
    patch_list_parameter_type,
    patch_operations_explicit_version,
    patch_plain_parameter_type,
    patch_reference_property,
    )
from lp.services.worlddata.interfaces.country import (
    ICountry,
    ICountrySet,
    )
from lp.services.worlddata.interfaces.language import (
    ILanguage,
    ILanguageSet,
    )
from lp.soyuz.enums import (
    PackagePublishingStatus,
    PackageUploadCustomFormat,
    PackageUploadStatus,
    )
from lp.soyuz.interfaces.archive import IArchive
from lp.soyuz.interfaces.archivedependency import IArchiveDependency
from lp.soyuz.interfaces.archivepermission import IArchivePermission
from lp.soyuz.interfaces.archivesubscriber import IArchiveSubscriber
from lp.soyuz.interfaces.binarypackagebuild import IBinaryPackageBuild
from lp.soyuz.interfaces.binarypackagerelease import (
    IBinaryPackageReleaseDownloadCount,
    )
from lp.soyuz.interfaces.buildrecords import IHasBuildRecords
from lp.soyuz.interfaces.distroarchseries import IDistroArchSeries
from lp.soyuz.interfaces.packageset import (
    IPackageset,
    IPackagesetSet,
    )
from lp.soyuz.interfaces.processor import IProcessor
from lp.soyuz.interfaces.publishing import (
    IBinaryPackagePublishingHistory,
    IBinaryPackagePublishingHistoryEdit,
    ISourcePackagePublishingHistory,
    ISourcePackagePublishingHistoryEdit,
    ISourcePackagePublishingHistoryPublic,
    )
from lp.soyuz.interfaces.queue import IPackageUpload
from lp.soyuz.interfaces.sourcepackagerelease import ISourcePackageRelease
from lp.translations.interfaces.hastranslationimports import (
    IHasTranslationImports,
    )
from lp.translations.interfaces.hastranslationtemplates import (
    IHasTranslationTemplates,
    )
from lp.translations.interfaces.pofile import IPOFile
from lp.translations.interfaces.potemplate import (
    IPOTemplate,
    IPOTemplateSharingSubset,
    IPOTemplateSubset,
    )
from lp.translations.interfaces.translationgroup import ITranslationGroup
from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    ITranslationImportQueueEntry,
    )


IBranch['bug_branches'].value_type.schema = IBugBranch
IBranch['linked_bugs'].value_type.schema = IBug
IBranch['dependent_branches'].value_type.schema = IBranchMergeProposal
IBranch['getSubscription'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)['return_type'].schema = IBranchSubscription
IBranch['landing_candidates'].value_type.schema = IBranchMergeProposal
IBranch['landing_targets'].value_type.schema = IBranchMergeProposal
IBranch['linkBug'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)['params']['bug'].schema = IBug
IBranch['linkSpecification'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)['params']['spec'].schema = ISpecification
IBranch['product'].schema = IProduct

patch_plain_parameter_type(
    IBranch, 'setTarget', 'project', IProduct)
patch_plain_parameter_type(
    IBranch, 'setTarget', 'source_package', ISourcePackage)
patch_reference_property(IBranch, 'sourcepackage', ISourcePackage)
patch_reference_property(IBranch, 'code_import', ICodeImport)

IBranch['spec_links'].value_type.schema = ISpecificationBranch
IBranch['subscribe'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)['return_type'].schema = IBranchSubscription
IBranch['subscriptions'].value_type.schema = IBranchSubscription
IBranch['unlinkBug'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)['params']['bug'].schema = IBug
IBranch['unlinkSpecification'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)['params']['spec'].schema = ISpecification

patch_entry_return_type(IBranch, '_createMergeProposal', IBranchMergeProposal)
patch_plain_parameter_type(
    IBranch, '_createMergeProposal', 'target_branch', IBranch)
patch_plain_parameter_type(
    IBranch, '_createMergeProposal', 'prerequisite_branch', IBranch)
patch_collection_return_type(
    IBranch, 'getMergeProposals', IBranchMergeProposal)

patch_collection_return_type(
    IBranchSet, 'getMergeProposals', IBranchMergeProposal)

IBranchMergeProposal['getComment'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)['return_type'].schema = ICodeReviewComment
IBranchMergeProposal['createComment'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)['params']['parent'].schema = \
        ICodeReviewComment
patch_entry_return_type(
    IBranchMergeProposal, 'createComment', ICodeReviewComment)
IBranchMergeProposal['all_comments'].value_type.schema = ICodeReviewComment
IBranchMergeProposal['nominateReviewer'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)['return_type'].schema = ICodeReviewVoteReference
IBranchMergeProposal['votes'].value_type.schema = ICodeReviewVoteReference
patch_collection_return_type(
    IBranchMergeProposal, 'getRelatedBugTasks', IBugTask)

patch_collection_return_type(IHasBranches, 'getBranches', IBranch)
patch_collection_return_type(
    IHasMergeProposals, 'getMergeProposals', IBranchMergeProposal)
patch_collection_return_type(
    IHasRequestedReviews, 'getRequestedReviews', IBranchMergeProposal)
patch_entry_return_type(
    IHasCodeImports, 'newCodeImport', ICodeImport)
patch_plain_parameter_type(
    IHasCodeImports, 'newCodeImport', 'owner', IPerson)

# IBugTask

IBugTask['findSimilarBugs'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)['return_type'].value_type.schema = IBug
patch_plain_parameter_type(
    IBug, 'linkHWSubmission', 'submission', IHWSubmission)
patch_plain_parameter_type(
    IBug, 'unlinkHWSubmission', 'submission', IHWSubmission)
patch_collection_return_type(
    IBug, 'getHWSubmissions', IHWSubmission)
IBug['getNominations'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)['params']['nominations'].value_type.schema = (
        IBugNomination)
patch_entry_return_type(IBug, 'addNomination', IBugNomination)
patch_entry_return_type(IBug, 'getNominationFor', IBugNomination)
patch_collection_return_type(IBug, 'getNominations', IBugNomination)

patch_choice_parameter_type(
    IHasBugs, 'searchTasks', 'hardware_bus', HWBus)

IPreviewDiff['branch_merge_proposal'].schema = IBranchMergeProposal

patch_reference_property(IPersonViewRestricted, 'archive', IArchive)
patch_collection_property(IPersonViewRestricted, 'ppas', IArchive)
patch_entry_return_type(IPersonLimitedView, 'getPPAByName', IArchive)
patch_entry_return_type(IPersonEditRestricted, 'createPPA', IArchive)

IHasBuildRecords['getBuildRecords'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)[
        'params']['pocket'].vocabulary = PackagePublishingPocket
IHasBuildRecords['getBuildRecords'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)[
        'params']['build_state'].vocabulary = BuildStatus
IHasBuildRecords['getBuildRecords'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)[
        'return_type'].value_type.schema = IBinaryPackageBuild

ISourcePackagePublic['distroseries'].schema = IDistroSeries
ISourcePackagePublic['productseries'].schema = IProductSeries
ISourcePackagePublic['getBranch'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)[
        'params']['pocket'].vocabulary = PackagePublishingPocket
ISourcePackagePublic['getBranch'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)['return_type'].schema = IBranch
ISourcePackageEdit['setBranch'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)[
        'params']['pocket'].vocabulary = PackagePublishingPocket
ISourcePackageEdit['setBranch'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)['params']['branch'].schema = IBranch
patch_reference_property(ISourcePackage, 'distribution', IDistribution)

# IPerson
patch_entry_return_type(IPerson, 'createRecipe', ISourcePackageRecipe)
patch_list_parameter_type(IPerson, 'createRecipe', 'distroseries',
                          Reference(schema=IDistroSeries))
patch_plain_parameter_type(IPerson, 'createRecipe', 'daily_build_archive',
                           IArchive)
patch_plain_parameter_type(IPerson, 'getArchiveSubscriptionURL', 'archive',
                           IArchive)

patch_entry_return_type(IPerson, 'getRecipe', ISourcePackageRecipe)

# IHasRecipe
patch_collection_property(
    IHasRecipes, 'recipes', ISourcePackageRecipe)

IPerson['hardware_submissions'].value_type.schema = IHWSubmission

# publishing.py
ISourcePackagePublishingHistoryPublic['getBuilds'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)['return_type'].value_type.schema = (
        IBinaryPackageBuild)
ISourcePackagePublishingHistoryPublic[
    'getPublishedBinaries'].queryTaggedValue(
        LAZR_WEBSERVICE_EXPORTED)[
            'return_type'].value_type.schema = IBinaryPackagePublishingHistory
patch_reference_property(
    IBinaryPackagePublishingHistory, 'distroarchseries',
    IDistroArchSeries)
patch_reference_property(
    IBinaryPackagePublishingHistory, 'archive', IArchive)
patch_reference_property(
    ISourcePackagePublishingHistory, 'archive', IArchive)
patch_reference_property(
    ISourcePackagePublishingHistory, 'ancestor',
    ISourcePackagePublishingHistory)
patch_reference_property(
    ISourcePackagePublishingHistory, 'packageupload', IPackageUpload)
patch_entry_return_type(
    ISourcePackagePublishingHistoryEdit, 'changeOverride',
    ISourcePackagePublishingHistory)
patch_entry_return_type(
    IBinaryPackagePublishingHistoryEdit, 'changeOverride',
    IBinaryPackagePublishingHistory)

# IArchive apocalypse.
patch_reference_property(IArchive, 'distribution', IDistribution)
patch_collection_property(IArchive, 'dependencies', IArchiveDependency)
patch_collection_property(
    IArchive, 'enabled_restricted_processors', IProcessor)
patch_collection_return_type(IArchive, 'getAllPermissions', IArchivePermission)
patch_collection_return_type(
    IArchive, 'getPermissionsForPerson', IArchivePermission)
patch_collection_return_type(
    IArchive, 'getUploadersForPackage', IArchivePermission)
patch_collection_return_type(
    IArchive, 'getUploadersForPackageset', IArchivePermission)
patch_collection_return_type(
    IArchive, 'getPackagesetsForUploader', IArchivePermission)
patch_collection_return_type(
    IArchive, 'getPackagesetsForSourceUploader', IArchivePermission)
patch_collection_return_type(
    IArchive, 'getPackagesetsForSource', IArchivePermission)
patch_collection_return_type(
    IArchive, 'getUploadersForComponent', IArchivePermission)
patch_collection_return_type(
    IArchive, 'getQueueAdminsForComponent', IArchivePermission)
patch_collection_return_type(
    IArchive, 'getComponentsForQueueAdmin', IArchivePermission)
patch_collection_return_type(
    IArchive, 'getQueueAdminsForPocket', IArchivePermission)
patch_collection_return_type(
    IArchive, 'getPocketsForQueueAdmin', IArchivePermission)
patch_collection_return_type(
    IArchive, 'getPocketsForUploader', IArchivePermission)
patch_collection_return_type(
    IArchive, 'getUploadersForPocket', IArchivePermission)
patch_entry_return_type(IArchive, 'newPackageUploader', IArchivePermission)
patch_entry_return_type(IArchive, 'newPackagesetUploader', IArchivePermission)
patch_entry_return_type(IArchive, 'newComponentUploader', IArchivePermission)
patch_entry_return_type(IArchive, 'newPocketUploader', IArchivePermission)
patch_entry_return_type(IArchive, 'newQueueAdmin', IArchivePermission)
patch_entry_return_type(IArchive, 'newPocketQueueAdmin', IArchivePermission)
patch_plain_parameter_type(IArchive, 'syncSources', 'from_archive', IArchive)
patch_plain_parameter_type(IArchive, 'syncSource', 'from_archive', IArchive)
patch_plain_parameter_type(IArchive, 'copyPackage', 'from_archive', IArchive)
patch_plain_parameter_type(
    IArchive, 'copyPackages', 'from_archive', IArchive)
patch_entry_return_type(IArchive, 'newSubscription', IArchiveSubscriber)
patch_plain_parameter_type(
    IArchive, 'getArchiveDependency', 'dependency', IArchive)
patch_entry_return_type(IArchive, 'getArchiveDependency', IArchiveDependency)
patch_plain_parameter_type(
    IArchive, 'getPublishedSources', 'distroseries', IDistroSeries)
patch_collection_return_type(
    IArchive, 'getPublishedSources', ISourcePackagePublishingHistory)
patch_choice_parameter_type(
    IArchive, 'getPublishedSources', 'status', PackagePublishingStatus)
patch_choice_parameter_type(
    IArchive, 'getPublishedSources', 'pocket', PackagePublishingPocket)
patch_plain_parameter_type(
    IArchive, 'getAllPublishedBinaries', 'distroarchseries',
    IDistroArchSeries)
patch_collection_return_type(
    IArchive, 'getAllPublishedBinaries', IBinaryPackagePublishingHistory)
patch_choice_parameter_type(
    IArchive, 'getAllPublishedBinaries', 'status', PackagePublishingStatus)
patch_choice_parameter_type(
    IArchive, 'getAllPublishedBinaries', 'pocket', PackagePublishingPocket)
patch_plain_parameter_type(
    IArchive, 'isSourceUploadAllowed', 'distroseries', IDistroSeries)
patch_plain_parameter_type(
    IArchive, '_checkUpload', 'distroseries', IDistroSeries)
patch_choice_parameter_type(
    IArchive, '_checkUpload', 'pocket', PackagePublishingPocket)
patch_choice_parameter_type(
    IArchive, 'getUploadersForPocket', 'pocket', PackagePublishingPocket)
patch_choice_parameter_type(
    IArchive, 'getQueueAdminsForPocket', 'pocket', PackagePublishingPocket)
patch_plain_parameter_type(
    IArchive, 'getQueueAdminsForPocket', 'distroseries', IDistroSeries)
patch_choice_parameter_type(
    IArchive, 'newPocketUploader', 'pocket', PackagePublishingPocket)
patch_choice_parameter_type(
    IArchive, 'newPocketQueueAdmin', 'pocket', PackagePublishingPocket)
patch_plain_parameter_type(
    IArchive, 'newPocketQueueAdmin', 'distroseries', IDistroSeries)
patch_choice_parameter_type(
    IArchive, 'deletePocketUploader', 'pocket', PackagePublishingPocket)
patch_choice_parameter_type(
    IArchive, 'deletePocketQueueAdmin', 'pocket', PackagePublishingPocket)
patch_plain_parameter_type(
    IArchive, 'deletePocketQueueAdmin', 'distroseries', IDistroSeries)
patch_plain_parameter_type(
    IArchive, 'newPackagesetUploader', 'packageset', IPackageset)
patch_plain_parameter_type(
    IArchive, 'getUploadersForPackageset', 'packageset', IPackageset)
patch_plain_parameter_type(
    IArchive, 'deletePackagesetUploader', 'packageset', IPackageset)
patch_plain_parameter_type(
    IArchive, 'removeArchiveDependency', 'dependency', IArchive)
patch_plain_parameter_type(
    IArchive, '_addArchiveDependency', 'dependency', IArchive)
patch_choice_parameter_type(
    IArchive, '_addArchiveDependency', 'pocket', PackagePublishingPocket)
patch_entry_return_type(
    IArchive, '_addArchiveDependency', IArchiveDependency)
patch_plain_parameter_type(
    IArchive, 'enableRestrictedProcessor', 'processor', IProcessor)

# IBuildFarmJob
IBuildFarmJob['status'].vocabulary = BuildStatus
IBuildFarmJob['buildqueue_record'].schema = IBuildQueue

# IComment
IComment['comment_author'].schema = IPerson

# IDistribution
IDistribution['series'].value_type.schema = IDistroSeries
IDistribution['derivatives'].value_type.schema = IDistroSeries
patch_reference_property(
    IDistribution, 'currentseries', IDistroSeries)
patch_entry_return_type(
    IDistribution, 'getArchive', IArchive)
patch_entry_return_type(
    IDistribution, 'getSeries', IDistroSeries)
patch_collection_return_type(
    IDistribution, 'getDevelopmentSeries', IDistroSeries)
patch_entry_return_type(
    IDistribution, 'getSourcePackage', IDistributionSourcePackage)
patch_collection_return_type(
    IDistribution, 'searchSourcePackages', IDistributionSourcePackage)
patch_reference_property(
    IDistribution, 'main_archive', IArchive)
IDistribution['all_distro_archives'].value_type.schema = IArchive


# IDistributionMirror
IDistributionMirror['distribution'].schema = IDistribution


# IDistroSeries
patch_entry_return_type(
    IDistroSeries, 'getDistroArchSeries', IDistroArchSeries)
patch_reference_property(
    IDistroSeries, 'main_archive', IArchive)
patch_collection_property(
    IDistroSeries, 'enabled_architectures', IDistroArchSeries)
patch_reference_property(
    IDistroSeries, 'distribution', IDistribution)
patch_choice_parameter_type(
    IDistroSeries, 'getPackageUploads', 'status', PackageUploadStatus)
patch_choice_parameter_type(
    IDistroSeries, 'getPackageUploads', 'pocket', PackagePublishingPocket)
patch_choice_parameter_type(
    IDistroSeries, 'getPackageUploads', 'custom_type',
    PackageUploadCustomFormat)
patch_plain_parameter_type(
    IDistroSeries, 'getPackageUploads', 'archive', IArchive)
patch_collection_return_type(
    IDistroSeries, 'getPackageUploads', IPackageUpload)
patch_reference_property(IDistroSeries, 'previous_series', IDistroSeries)
patch_reference_property(
    IDistroSeries, 'nominatedarchindep', IDistroArchSeries)
patch_collection_return_type(
    IDistroSeries, 'getDerivedSeries', IDistroSeries)
patch_collection_return_type(
    IDistroSeries, 'getParentSeries', IDistroSeries)
patch_plain_parameter_type(
    IDistroSeries, 'getDifferencesTo', 'parent_series', IDistroSeries)
patch_choice_parameter_type(
    IDistroSeries, 'getDifferencesTo', 'status', DistroSeriesDifferenceStatus)
patch_choice_parameter_type(
    IDistroSeries, 'getDifferencesTo', 'difference_type',
    DistroSeriesDifferenceType)
patch_collection_return_type(
    IDistroSeries, 'getDifferencesTo', IDistroSeriesDifference)
patch_collection_return_type(
    IDistroSeries, 'getDifferenceComments', IDistroSeriesDifferenceComment)


# IDistroSeriesDifference
patch_reference_property(
    IDistroSeriesDifference, 'latest_comment', IDistroSeriesDifferenceComment)

# IDistroSeriesDifferenceComment
IDistroSeriesDifferenceComment['comment_author'].schema = IPerson

# IDistroArchSeries
patch_reference_property(IDistroArchSeries, 'main_archive', IArchive)

# IPackageset
patch_collection_return_type(
    IPackageset, 'setsIncluded', IPackageset)
patch_collection_return_type(
    IPackageset, 'setsIncludedBy', IPackageset)
patch_plain_parameter_type(
    IPackageset, 'getSourcesSharedBy', 'other_package_set', IPackageset)
patch_plain_parameter_type(
    IPackageset, 'getSourcesNotSharedBy', 'other_package_set', IPackageset)
patch_collection_return_type(
    IPackageset, 'relatedSets', IPackageset)

# IPackageUpload
IPackageUpload['pocket'].vocabulary = PackagePublishingPocket
patch_reference_property(IPackageUpload, 'distroseries', IDistroSeries)
patch_reference_property(IPackageUpload, 'archive', IArchive)
patch_reference_property(IPackageUpload, 'copy_source_archive', IArchive)

# IStructuralSubscription
patch_collection_property(
    IStructuralSubscription, 'bug_filters', IBugSubscriptionFilter)
patch_entry_return_type(
    IStructuralSubscription, "newBugFilter", IBugSubscriptionFilter)
patch_reference_property(
    IStructuralSubscription, 'target', IStructuralSubscriptionTarget)

# IStructuralSubscriptionTarget
patch_reference_property(
    IStructuralSubscriptionTarget, 'parent_subscription_target',
    IStructuralSubscriptionTarget)
patch_entry_return_type(
    IStructuralSubscriptionTarget, 'addBugSubscriptionFilter',
    IBugSubscriptionFilter)

# ISourcePackageRelease
patch_reference_property(
    ISourcePackageRelease, 'source_package_recipe_build',
    ISourcePackageRecipeBuild)

# ISourcePackageRecipeView
patch_entry_return_type(
    ISourcePackageRecipe, 'requestBuild', ISourcePackageRecipeBuild)
patch_reference_property(
    ISourcePackageRecipe, 'last_build', ISourcePackageRecipeBuild)
patch_collection_property(
    ISourcePackageRecipe, 'builds', ISourcePackageRecipeBuild)
patch_collection_property(
    ISourcePackageRecipe, 'pending_builds', ISourcePackageRecipeBuild)
patch_collection_property(
    ISourcePackageRecipe, 'completed_builds', ISourcePackageRecipeBuild)

# IHasBugs
patch_plain_parameter_type(
    IHasBugs, 'searchTasks', 'assignee', IPerson)
patch_plain_parameter_type(
    IHasBugs, 'searchTasks', 'bug_reporter', IPerson)
patch_plain_parameter_type(
    IHasBugs, 'searchTasks', 'bug_supervisor', IPerson)
patch_plain_parameter_type(
    IHasBugs, 'searchTasks', 'bug_commenter', IPerson)
patch_plain_parameter_type(
    IHasBugs, 'searchTasks', 'bug_subscriber', IPerson)
patch_plain_parameter_type(
    IHasBugs, 'searchTasks', 'owner', IPerson)
patch_plain_parameter_type(
    IHasBugs, 'searchTasks', 'affected_user', IPerson)
patch_plain_parameter_type(
    IHasBugs, 'searchTasks', 'structural_subscriber', IPerson)

# IBugTask
patch_reference_property(IBugTask, 'owner', IPerson)

# IBugWatch
patch_reference_property(IBugWatch, 'owner', IPerson)

# IHasTranslationImports
patch_collection_return_type(
    IHasTranslationImports, 'getTranslationImportQueueEntries',
    ITranslationImportQueueEntry)

# IIndexedMessage
patch_reference_property(IIndexedMessage, 'inside', IBugTask)

# IMessage
patch_reference_property(IMessage, 'owner', IPerson)

# IUserToUserEmail
patch_reference_property(IUserToUserEmail, 'sender', IPerson)
patch_reference_property(IUserToUserEmail, 'recipient', IPerson)

# IBug
patch_plain_parameter_type(
    IBug, 'addNomination', 'target', IBugTarget)
patch_plain_parameter_type(
    IBug, 'canBeNominatedFor', 'target', IBugTarget)
patch_plain_parameter_type(
    IBug, 'getNominationFor', 'target', IBugTarget)
patch_plain_parameter_type(
    IBug, 'getNominations', 'target', IBugTarget)
patch_choice_vocabulary(
    IBug, 'subscribe', 'level', BugNotificationLevel)


# IFrontPageBugAddForm
patch_reference_property(IFrontPageBugAddForm, 'bugtarget', IBugTarget)

# IBugTracker
patch_reference_property(IBugTracker, 'owner', IPerson)
patch_entry_return_type(
    IBugTracker, 'getRemoteComponentGroup', IBugTrackerComponentGroup)
patch_entry_return_type(
    IBugTracker, 'addRemoteComponentGroup', IBugTrackerComponentGroup)
patch_collection_return_type(
    IBugTracker, 'getAllRemoteComponentGroups', IBugTrackerComponentGroup)
patch_entry_return_type(
    IBugTracker, 'getRemoteComponentForDistroSourcePackageName',
    IBugTrackerComponent)

## IBugTrackerComponent
patch_reference_property(
    IBugTrackerComponent, "distro_source_package",
    IDistributionSourcePackage)

# IHasTranslationTemplates
patch_collection_return_type(
    IHasTranslationTemplates, 'getTranslationTemplates', IPOTemplate)

# IPOTemplate
patch_collection_property(IPOTemplate, 'pofiles', IPOFile)
patch_reference_property(IPOTemplate, 'product', IProduct)

# IPOTemplateSubset
patch_reference_property(IPOTemplateSubset, 'distroseries', IDistroSeries)
patch_reference_property(IPOTemplateSubset, 'productseries', IProductSeries)

# IPOTemplateSharingSubset
patch_reference_property(IPOTemplateSharingSubset, 'product', IProduct)

# IPerson
patch_collection_return_type(
    IPerson, 'getBugSubscriberPackages', IDistributionSourcePackage)

# IProductSeries
patch_reference_property(IProductSeries, 'product', IProduct)

# ISpecification
ISpecification['linkBug'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)['params']['bug'].schema = IBug
ISpecification['unlinkBug'].queryTaggedValue(
    LAZR_WEBSERVICE_EXPORTED)['params']['bug'].schema = IBug
patch_collection_property(ISpecification, 'dependencies', ISpecification)
patch_collection_property(
    ISpecification, 'linked_branches', ISpecificationBranch)

# ISpecificationTarget
patch_entry_return_type(
    ISpecificationTarget, 'getSpecification', ISpecification)

# IHasSpecifications
patch_collection_property(
    IHasSpecifications, 'visible_specifications', ISpecification)
patch_collection_property(
    IHasSpecifications, 'api_valid_specifications', ISpecification)


###
#
# Our web service configuration requires that every entry, field, and
# named operation explicitly name the version in which it first
# appears. This code grandfathers in entries and named operations that
# were defined before this rule came into effect. When you change an
# interface in the future, you should add explicit version statements to
# its definition and get rid of the patch calls here.
#
###

# IArchive
patch_entry_explicit_version(IArchive, 'beta')
patch_operations_explicit_version(
    IArchive, 'beta', "_checkUpload", "deleteComponentUploader",
    "deletePackageUploader", "deletePackagesetUploader", "deleteQueueAdmin",
    "getAllPublishedBinaries", "getArchiveDependency", "getBuildCounters",
    "getBuildSummariesForSourceIds", "getComponentsForQueueAdmin",
    "getPackagesetsForSource", "getPackagesetsForSourceUploader",
    "getPackagesetsForUploader", "getPermissionsForPerson",
    "getPublishedSources", "getQueueAdminsForComponent",
    "getUploadersForComponent", "getUploadersForPackage",
    "getUploadersForPackageset", "isSourceUploadAllowed",
    "newComponentUploader", "newPackageUploader", "newPackagesetUploader",
    "newQueueAdmin", "newSubscription", "syncSource", "syncSources")

# IArchiveDependency
patch_entry_explicit_version(IArchiveDependency, 'beta')

# IArchivePermission
patch_entry_explicit_version(IArchivePermission, 'beta')

# IArchiveSubscriber
patch_entry_explicit_version(IArchiveSubscriber, 'beta')

# IBinaryPackageBuild
patch_entry_explicit_version(IBinaryPackageBuild, 'beta')
patch_operations_explicit_version(
    IBinaryPackageBuild, 'beta', "rescore", "retry")

# IBinaryPackagePublishingHistory
patch_entry_explicit_version(IBinaryPackagePublishingHistory, 'beta')
patch_operations_explicit_version(
    IBinaryPackagePublishingHistory, 'beta', "getDailyDownloadTotals",
    "getDownloadCount", "getDownloadCounts")

# IBinaryPackageReleaseDownloadCount
patch_entry_explicit_version(IBinaryPackageReleaseDownloadCount, 'beta')

# IBranch
patch_entry_explicit_version(IBranch, 'beta')

# IBranchMergeProposal
patch_entry_explicit_version(IBranchMergeProposal, 'beta')
patch_operations_explicit_version(
    IBranchMergeProposal, 'beta', "createComment", "getComment",
    "nominateReviewer", "setStatus")

# IBranchMergeQueue
patch_entry_explicit_version(IBranchMergeQueue, 'beta')
patch_operations_explicit_version(
    IBranchMergeQueue, 'beta', "setMergeQueueConfig")

# IBranchSubscription
patch_entry_explicit_version(IBranchSubscription, 'beta')
patch_operations_explicit_version(
    IBranchSubscription, 'beta', "canBeUnsubscribedByUser")

# IBug
patch_entry_explicit_version(IBug, 'beta')
patch_operations_explicit_version(
    IBug, 'beta', "addAttachment", "addNomination", "addTask", "addWatch",
    "canBeNominatedFor", "getHWSubmissions", "getNominationFor",
    "getNominations", "isExpirable", "isUserAffected",
    "linkCVE", "linkHWSubmission", "markAsDuplicate",
    "markUserAffected", "newMessage", "setCommentVisibility", "setPrivate",
    "setSecurityRelated", "subscribe", "unlinkCVE", "unlinkHWSubmission",
    "unsubscribe", "unsubscribeFromDupes")

# IBugActivity
patch_entry_explicit_version(IBugActivity, 'beta')

# IBugAttachment
patch_entry_explicit_version(IBugAttachment, 'beta')
patch_operations_explicit_version(
    IBugAttachment, 'beta', "removeFromBug")

# IBugBranch
patch_entry_explicit_version(IBugBranch, 'beta')

# IBugNomination
patch_entry_explicit_version(IBugNomination, 'beta')
patch_operations_explicit_version(
    IBugNomination, 'beta', "approve", "canApprove", "decline")

# IBugSubscriptionFilter
patch_entry_explicit_version(IBugSubscriptionFilter, 'beta')
patch_operations_explicit_version(
    IBugSubscriptionFilter, 'beta', "delete")

# IBugTarget
patch_entry_explicit_version(IBugTarget, 'beta')

# IBugTask
patch_entry_explicit_version(IBugTask, 'beta')
patch_operations_explicit_version(
    IBugTask, 'beta', "findSimilarBugs", "transitionToAssignee",
    "transitionToImportance", "transitionToMilestone", "transitionToStatus",
    "transitionToTarget")

# IBugTracker
patch_entry_explicit_version(IBugTracker, 'beta')
patch_operations_explicit_version(
    IBugTracker, 'beta', "addRemoteComponentGroup",
    "getAllRemoteComponentGroups", "getRemoteComponentGroup")

# IBugTrackerComponent
patch_entry_explicit_version(IBugTrackerComponent, 'beta')

# IBugTrackerComponentGroup
patch_entry_explicit_version(IBugTrackerComponentGroup, 'beta')
patch_operations_explicit_version(
    IBugTrackerComponentGroup, 'beta', "addComponent")

# IBugTrackerSet
patch_operations_explicit_version(
    IBugTrackerSet, 'beta', "ensureBugTracker", "getByName", "queryByBaseURL")

# IBugWatch
patch_entry_explicit_version(IBugWatch, 'beta')

# IBuilder
patch_entry_explicit_version(IBuilder, 'beta')

# IBuilderSet
patch_operations_explicit_version(IBuilderSet, 'beta', "getByName")

# ICodeImport
patch_entry_explicit_version(ICodeImport, 'beta')
patch_operations_explicit_version(
    ICodeImport, 'beta', "requestImport")

# ICodeReviewComment
patch_entry_explicit_version(ICodeReviewComment, 'beta')

# ICodeReviewVoteReference
patch_entry_explicit_version(ICodeReviewVoteReference, 'beta')
patch_operations_explicit_version(
    ICodeReviewVoteReference, 'beta', "claimReview", "delete",
    "reassignReview")

# ICommercialSubscription
patch_entry_explicit_version(ICommercialSubscription, 'beta')

# ICountry
patch_entry_explicit_version(ICountry, 'beta')

# ICountrySet
patch_operations_explicit_version(
    ICountrySet, 'beta', "getByCode", "getByName")

# ICve
patch_entry_explicit_version(ICve, 'beta')

# IDistribution
patch_operations_explicit_version(
    IDistribution, 'beta', "getArchive", "getCountryMirror",
    "getDevelopmentSeries", "getMirrorByName", "getSeries",
    "getSourcePackage", "searchSourcePackages")

# IDistributionMirror
patch_entry_explicit_version(IDistributionMirror, 'beta')
patch_operations_explicit_version(
    IDistributionMirror, 'beta', "canTransitionToCountryMirror",
    "getOverallFreshness", "isOfficial", "transitionToCountryMirror")

# IDistributionSourcePackage
patch_entry_explicit_version(IDistributionSourcePackage, 'beta')

# IDistroArchSeries
patch_entry_explicit_version(IDistroArchSeries, 'beta')

# IDistroSeries
patch_entry_explicit_version(IDistroSeries, 'beta')
patch_operations_explicit_version(
    IDistroSeries, 'beta', "initDerivedDistroSeries", "getDerivedSeries",
    "getParentSeries", "getDistroArchSeries", "getPackageUploads",
    "getSourcePackage", "newMilestone")

# IDistroSeriesDifference
patch_entry_explicit_version(IDistroSeriesDifference, 'beta')
patch_operations_explicit_version(
    IDistroSeriesDifference, 'beta', "addComment", "blacklist",
    "requestPackageDiffs", "unblacklist")

# IDistroSeriesDifferenceComment
patch_entry_explicit_version(IDistroSeriesDifferenceComment, 'beta')

# IGPGKey
patch_entry_explicit_version(IGPGKey, 'beta')

# IHWDBApplication
patch_entry_explicit_version(IHWDBApplication, 'beta')
patch_operations_explicit_version(
    IHWDBApplication, 'beta', "deviceDriverOwnersAffectedByBugs", "devices",
    "drivers", "hwInfoByBugRelatedUsers", "numDevicesInSubmissions",
    "numOwnersOfDevice", "numSubmissionsWithDevice", "search", "vendorIDs")

# IHWDevice
patch_entry_explicit_version(IHWDevice, 'beta')
patch_operations_explicit_version(
    IHWDevice, 'beta', "getOrCreateDeviceClass", "getSubmissions",
    "removeDeviceClass")

# IHWDeviceClass
patch_entry_explicit_version(IHWDeviceClass, 'beta')
patch_operations_explicit_version(
    IHWDeviceClass, 'beta', "delete")

# IHWDriver
patch_entry_explicit_version(IHWDriver, 'beta')
patch_operations_explicit_version(
    IHWDriver, 'beta', "getSubmissions")

# IHWDriverName
patch_entry_explicit_version(IHWDriverName, 'beta')

# IHWDriverPackageName
patch_entry_explicit_version(IHWDriverPackageName, 'beta')

# IHWSubmission
patch_entry_explicit_version(IHWSubmission, 'beta')

# IHWSubmissionDevice
patch_entry_explicit_version(IHWSubmissionDevice, 'beta')

# IHWVendorID
patch_entry_explicit_version(IHWVendorID, 'beta')

# IHasBugs
patch_entry_explicit_version(IHasBugs, 'beta')

# IHasMilestones
patch_entry_explicit_version(IHasMilestones, 'beta')

# IHasTranslationImports
patch_entry_explicit_version(IHasTranslationImports, 'beta')

# IIrcID
patch_entry_explicit_version(IIrcID, 'beta')

# IJabberID
patch_entry_explicit_version(IJabberID, 'beta')

# ILanguage
patch_entry_explicit_version(ILanguage, 'beta')

# ILanguageSet
patch_operations_explicit_version(ILanguageSet, 'beta', "getAllLanguages")

# IMaloneApplication
patch_operations_explicit_version(IMaloneApplication, 'beta', "createBug")

# IMessage
patch_entry_explicit_version(IMessage, 'beta')

# IMilestone
patch_entry_explicit_version(IMilestone, 'beta')

# IPOFile
patch_entry_explicit_version(IPOFile, 'beta')

# IPOTemplate
patch_entry_explicit_version(IPOTemplate, 'beta')

# IPackageUpload
patch_entry_explicit_version(IPackageUpload, 'beta')

# IPackageset
patch_entry_explicit_version(IPackageset, 'beta')
patch_operations_explicit_version(
    IPackageset, 'beta', "addSources", "addSubsets", "getSourcesIncluded",
    "getSourcesNotSharedBy", "getSourcesSharedBy", "relatedSets",
    "removeSources", "removeSubsets", "setsIncluded", "setsIncludedBy")

# IPackagesetSet
patch_operations_explicit_version(
    IPackagesetSet, 'beta', "getByName", "new", "setsIncludingSource")

# IPerson
patch_entry_explicit_version(IPerson, 'beta')

# IPillar
patch_entry_explicit_version(IPillar, 'beta')

# IPillarNameSet
patch_entry_explicit_version(IPillarNameSet, 'beta')
patch_operations_explicit_version(
    IPillarNameSet, 'beta', "search")

# IPreviewDiff
patch_entry_explicit_version(IPreviewDiff, 'beta')

# IProduct
patch_entry_explicit_version(IProduct, 'beta')
patch_operations_explicit_version(
    IProduct, 'beta', "getRelease", "getSeries", "getTimeline", "newSeries")

# IProductRelease
patch_entry_explicit_version(IProductRelease, 'beta')
patch_operations_explicit_version(
    IProductRelease, 'beta', "addReleaseFile", "destroySelf")

# IProductReleaseFile
patch_entry_explicit_version(IProductReleaseFile, 'beta')
patch_operations_explicit_version(
    IProductReleaseFile, 'beta', "destroySelf")

# IProductSeries
patch_entry_explicit_version(IProductSeries, 'beta')
patch_operations_explicit_version(
    IProductSeries, 'beta', "getTimeline", "newMilestone")

# IProductSet
patch_operations_explicit_version(
    IProductSet, 'beta', "createProduct", "forReview", "latest", "search")

# IProjectGroup
patch_entry_explicit_version(IProjectGroup, 'beta')

# IProjectGroupSet
patch_operations_explicit_version(
    IProjectGroupSet, 'beta', "search")

# ISSHKey
patch_entry_explicit_version(ISSHKey, 'beta')

# ISourcePackage
patch_entry_explicit_version(ISourcePackage, 'beta')
patch_operations_explicit_version(
    ISourcePackage, 'beta', "getBranch", "linkedBranches", "setBranch")

# ISourcePackagePublishingHistory
patch_entry_explicit_version(ISourcePackagePublishingHistory, 'beta')
patch_operations_explicit_version(
    ISourcePackagePublishingHistory, 'beta', "api_requestDeletion",
    "binaryFileUrls", "changesFileUrl", "getBuilds", "getPublishedBinaries",
    "packageDiffUrl", "sourceFileUrls")

# ISourcePackageRecipe
patch_entry_explicit_version(ISourcePackageRecipe, 'beta')
patch_operations_explicit_version(
    ISourcePackageRecipe, 'beta', "performDailyBuild", "requestBuild",
    "setRecipeText")

# ISourcePackageRecipeBuild
patch_entry_explicit_version(ISourcePackageRecipeBuild, 'beta')

# IStructuralSubscription
patch_entry_explicit_version(IStructuralSubscription, 'beta')
patch_operations_explicit_version(
    IStructuralSubscription, 'beta', "delete", "newBugFilter")

# IStructuralSubscriptionTarget
patch_entry_explicit_version(IStructuralSubscriptionTarget, 'beta')

# ITeam
patch_entry_explicit_version(ITeam, 'beta')

# ITeamMembership
patch_entry_explicit_version(ITeamMembership, 'beta')
patch_operations_explicit_version(
    ITeamMembership, 'beta', "setExpirationDate", "setStatus")

# ITimelineProductSeries
patch_entry_explicit_version(ITimelineProductSeries, 'beta')

# ITranslationGroup
patch_entry_explicit_version(ITranslationGroup, 'beta')

# ITranslationImportQueue
patch_operations_explicit_version(
    ITranslationImportQueue, 'beta', "getAllEntries", "getFirstEntryToImport",
    "getRequestTargets")

# ITranslationImportQueueEntry
patch_entry_explicit_version(ITranslationImportQueueEntry, 'beta')
patch_operations_explicit_version(
    ITranslationImportQueueEntry, 'beta', "setStatus")

# IWikiName
patch_entry_explicit_version(IWikiName, 'beta')
