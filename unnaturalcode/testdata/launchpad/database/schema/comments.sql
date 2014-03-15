/*
  Add Comments to Launchpad database. Please keep these alphabetical by
  table.

     Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
     GNU Affero General Public License version 3 (see the file LICENSE).
*/

-- AccessArtifact

COMMENT ON TABLE AccessArtifact IS 'An artifact that an access grant can apply to. Additional private artifacts should be handled by adding new columns here, rather than new tables or columns on AccessArtifactGrant.';
COMMENT ON COLUMN AccessArtifact.bug IS 'The bug that this abstract artifact represents.';
COMMENT ON COLUMN AccessArtifact.branch IS 'The branch that this abstract artifact represents.';

-- AccessArtifactGrant

COMMENT ON TABLE AccessArtifactGrant IS 'A grant for a person to access an artifact.';
COMMENT ON COLUMN AccessArtifactGrant.artifact IS 'The artifact on which access is granted.';
COMMENT ON COLUMN AccessArtifactGrant.grantee IS 'The person to whom access is granted.';
COMMENT ON COLUMN AccessArtifactGrant.grantor IS 'The person who granted the access.';
COMMENT ON COLUMN AccessArtifactGrant.date_created IS 'The date the access was granted.';

-- AccessPolicy

COMMENT ON TABLE AccessPolicy IS 'An access policy used to manage a project or distribution''s artifacts.';
COMMENT ON COLUMN AccessPolicy.product IS 'The product that this policy is used on.';
COMMENT ON COLUMN AccessPolicy.distribution IS 'The distribution that this policy is used on.';
COMMENT ON COLUMN AccessPolicy.type IS 'The type of policy (an enum value). Private, Security, etc.';

-- AccessPolicyArtifact

COMMENT ON TABLE AccessPolicyArtifact IS 'An association between an artifact and a policy. A grant for any related policy grants access to the artifact.';
COMMENT ON COLUMN AccessPolicyArtifact.artifact IS 'The artifact associated with this policy.';
COMMENT ON COLUMN AccessPolicyArtifact.policy IS 'The policy associated with this artifact.';

-- AccessPolicyGrantFlat

COMMENT ON TABLE AccessPolicyGrantFlat IS 'A fact table for access queries. AccessPolicyGrants are included verbatim, but AccessArtifactGrants are included with their artifacts'' corresponding policies.';
COMMENT ON COLUMN AccessPolicyGrantFlat.policy IS 'The policy on which access is granted.';
COMMENT ON COLUMN AccessPolicyGrantFlat.artifact IS 'The artifact on which access is granted. If null, the grant is for the whole policy';
COMMENT ON COLUMN AccessPolicyGrantFlat.grantee IS 'The person to whom access is granted.';

-- AccessPolicyGrant

COMMENT ON TABLE AccessPolicyGrant IS 'A grant for a person to access a policy''s artifacts.';
COMMENT ON COLUMN AccessPolicyGrant.policy IS 'The policy on which access is granted.';
COMMENT ON COLUMN AccessPolicyGrant.grantee IS 'The person to whom access is granted.';
COMMENT ON COLUMN AccessPolicyGrant.grantor IS 'The person who granted the access.';
COMMENT ON COLUMN AccessPolicyGrant.date_created IS 'The date the access was granted.';

-- Announcement

COMMENT ON TABLE Announcement IS 'A project announcement. This is a single item of news or information that the project is communicating. Announcements can be attached to a Project, a Product or a Distribution.';
COMMENT ON COLUMN Announcement.date_announced IS 'The date at which an announcement will become public, if it is active. If this is not set then the announcement will not become public until someone consciously publishes it (which sets this date).';
COMMENT ON COLUMN Announcement.url IS 'A web location for the announcement itself.';
COMMENT ON COLUMN Announcement.active IS 'Whether or not the announcement is public. This is TRUE by default, but can be set to FALSE if the project "retracts" the announcement.';

-- AnswerContact

COMMENT ON TABLE AnswerContact IS 'Defines the answer contact for a given question target. The answer contact will be automatically notified about changes to any questions filed on the question target.';
COMMENT ON COLUMN AnswerContact.product IS 'The product that the answer contact supports.';
COMMENT ON COLUMN AnswerContact.distribution IS 'The distribution that the answer contact supports.';
COMMENT ON COLUMN AnswerContact.sourcepackagename IS 'The sourcepackagename that the answer contact supports.';
COMMENT ON COLUMN AnswerContact.person IS 'The person or team associated with the question target.';
COMMENT ON COLUMN AnswerContact.date_created IS 'The date the answer contact was submitted.';

-- ApportJob

COMMENT ON TABLE ApportJob IS 'Contains references to jobs to be run against Apport BLOBs.';
COMMENT ON COLUMN ApportJob.blob IS 'The TemporaryBlobStorage entry on which the job is to be run.';
COMMENT ON COLUMN ApportJob.job_type IS 'The type of job (enumeration value). Allows us to query the database for a given subset of ApportJobs.';
COMMENT ON COLUMN ApportJob.json_data IS 'A JSON struct containing data for the job.';

-- ArchiveJob

COMMENT ON TABLE ArchiveJob is 'Contains references to jobs to be run against Archives.';
COMMENT ON COLUMN ArchiveJob.archive IS 'The archive on which the job is to be run.';
COMMENT ON COLUMN ArchiveJob.job_type IS 'The type of job (enumeration value). Allows us to query the database for a given subset of ArchiveJobs.';
COMMENT ON COLUMN ArchiveJob.json_data IS 'A JSON struct containing data for the job.';


-- Branch
COMMENT ON TABLE Branch IS 'Bzr branch';
COMMENT ON COLUMN Branch.registrant IS 'The user that registered the branch.';
COMMENT ON COLUMN Branch.branch_type IS 'Branches are currently one of HOSTED (1), MIRRORED (2), or IMPORTED (3).';
COMMENT ON COLUMN Branch.whiteboard IS 'Notes on the current status of the branch';
COMMENT ON COLUMN Branch.summary IS 'A single paragraph description of the branch';
COMMENT ON COLUMN Branch.lifecycle_status IS 'Authors assesment of the branchs maturity';
COMMENT ON COLUMN Branch.mirror_status_message IS 'The last message we got when mirroring this branch.';
COMMENT ON COLUMN Branch.last_mirrored IS 'The time when the branch was last mirrored.';
COMMENT ON COLUMN Branch.last_mirrored_id IS 'The revision ID of the branch when it was last mirrored.';
COMMENT ON COLUMN Branch.last_scanned IS 'The time when the branch was last scanned.';
COMMENT ON COLUMN Branch.last_scanned_id IS 'The revision ID of the branch when it was last scanned.';
COMMENT ON COLUMN Branch.revision_count IS 'The number of revisions in the associated bazaar branch revision_history.';
COMMENT ON COLUMN Branch.next_mirror_time IS 'The time when we will next mirror this branch (NULL means never). This will be set automatically by pushing to a hosted branch, which, once mirrored, will be set back to NULL.';
COMMENT ON COLUMN Branch.date_last_modified IS 'A branch is modified any time a user updates something using a view, a new revision for the branch is scanned, or the branch is linked to a bug, blueprint or merge proposal.';
COMMENT ON COLUMN Branch.reviewer IS 'The reviewer (person or) team are able to transition merge proposals targetted at the branch throught the CODE_APPROVED state.';
COMMENT ON COLUMN Branch.home_page IS 'This column is deprecated and to be removed soon.';
COMMENT ON COLUMN Branch.branch_format IS 'The bzr branch format';
COMMENT ON COLUMN Branch.repository_format IS 'The bzr repository format';
COMMENT ON COLUMN Branch.metadir_format IS 'The bzr metadir format';
COMMENT ON COLUMN Branch.stacked_on IS 'The Launchpad branch that this branch is stacked on (if any).';
COMMENT ON COLUMN Branch.distroseries IS 'The distribution series that the branch belongs to.';
COMMENT ON COLUMN Branch.sourcepackagename IS 'The source package this is a branch of.';
COMMENT ON COLUMN Branch.size_on_disk IS 'The size in bytes of this branch in the mirrored area.';
COMMENT ON COLUMN Branch.merge_queue IS 'A reference to the BranchMergeQueue record that manages merges.';
COMMENT ON COLUMN Branch.merge_queue_config IS 'A JSON string of configuration values that can be read by a merge queue script.';
COMMENT ON COLUMN Branch.information_type IS 'Enum describing what type of information is stored, such as type of private or security related data, and used to determine how to apply an access policy.';

-- BranchMergeQueue
COMMENT ON TABLE BranchMergeQueue IS 'Queue for managing the merge workflow for branches.';
COMMENT ON COLUMN BranchMergeQueue.id IS 'The id of the merge queue.';
COMMENT ON COLUMN BranchMergeQueue.registrant IS 'A reference to the person who created the merge queue.';
COMMENT ON COLUMN BranchMergeQueue.owner IS 'A reference to the person who owns the merge queue.';
COMMENT ON COLUMN BranchMergeQueue.name IS 'The name of the queue.';
COMMENT ON COLUMN BranchMergeQueue.description IS 'A description of the queue.';
COMMENT ON COLUMN BranchMergeQueue.configuration IS 'A JSON string of configuration data to be read by the merging script.';
COMMENT ON COLUMN BranchMergeQueue.date_created IS 'The date the queue was created.';


-- BranchJob

COMMENT ON TABLE BranchJob IS 'Contains references to jobs that are executed for a branch.';
COMMENT ON COLUMN BranchJob.job IS 'A reference to a row in the Job table that has all the common job details.';
COMMENT ON COLUMN BranchJob.branch IS 'The branch that this job is for.';
COMMENT ON COLUMN BranchJob.job_type IS 'The type of job, like new revisions, or attribute change.';
COMMENT ON COLUMN BranchJob.json_data IS 'Data that is specific to the type of job, whether this be the revisions to send email out for, or the changes that were recorded for the branch.';

-- BranchMergeProposal

COMMENT ON TABLE BranchMergeProposal IS 'Branch merge proposals record the intent of landing (or merging) one branch on another.';
COMMENT ON COLUMN BranchMergeProposal.registrant IS 'The person that created the merge proposal.';
COMMENT ON COLUMN BranchMergeProposal.source_branch IS 'The branch where the work is being written.  This branch contains the changes that the registrant wants to land.';
COMMENT ON COLUMN BranchMergeProposal.target_branch IS 'The branch where the user wants the changes from the source branch to be merged into.';
COMMENT ON COLUMN BranchMergeProposal.dependent_branch IS 'If the source branch was not branched off the target branch, then this is considered the dependent_branch.';
COMMENT ON COLUMN BranchMergeProposal.date_created IS 'When the registrant created the merge proposal.';
COMMENT ON COLUMN BranchMergeProposal.whiteboard IS 'Used to write other information about the branch, like test URLs.';
COMMENT ON COLUMN BranchMergeProposal.merged_revno IS 'This is the revision number of the revision on the target branch that includes the merge from the source branch.';
COMMENT ON COLUMN BranchMergeProposal.merge_reporter IS 'This is the user that marked the proposal as merged.';
COMMENT ON COLUMN BranchMergeProposal.date_merged IS 'This is the date that merge occurred.';
COMMENT ON COLUMN BranchMergeProposal.commit_message IS 'This is the commit message that is to be used when the branch is landed by a robot.';
COMMENT ON COLUMN BranchMergeProposal.queue_position IS 'The position on the merge proposal in the overall landing queue.  If the branch has a merge_robot set and the merge robot controls multiple branches then the queue position is unique over all the queued merge proposals for the landing robot.';
COMMENT ON COLUMN BranchMergeProposal.queue_status IS 'This is the current state of the merge proposal.';
COMMENT ON COLUMN BranchMergeProposal.date_review_requested IS 'The date that the merge proposal enters the REVIEW_REQUESTED state. This is stored so that we can determine how long a branch has been waiting for code approval.';
COMMENT ON COLUMN BranchMergeProposal.reviewer IS 'The individual who said that the code in this branch is OK to land.';
COMMENT ON COLUMN BranchMergeProposal.date_reviewed IS 'When the reviewer said the code is OK to land.';
COMMENT ON COLUMN BranchMergeProposal.reviewed_revision_id IS 'The Bazaar revision ID that was approved to land.';
COMMENT ON COLUMN BranchMergeProposal.queuer IS 'The individual who submitted the branch to the merge queue. This is usually the merge proposal registrant.';
COMMENT ON COLUMN BranchMergeProposal.date_queued IS 'When the queuer submitted the branch to the merge queue.';
COMMENT ON COLUMN BranchMergeProposal.queued_revision_id IS 'The Bazaar revision ID that is queued to land.';
COMMENT ON COLUMN BranchMergeProposal.merger IS 'The merger is the person who merged the branch.';
COMMENT ON COLUMN BranchMergeProposal.merged_revision_id IS 'The Bazaar revision ID that was actually merged.  If the owner of the source branch is a trusted person, this may be different than the revision_id that was actually queued or reviewed.';
COMMENT ON COLUMN BranchMergeProposal.date_merge_started IS 'If the merge is performed by a bot the time the merge was started is recorded otherwise it is NULL.';
COMMENT ON COLUMN BranchMergeProposal.date_merge_finished IS 'If the merge is performed by a bot the time the merge was finished is recorded otherwise it is NULL.';
COMMENT ON COLUMN BranchMergeProposal.merge_log_file IS 'If the merge is performed by a bot the log file is accessible from the librarian.';
COMMENt ON COLUMN BranchMergeProposal.root_message_id IS 'The root message of this BranchMergeProposal''s mail thread.';
COMMENT ON COLUMN BranchMergeProposal.superseded_by IS 'The proposal to merge has been superceded by this one.';


-- BranchMergeProposalJob

COMMENT ON TABLE BranchMergeProposalJob IS 'Contains references to jobs that are executed for a branch merge proposal.';
COMMENT ON COLUMN BranchMergeProposalJob.job IS 'A reference to a row in the Job table that has all the common job details.';
COMMENT ON COLUMN BranchMergeProposalJob.branch_merge_proposal IS 'The branch merge proposal that this job is for.';
COMMENT ON COLUMN BranchMergeProposalJob.job_type IS 'The type of job, like new proposal, review comment, or new review requested.';
COMMENT ON COLUMN BranchMergeProposalJob.json_data IS 'Data that is specific to the type of job, normally references to code review messages and or votes.';

-- SeriesSourcePackageBranch

COMMENT ON TABLE SeriesSourcePackageBranch IS 'Link between branches and distribution suite.';
COMMENT ON COLUMN SeriesSourcePackageBranch.distroseries IS 'The distroseries the branch is linked to.';
COMMENT ON COLUMN SeriesSourcePackageBranch.pocket IS 'The pocket the branch is linked to.';
COMMENT ON COLUMN SeriesSourcePackageBranch.sourcepackagename IS 'The sourcepackagename the branch is linked to.';
COMMENT ON COLUMN SeriesSourcePackageBranch.branch IS 'The branch being linked to a distribution suite.';
COMMENT ON COLUMN SeriesSourcePackageBranch.registrant IS 'The person who registered this link.';
COMMENT ON COLUMN SeriesSourcePackageBranch.date_created IS 'The date this link was created.';

-- SubunitStream

COMMENT ON TABLE SubunitStream IS 'Raw gz compressed subunit streams.';
COMMENT ON COLUMN SubunitStream.uploader IS 'The account used to upload the stream.';
COMMENT ON COLUMN SubunitStream.date_created IS 'The date of the upload.';
COMMENT ON COLUMN SubunitStream.branch IS 'The branch which the stream was created on/for/with.';
COMMENT ON COLUMN SubunitStream.stream IS 'The library file alias which contains the stream content.';

-- BranchSubscription

COMMENT ON TABLE BranchSubscription IS 'An association between a person or team and a bazaar branch.';
COMMENT ON COLUMN BranchSubscription.person IS 'The person or team associated with the branch.';
COMMENT ON COLUMN BranchSubscription.branch IS 'The branch associated with the person or team.';
COMMENT ON COLUMN BranchSubscription.notification_level IS 'The level of email the person wants to receive from branch updates.';
COMMENT ON COLUMN BranchSubscription.max_diff_lines IS 'If the generated diff for a revision is larger than this number, then the diff is not sent in the notification email.';
COMMENT ON COLUMN BranchSubscription.review_level IS 'The level of email the person wants to receive from review activity';

-- Bug

COMMENT ON TABLE Bug IS 'A software bug that requires fixing. This particular bug may be linked to one or more products or source packages to identify the location(s) that this bug is found.';
COMMENT ON COLUMN Bug.name IS 'A lowercase name uniquely identifying the bug';
COMMENT ON COLUMN Bug.description IS 'A detailed description of the bug. Initially this will be set to the contents of the initial email or bug filing comment, but later it can be edited to give a more accurate description of the bug itself rather than the symptoms observed by the reporter.';
COMMENT ON COLUMN Bug.date_last_message IS 'When the last BugMessage was attached to this Bug. Maintained by a trigger on the BugMessage table.';
COMMENT ON COLUMN Bug.number_of_duplicates IS 'The number of bugs marked as duplicates of this bug, populated by a trigger after setting the duplicateof of bugs.';
COMMENT ON COLUMN Bug.message_count IS 'The number of messages (currently just comments) on this bugbug, maintained by the set_bug_message_count_t trigger.';
COMMENT ON COLUMN Bug.users_affected_count IS 'The number of users affected by this bug, maintained by the set_bug_users_affected_count_t trigger.';
COMMENT ON COLUMN Bug.heat IS 'The relevance of this bug. This value is computed periodically using bug_affects_person and other bug values.';
COMMENT ON COLUMN Bug.heat_last_updated IS 'The time this bug''s heat was last updated, or NULL if the heat has never yet been updated.';
COMMENT ON COLUMN Bug.latest_patch_uploaded IS 'The time when the most recent patch has been attached to this bug or NULL if no patches are attached';
COMMENT ON COLUMN Bug.information_type IS 'Enum describing what type of information is stored, such as type of private or security related data, and used to determine how to apply an access policy.';

-- BugBranch
COMMENT ON TABLE BugBranch IS 'A branch related to a bug, most likely a branch for fixing the bug.';
COMMENT ON COLUMN BugBranch.bug IS 'The bug associated with this branch.';
COMMENT ON COLUMN BugBranch.branch IS 'The branch associated to the bug.';
COMMENT ON COLUMN BugBranch.revision_hint IS 'An optional revision at which this branch became interesting to this bug, and/or may contain a fix for the bug.';
COMMENT ON COLUMN BugBranch.whiteboard IS 'Additional information about the status of the bugfix in this branch.';
COMMENT ON COLUMN BugBranch.registrant IS 'The person who linked the bug to the branch.';

-- BugMute
COMMENT ON TABLE BugMute IS 'Mutes for bug notifications.';
COMMENT ON COLUMN BugMute.person IS 'The person that muted all notifications from this bug.';
COMMENT ON COLUMN BugMute.bug IS 'The bug of this record';
COMMENT ON COLUMN BugMute.date_created IS 'The date at which this mute was created.';

-- BugNomination
COMMENT ON TABLE BugNomination IS 'A bug nominated for fixing in a distroseries or productseries';
COMMENT ON COLUMN BugNomination.bug IS 'The bug being nominated.';
COMMENT ON COLUMN BugNomination.distroseries IS 'The distroseries for which the bug is nominated.';
COMMENT ON COLUMN BugNomination.productseries IS 'The productseries for which the bug is nominated.';
COMMENT ON COLUMN BugNomination.status IS 'The status of the nomination.';
COMMENT ON COLUMN BugNomination.date_created IS 'The date the nomination was submitted.';
COMMENT ON COLUMN BugNomination.date_decided IS 'The date the nomination was approved or declined.';
COMMENT ON COLUMN BugNomination.owner IS 'The person that submitted the nomination';
COMMENT ON COLUMN BugNomination.decider IS 'The person who approved or declined the nomination';

--- BugSubscription
COMMENT ON TABLE BugSubscription IS 'A subscription by a Person to a bug.';
COMMENT ON COLUMN BugSubscription.bug_notification_level IS 'The level of notifications which the Person will receive from this subscription.';

-- BugSubscriptionFilter
COMMENT ON TABLE BugSubscriptionFilter IS 'A filter with search criteria. Emails are sent only if the affected bug matches the specified parameters. The parameters are the same as those used for bugtask searches.';
COMMENT ON COLUMN BugSubscriptionFilter.structuralsubscription IS 'The structural subscription to be filtered.';
COMMENT ON COLUMN BugSubscriptionFilter.bug_notification_level IS 'The volume and type of bug notifications this filter will allow. The value is an item of the enumeration `BugNotificationLevel`.';
COMMENT ON COLUMN BugSubscriptionFilter.find_all_tags IS 'If set, search for bugs having all tags specified in BugSubscriptionFilterTag, else search for bugs having any of the tags specified in BugSubscriptionFilterTag.';
COMMENT ON COLUMN BugSubscriptionFilter.include_any_tags IS 'If True, include messages for bugs having any tag set.';
COMMENT ON COLUMN BugSubscriptionFilter.exclude_any_tags IS 'If True, exclude bugs having any tag set.';
COMMENT ON COLUMN BugSubscriptionFilter.other_parameters IS 'Other filter paremeters. Actual filtering is implemented on Python level.';
COMMENT ON COLUMN BugSubscriptionFilter.description IS 'A description of the filter, allowing subscribers to note the intent of the filter.';

-- BugSubscriptionFilterStatus
COMMENT ON TABLE BugSubscriptionFilterStatus IS 'Filter a bugsubscription by bug task status.';
COMMENT ON COLUMN BugSubscriptionFilterStatus.filter IS 'The subscription filter of this record.';
COMMENT ON COLUMN BugSubscriptionFilterStatus.status IS 'The bug task status.';

-- BugSubscriptionFilterImportance
COMMENT ON TABLE BugSubscriptionFilterImportance IS 'Filter a bugsubscription by bug task status.';
COMMENT ON COLUMN BugSubscriptionFilterImportance.filter IS 'The subscription filter of this record.';
COMMENT ON COLUMN BugSubscriptionFilterImportance.importance IS 'The bug task importance.';

-- BugSubscriptionFilterTag
COMMENT ON TABLE BugSubscriptionFilterTag IS 'Filter by bug tag.';
COMMENT ON COLUMN BugSubscriptionFilterTag.filter IS 'The subscription filter of this record.';
COMMENT ON COLUMN BugSubscriptionFilterTag.tag IS 'A bug tag.';
COMMENT ON COLUMN BugSubscriptionFilterTag.include IS 'If True, send only messages for bugs having this tag, else send only messages for bugs which do not have this tag.';

-- BugSubscriptionFilterMute
COMMENT ON TABLE BugSubscriptionFilterMute IS 'Mutes for subscription filters.';
COMMENT ON COLUMN BugSubscriptionFilterMute.person IS 'The person that muted their subscription to this filter.';
COMMENT ON COLUMN BugSubscriptionFilterMute.filter IS 'The subscription filter of this record';
COMMENT ON COLUMN BugSubscriptionFilterMute.date_created IS 'The date at which this mute was created.';

-- BugSummary

COMMENT ON TABLE BugSummary IS 'A fact table for bug metadata aggregate queries. Each row represents the number of bugs that are in the system addressed by all the dimensions (e.g. product or productseries etc). ';
COMMENT ON COLUMN BugSummary.milestone IS 'A milestone present on the bug. All bugs are also aggregated with a NULL entry for milestone to permit querying totals (because the milestone figures cannot be summed as many milestones can be on a single bug)';
COMMENT ON COLUMN BugSummary.sourcepackagename IS 'The sourcepackagename for the aggregate. Counting bugs in a distribution/distroseries requires selecting all rows by sourcepackagename. If this is too slow, add the bug to the NULL row and select with sourcepackagename is NULL to exclude them from the calculations';

-- BugTag
COMMENT ON TABLE BugTag IS 'Attaches simple text tags to a bug.';
COMMENT ON COLUMN BugTag.bug IS 'The bug the tags is attached to.';
COMMENT ON COLUMN BugTag.tag IS 'The text representation of the tag.';

-- OfficialBugTag
COMMENT ON TABLE OfficialBugTag IS 'Bug tags that have been officially endorced by this product''s or distribution''s lead';

-- BugTask
COMMENT ON TABLE BugTask IS 'Links a given Bug to a particular (sourcepackagename, distro) or product.';
COMMENT ON COLUMN BugTask.targetnamecache IS 'A cached value of the target name of this bugtask, to make it easier to sort and search on the target name.';
COMMENT ON COLUMN BugTask.bug IS 'The bug that is assigned to this (sourcepackagename, distro) or product.';
COMMENT ON COLUMN BugTask.product IS 'The product in which this bug shows up.';
COMMENT ON COLUMN BugTask.productseries IS 'The product series to which the bug is targeted';
COMMENT ON COLUMN BugTask.sourcepackagename IS 'The name of the sourcepackage in which this bug shows up.';
COMMENT ON COLUMN BugTask.distribution IS 'The distro of the named sourcepackage.';
COMMENT ON COLUMN BugTask.status IS 'The general health of the bug, e.g. Accepted, Rejected, etc.';
COMMENT ON COLUMN BugTask.importance IS 'The importance of fixing the bug.';
COMMENT ON COLUMN BugTask.assignee IS 'The person who has been assigned to fix this bug in this product or (sourcepackagename, distro)';
COMMENT ON COLUMN BugTask.date_assigned IS 'The date on which the bug in this (sourcepackagename, distro) or product was assigned to someone to fix';
COMMENT ON COLUMN BugTask.datecreated IS 'A timestamp for the creation of this bug assignment. Note that this is not the date the bug was created (though it might be), it''s the date the bug was assigned to this product, which could have come later.';
COMMENT ON COLUMN BugTask.date_confirmed IS 'The date when this bug transitioned from an unconfirmed status to a confirmed one. If the state regresses to a one that logically occurs before Confirmed, e.g., Unconfirmed, this date is cleared.';
COMMENT ON COLUMN BugTask.date_inprogress IS 'The date on which this bug transitioned from not being in progress to a state >= In Progress. If the status moves back to a pre-In Progress state, this date is cleared';
COMMENT ON COLUMN BugTask.date_closed IS 'The date when this bug transitioned to a resolved state, e.g., Rejected, Fix Released, etc. If the state changes back to a pre-closed state, this date is cleared';
COMMENT ON COLUMN BugTask.milestone IS 'A way to mark a bug for grouping purposes, e.g. to say it needs to be fixed by version 1.2';
COMMENT ON COLUMN BugTask.bugwatch IS 'This column allows us to link a bug
task to a bug watch. In other words, we are connecting the state of the task
to the state of the bug in a different bug tracking system. To the best of
our ability we''ll try and keep the bug task syncronised with the state of
the remote bug watch.';
COMMENT ON COLUMN BugTask.date_left_new IS 'The date when this bug first transitioned out of the NEW status.';
COMMENT ON COLUMN BugTask.date_triaged IS 'The date when this bug transitioned to a status >= TRIAGED.';
COMMENT ON COLUMN BugTask.date_fix_committed IS 'The date when this bug transitioned to a status >= FIXCOMMITTED.';
COMMENT ON COLUMN BugTask.date_fix_released IS 'The date when this bug transitioned to a FIXRELEASED status.';
COMMENT ON COLUMN BugTask.date_left_closed IS 'The date when this bug last transitioned out of a CLOSED status.';
COMMENT ON COLUMN BugTask.date_milestone_set IS 'The date when this bug was targed to the milestone that is currently set.';


-- BugNotification

COMMENT ON TABLE BugNotification IS 'The text representation of changes to a bug, which are used to send email notifications to bug changes.';
COMMENT ON COLUMN BugNotification.bug IS 'The bug that was changed.';
COMMENT ON COLUMN BugNotification.message IS 'The message the contains the textual representation of the change.';
COMMENT ON COLUMN BugNotification.is_comment IS 'Is the change a comment addition.';
COMMENT ON COLUMN BugNotification.date_emailed IS 'When this notification was emailed to the bug subscribers.';
COMMENT ON COLUMN BugNotification.activity IS 'The BugActivity record corresponding to this notification, if any.';
COMMENT ON COLUMN BugNotification.status IS 'The status of this bug notification: pending, omitted, or sent.';


-- BugNotificationAttachment

COMMENT ON TABLE BugNotificationAttachment IS 'Attachments to be attached to a bug notification.';
COMMENT ON COLUMN BugNotificationAttachment.message IS 'A message to be attached to the sent bug notification. It will be attached as a mime/multipart part, with a content type of message/rfc822.';
COMMENT ON COLUMN BugNotificationAttachment.bug_notification IS 'The bug notification, to which things should be attached to.';


-- BugNotificationFilter

COMMENT ON TABLE BugNotificationFilter IS 'BugSubscriptionFilters that caused BugNotification to be generated.';
COMMENT ON COLUMN BugNotificationFilter.bug_subscription_filter IS 'A BugSubscriptionFilter that caused a notification to go off.';
COMMENT ON COLUMN BugNotificationFilter.bug_notification IS 'The bug notification which a filter caused to be emitted.';


-- BugNotificationRecipient
COMMENT ON TABLE BugNotificationRecipient IS 'The recipient for a bug notification.';
COMMENT ON COLUMN BugNotificationRecipient.bug_notification IS 'The notification this recipient should get.';
COMMENT ON COLUMN BugNotificationRecipient.person IS 'The person who should receive this notification.';
COMMENT ON COLUMN BugNotificationRecipient.reason_header IS 'The reason this person is receiving this notification (the value for the X-Launchpad-Message-Rationale header).';
COMMENT ON COLUMN BugNotificationRecipient.reason_body IS 'A line of text describing the reason this person is receiving this notification (to be included in the email message).';


-- BugTracker

COMMENT ON TABLE BugTracker IS 'A bug tracker in some other project. Malone allows us to link Malone bugs with bugs recorded in other bug tracking systems, and to keep the status of the relevant bug task in sync with the status in that upstream bug tracker. So, for example, you might note that Malone bug #43224 is the same as a bug in the Apache bugzilla, number 534536. Then when the upstream guys mark that bug fixed in their bugzilla, Malone know that the bug is fixed upstream.';
COMMENT ON COLUMN BugTracker.bugtrackertype IS 'The type of bug tracker, a pointer to the table of bug tracker types. Currently we know about debbugs and bugzilla bugtrackers, and plan to support roundup and sourceforge as well.';
COMMENT ON COLUMN BugTracker.name IS 'The unique name of this bugtracker, allowing us to refer to it directly.';
COMMENT ON COLUMN BugTracker.summary IS 'A brief summary of this bug tracker, which might for example list any interesting policies regarding the use of the bug tracker. The summary is displayed in bold at the top of the bug tracker page.';
COMMENT ON COLUMN BugTracker.title IS 'A title for the bug tracker, used in listings of all the bug trackers and also displayed at the top of the descriptive page for the bug tracker.';
COMMENT ON COLUMN BugTracker.contactdetails IS 'The contact details of the people responsible for that bug tracker. This allows us to coordinate the syncing of bugs to and from that bug tracker with the responsible people on the other side.';
COMMENT ON COLUMN BugTracker.baseurl IS 'The base URL for this bug tracker. Using our knowledge of the bugtrackertype, and the details in the BugWatch table we are then able to calculate relative URLs for relevant pages in the bug tracker based on this baseurl.';
COMMENT ON COLUMN BugTracker.owner IS 'The person who created this bugtracker entry and who thus has permission to modify it. Ideally we would like this to be the person who coordinates the running of the actual bug tracker upstream.';
COMMENT ON COLUMN BugTracker.version IS 'The version of the bug tracker software being used.';
COMMENT ON COLUMN BugTracker.block_comment_pushing IS 'Whether to block pushing comments to the bug tracker. Having a value of false means that we will push the comments if the bug tracker supports it.';
COMMENT ON COLUMN BugTracker.has_lp_plugin IS 'Whether we have confirmed that the Launchpad plugin was installed on the bug tracker, the last time checkwatches was run.';

-- BugTrackerAlias

COMMENT ON TABLE BugTrackerAlias IS 'A bugtracker alias is a URL that also refers to the same bugtracker as the master bugtracker. For example, a bugtracker might be accessible as both http://www.bugsrus.com/ and http://bugsrus.com/. A bugtracker can have many aliases, and all of them are checked to prevents users registering duplicate bugtrackers inadvertently.';
COMMENT ON COLUMN BugTrackerAlias.bugtracker IS 'The master bugtracker that this alias refers to.';
COMMENT ON COLUMN BugTrackerAlias.base_url IS 'Another base URL for this bug tracker. See BugTracker.baseurl.';

-- BugTrackerPerson

COMMENT ON TABLE BugTrackerPerson IS 'A mapping from a user in an external bug tracker to a Person record in Launchpad. This is used when we can''t get an e-mail address from the bug tracker.';
COMMENT ON COLUMN BugTrackerPerson.date_created IS 'When was this mapping added.';
COMMENT ON COLUMN BugTrackerPerson.bugtracker IS 'The external bug tracker in which this user has an account.';
COMMENT ON COLUMN BugTrackerPerson.name IS 'The (within the bug tracker) unique username in the external bug tracker.';
COMMENT ON COLUMN BugTrackerPerson.person IS 'The Person record in Launchpad this user corresponds to.';

-- BugTrackerComponent

COMMENT ON TABLE BugTrackerComponent IS 'A software component in a remote bug tracker, which can be linked to the corresponding source package in a distribution using this table.';
COMMENT ON COLUMN BugTrackerComponent.name IS 'The name of the component as registered in the remote bug tracker.';
COMMENT ON COLUMN BugTrackerComponent.is_visible IS 'Whether to display or hide the item in the Launchpad user interface.';
COMMENT ON COLUMN BugTrackerComponent.is_custom IS 'Whether the item was added by a user in Launchpad or is kept in sync with the remote bug tracker.';
COMMENT ON COLUMN BugTrackerComponent.component_group IS 'The product or other higher level category used by the remote bug tracker to group projects, if any.';
COMMENT ON COLUMN BugTrackerComponent.distribution IS 'Link to the distribution for the associated source package.  This can be NULL if no ling has been established.';
COMMENT ON COLUMN BugTrackerComponent.source_package_name IS 'The text name of the source package in a distribution that corresponds to this component.  This can be NULL if no link has been established yet.';

-- BugTrackerComponentGroup

COMMENT ON TABLE BugTrackerComponentGroup IS 'A collection of components as modeled in a remote bug tracker, often referred to as a product.  Some bug trackers do not categorize software components this way, so they will have a single default component group that all components belong to.';
COMMENT ON COLUMN BugTrackerComponentGroup.name IS 'The product or category name used in the remote bug tracker for grouping components.';
COMMENT ON COLUMN BugTrackerComponentGroup.bug_tracker IS 'The external bug tracker this component group belongs to.';

-- BugCve

COMMENT ON TABLE BugCve IS 'A table that records the link between a given malone bug number, and a CVE entry.';


-- BugWatch

COMMENT ON COLUMN BugWatch.last_error_type IS 'The type of error which last prevented this entry from being updated. Legal values are defined by the BugWatchErrorType enumeration.';
COMMENT ON COLUMN BugWatch.remote_importance IS 'The importance of the bug as returned by the remote server. This will be converted into a Launchpad BugTaskImportance value.';
COMMENT ON COLUMN BugWatch.remote_lp_bug_id IS 'The bug in Launchpad that the remote bug is pointing at. This can be different than the BugWatch.bug column, since the same remote bug can be linked from multiple bugs in Launchpad, but the remote bug can only link to a single bug in Launchpad. The main use case for this column is to avoid having to query the remote bug tracker for this information, in order to decide whether we need to give this information to the remote bug tracker.';
COMMENT ON COLUMN BugWatch.next_check IS 'The time after which the watch should next be checked. Note that this does not denote an exact schedule for the next check since checkwatches only runs periodically.';


-- BugWatchActivity

COMMENT ON TABLE BugWatchActivity IS 'This table contains a record of each update for a given bug watch. This allows us to track whether a given update was successful or not and, if not, the details of the error which caused the update to fail.';
COMMENT ON COLUMN BugWatchActivity.bug_watch IS 'The bug_watch to which this activity entry relates.';
COMMENT ON COLUMN BugWatchActivity.activity_date IS 'The datetime at which the activity occurred.';
COMMENT ON COLUMN BugWatchActivity.result IS 'The result of the update. Legal values are defined in the BugWatchErrorType enumeration. An update is considered successful if its error_type is NULL.';
COMMENT ON COLUMN BugWatchActivity.message IS 'The message (if any) associated with the update.';
COMMENT ON COLUMN BugWatchActivity.oops_id IS 'The OOPS id, if any, associated with the error that caused the update to fail.';


-- BugAffectsPerson

COMMENT ON TABLE BugAffectsPerson IS 'This table maintains a mapping between bugs and users indicating that they are affected by that bug. The value is calculated and cached in the Bug.users_affected_count column.';
COMMENT ON COLUMN BugAffectsPerson.bug IS 'The bug affecting this person.';
COMMENT ON COLUMN BugAffectsPerson.person IS 'The person affected by this bug.';


-- CodeImport

COMMENT ON TABLE CodeImport IS 'The persistent record of an import from a foreign version control system to Bazaar, from the initial request to the regularly updated import branch.';
COMMENT ON COLUMN CodeImport.branch IS 'The Bazaar branch produced by the import system.  Always non-NULL: a placeholder branch is created when the import is created.  The import is associated to a Product and Series though the branch.';
COMMENT ON COLUMN CodeImport.registrant IS 'The person who originally requested this import.';
COMMENT ON COLUMN CodeImport.owner IS 'The person who is currently responsible for keeping the import details up to date, initially set to the registrant. This person can edit some of the details of the code import branch.';
COMMENT ON COLUMN CodeImport.review_status IS 'Whether this code import request has been reviewed, and whether it was accepted.';
COMMENT ON COLUMN CodeImport.rcs_type IS 'The revision control system used by the import source. The value is defined in dbschema.RevisionControlSystems.';
COMMENT ON COLUMN CodeImport.url IS 'The URL of the foreign VCS branch for this import.';
COMMENT ON COLUMN CodeImport.cvs_root IS 'The $CVSROOT details, probably of the form :pserver:user@host:/path.';
COMMENT ON COLUMN CodeImport.cvs_module IS 'The module in cvs_root to import, often the name of the project.';
COMMENT ON COLUMN CodeImport.date_last_successful IS 'When this code import last succeeded. NULL if this import has never succeeded.';
COMMENT ON COLUMN CodeImport.assignee IS 'The person in charge of delivering this code import and interacting with the owner.';
COMMENT ON COLUMN Codeimport.update_interval IS 'How often should this import be updated. If NULL, defaults to a system-wide value set by the Launchpad administrators.';
--COMMENT ON COLUMN CodeImport.modified_by IS 'The user modifying the CodeImport.  This column is never actually set in the database -- it is only present to communicate to the trigger that creates the event, which will intercept and remove the value for this column.';

-- CodeImportEvent

COMMENT ON TABLE CodeImportEvent IS 'A record of events in the code import system.  Rows in this table are created by triggers on other code import tables.';
COMMENT ON COLUMN CodeImportEvent.entry_type IS 'The type of event that is recorded by this entry. Legal values are defined by the CodeImportEventType enumeration.';
COMMENT ON COLUMN CodeImportEvent.code_import IS 'The code import that was associated to this event, if any and if it has not been deleted.';
COMMENT ON COLUMN CodeImportEvent.person IS 'The user who caused the event, if the event is not automatically generated.';
COMMENT ON COLUMN CodeImportEvent.machine IS 'The code import machine that was concerned by this event, if any.';

-- CodeImportEventData

COMMENT ON TABLE CodeImportEventData IS 'Additional data associated to a particular code import event.';
COMMENT ON COLUMN CodeImportEventData.event IS 'The event the data is associated to.';
COMMENT ON COLUMN CodeImportEventData.data_type IS 'The type of additional data, from the CodeImportEventDataType enumeration.';
COMMENT ON COLUMN CodeImportEventData.data_value IS 'The value of the additional data.  A string.';

-- CodeImportJob

COMMENT ON TABLE CodeImportJob IS 'A pending or active code import job.  There is always such a row for any active import, but it will not run until date_due is in the past.';
COMMENT ON COLUMN CodeImportJob.code_import IS 'The code import that is being worked upon.';
COMMENT ON COLUMN CodeImportJob.machine IS 'The machine job is currently scheduled to run on, or where the job is currently running.';
COMMENT ON COLUMN CodeImportJob.date_due IS 'When the import should happen.';
COMMENT ON COLUMN CodeImportJob.state IS 'One of PENDING (waiting until its due or a machine is online), SCHEDULED (assigned to a machine, but not yet running) or RUNNING (actually in the process of being imported now).';
COMMENT ON COLUMN CodeImportJob.requesting_user IS 'The user who requested the import, if any. Set if and only if reason = REQUEST.';
COMMENT ON COLUMN CodeImportJob.ordering IS 'A measure of how urgent the job is -- queue entries with lower "ordering" should be processed first, or in other works "ORDER BY ordering" returns the most import jobs first.';
COMMENT ON COLUMN CodeImportJob.heartbeat IS 'While the job is running, this field should be updated frequently to indicate that the import job hasn''t crashed.';
COMMENT ON COLUMN CodeImportJob.logtail IS 'The last few lines of output produced by the running job. It should be updated at the same time as the heartbeat.';
COMMENT ON COLUMN CodeImportJob.date_started IS 'When the import began to be processed.';

-- CodeImportResult

COMMENT ON TABLE CodeImportResult IS 'A completed code import job.';
COMMENT ON COLUMN CodeImportResult.code_import IS 'The code import for which the job was run.';
COMMENT ON COLUMN CodeImportResult.machine IS 'The machine the job ran on.';
COMMENT ON COLUMN CodeImportResult.log_file IS 'A partial log of the job for users to see. It is normally only recorded if the job failed in a step that interacts with the remote repository. If a job was successful, or failed in a houskeeping step, the log file would not contain information useful to the user.';
COMMENT ON COLUMN CodeImportResult.log_excerpt IS 'The last few lines of the partial log, in case it is set.';
COMMENT ON COLUMN CodeImportResult.status IS 'How the job ended. Success, some kind of failure, or some kind of interruption before completion.';
COMMENT ON COLUMN CodeImportResult.date_job_started IS 'When the job started to run (date_created is when it finished).';
--COMMENT ON COLUMN CodeImportResult.killing_user IS 'The user who killed the job.';

-- CodeImportMachine

COMMENT ON TABLE CodeImportMachine IS 'The record of a machine capable of performing jobs for the code import system.';
COMMENT ON COLUMN CodeImportMachine.hostname IS 'The (unique) hostname of the machine.';
COMMENT ON COLUMN CodeImportMachine.heartbeat IS 'When the code-import-controller daemon was last known to be running on this machine. If it is not updated for a long time the machine state will change to offline.';
COMMENT ON COLUMN CodeImportMachine.state IS 'Whether the controller daemon on this machine is offline, online, or quiescing (running but not accepting new jobs).';
--COMMENT ON COLUMN CodeImportMachine.quiescing_requested_by IS 'The user who put this machine in the quiescing state.';
--COMMENT ON COLUMN CodeImportMachine.quiescing_message IS 'The reason for the quiescing request.';
--COMMENT ON COLUMN CodeImportMachine.offline_reason IS 'The reason the machine was taken offline, from the CodeImportMachineOfflineReason enumeration.';


-- CodeReviewMessage

COMMENT ON TABLE CodeReviewMessage IS 'A message that is part of a code review discussion.';
COMMENT ON COLUMN CodeReviewMessage.branch_merge_proposal IS 'The merge proposal that is being discussed.';
COMMENT ON COLUMN CodeReviewMessage.message IS 'The actual message.';
COMMENT ON COLUMN CodeReviewMessage.vote IS 'The reviewer''s vote for this message.';
COMMENT ON COLUMN CodeReviewMessage.vote_tag IS 'A short description of the vote';

-- CodeReviewVote

COMMENT ON TABLE CodeReviewVote IS 'Reference to a person''s last vote in a code review discussion.';
COMMENT ON COLUMN CodeReviewVote.branch_merge_proposal IS 'The BranchMergeProposal for the code review.';
COMMENT ON COLUMN CodeReviewVote.reviewer IS 'The person performing the review.';
COMMENT ON COLUMN CodeReviewVote.review_type IS 'The aspect of the code being reviewed.';
COMMENT ON COLUMN CodeReviewVote.registrant IS 'The person who registered this vote';
COMMENT ON COLUMN CodeReviewVote.vote_message IS 'The message associated with the vote';
COMMENT ON COLUMN CodeReviewVote.date_created IS 'The date this vote reference was created';

-- CommercialSubscription
COMMENT ON TABLE CommercialSubscription is 'A Commercial Subscription entry for a project.  Projects with licenses of Other/Proprietary must purchase a subscription in order to use Launchpad.';
COMMENT ON COLUMN CommercialSubscription.date_created IS 'The date this subscription was created in Launchpad.';
COMMENT ON COLUMN CommercialSubscription.date_last_modified IS 'The date this subscription was last modified.';
COMMENT ON COLUMN CommercialSubscription.date_starts IS 'The beginning date for this subscription.  It is invalid until that date.';
COMMENT ON COLUMN CommercialSubscription.date_expires IS 'The expiration date for this subscription.  It is invalid after that date.';
COMMENT ON COLUMN CommercialSubscription.status IS 'The current status.  One of: SUBSCRIBED, LAPSED, SUSPENDED.';
COMMENT ON COLUMN CommercialSubscription.product IS 'The product this subscription enables.';
COMMENT ON COLUMN CommercialSubscription.registrant IS 'The person who created this subscription.';
COMMENT ON COLUMN CommercialSubscription.purchaser IS 'The person who purchased this subscription.';
COMMENT ON COLUMN CommercialSubscription.whiteboard IS 'A place for administrators to store comments related to this subscription.';
COMMENT ON COLUMN CommercialSubscription.sales_system_id IS 'A reference in the external sales system (e.g. Salesforce) that can be used to identify this subscription.';

-- CustomLanguageCode
COMMENT ON TABLE CustomLanguageCode IS 'Overrides translation importer''s interpretation of language codes where needed.';
COMMENT ON COLUMN CustomLanguageCode.product IS 'Product for which this custom language code applies (alternative to distribution + source package name).';
COMMENT ON COLUMN CustomLanguageCode.distribution IS 'Distribution in which this custom language code applies (if not a product).';
COMMENT ON COLUMN CustomLanguageCode.sourcepackagename IS 'Source package name to which this custom language code applies; goes with distribution.';
COMMENT ON COLUMN CustomLanguageCode.language_code IS 'Custom language code; need not be for a real language, and typically not for a "useful" language.';
COMMENT ON COLUMN CustomLanguageCode.language IS 'Language to which code really refers in this context, or NULL if files with this code are to be rejected.';

-- CVE

COMMENT ON TABLE CVE IS 'A CVE Entry. The formal database of CVE entries is available at http://cve.mitre.org/ and we sync that database into Launchpad on a regular basis.';
COMMENT ON COLUMN CVE.sequence IS 'The official CVE entry number. It takes the form XXXX-XXXX where the first four digits are a year indicator, like 2004, and the latter four are the sequence number of the vulnerability in that year.';
COMMENT ON COLUMN CVE.status IS 'The current status of the CVE. The values are documented in dbschema.CVEState, and are Entry, Candidate, and Deprecated.';
COMMENT ON COLUMN CVE.datemodified IS 'The last time this CVE entry changed in some way - including addition or modification of references.';


-- CveReference

COMMENT ON TABLE CveReference IS 'A reference in the CVE system that shows what outside tracking numbers are associated with the CVE. These are tracked in the CVE database and extracted from the daily XML dump that we fetch.';
COMMENT ON COLUMN CveReference.source IS 'The SOURCE of the CVE reference. This is a text string, like XF or BUGTRAQ or MSKB. Each string indicates a different kind of reference. The list of known types is documented on the CVE web site. At some future date we might turn this into an enum rather than a text, but for the moment we prefer to keep it fluid and just suck in what CVE gives us. This means that CVE can add new source types without us having to update our code.';
COMMENT ON COLUMN CveReference.url IS 'The URL to this reference out there on the web, if it was present in the CVE database.';
COMMENT ON COLUMN CveReference.content IS 'The content of the ref in the CVE database. This is sometimes a comment, sometimes a description, sometimes a bug number... it is not predictable.';

-- Diff

COMMENT ON TABLE Diff IS 'Information common to static or preview diffs';
COMMENT ON COLUMN Diff.added_lines_count IS 'The number of lines added in the diff.';
COMMENT ON COLUMN Diff.diff_text IS 'The library copy of the fulltext of the diff';
COMMENT ON COLUMN Diff.diff_lines_count IS 'The number of lines in the diff';
COMMENT ON COLUMN Diff.diffstat IS 'Statistics about the diff';
COMMENT ON COLUMN Diff.removed_lines_count IS 'The number of lines removed in the diff';

-- DistributionSourcepackage

COMMENT ON TABLE DistributionSourcePackage IS 'Representing a sourcepackage in a distribution across all distribution series.';
COMMENT ON COLUMN DistributionSourcePackage.bug_reporting_guidelines IS 'Guidelines to the end user for reporting bugs on a particular a source package in a distribution.';
COMMENT ON COLUMN DistributionSourcePackage.max_bug_heat IS 'The highest heat value across bugs for this source package. NULL means it has not yet been calculated.';
COMMENT ON COLUMN DistributionSourcePackage.total_bug_heat IS 'Sum of bug heat matching the package distribution and sourcepackagename. NULL means it has not yet been calculated.';
COMMENT ON COLUMN DistributionSourcePackage.bug_count IS 'Number of bugs matching the package distribution and sourcepackagename. NULL means it has not yet been calculated.';
COMMENT ON COLUMN DistributionSourcePackage.po_message_count IS 'Number of translations matching the package distribution and sourcepackagename. NULL means it has not yet been calculated.';
COMMENT ON COLUMN DistributionSourcePackage.is_upstream_link_allowed IS 'Whether an upstream link may be added if it does not already exist.';
COMMENT ON COLUMN DistributionSourcePackage.bug_reported_acknowledgement IS 'A message of acknowledgement to display to a bug reporter after they''ve reported a new bug.';
COMMENT ON COLUMN DistributionSourcePackage.enable_bugfiling_duplicate_search IS 'Enable/disable a search for posiible duplicates when a bug is filed.';

-- DistributionSourcePackageCache

COMMENT ON TABLE DistributionSourcePackageCache IS 'A cache of the text associated with binary and source packages in the distribution. This table allows for fast queries to find a source packagename that matches a given text.';
COMMENT ON COLUMN DistributionSourcePackageCache.distribution IS 'The distribution in which we are checking.';
COMMENT ON COLUMN DistributionSourcePackageCache.sourcepackagename IS 'The source package name for which we are caching details.';
COMMENT ON COLUMN DistributionSourcePackageCache.name IS 'The source package name itself. This is just a copy of the value of sourcepackagename.name. We have it here so it can be part of the full text index.';
COMMENT ON COLUMN DistributionSourcePackageCache.binpkgnames IS 'The binary package names of binary packages generated from these source packages across all architectures.';
COMMENT ON COLUMN DistributionSourcePackageCache.binpkgsummaries IS 'The aggregated summaries of all the binary packages generated from these source packages in this distribution.';
COMMENT ON COLUMN DistributionSourcePackageCache.binpkgdescriptions IS 'The aggregated description of all the binary packages generated from these source packages in this distribution.';
COMMENT ON COLUMN DistributionSourcePackageCache.changelog IS 'A concatenation of the source package release changelogs for this source package, where the status is not REMOVED.';
COMMENT ON COLUMN DistributionSourcePackageCache.archive IS 'The archive where the source is published.';

-- DistroSeriesDifference
COMMENT ON TABLE DistroSeriesDifference IS 'A difference of versions for a package in a derived distroseries and its parent distroseries.';
COMMENT ON COLUMN DistroSeriesDifference.derived_series IS 'The derived distroseries with the difference from its parent.';
COMMENT ON COLUMN DistroSeriesDifference.parent_series IS 'The parent distroseries with the difference from its child.';
COMMENT ON COLUMN DistroSeriesDifference.source_package_name IS 'The name of the source package which is different in the two series.';
COMMENT ON COLUMN DistroSeriesDifference.package_diff IS 'The most recent package diff that was created for the base version to derived version.';
COMMENT ON COLUMN DistroSeriesDifference.parent_package_diff IS 'The most recent package diff that was created for the base version to the parent version.';
COMMENT ON COLUMN DistroSeriesDifference.status IS 'A distroseries difference can be needing attention, ignored or resolved.';
COMMENT ON COLUMN DistroSeriesDifference.difference_type IS 'The type of difference that this record represents - a package unique to the derived series, or missing, or in both.';
COMMENT ON COLUMN DistroSeriesDifference.source_version IS 'The version of the package in the derived series.';
COMMENT ON COLUMN DistroSeriesDifference.parent_source_version IS 'The version of the package in the parent series.';
COMMENT ON COLUMN DistroSeriesDifference.base_version IS 'The common base version of the package for the derived and parent series.';

-- DistroSeriesDifferenceMessage
COMMENT ON TABLE DistroSeriesDifferenceMessage IS 'A message/comment on a distro series difference.';
COMMENT ON COLUMN DistroSeriesDifferenceMessage.distro_series_difference IS 'The distro series difference for this comment.';
COMMENT ON COLUMN DistroSeriesDifferenceMessage.message IS 'The comment for the distro series difference.';

-- DistroSeriesParent
COMMENT ON TABLE DistroSeriesParent IS 'A list of all the derived distroseries for a parent series.';
COMMENT ON COLUMN DistroSeriesParent.derived_series is 'The derived distroseries';
COMMENT ON COLUMN DistroSeriesParent.parent_series is 'The parent distroseries';
COMMENT ON COLUMN DistroSeriesParent.initialized is 'Whether or not the derived series was initialized by copying packages from the parent.';
COMMENT ON COLUMN DistroSeriesParent.is_overlay is 'Whether or not the derived series is an overlay over the parent series.';
COMMENT ON COLUMN DistroSeriesParent.ordering is 'The parent ordering. Parents are ordered in ascending order starting from 1.';
COMMENT ON COLUMN DistroSeriesParent.pocket is 'The pocket for this overlay.';
COMMENT ON COLUMN DistroSeriesParent.component is 'The component for this overlay.';

-- DistroSeriesPackageCache

COMMENT ON TABLE DistroSeriesPackageCache IS 'A cache of the text associated with binary packages in the distroseries. This table allows for fast queries to find a binary packagename that matches a given text.';
COMMENT ON COLUMN DistroSeriesPackageCache.distroseries IS 'The distroseries in which we are checking.';
COMMENT ON COLUMN DistroSeriesPackageCache.binarypackagename IS 'The binary package name for which we are caching details.';
COMMENT ON COLUMN DistroSeriesPackageCache.name IS 'The binary package name itself. This is just a copy of the value of binarypackagename.name. We have it here so it can be part of the full text index.';
COMMENT ON COLUMN DistroSeriesPackageCache.summary IS 'A single summary for one of the binary packages of this name in this distroseries. We could potentially have binary packages in different architectures with the same name and different summaries, so this is a way of collapsing to one arbitrarily-chosen one, for display purposes. The chances of actually having different summaries and descriptions is pretty small. It could happen, though, because of the way package superseding works when a package does not build on a specific architecture.';
COMMENT ON COLUMN DistroSeriesPackageCache.summaries IS 'The aggregated summaries of all the binary packages with this name in this distroseries.';
COMMENT ON COLUMN DistroSeriesPackageCache.descriptions IS 'The aggregated description of all the binary packages with this name in this distroseries.';
COMMENT ON COLUMN DistroSeriesPackageCache.archive IS 'The archive where the binary is published.';

-- EmailAddress

COMMENT ON COLUMN EmailAddress.email IS 'An email address used by a Person. The email address is stored in a casesensitive way, but must be case insensitivly unique.';
COMMENT ON INDEX emailaddress__person__key IS 'Ensures that a Person only has one preferred email address';


-- FeaturedProject

COMMENT ON TABLE FeaturedProject IS 'A list of featured projects. This table is really just a list of pillarname IDs, if a project''s pillar name is in this list then it is a featured project and will be listed on the Launchpad home page.';
COMMENT ON COLUMN FeaturedProject.pillar_name IS 'A reference to PillarName.id';

-- FeatureFlag

COMMENT ON TABLE FeatureFlag IS
    'Configuration that varies by the active scope and that \
can be changed without restarting Launchpad
<https://dev.launchpad.net/LEP/FeatureFlags>';

COMMENT ON COLUMN FeatureFlag.scope IS
    'Scope in which this setting is active';

COMMENT ON COLUMN FeatureFlag.priority IS
    'Higher priority flags override lower';

COMMENT ON COLUMN FeatureFlag.flag IS
    'Name of the flag being controlled';

-- FeatureFlagChange

COMMENT ON TABLE FeatureFlagChangelogEntry IS 'A record of changes to the FeatureFlag table.';
COMMENT ON COLUMN FeatureFlagChangelogEntry.date_changed IS 'The timestamp for when the change was made';
COMMENT ON COLUMN FeatureFlagChangelogEntry.diff IS 'A unified diff of the change.';
COMMENT ON COLUMN FeatureFlagChangelogEntry.comment IS 'A comment explaining the change.';
COMMENT ON COLUMN FeatureFlagChangelogEntry.person IS 'The person who made this change.';

-- KarmaCategory

COMMENT ON TABLE KarmaCategory IS 'A category of karma. This allows us to
present an overall picture of the different areas where a user has been
active.';


-- LaunchpadStatistic

COMMENT ON TABLE LaunchpadStatistic IS 'A store of system-wide statistics or other integer values, keyed by names. The names are unique and the values can be any integer. Each field has a place to store the timestamp when it was last updated, so it is possible to know how far out of date any given statistic is.';

-- MailingList

COMMENT ON TABLE MailingList IS 'The mailing list for a team.  Teams may have zero or one mailing list, and a mailing list is associated with exactly one team.  This table manages the state changes that a team mailing list can go through, and it contains information that will be used to instruct Mailman how to create, delete, and modify mailing lists (via XMLRPC).';
COMMENT ON COLUMN MailingList.team IS 'The team this mailing list is associated with.';
COMMENT ON COLUMN MailingList.registrant IS 'The id of the Person who requested this list be created.';
COMMENT ON COLUMN MailingList.date_registered IS 'Date the list was requested to be created';
COMMENT ON COLUMN MailingList.reviewer IS 'The id of the Person who reviewed the creation request, or NULL if not yet reviewed.';
COMMENT ON COLUMN MailingList.date_reviewed IS 'The date the request was reviewed, or NULL if not yet reviewed.';
COMMENT ON COLUMN MailingList.date_activated IS 'The date the list was (last) activated.  If the list is not yet active, this field will be NULL.';
COMMENT ON COLUMN MailingList.status IS 'The current status of the mailing list, as a dbschema.MailingListStatus value.';
COMMENT ON COLUMN MailingList.welcome_message IS 'Text sent to new members when they are subscribed to the team list.  If NULL, no welcome message is sent.';

-- MailingListSubscription

COMMENT ON TABLE MailingListSubscription IS 'Track the subscriptions of a person to team mailing lists.';
COMMENT ON COLUMN MailingListSubscription.person IS 'The person who is subscribed to the mailing list.';
COMMENT ON COLUMN MailingListSubscription.mailing_list IS 'The mailing list this person is subscribed to.';
COMMENT ON COLUMN MailingListSubscription.date_joined IS 'The date this person subscribed to the mailing list.';
COMMENT ON COLUMN MailingListSubscription.email_address IS 'Which of the person''s email addresses are subscribed to the mailing list.  This may be NULL to indicate that it''s the person''s preferred address.';

-- MergeDirectiveJob
COMMENT ON TABLE MergeDirectiveJob IS 'A job to process a merge directive.';
COMMENT ON COLUMN MergeDirectiveJob.job IS 'The job associated with this MergeDirectiveJob.';
COMMENT ON COLUMN MergeDirectiveJob.merge_directive IS 'Full MIME content of the message containing the merge directive.';
COMMENt ON COLUMN MergeDirectiveJob.action IS 'Enumeration of the action to perform with the merge directive; push or create merge proposal.';


-- MessageApproval

COMMENT ON TABLE MessageApproval IS 'Track mailing list postings awaiting approval from the team owner.';
COMMENT ON COLUMN MessageApproval.message IS 'Foreign key to message table pointing to the posted message.';
COMMENT ON COLUMN MessageApproval.posted_by IS 'The person who posted the message.';
COMMENT ON COLUMN MessageApproval.mailing_list IS 'The mailing list to which the message was posted.';
COMMENT ON COLUMN MessageApproval.posted_message IS 'Foreign key to libraryfilealias table pointing to where the posted message''s text lives.';
COMMENT ON COLUMN MessageApproval.posted_date IS 'The date the message was posted.';
COMMENT ON COLUMN MessageApproval.status IS 'The status of the posted message.  Values are described in dbschema.PostedMessageStatus.';
COMMENT ON COLUMN MessageApproval.reason IS 'The reason for the current status if any. This information will be displayed to the end user and mailing list moderators need to be aware of this - not a private whiteboard.';
COMMENT ON COLUMN MessageApproval.disposed_by IS 'The person who disposed of (i.e. approved or rejected) the message, or NULL if no disposition has yet been made.';
COMMENT ON COLUMN MessageApproval.disposal_date IS 'The date on which this message was disposed, or NULL if no disposition has yet been made.';


-- PreviewDiff
COMMENT ON TABLE PreviewDiff IS 'Contains information about preview diffs, without duplicating information with BranchMergeProposal.';
COMMENT ON COLUMN PreviewDiff.conflicts IS 'The text description of any conflicts present.';
COMMENT ON COLUMN PreviewDiff.diff IS 'The last Diff generated for this PreviewDiff.';
COMMENT ON COLUMN PreviewDiff.dependent_revision_id IS 'The dependant branch revision_id used to generate this diff.';
COMMENT ON COLUMN PreviewDiff.source_revision_id IS 'The source branch revision_id used to generate this diff.';
COMMENT ON COLUMN PreviewDiff.target_revision_id IS 'The target branch revision_id used to generate this diff.';


-- ProcessAcceptedBugsJob
COMMENT ON TABLE ProcessAcceptedBugsJob IS 'Contains references to jobs for modifying bugs in response to accepting package uploads.';
COMMENT ON COLUMN ProcessAcceptedBugsJob.job IS 'The Job related to this ProcessAcceptedBugsJob.';
COMMENT ON COLUMN ProcessAcceptedBugsJob.distroseries IS 'The DistroSeries of the accepted upload.';
COMMENT ON COLUMN ProcessAcceptedBugsJob.sourcepackagerelease IS 'The SourcePackageRelease of the accepted upload.';
COMMENT ON COLUMN ProcessAcceptedBugsJob.json_data IS 'A JSON struct containing data for the job.';


-- Product
COMMENT ON TABLE Product IS 'Product: a DOAP Product. This table stores core information about an open source product. In Launchpad, anything that can be shipped as a tarball would be a product, and in some cases there might be products for things that never actually ship, depending on the project. For example, most projects will have a ''website'' product, because that allows you to file a Malone bug against the project website. Note that these are not actual product releases, which are stored in the ProductRelease table.';
COMMENT ON COLUMN Product.owner IS 'The Product owner would typically be the person who created this product in Launchpad. But we will encourage the upstream maintainer of a product to become the owner in Launchpad. The Product owner can edit any aspect of the Product, as well as appointing people to specific roles with regard to the Product. Also, the owner can add a new ProductRelease and also edit Rosetta POTemplates associated with this product.';
COMMENT ON COLUMN Product.registrant IS 'The Product registrant is the Person who created the product in Launchpad.  It is set at creation and is never changed thereafter.';
COMMENT ON COLUMN Product.summary IS 'A brief summary of the product. This will be displayed in bold at the top of the product page, above the description.';
COMMENT ON COLUMN Product.description IS 'A detailed description of the product, highlighting primary features of the product that may be of interest to end-users. The description may also include links and other references to useful information on the web about this product. The description will be displayed on the product page, below the product summary.';
COMMENT ON COLUMN Product.project IS 'Every Product belongs to one and only one Project, which is referenced in this column.';
COMMENT ON COLUMN Product.listurl IS 'This is the URL where information about a mailing list for this Product can be found. The URL might point at a web archive or at the page where one can subscribe to the mailing list.';
COMMENT ON COLUMN Product.programminglang IS 'This field records, in plain text, the name of any significant programming languages used in this product. There are no rules, conventions or restrictions on this field at present, other than basic sanity. Examples might be "Python", "Python, C" and "Java".';
COMMENT ON COLUMN Product.downloadurl IS 'The download URL for a Product should be the best place to download that product, typically off the relevant Project web site. This should not point at the actual file, but at a web page with download information.';
COMMENT ON COLUMN Product.lastdoap IS 'This column stores a cached copy of the last DOAP description we saw for this product. See the Project.lastdoap field for more info.';
COMMENT ON COLUMN Product.sourceforgeproject IS 'The SourceForge project name for this product. This is not unique as SourceForge doesn''t use the same project/product structure as DOAP.';
COMMENT ON COLUMN Product.freshmeatproject IS 'The FreshMeat project name for this product. This is not unique as FreshMeat does not have the same project/product structure as DOAP';
COMMENT ON COLUMN Product.reviewed IS 'Whether or not someone at Canonical has reviewed this product.';
COMMENT ON COLUMN Product.active IS 'Whether or not this product should be considered active.';
COMMENT ON COLUMN Product.translationgroup IS 'The TranslationGroup that is responsible for translations for this product. Note that the Product may be part of a Project which also has a TranslationGroup, in which case the translators from both the product and project translation group have permission to edit the translations of this product.';
COMMENT ON COLUMN Product.translationpermission IS 'The level of openness of this product''s translation process. The enum lists different approaches to translation, from the very open (anybody can edit any translation in any language) to the completely closed (only designated translators can make any changes at all).';
COMMENT ON COLUMN Product.official_rosetta IS 'Whether or not this product upstream uses Rosetta for its official translation team and coordination. This is a useful indicator in terms of whether translations in Rosetta for this upstream will quickly move upstream.';
COMMENT ON COLUMN Product.official_malone IS 'Whether or not this product upstream uses Malone for an official bug tracker. This is useful to help indicate whether or not people are likely to pick up on bugs registered in Malone.';
COMMENT ON COLUMN Product.official_answers IS 'Whether or not this product upstream uses Answers officialy. This is useful to help indicate whether or not that a question will receive an answer.';
COMMENT ON COLUMN Product.bug_supervisor IS 'Person who is responsible for managing bugs on this product.';
COMMENT ON COLUMN Product.driver IS 'This is a driver for the overall product. This driver will be able to approve nominations of bugs and specs to any series in the product, including backporting to old stable series. You want the smallest group of "overall drivers" here, because you can add specific drivers to each series individually.';
COMMENT ON COLUMN Product.translation_focus IS 'The ProductSeries that should get the translation effort focus.';
--COMMENT ON COLUMN Product.bugtracker IS 'The external bug tracker that is used to track bugs primarily for this product, if it''s different from the project bug tracker.';
COMMENT ON COLUMN Product.development_focus IS 'The product series that is the current focus of development.';
COMMENT ON COLUMN Product.homepage_content IS 'A home page for this product in the Launchpad.';
COMMENT ON COLUMN Product.icon IS 'The library file alias to a small image to be used as an icon whenever we are referring to a product.';
COMMENT ON COLUMN Product.mugshot IS 'The library file alias of a mugshot image to display as the branding of a product, on its home page.';
COMMENT ON COLUMN Product.logo IS 'The library file alias of a smaller version of this product''s mugshot.';
COMMENT ON COLUMN Product.private_specs IS 'Indicates whether specs filed in this product are automatically marked as private.';
COMMENT ON COLUMN Product.license_info IS 'Additional information about licenses that are not included in the License enumeration.';
COMMENT ON COLUMN Product.enable_bug_expiration IS 'Indicates whether automatic bug expiration is enabled.';
COMMENT ON COLUMN Product.official_blueprints IS 'Whether or not this product upstream uses Blueprints officially. This is useful to help indicate whether or not the upstream project will be actively watching the blueprints in Launchpad.';
COMMENT ON COLUMN Product.bug_reporting_guidelines IS 'Guidelines to the end user for reporting bugs on this product.';
COMMENT ON COLUMN Product.reviewer_whiteboard IS 'A whiteboard for Launchpad admins, registry experts and the project owners to capture the state of current issues with the project.';
COMMENT ON COLUMN Product.license_approved IS 'The Other/Open Source license has been approved by an administrator.';
COMMENT ON COLUMN Product.remote_product IS 'The ID of this product on its remote bug tracker.';
COMMENT ON COLUMN Product.max_bug_heat IS 'The highest heat value across bugs for this product.';
COMMENT ON COLUMN Product.bug_reported_acknowledgement IS 'A message of acknowledgement to display to a bug reporter after they''ve reported a new bug.';
COMMENT ON COLUMN Product.enable_bugfiling_duplicate_search IS 'Enable/disable a search for posiible duplicates when a bug is filed.';
COMMENT ON COLUMN Product.information_type IS 'Enum describing what type of information is stored, such as type of private or security related data, and used to determine how to apply an access policy.';

-- ProductJob
COMMENT ON TABLE productjob IS 'Contains references to jobs for updating projects and sendd notifications.';
COMMENT ON COLUMN productjob.job IS 'A reference to a row in the Job table that has all the common job details.';
COMMENT ON COLUMN productjob.job_type IS 'The type of job, like 30-day-renewal.';
COMMENT ON COLUMN productjob.product IS 'The product that is being updated or the maintainers needs notification.';
COMMENT ON COLUMN productjob.json_data IS 'Data that is specific to the job type, such as text for notifications.';

-- ProductLicense
COMMENT ON TABLE ProductLicense IS 'The licenses that cover the software for a product.';
COMMENT ON COLUMN ProductLicense.product IS 'Foreign key to the product that has licenses associated with it.';
COMMENT ON COLUMN ProductLicense.license IS 'An integer referencing a value in the License enumeration in product.py';

-- ProductRelease

COMMENT ON TABLE ProductRelease IS 'A Product Release. This is table stores information about a specific ''upstream'' software release, like Apache 2.0.49 or Evolution 1.5.4.';
COMMENT ON COLUMN ProductRelease.milestone IS 'The milestone for this product release. This is scheduled to become a NOT NULL column, so every product release will be linked to a unique milestone.';
COMMENT ON COLUMN ProductRelease.datecreated IS 'The timestamp when this product release was created.';
COMMENT ON COLUMN ProductRelease.datereleased IS 'The date when this version of the product was released.';
COMMENT ON COLUMN ProductRelease.release_notes IS 'Description of changes in this product release.';
COMMENT ON COLUMN ProductRelease.changelog IS 'Detailed description of changes in this product release.';
COMMENT ON COLUMN ProductRelease.owner IS 'The person who created this product release.';

-- ProductReleaseFile

COMMENT ON TABLE ProductReleaseFile IS 'Links a ProductRelease to one or more files in the Librarian.';
COMMENT ON COLUMN ProductReleaseFile.productrelease IS 'This is the product release this file is associated with';
COMMENT ON COLUMN ProductReleaseFile.libraryfile IS 'This is the librarian entry';
COMMENT ON COLUMN ProductReleaseFile.signature IS 'This is the signature of the librarian entry as uploaded by the user.';
COMMENT ON COLUMN ProductReleaseFile.description IS 'A description of what the file contains';
COMMENT ON COLUMN ProductReleaseFile.filetype IS 'An enum of what kind of file this is. Code tarballs are marked for special treatment (importing into bzr)';
COMMENT ON COLUMN ProductReleaseFile.uploader IS 'The person who uploaded this file.';
COMMENT ON COLUMN ProductReleaseFile.date_uploaded IS 'The date this file was uploaded.';
COMMENT on COLUMN ProductReleaseFile.id IS '';

-- ProductSeries
COMMENT ON TABLE ProductSeries IS 'A ProductSeries is a set of product releases that are related to a specific version of the product. Typically, each major release of the product starts a new ProductSeries. These often map to a branch in the revision control system of the project, such as "2_0_STABLE". A few conventional Series names are "head" for releases of the HEAD branch, "1.0" for releases with version numbers like "1.0.0" and "1.0.1".  Each product has at least one ProductSeries';
COMMENT ON COLUMN ProductSeries.name IS 'The name of the ProductSeries is like a unix name, it should not contain any spaces and should start with a letter or number. Good examples are "2.0", "3.0", "head" and "development".';
COMMENT ON COLUMN ProductSeries.status IS 'The current status of this productseries.';
COMMENT ON COLUMN ProductSeries.summary IS 'A summary of this Product Series. A good example would include the date the series was initiated and whether this is the current recommended series for people to use. The summary is usually displayed at the top of the page, in bold, just beneath the title and above the description, if there is a description field.';
COMMENT ON COLUMN ProductSeries.driver IS 'This is a person or team who can approve spes and bugs for implementation or fixing in this specific series. Note that the product drivers and project drivers can also do this for any series in the product or project, so use this only for the specific team responsible for this specific series.';
COMMENT ON COLUMN ProductSeries.releasefileglob IS 'A fileglob that lets us
see which URLs are potentially new upstream tarball releases. For example:
http://ftp.gnu.org/gnu/libtool/libtool-1.5.*.gz.';
COMMENT ON COLUMN ProductSeries.releaseverstyle IS 'An enum giving the style
of this product series release version numbering system.  The options are
documented in dbschema.UpstreamReleaseVersionStyle.  Most applications use
Gnu style numbering, but there are other alternatives.';
COMMENT ON COLUMN ProductSeries.branch IS 'The branch for this product
series.';
COMMENT ON COLUMN ProductSeries.translations_autoimport_mode IS 'Level of
translations imports from codehosting branch: None, templates only, templates
and translations. See TranslationsBranchImportMode.';
COMMENT ON COLUMN ProductSeries.translations_branch IS 'Branch to push translations updates to.';

-- Project
COMMENT ON TABLE Project IS 'Project: A DOAP Project. This table is the core of the DOAP section of the Launchpad database. It contains details of a single open source Project and is the anchor point for products, potemplates, and translationefforts.';
COMMENT ON COLUMN Project.owner IS 'The owner of the project will initially be the person who creates this Project in the system. We will encourage upstream project leaders to take on this role. The Project owner is able to edit the project.';
COMMENT ON COLUMN Project.registrant IS 'The registrant is the Person who created the project in Launchpad.  It is set at creation and is never changed thereafter.';
COMMENT ON COLUMN Project.driver IS 'This person or team has the ability to approve specs as goals for any series in any product in the project. Similarly, this person or team can approve bugs as targets for fixing in any series, or backporting of fixes to any series.';
COMMENT ON COLUMN Project.summary IS 'A brief summary of this project. This
will be displayed in bold text just above the description and below the
title. It should be a single paragraph of not more than 80 words.';
COMMENT ON COLUMN Project.description IS 'A detailed description of this
project. This should primarily be focused on the organisational aspects of
the project, such as the people involved and the structures that the project
uses to govern itself. It might refer to the primary products of the project
but the detailed descriptions of those products should be in the
Product.description field, not here. So, for example, useful information
such as the dates the project was started and the way the project
coordinates itself are suitable here.';
COMMENT ON COLUMN Project.homepageurl IS 'The home page URL of this project. Note that this could well be the home page of the main product of this project as well, if the project is too small to have a separate home page for project and product.';
COMMENT ON COLUMN Project.wikiurl IS 'This is the URL of a wiki that includes information about the project. It might be a page in a bigger wiki, or it might be the top page of a wiki devoted to this project.';
COMMENT ON COLUMN Project.lastdoap IS 'This column stores a cached copy of the last DOAP description we saw for this project. We cache the last DOAP fragment for this project because there may be some aspects of it which we are unable to represent in the database (such as multiple homepageurl''s instead of just a single homepageurl) and storing the DOAP file allows us to re-parse it later and recover this information when our database model has been updated appropriately.';
COMMENT ON COLUMN Project.name IS 'A short lowercase name uniquely identifying the product. Use cases include being used as a key in URL traversal.';
COMMENT ON COLUMN Project.sourceforgeproject IS 'The SourceForge project name for this project. This is not unique as SourceForge doesn''t use the same project/product structure as DOAP.';
COMMENT ON COLUMN Project.freshmeatproject IS 'The FreshMeat project name for this project. This is not unique as FreshMeat does not have the same project/product structure as DOAP';
COMMENT ON COLUMN Project.reviewed IS 'Whether or not someone at Canonical has reviewed this project.';
COMMENT ON COLUMN Project.active IS 'Whether or not this project should be considered active.';
COMMENT ON COLUMN Project.translationgroup IS 'The translation group that has permission to edit translations across all products in this project. Note that individual products may have their own translationgroup, in which case those translators will also have permission to edit translations for that product.';
COMMENT ON COLUMN Project.translationpermission IS 'The level of openness of
this project''s translation process. The enum lists different approaches to
translation, from the very open (anybody can edit any translation in any
language) to the completely closed (only designated translators can make any
changes at all).';
-- COMMENT ON COLUMN Project.bugtracker IS 'The external bug tracker that is used to track bugs primarily for products within this project.';
COMMENT ON COLUMN Project.homepage_content IS 'A home page for this project in the Launchpad.';
COMMENT ON COLUMN Project.icon IS 'The library file alias to a small image to be used as an icon whenever we are referring to a project.';
COMMENT ON COLUMN Project.mugshot IS 'The library file alias of a mugshot image to display as the branding of a project, on its home page.';
COMMENT ON COLUMN Project.logo IS 'The library file alias of a smaller version of this product''s mugshot.';
COMMENT ON COLUMN Project.bug_reporting_guidelines IS 'Guidelines to the end user for reporting bugs on products in this project.';
COMMENT ON COLUMN Project.reviewer_whiteboard IS 'A whiteboard for Launchpad admins, registry experts and the project owners to capture the state of current issues with the project.';
COMMENT ON COLUMN Project.max_bug_heat IS 'The highest heat value across bugs for products in this project.';
COMMENT ON COLUMN Project.bug_reported_acknowledgement IS 'A message of acknowledgement to display to a bug reporter after they''ve reported a new bug.';

-- POTMsgSet
COMMENT ON TABLE POTMsgSet IS 'This table is stores a collection of msgids
without their translations and all kind of information associated to that set
of messages that could be found in a potemplate file.';
COMMENT ON COLUMN POTMsgSet.context IS 'Context uniquely defining a message when there are messages with same primemsgids.';
COMMENT ON COLUMN POTMsgSet.msgid_singular IS 'The singular msgid for this message.';
COMMENT ON COLUMN POTMsgSet.msgid_plural IS 'The plural msgid for this message.';
COMMENT ON COLUMN POTMsgSet.commenttext IS 'The comment text that is associated to this message set.';
COMMENT ON COLUMN POTMsgSet.filereferences IS 'The list of files and their line number where this message set was extracted from.';
COMMENT ON COLUMN POTMsgSet.sourcecomment IS 'The comment that was extracted from the source code.';
COMMENT ON COLUMN POTMsgSet.flagscomment IS 'The flags associated with this set (like c-format).';

-- POTemplate
COMMENT ON TABLE POTemplate IS 'This table stores a pot file for a given product.';
COMMENT ON COLUMN POTemplate.sourcepackagename IS 'A reference to a sourcepackage name from where this POTemplate comes.';
COMMENT ON COLUMN POTemplate.distroseries IS 'A reference to the distribution from where this POTemplate comes.';
COMMENT ON COLUMN POTemplate.sourcepackageversion IS 'The sourcepackage version string from where this potemplate was imported last time with our buildd <-> Rosetta gateway.';
COMMENT ON COLUMN POTemplate.header IS 'The header of a .pot file when we import it. Most important info from it is POT-Creation-Date and custom headers.';
COMMENT ON COLUMN POTemplate.name IS 'The name of the POTemplate set. It must be unique';
COMMENT ON COLUMN POTemplate.productseries IS 'A reference to a ProductSeries from where this POTemplate comes.';
COMMENT ON COLUMN POTemplate.path IS 'The path to the .pot source file inside the tarball tree, including the filename.';
COMMENT ON COLUMN POTemplate.from_sourcepackagename IS 'The sourcepackagename from where the last .pot file came (only if it''s different from POTemplate.sourcepackagename)';
COMMENT ON COLUMN POTemplate.source_file IS 'Reference to Librarian file storing the last uploaded template file.';
COMMENT ON COLUMN POTemplate.source_file_format IS 'File format for the Librarian file referenced in "source_file" column.';
COMMENT ON COLUMN POTemplate.translation_domain IS 'The translation domain for this POTemplate';

-- POFile
COMMENT ON TABLE POFile IS 'This table stores a PO file for a given PO template.';
COMMENT ON COLUMN POFile.path IS 'The path (included the filename) inside the tree from where the content was imported.';
COMMENT ON COLUMN POFile.from_sourcepackagename IS 'The sourcepackagename from where the last .po file came (only if it''s different from POFile.potemplate.sourcepackagename)';
COMMENT ON COLUMN POFile.unreviewed_count IS 'Number of POTMsgSets with new,
unreviewed TranslationMessages for this POFile.';

-- TranslationRelicensingAgreement
COMMENT ON TABLE TranslationRelicensingAgreement IS 'Who of translation contributors wants their translations relicensed and who does not.';
COMMENT ON COLUMN TranslationRelicensingAgreement.person IS 'A translator which has submitted their answer.';
COMMENT ON COLUMN TranslationRelicensingAgreement.allow_relicensing IS 'Does this person want their translations relicensed under BSD.';
COMMENT ON COLUMN TranslationRelicensingAgreement.date_decided IS 'Date when the last change of opinion was registered.';

-- TranslationTemplatesBuild
COMMENT ON TABLE TranslationTemplatesBuild IS 'Build-farm record of a translation templates build.';
COMMENT ON COLUMN TranslationTemplatesBuild.build_farm_job IS 'Associated BuildFarmJob.';
COMMENT ON COLUMN TranslationTemplatesBuild.branch IS 'Branch to build templates out of.';

-- RevisionAuthor
COMMENT ON TABLE RevisionAuthor IS 'All distinct authors for revisions.';
COMMENT ON COLUMN RevisionAuthor.name IS 'The exact text extracted from the branch revision.';
COMMENT ON COLUMN RevisionAuthor.email IS 'A valid email address extracted from the name.  This email address may or may not be associated with a Launchpad user at this stage.';
COMMENT ON COLUMN RevisionAuthor.person IS 'The Launchpad person that has a verified email address that matches the email address of the revision author.';

-- RevisionCache
COMMENT ON TABLE RevisionCache IS 'A cache of revisions where the revision date is in the last 30 days.';
COMMENT ON COLUMN RevisionCache.revision IS 'A reference to the actual revision.';
COMMENT ON COLUMN RevisionCache.revision_author IS 'A refernce to the revision author for the revision.';
COMMENT ON COLUMN RevisionCache.revision_date IS 'The date the revision was made.  Should be within 30 days of today (or the cleanup code is not cleaning up).';
COMMENT ON COLUMN RevisionCache.product IS 'The product that the revision is found in (if it is indeed in a particular product).';
COMMENT ON COLUMN RevisionCache.distroseries IS 'The distroseries for which a source package branch contains the revision.';
COMMENT ON COLUMN RevisionCache.sourcepackagename IS 'The sourcepackagename for which a source package branch contains the revision.';
COMMENT ON COLUMN RevisionCache.private IS 'True if the revision is only found in private branches, False if it can be found in a non-private branch.';

-- specificationworkitem
COMMENT ON TABLE specificationworkitem IS 'A work item which is a piece of work relating to a blueprint.';
COMMENT ON COLUMN specificationworkitem.id IS 'The id of the work item.';
COMMENT ON COLUMN specificationworkitem.title IS 'The title of the work item.';
COMMENT ON COLUMN specificationworkitem.specification IS 'The blueprint that this work item is a part of.';
COMMENT ON COLUMN specificationworkitem.assignee IS 'The person who is assigned to complete the work item.';
COMMENT ON COLUMN specificationworkitem.milestone IS 'The milestone this work item is targetted to.';
COMMENT ON COLUMN specificationworkitem.date_created IS 'The date on which the work item was created.';
COMMENT ON COLUMN specificationworkitem.sequence IS 'The sequence number specifies the order of work items in the UI.';
COMMENT ON COLUMN specificationworkitem.deleted IS 'Marks if the work item has been deleted. To be able to keep history we do not want to actually delete them from the database.';

-- specificationworkitemchange
COMMENT ON TABLE specificationworkitemchange IS 'A property change on a work item.';
COMMENT ON COLUMN specificationworkitemchange.id IS 'Id of the change.';
COMMENT ON COLUMN specificationworkitemchange.work_item IS 'The work item for which a propery has changed.';
COMMENT ON COLUMN specificationworkitemchange.new_status IS 'The new status for the work item.';
COMMENT ON COLUMN specificationworkitemchange.new_milestone IS 'The new milestone the work item has been targetted to.';
COMMENT ON COLUMN specificationworkitemchange.new_assignee IS 'The person which the work item has be assigned to.';
COMMENT ON COLUMN specificationworkitemchange.date_created IS 'The time of the change.';

-- specificationworkitemstats
COMMENT ON TABLE specificationworkitemstats IS 'Stats for work items that are collected by a scheduled script.';
COMMENT ON COLUMN specificationworkitemstats.id IS 'The id for this stats collection.';
COMMENT ON COLUMN specificationworkitemstats.specification IS 'The related blueprint.';
COMMENT ON COLUMN specificationworkitemstats.day IS 'Day when the stats where collected.';
COMMENT ON COLUMN specificationworkitemstats.status IS 'The work item status that work items are counted for.';
COMMENT ON COLUMN specificationworkitemstats.assignee IS 'The assignee that work items are counted for.';
COMMENT ON COLUMN specificationworkitemstats.milestone IS 'The milestone that work items are counted for.';
COMMENT ON COLUMN specificationworkitemstats.count IS 'The number of work items for the blueprint with the particular status, assignee and milestone.';

-- Sprint
COMMENT ON TABLE Sprint IS 'A meeting, sprint or conference. This is a convenient way to keep track of a collection of specs that will be discussed, and the people that will be attending.';
COMMENT ON COLUMN Sprint.driver IS 'The driver (together with the registrant or owner) is responsible for deciding which topics will be accepted onto the agenda of the sprint.';
COMMENT ON COLUMN Sprint.time_zone IS 'The timezone of the sprint, stored in text format from the Olsen database names, like "US/Eastern".';
COMMENT ON COLUMN Sprint.homepage_content IS 'A home page for this sprint in the Launchpad.';
COMMENT ON COLUMN Sprint.icon IS 'The library file alias to a small image to be used as an icon whenever we are referring to a sprint.';
COMMENT ON COLUMN Sprint.mugshot IS 'The library file alias of a mugshot image to display as the branding of a sprint, on its home page.';
COMMENT ON COLUMN Sprint.logo IS 'The library file alias of a smaller version of this sprint''s mugshot.';

-- SprintAttendance
COMMENT ON TABLE SprintAttendance IS 'The record that someone will be attending a particular sprint or meeting.';
COMMENT ON COLUMN SprintAttendance.attendee IS 'The person attending the sprint.';
COMMENT ON COLUMN SprintAttendance.sprint IS 'The sprint the person is attending.';
COMMENT ON COLUMN SprintAttendance.time_starts IS 'The time from which the person will be available to participate in meetings at the sprint.';
COMMENT ON COLUMN SprintAttendance.time_ends IS 'The time of departure from the sprint or conference - this is the last time at which the person is available for meetings during the sprint.';
COMMENT ON COLUMN SprintAttendance.is_physical IS 'Is the person physically attending the sprint';


-- SprintSpecification
COMMENT ON TABLE SprintSpecification IS 'The link between a sprint and a specification, so that we know which specs are going to be discussed at which sprint.';
COMMENT ON COLUMN SprintSpecification.status IS 'Whether or not the spec has been approved on the agenda for this sprint.';
COMMENT ON COLUMN SprintSpecification.whiteboard IS 'A place to store comments specifically related to this spec being on the agenda of this meeting.';
COMMENT ON COLUMN SprintSpecification.registrant IS 'The person who nominated this specification for the agenda of the sprint.';
COMMENT ON COLUMN SprintSpecification.decider IS 'The person who approved or declined this specification for the sprint agenda.';
COMMENT ON COLUMN SprintSpecification.date_decided IS 'The date this specification was approved or declined for the agenda.';

-- TeamMembership
COMMENT ON TABLE TeamMembership IS 'The direct membership of a person on a given team.';
COMMENT ON COLUMN TeamMembership.person IS 'The person.';
COMMENT ON COLUMN TeamMembership.team IS 'The team.';
COMMENT ON COLUMN TeamMembership.status IS 'The state of the membership.';
COMMENT ON COLUMN TeamMembership.date_created IS 'The date this membership was created.';
COMMENT ON COLUMN TeamMembership.date_joined IS 'The date this membership was made active for the first time.';
COMMENT ON COLUMN TeamMembership.date_expires IS 'The date this membership will expire, if any.';
COMMENT ON COLUMN TeamMembership.last_changed_by IS 'The person who reviewed the last change to this membership.';
COMMENT ON COLUMN TeamMembership.last_change_comment IS 'The comment left by the reviewer for the change.';
COMMENT ON COLUMN TeamMembership.date_last_changed IS 'The date this membership was last changed.';
COMMENT ON COLUMN TeamMembership.proposed_by IS 'The user who proposed the person as member of the team.';
COMMENT ON COLUMN TeamMembership.proponent_comment IS 'The comment left by the proponent.';
COMMENT ON COLUMN TeamMembership.date_proposed IS 'The date of the proposal.';
COMMENT ON COLUMN TeamMembership.acknowledged_by IS 'The member (or someone acting on his behalf) who accepts an invitation to join a team';
COMMENT ON COLUMN TeamMembership.date_acknowledged IS 'The date of acknowledgement.';
COMMENT ON COLUMN TeamMembership.acknowledger_comment IS 'The comment left by the person who acknowledged the membership.';
COMMENT ON COLUMN TeamMembership.reviewed_by IS 'The team admin who reviewed (approved/declined) the membership.';
COMMENT ON COLUMN TeamMembership.reviewer_comment IS 'The comment left by the approver.';
COMMENT ON COLUMN TeamMembership.date_reviewed IS 'The date the membership was
approved/declined.';

-- TeamParticipation
COMMENT ON TABLE TeamParticipation IS 'The participation of a person on a team, which can be a direct or indirect membership.';
COMMENT ON COLUMN TeamParticipation.person IS 'The member.';
COMMENT ON COLUMN TeamParticipation.team IS 'The team.';

-- TranslationMessage
COMMENT ON TABLE TranslationMessage IS 'This table stores a concrete
translation for a POTMsgSet message. It knows who, when and where did it,
and whether it was reviewed by someone and when was it reviewed.';
COMMENT ON COLUMN TranslationMessage.potmsgset IS 'The template message which
this translation message is a translation of.';
COMMENT ON COLUMN TranslationMessage.date_created IS 'The date we saw this
translation first.';
COMMENT ON COLUMN TranslationMessage.submitter IS 'The person that made
the submission through the web to Launchpad, or the last translator on the
translation file that we are processing, or the person who uploaded that
pofile to Launchpad. In short, our best guess as to the person who is
contributing that translation.';
COMMENT ON COLUMN TranslationMessage.date_reviewed IS 'The date when this
message was reviewed for last time.';
COMMENT ON COLUMN TranslationMessage.reviewer IS 'The person who did the
review and accepted current translations.';
COMMENT ON COLUMN TranslationMessage.msgstr0 IS 'Translation for plural form 0
(if any).';
COMMENT ON COLUMN TranslationMessage.msgstr1 IS 'Translation for plural form 1
(if any).';
COMMENT ON COLUMN TranslationMessage.msgstr2 IS 'Translation for plural form 2
(if any).';
COMMENT ON COLUMN TranslationMessage.msgstr3 IS 'Translation for plural form 3
(if any).';
COMMENT ON COLUMN TranslationMessage.comment IS 'Text of translator
comment from the translation file.';
COMMENT ON COLUMN TranslationMessage.origin IS 'The source of this
translation. This indicates whether the translation was in a translation file
that we parsed (probably one published in a package or branch or tarball), in
which case its value will be 1, or was submitted through the web, in which
case its value will be 2.';
COMMENT ON COLUMN TranslationMessage.validation_status IS 'Whether we have
validated this translation. Being 0 the value that says this row has not been
validated yet, 1 the value that says it is correct and 2 the value noting that
there was an unknown error with the validation.';
COMMENT ON COLUMN TranslationMessage.is_current_ubuntu IS 'Whether this translation
is being used in Ubuntu.';
COMMENT ON COLUMN TranslationMessage.is_current_upstream IS 'Whether this translation
is being used upstream.';
COMMENT ON COLUMN TranslationMessage.was_obsolete_in_last_import IS 'Whether
this translation was obsolete in last imported file.';

-- Question
COMMENT ON TABLE Question IS 'A question, or support request, for a distribution or for an application. Such questions are created by end users who need support on a particular feature or package or product.';
COMMENT ON COLUMN Question.assignee IS 'The person who has been assigned to resolve this question. Note that there is no requirement that every question be assigned somebody. Anybody can chip in to help resolve a question, and if they think they have done so we call them the "answerer".';
COMMENT ON COLUMN Question.answerer IS 'The person who last claimed to have "solved" this support question, giving a response that the owner believe should be sufficient to close the question. This will move the status of the question to "SOLVED". Note that the only person who can actually set the status to SOLVED is the person who asked the question.';
COMMENT ON COLUMN Question.answer IS 'The QuestionMessage that was accepted by the submitter as the "answer" to the question';
COMMENT ON COLUMN Question.product IS 'The upstream product to which this quesiton is related. Note that a quesiton MUST be linked either to a product, or to a distribution.';
COMMENT ON COLUMN Question.distribution IS 'The distribution for which a question was filed. Note that a request MUST be linked either to a product or a distribution.';
COMMENT ON COLUMN Question.sourcepackagename IS 'An optional source package name. This only makes sense if the question is bound to a distribution.';
COMMENT ON COLUMN Question.datelastquery IS 'The date we last saw a comment from the requester (owner).';
COMMENT ON COLUMN Question.datelastresponse IS 'The date we last saw a comment from somebody other than the requester.';
COMMENT ON COLUMN Question.dateaccepted IS 'The date we "confirmed" or "accepted" this question. It is usually set to the date of the first response by someone other than the requester. This allows us to track the time between first request and first response.';
COMMENT ON COLUMN Question.datedue IS 'The date this question is "due", if such a date can be established. Usually this will be set automatically on the basis of a support contract SLA commitment.';
COMMENT ON COLUMN Question.date_solved IS 'The date this question was last marked as solved by the requester (owner). The requester either found a solution, or accepted an answer from another user.';
COMMENT ON COLUMN Question.dateclosed IS 'The date the requester marked this question CLOSED.';
COMMENT ON COLUMN Question.language IS 'The language of the question''s title and description.';
COMMENT ON COLUMN Question.whiteboard IS 'A general status whiteboard. This is a scratch space to which arbitrary data can be added (there is only one constant whiteboard with no history). It is displayed at the top of the question. So its a useful way for projects to add their own semantics or metadata to the Answer Tracker.';
COMMENT ON COLUMN Question.faq IS 'The FAQ document that contains the long answer to this question.';

-- QuestionBug

COMMENT ON TABLE QuestionBug IS 'A link between a question and a bug, showing that the bug is somehow related to this question.';

-- QuestionMessage

COMMENT ON TABLE QuestionMessage IS 'A link between a question and a message. This means that the message will be displayed on the question page.';
COMMENT ON COLUMN QuestionMessage.action IS 'The action on the question that was done with this message. This is a value from the QuestionAction enum.';
COMMENT ON COLUMN QuestionMessage.new_status IS 'The status of the question after this message.';
COMMENT ON COLUMN QuestionMessage.owner IS 'Denormalised owner from Message, used for efficient queries on commentors.';

-- QuestionReopening

COMMENT ON TABLE QuestionReopening IS 'A record of the times when a question was re-opened. In each case we store the time that it happened, the person who did it, and the person who had previously answered / rejected the question.';
COMMENT ON COLUMN QuestionReopening.reopener IS 'The person who reopened the question.';
COMMENT ON COLUMN QuestionReopening.answerer IS 'The person who was previously listed as the answerer of the question.';
COMMENT ON COLUMN QuestionReopening.priorstate IS 'The state of the question before it was reopened. You can reopen a question that is ANSWERED, or CLOSED, or REJECTED.';


-- QuestionSubscription

COMMENT ON TABLE QuestionSubscription IS 'A subscription of a person to a particular question.';


-- FAQ
COMMENT ON TABLE FAQ IS 'A technical document containing the answer to a common question.';
COMMENT ON COLUMN FAQ.id IS 'The FAQ document sequence number.';
COMMENT ON COLUMN FAQ.title IS 'The document title.';
COMMENT ON COLUMN FAQ.tags IS 'White-space separated list of tags.';
COMMENT ON COLUMN FAQ.content IS 'The content of FAQ. It can also contain a short summary and a link.';
COMMENT ON COLUMN FAQ.product IS 'The product to which this document is
related. Either "product" or "distribution" must be set.';
COMMENT ON COLUMN FAQ.distribution IS 'The distribution to which this document
is related. Either "product" or "distribution" must be set.';
COMMENT ON COLUMN FAQ.owner IS 'The person who created the document.';
COMMENT ON COLUMN FAQ.date_created IS 'The datetime when the document was created.';
COMMENT ON COLUMN FAQ.last_updated_by IS 'The person who last modified the document.';
COMMENT ON COLUMN FAQ.date_last_updated IS 'The datetime when the document was last modified.';


-- DistroSeriesLanguage

COMMENT ON TABLE DistroSeriesLanguage IS 'A cache of the current translation status of that language across an entire distroseries.';
COMMENT ON COLUMN DistroSeriesLanguage.dateupdated IS 'The date these statistucs were last updated.';
COMMENT ON COLUMN DistroSeriesLanguage.currentcount IS 'As per IRosettaStats.';
COMMENT ON COLUMN DistroSeriesLanguage.updatescount IS 'As per IRosettaStats.';
COMMENT ON COLUMN DistroSeriesLanguage.rosettacount IS 'As per IRosettaStats.';
COMMENT ON COLUMN DistroSeriesLanguage.unreviewed_count IS 'As per IRosettaStats.';
COMMENT ON COLUMN DistroSeriesLanguage.contributorcount IS 'The total number of contributors to the translation of this distroseries into this language.';

COMMENT ON COLUMN SourcePackageName.name IS
    'A lowercase name identifying one or more sourcepackages';
COMMENT ON COLUMN BinaryPackageName.name IS
    'A lowercase name identifying one or more binarypackages';


-- Distribution

COMMENT ON COLUMN Distribution.members IS 'Person or team with upload and commit priviledges relating to this distribution. Other rights may be assigned to this role in the future.';
COMMENT ON COLUMN Distribution.mirror_admin IS 'Person or team with privileges to mark a mirror as official.';
COMMENT ON COLUMN Distribution.driver IS 'The team or person responsible for approving goals for each release in the distribution. This should usually be a very small team because the Distribution driver can approve items for backporting to past releases as well as the current release under development. Each distroseries has its own driver too, so you can have the small superset in the Distribution driver, and then specific teams per distroseries for backporting, for example, or for the current release management team on the current development focus release.';
COMMENT ON COLUMN Distribution.translationgroup IS 'The translation group that is responsible for all translation work in this distribution.';
COMMENT ON COLUMN Distribution.translationpermission IS 'The level of openness of this distribution''s translation process. The enum lists different approaches to translation, from the very open (anybody can edit any translation in any language) to the completely closed (only designated translators can make any changes at all).';
COMMENT ON COLUMN Distribution.bug_supervisor IS 'Person who is responsible for managing bugs on this distribution.';
COMMENT ON COLUMN Distribution.official_rosetta IS 'Whether or not this distribution uses Rosetta for its official translation team and coordination.';
COMMENT ON COLUMN Distribution.official_malone IS 'Whether or not this distribution uses Malone for an official bug tracker.';
COMMENT ON COLUMN Distribution.official_answers IS 'Whether or not this product upstream uses Answers officialy.';

COMMENT ON COLUMN Distribution.translation_focus IS 'The DistroSeries that should get the translation effort focus.';
COMMENT ON COLUMN Distribution.language_pack_admin IS 'The Person or Team that handle language packs for the distro release.';
COMMENT ON COLUMN Distribution.enable_bug_expiration IS 'Indicates whether automatic bug expiration is enabled.';
COMMENT ON COLUMN Distribution.bug_reporting_guidelines IS 'Guidelines to the end user for reporting bugs on this distribution.';
COMMENT ON COLUMN Distribution.reviewer_whiteboard IS 'A whiteboard for Launchpad admins, registry experts and the project owners to capture the state of current issues with the project.';
COMMENT ON COLUMN Distribution.max_bug_heat IS 'The highest heat value across bugs for this distribution.';
COMMENT ON COLUMN Distribution.bug_reported_acknowledgement IS 'A message of acknowledgement to display to a bug reporter after they''ve reported a new bug.';
COMMENT ON COLUMN Distribution.registrant IS 'The person in launchpad who registered this distribution.';
COMMENT ON COLUMN Distribution.package_derivatives_email IS 'The optional email address template to use when sending emails about package updates in a distributrion. The string {package_name} in the template will be replaced with the actual package name being updated.';
COMMENT ON COLUMN Distribution.redirect_release_uploads IS 'Whether uploads to the release pocket of this distribution should be redirected to the proposed pocket instead.';

-- DistroSeries

COMMENT ON COLUMN DistroSeries.summary IS 'A brief summary of the distro release. This will be displayed in bold at the top of the distroseries page, above the distroseries description. It should include any high points that are particularly important to draw to the attention of users.';
COMMENT ON COLUMN DistroSeries.description IS 'An extensive list of the features in this release of the distribution. This will be displayed on the main distro release page, below the summary.';
COMMENT ON COLUMN DistroSeries.hide_all_translations IS 'Whether we should hid
e all available translations for this distro release to non admin users.';
COMMENT ON COLUMN DistroSeries.messagecount IS 'This is a cached value and may be a few hours out of sync with reality. It should, however, be in sync with the values in DistroSeriesLanguage, and should never be updated separately. The total number of translation messages in this distro release, as per IRosettaStats.';
COMMENT ON COLUMN DistroSeries.nominatedarchindep IS 'This is the DistroArchSeries nominated to build architecture independent packages within this DistroRelase, it is mandatory for buildable distroseries, i.e., Auto Build System will avoid to create build jobs for a DistroSeries with no nominatedarchindep, but the database model allow us to do it (for non-buildable DistroSeries). See further info in NominatedArchIndep specification.';
COMMENT ON COLUMN DistroSeries.binarycount IS 'A cache of the number of distinct binary package names published in this distro release.';
COMMENT ON COLUMN DistroSeries.sourcecount IS 'A cache of the number of distinct source package names published in this distro release.';
COMMENT ON COLUMN DistroSeries.language_pack_base IS 'Current full export language pack for this distribution release.';
COMMENT ON COLUMN DistroSeries.language_pack_delta IS 'Current language pack update based on language_pack_base information.';
COMMENT ON COLUMN DistroSeries.language_pack_proposed IS 'Either a full or update language pack being tested to be used in language_pack_base or language_pack_delta.';
COMMENT ON COLUMN DistroSeries.language_pack_full_export_requested IS 'Whether next language pack export should be a full export or an update.';
COMMENT ON COLUMN DistroSeries.proposed_not_automatic IS 'Whether the -proposed pocket is set NotAutomatic and ButAutomaticUpgrades so that apt does not offer users upgrades into -proposed, but does offer upgrades within it.';


-- PackageCopyJob

COMMENT ON TABLE PackageCopyJob IS 'Contains references to jobs for copying packages between archives.';
COMMENT ON COLUMN PackageCopyJob.source_archive IS 'The archive from which packages are copied.';
COMMENT ON COLUMN PackageCopyJob.target_archive IS 'The archive to which packages are copied.';
COMMENT ON COLUMN PackageCopyJob.target_distroseries IS 'The distroseries to which packages are copied.';
COMMENT ON COLUMN PackageCopyJob.job_type IS 'The type of job';
COMMENT ON COLUMN PackageCopyJob.json_data IS 'A JSON struct containing data for the job.';


-- PackageDiff

COMMENT ON TABLE PackageDiff IS 'This table stores diffs bettwen two scpecific SourcePackageRelease versions.';
COMMENT ON COLUMN PackageDiff.date_requested IS 'Instant when the diff was requested.';
COMMENT ON COLUMN PackageDiff.requester IS 'The Person responsible for the request.';
COMMENT ON COLUMN PackageDiff.from_source IS 'The SourcePackageRelease to diff from.';
COMMENT ON COLUMN PackageDiff.to_source IS 'The SourcePackageRelease to diff to.';
COMMENT ON COLUMN PackageDiff.date_fulfilled IS 'Instant when the diff was completed.';
COMMENT ON COLUMN PackageDiff.diff_content IS 'LibraryFileAlias containing the th diff results.';
COMMENT ON COLUMN PackageDiff.status IS 'Request status, PENDING(0) when created then goes to COMPLETED(1) or FAILED(2), both terminal status where diff_content and date_fulfilled will contain the results of the request.';


-- PackageUpload
COMMENT ON TABLE PackageUpload IS 'An upload. This table stores information pertaining to uploads to a given DistroSeries/Archive.';

COMMENT ON COLUMN PackageUpload.status IS 'This is an integer field containing the current status of the upload. Possible values are given by the UploadStatus class in dbschema.py';

COMMENT ON COLUMN PackageUpload.distroseries IS 'This integer field refers to the DistroSeries to which this upload is targeted';

COMMENT ON COLUMN PackageUpload.pocket IS 'This is the pocket the upload is targeted at.';

COMMENT ON COLUMN PackageUpload.changesfile IS 'The changes file associated with this upload.';

COMMENT ON COLUMN PackageUpload.archive IS 'The archive to which this upload is targetted.';

-- PackageUploadSource
COMMENT ON TABLE PackageUploadSource IS 'Link between an upload and a source package. This table stores information pertaining to the source files in a package upload.';

COMMENT ON COLUMN PackageUploadSource.packageupload IS 'This integer field refers to the PackageUpload row that this source belongs to.';

COMMENT ON COLUMN PackageUploadSource.sourcepackagerelease IS 'This integer field refers to the SourcePackageRelease record related to this upload.';

-- PackageUploadBuild
COMMENT ON TABLE PackageUploadBuild IS 'An upload binary build. This table stores information pertaining to the builds in a package upload.';

COMMENT ON COLUMN PackageUploadBuild.packageupload IS 'This integer field refers to the PackageUpload row that this source belongs to.';

COMMENT ON COLUMN PackageUploadBuild.build IS 'This integer field refers to the Build record related to this upload.';

-- PackageUploadCustom
COMMENT ON TABLE PackageUploadCustom IS 'An uploaded custom format file. This table stores information pertaining to the custom upload formats in a package upload.';

COMMENT ON COLUMN PackageUploadCustom.packageupload IS 'The PackageUpload row this refers to.';

COMMENT ON COLUMN PackageUploadCustom.customformat IS 'The format of this particular custom uploaded file.';

COMMENT ON COLUMN PackageUploadCustom.libraryfilealias IS 'The actual file as a librarian alias.';

-- SourcePackageName
COMMENT ON COLUMN SourcePackageName.name IS
    'A lowercase name identifying one or more sourcepackages';
COMMENT ON COLUMN BinaryPackageName.name IS
    'A lowercase name identifying one or more binarypackages';

-- BinaryPackagePublishingHistory
COMMENT ON TABLE BinaryPackagePublishingHistory IS 'PackagePublishingHistory: The history of a BinaryPackagePublishing record. This table represents the lifetime of a publishing record from inception to deletion. Records are never removed from here and in time the publishing table may become a view onto this table. A column being NULL indicates there''s no data for that state transition. E.g. a package which is removed without being superseded won''t have datesuperseded or supersededby filled in.';
COMMENT ON COLUMN BinaryPackagePublishingHistory.binarypackagename IS 'Reference to a BinaryPackageName.';
COMMENT ON COLUMN BinaryPackagePublishingHistory.binarypackagerelease IS 'The binarypackage being published.';
COMMENT ON COLUMN BinaryPackagePublishingHistory.distroarchseries IS 'The distroarchseries into which the binarypackage is being published.';
COMMENT ON COLUMN BinaryPackagePublishingHistory.status IS 'The current status of the publishing.';
COMMENT ON COLUMN BinaryPackagePublishingHistory.component IS 'The component into which the publishing takes place.';
COMMENT ON COLUMN BinaryPackagePublishingHistory.section IS 'The section into which the publishing takes place.';
COMMENT ON COLUMN BinaryPackagePublishingHistory.priority IS 'The priority at which the publishing takes place.';
COMMENT ON COLUMN BinaryPackagePublishingHistory.datecreated IS 'The date/time on which the publishing record was created.';
COMMENT ON COLUMN BinaryPackagePublishingHistory.datepublished IS 'The date/time on which the source was actually published into an archive.';
COMMENT ON COLUMN BinaryPackagePublishingHistory.datesuperseded IS 'The date/time on which the source was superseded by a new source.';
COMMENT ON COLUMN BinaryPackagePublishingHistory.supersededby IS 'The build which superseded this package. This seems odd but it is important because a new build may not actually build a given binarypackage and we need to supersede it appropriately';
COMMENT ON COLUMN BinaryPackagePublishingHistory.datemadepending IS 'The date/time on which this publishing record was made to be pending removal from the archive.';
COMMENT ON COLUMN BinaryPackagePublishingHistory.scheduleddeletiondate IS 'The date/time at which the package is/was scheduled to be deleted.';
COMMENT ON COLUMN BinaryPackagePublishingHistory.dateremoved IS 'The date/time at which the package was actually deleted.';
COMMENT ON COLUMN BinaryPackagePublishingHistory.pocket IS 'The pocket into which this record is published. The RELEASE pocket (zero) provides behaviour as normal. Other pockets may append things to the distroseries name such as the UPDATES pocket (-updates) or the SECURITY pocket (-security).';
COMMENT ON COLUMN BinaryPackagePublishingHistory.archive IS 'Target archive for this publishing record.';
COMMENT ON COLUMN BinaryPackagePublishingHistory.removed_by IS 'Person responsible for the removal.';
COMMENT ON COLUMN BinaryPackagePublishingHistory.removal_comment IS 'Reason why the publication was removed.';
COMMENT ON COLUMN BinaryPackagePublishingHistory.phased_update_percentage IS 'Percentage of users for whom this package should be recommended. NULL indicates no phasing, i.e. publish the update for everyone.';

-- Processor

COMMENT ON TABLE Processor IS 'A single processor for which code might be compiled. For example, i386, P2, P3, P4, Itanium1, Itanium2...';
COMMENT ON COLUMN Processor.name IS 'The name of this processor, for example, i386, Pentium, P2, P3, P4, Itanium, Itanium2, K7, Athlon, Opteron... it should be short and unique.';

-- DistroArchSeries

COMMENT ON COLUMN DistroArchSeries.processor IS 'A link to the Processor table, giving the architecture of this DistroArchSeries.';
COMMENT ON COLUMN DistroArchSeries.architecturetag IS 'The name of this architecture in the context of this specific distro release. For example, some distributions might label amd64 as amd64, others might call is x86_64. This information is used, for example, in determining the names of the actual package files... such as the "amd64" part of "apache2_2.0.56-1_amd64.deb"';
COMMENT ON COLUMN DistroArchSeries.official IS 'Whether or not this architecture or "port" is an official release. If it is not official then you may not be able to install it or get all the packages for it.';
COMMENT ON COLUMN DistroArchSeries.package_count IS 'A cache of the number of binary packages published in this distro arch release. The count only includes packages published in the release pocket.';
COMMENT ON COLUMN DistroArchSeries.supports_virtualized IS 'Whether or not
virtualized build support should be provided by this specific distroarchseries';
COMMENT ON COLUMN DistroArchSeries.enabled IS 'Whether to allow build creation and publishing for this DistroArchSeries.';

-- LauncpadDatabaseRevision
COMMENT ON TABLE LaunchpadDatabaseRevision IS 'This table contains a list of the database patches that have been successfully applied to this database.';
COMMENT ON COLUMN LaunchpadDatabaseRevision.major IS 'Major number. This is the version of the baseline schema the patch was made agains.';
COMMENT ON COLUMN LaunchpadDatabaseRevision.minor IS 'Minor number. Patches made during development each increment the minor number.';
COMMENT ON COLUMN LaunchpadDatabaseRevision.patch IS 'The patch number will hopefully always be ''0'', as it exists to support emergency patches made to the production server. eg. If production is running ''4.0.0'' and needs to have a patch applied ASAP, we would create a ''4.0.1'' patch and roll it out. We then may need to refactor all the existing ''4.x.0'' patches.';

-- LaunchpadDatabaseUpdateLog
COMMENT ON TABLE LaunchpadDatabaseUpdateLog IS 'Record of Launchpad database schema updates. When and what update.py was run.';

-- Karma
COMMENT ON TABLE Karma IS 'Used to quantify all the ''operations'' a user performs inside the system, which maybe reporting and fixing bugs, uploading packages, end-user support, wiki editting, etc.';
COMMENT ON COLUMN Karma.action IS 'A foreign key to the KarmaAction table.';
COMMENT ON COLUMN Karma.datecreated IS 'A timestamp for the assignment of this Karma.';
COMMENT ON COLUMN Karma.Person IS 'The Person for wich this Karma was assigned.';
COMMENT ON COLUMN Karma.product IS 'The Product on which a person performed an action that resulted on this karma.';
COMMENT ON COLUMN Karma.distribution IS 'The Distribution on which a person performed an action that resulted on this karma.';
COMMENT ON COLUMN Karma.sourcepackagename IS 'The SourcePackageName on which a person performed an action that resulted on this karma.';

-- KarmaAction
COMMENT ON TABLE KarmaAction IS 'Stores all the actions that would give karma to the user which performed it.';
COMMENT ON COLUMN KarmaAction.name IS 'The unique name of this action.';
COMMENT ON COLUMN KarmaAction.category IS 'A dbschema value used to group actions together.';
COMMENT ON COLUMN KarmaAction.points IS 'The number of points this action is worth of.';

-- KarmaCache
COMMENT ON TABLE KarmaCache IS 'Stores a cached value of a person''s karma points, grouped by the action category and the context where that action was performed.';
COMMENT ON COLUMN KarmaCache.Person IS 'The person which performed the actions of this category, and thus got the karma.';
COMMENT ON COLUMN KarmaCache.Category IS 'The category of the actions.';
COMMENT ON COLUMN KarmaCache.KarmaValue IS 'The karma points of all actions of this category performed by this person on this context (product/distribution).';
COMMENT ON COLUMN Karma.product IS 'The Product on which a person performed an action that resulted on this karma.';
COMMENT ON COLUMN Karma.product IS 'The Project to which this Product belongs.  An entry on this table with a non-NULL Project and a NULL Product represents the total karma of the person across all products of that project..';
COMMENT ON COLUMN Karma.distribution IS 'The Distribution on which a person performed an action that resulted on this karma.';
COMMENT ON COLUMN Karma.sourcepackagename IS 'The SourcePackageName on which a person performed an action that resulted on this karma.';


-- Account
COMMENT ON TABLE Account IS 'An account that may be used for authenticating to Canonical or other systems.';
COMMENT ON COLUMN Account.status IS 'The status of the account.';
COMMENT ON COLUMN Account.status_comment IS 'The comment on the status of the account.';
COMMENT ON COLUMN Person.creation_rationale IS 'The rationale for the creation of this Account -- a PersonCreationRationale value.';
COMMENT ON COLUMN Account.date_status_set IS 'When the status was last changed.';
COMMENT ON COLUMN Account.displayname IS 'Name to display when rendering information about this account.';


-- Person
COMMENT ON TABLE Person IS 'A row represents a person if teamowner is NULL, and represents a team if teamowner is set.';
COMMENT ON COLUMN Person.account IS 'The Account linked to this Person, if there is one.';
COMMENT ON COLUMN Person.displayname IS 'Person or group''s name as it should be rendered to screen';
COMMENT ON COLUMN Person.teamowner IS 'id of the team owner. Team owners will have authority to add or remove people from the team.';
COMMENT ON COLUMN Person.teamdescription IS 'Informative description of the team. Format and restrictions are as yet undefined.';
COMMENT ON COLUMN Person.name IS 'Short mneumonic name uniquely identifying this person or team. Useful for url traversal or in places where we need to unambiguously refer to a person or team (as displayname is not unique).';
COMMENT ON COLUMN Person.language IS 'Preferred language for this person (unset for teams). UI should be displayed in this language wherever possible.';
COMMENT ON COLUMN Person.homepage_content IS 'A home page for this person in the Launchpad. In short, this is like a personal wiki page. The person will get to edit their own page, and it will be published on /people/foo/. Note that this is in text format, and will migrate to being in Moin format as a sort of mini-wiki-homepage.';
COMMENT ON COLUMN Person.icon IS 'The library file alias to a small image to be used as an icon whenever we are referring to that person.';
COMMENT ON COLUMN Person.mugshot IS 'The library file alias of a hackermugshot image to display as the "face" of a person, on their home page.';
COMMENT ON COLUMN Person.logo IS 'The library file alias of a smaller version of this person''s mugshot.';
COMMENT ON COLUMN Person.creation_rationale IS 'The rationale for the creation of this person -- a dbschema value.';
COMMENT ON COLUMN Person.creation_comment IS 'A text comment for the creation of this person.';
COMMENT ON COLUMN Person.registrant IS 'The user who created this profile.';
COMMENT ON COLUMN Person.subscriptionpolicy IS 'The policy for new members to join this team.';
COMMENT ON COLUMN Person.renewal_policy IS 'The policy for membership renewal on this team.';
COMMENT ON COLUMN Person.personal_standing IS 'The standing of the person, which indicates (for now, just) whether the person can post to a mailing list without requiring first post moderation.  Values are documented in dbschema.PersonalStanding.';
COMMENT ON COLUMN Person.personal_standing_reason IS 'The reason a person''s standing has changed.';
COMMENT ON COLUMN Person.mail_resumption_date IS 'A NULL resumption date or a date in the past indicates that there is no vacation in effect.  Vacations are granular to the day, so a datetime is not necessary.';
COMMENT ON COLUMN Person.mailing_list_auto_subscribe_policy IS 'The auto-subscription policy for the person, i.e. whether and how the user is automatically subscribed to mailing lists for teams they join.  Values are described in dbschema.MailingListAutoSubscribePolicy.';
COMMENT ON COLUMN Person.mailing_list_receive_duplicates IS 'True means the user wants to receive list copies of messages on which they are explicitly named as a recipient.';
COMMENT ON COLUMN Person.visibility IS 'person.PersonVisibility enumeration which can be set to Public, Public with Private Membership, or Private.';
COMMENT ON COLUMN Person.verbose_bugnotifications  IS 'If true, all bugnotifications sent to this Person will include the bug description.';

COMMENT ON TABLE PersonSettings IS 'Flags and settings corresponding to a Person. These are in a separate table to remove infrequently used data from the Person table itself.';
COMMENT ON COLUMN PersonSettings.selfgenerated_bugnotifications  IS 'If true, users receive bugnotifications for actions they personally triggered.';

COMMENT ON VIEW ValidPersonCache IS 'A materialized view listing the Person.ids of all valid people (but not teams).';

-- PersonLanguage
COMMENT ON TABLE PersonLanguage IS 'PersonLanguage: This table stores the preferred languages that a Person has, it''s used in Rosetta to select the languages that should be showed to be translated.';
COMMENT ON COLUMN PersonLanguage.person IS 'This field is a reference to a Person object that has this preference.';
COMMENT ON COLUMN PersonLanguage.language IS 'This field is a reference to a Language object that says that the Person associated to this row knows how to translate/understand this language.';

-- PersonLocation
COMMENT ON TABLE PersonLocation IS 'The geographical coordinates and time zone for a person.';
COMMENT ON COLUMN PersonLocation.time_zone IS 'The name of the time zone this person prefers (if unset, UTC is used).  UI should display dates and times in this time zone wherever possible.';
COMMENT ON COLUMN PersonLocation.latitude IS 'The latitude this person has given for their default location.';
COMMENT ON COLUMN PersonLocation.longitude IS 'The longitude this person has given for their default location.';
COMMENT ON COLUMN PersonLocation.last_modified_by IS 'The person who last updated this record. We allow people to provide location and time zone information for other users, when those users have not specified their own location. This allows people to garden the location information for their teams, for example, like a wiki.';
COMMENT ON COLUMN PersonLocation.date_last_modified IS 'The date this record was last modified.';
COMMENT ON COLUMN PersonLocation.locked IS 'Whether or not this record can be modified by someone other than the person himself?';
COMMENT ON COLUMN PersonLocation.visible IS 'Should this person''s location and time zone be visible to others?';


-- PersonNotification
COMMENT ON TABLE PersonNotification IS 'Notifications to be sent that are related to edits and changes of the details of a specific person or team. Note that these are not keyed against the "person who will be notified", these are notifications "about a person". We use this table to queue up notifications that can then be sent asyncronously - when one user edits information about another person (like the PersonLocation) we want to notify the person concerned that their details have been modified but we do not want to do this during the handling of the form submission. So we store the reminder to notify here, and send it later in a batch. This is modelled on the pattern of BugNotification.';
COMMENT ON COLUMN PersonNotification.person IS 'The Person who has been edited or modified.';
COMMENT ON COLUMN PersonNotification.body IS 'The textual body of the notification to be sent.';
COMMENT ON COLUMN PersonNotification.subject IS 'The subject of the mail to be sent.';
COMMENT ON COLUMN PersonNotification.date_emailed IS 'When this notification was emailed to the relevant people.';

-- PersonTransferJob

COMMENT ON TABLE PersonTransferJob IS 'Contains references to jobs for adding team members or merging person entries.';
COMMENT ON COLUMN PersonTransferJob.job IS 'A reference to a row in the Job table that has all the common job details.';
COMMENT ON COLUMN PersonTransferJob.job_type IS 'The type of job, like add-member notification or merge persons.';
COMMENT ON COLUMN PersonTransferJob.json_data IS 'Data that is specific to the type of job, normally stores text to append to email notifications.';
COMMENT ON COLUMN PersonTransferJob.minor_person IS 'The person that is being added is a new member or being merged into another person.';
COMMENT ON COLUMN PersonTransferJob.major_person IS 'The team receiving a new member or the person that another person is merged into.';

-- QuestionJob

COMMENT ON TABLE QuestionJob IS 'Contains references to jobs regarding questions.';
COMMENT ON COLUMN QuestionJob.job IS 'A reference to a row in the Job table that has all the common job details.';
COMMENT ON COLUMN QuestionJob.job_type IS 'The type of job, such as new-answer-notification.';
COMMENT ON COLUMN QuestionJob.json_data IS 'Data that is specific to the type of job, normally stores text to append to email notifications.';
COMMENT ON COLUMN QuestionJob.question IS 'The newly added question message.';

-- BugMessages
COMMENT ON TABLE BugMessage IS 'This table maps a message to a bug. In other words, it shows that a particular message is associated with a particular bug.';
COMMENT ON COLUMN BugMessage.bugwatch IS 'The external bug this bug comment was imported from.';
COMMENT ON COLUMN BugMessage.remote_comment_id IS 'The id this bug comment has in the external bug tracker, if it is an imported comment. If it is NULL while having a bugwatch set, this comment was added in Launchpad and needs to be pushed to the external bug tracker.';
COMMENT ON COLUMN BugMessage.index IS 'The index (used in urls) of the message in a particular bug.';
COMMENT ON COLUMN BugMessage.owner IS 'Denormalised owner from Message, used for efficient queries on commentors.';

-- Messaging subsytem
COMMENT ON TABLE Message IS 'This table stores a single RFC822-style message. Messages can be threaded (using the parent field). These messages can then be referenced from elsewhere in the system, such as the BugMessage table, integrating messageboard facilities with the rest of The Launchpad.';
COMMENT ON COLUMN Message.parent IS 'A "parent message". This allows for some level of threading in Messages.';
COMMENT ON COLUMN Message.subject IS 'The title text of the message, or the subject if it was an email.';
COMMENT ON COLUMN Message.distribution IS 'The distribution in which this message originated, if we know it.';
COMMENT ON COLUMN Message.raw IS 'The original unadulterated message if it arrived via email. This is required to provide access to the original, undecoded message.';
COMMENT ON COLUMN Message.visible IS 'If false, the message is hidden and should not be shown in any UI.';

COMMENT ON TABLE MessageChunk IS 'This table stores a single chunk of a possibly multipart message. There will be at least one row in this table for each message. text/* parts are stored in the content column. All other parts are stored in the Librarian and referenced via the blob column. If both content and blob are NULL, then this chunk has been removed (eg. offensive, legal reasons, virus etc.)';
COMMENT ON COLUMN MessageChunk.content IS 'Text content for this chunk of the message. This content is full text searchable.';
COMMENT ON COLUMN MessageChunk.blob IS 'Binary content for this chunk of the message.';
COMMENT ON COLUMN MessageChunk.sequence IS 'Order of a particular chunk. Chunks are orders in ascending order starting from 1.';

-- Comments on Lucille views
COMMENT ON VIEW SourcePackageFilePublishing IS 'This view is used mostly by Lucille while performing publishing and unpublishing operations. It lists all the files associated with a sourcepackagerelease and collates all the textual representations needed for publishing components etc to allow rapid queries from SQLObject.';
COMMENT ON VIEW BinaryPackageFilePublishing IS 'This view is used mostly by Lucille while performing publishing and unpublishing operations. It lists all the files associated with a binarypackage and collates all the textual representations needed for publishing components etc to allow rapid queries from SQLObject.';

-- SourcePackageRelease

COMMENT ON TABLE SourcePackageRelease IS 'SourcePackageRelease: A source
package release. This table represents a specific release of a source
package. Source package releases may be published into a distroseries, or
even multiple distroseries.';
COMMENT ON COLUMN SourcePackageRelease.creator IS 'The creator of this
sourcepackagerelease. This is the person referred to in the top entry in the
package changelog in debian terms. Note that a source package maintainer in
Ubuntu might be person A, but a particular release of that source package
might in fact have been created by a different person B. The maintainer
would be recorded in the Maintainership table, while the creator of THIS
release would be recorded in the SourcePackageRelease.creator field.';
COMMENT ON COLUMN SourcePackageRelease.version IS 'The version string for
this source package release. E.g. "1.0-2" or "1.4-5ubuntu9.1". Note that, in
ubuntu-style and redhat-style distributions, the version+sourcepackagename
is unique, even across distroseries. In other words, you cannot have a
foo-1.2-1 package in Hoary that is different from foo-1.2-1 in Warty.';
COMMENT ON COLUMN SourcePackageRelease.dateuploaded IS 'The date/time that
this sourcepackagerelease was first uploaded to the Launchpad.';
COMMENT ON COLUMN SourcePackageRelease.urgency IS 'The urgency of the
upload. This is generally used to prioritise buildd activity but may also be
used for "testing" systems or security work in the future. The "urgency" is
set by the uploader, in the DSC file.';
COMMENT ON COLUMN SourcePackageRelease.dscsigningkey IS 'The GPG key used to
sign the DSC. This is not necessarily the maintainer''s key, or the
creator''s key. For example, it''s possible to produce a package, then ask a
sponsor to upload it.';
COMMENT ON COLUMN SourcePackageRelease.component IS 'The component in which
this sourcepackagerelease is intended (by the uploader) to reside. E.g.
main, universe, restricted. Note that the distribution managers will often
override this data and publish the package in an entirely different
component.';
COMMENT ON COLUMN SourcePackageRelease.changelog_entry IS 'Changelog text section extracted from the changesfile.';
COMMENT ON COLUMN SourcePackageRelease.builddepends IS 'The build
dependencies for this source package release.';
COMMENT ON COLUMN SourcePackageRelease.builddependsindep IS 'The
architecture-independant build dependancies for this source package release.';
COMMENT ON COLUMN SourcePackageRelease.architecturehintlist IS 'The
architectures which this source package release believes it should be built.
This is used as a hint to the build management system when deciding what
builds are still needed.';
COMMENT ON COLUMN SourcePackageRelease.format IS 'The format of this
sourcepackage release, e.g. DPKG, RPM, EBUILD, etc. This is an enum, and the
values are listed in dbschema.SourcePackageFormat';
COMMENT ON COLUMN SourcePackageRelease.dsc IS 'The "Debian Source Control"
file for the sourcepackagerelease, from its upload into Ubuntu for the
first time.';
COMMENT ON COLUMN SourcePackageRelease.upload_distroseries IS 'The
distroseries into which this source package release was uploaded into
Launchpad / Ubuntu for the first time. In general, this will be the
development Ubuntu release into which this package was uploaded. For a
package which was unchanged between warty and hoary, this would show Warty.
For a package which was uploaded into Hoary, this would show Hoary.';
COMMENT ON COLUMN SourcePackageRelease.upload_archive IS 'The archive into which this sourcepackagerelese was originally uploaded.';
COMMENT ON COLUMN SourcePackageRelease.section IS 'This integer field references the Section which the source package claims to be in';
COMMENT ON COLUMN SourcePackageRelease.maintainer IS 'Reference to the person noted as source package maintainer in the DSC.';
COMMENT ON COLUMN SourcePackageRelease.sourcepackagename IS 'Reference to a SourcePackageName.';
COMMENT ON COLUMN SourcePackageRelease.dsc_maintainer_rfc822 IS 'The original maintainer line in RFC-822 format, to be used in archive indexes.';
COMMENT ON COLUMN SourcePackageRelease.dsc_standards_version IS 'DSC standards version (such as "3.6.2", "3.5.9", etc) used to build this source.';
COMMENT ON COLUMN SourcePackageRelease.dsc_format IS 'DSC format version (such as "1.0").';
COMMENT ON COLUMN SourcePackageRelease.dsc_binaries IS 'DSC binary line, claimed binary-names produce by this source.';
COMMENT ON COLUMN SourcePackageRelease.copyright IS 'The copyright associated with this sourcepackage. Often in the case of debian packages and will be found after the installation in /usr/share/doc/<binarypackagename>/copyright';
COMMENT ON COLUMN SourcePackageRelease.build_conflicts IS 'The list of packages that will conflict with this source while building, as mentioned in the control file "Build-Conflicts:" field.';
COMMENT ON COLUMN SourcePackageRelease.build_conflicts_indep IS 'The list of packages that will conflict with this source while building in architecture independent environment, as mentioned in the control file "Build-Conflicts-Indep:" field.';
COMMENT ON COLUMN SourcePackageRelease.changelog IS 'The LibraryFileAlias ID of changelog associated with this sourcepackage.  Often in the case of debian packages and will be found after the installation in /usr/share/doc/<binarypackagename>/changelog.Debian.gz';
COMMENT ON COLUMN SourcePackageRelease.user_defined_fields IS 'A JSON struct containing a sequence of key-value pairs with user defined fields in the control file.';
COMMENT ON COLUMN SourcePackageRelease.homepage IS 'Upstream project homepage URL, not checked for validity.';

-- SourcePackageName

COMMENT ON TABLE SourcePackageName IS 'SourcePackageName: A soyuz source package name.';

-- SourcePackageRecipeData

COMMENT ON TABLE SourcePackageRecipeData IS 'The database representation of a BaseRecipeBranch from bzr-builder.  Exactly one of sourcepackage_recipe or sourcepackage_recipe_build will be non-NULL.';
COMMENT ON COLUMN SourcePackageRecipeData.base_branch IS 'The branch the recipe is based on.';
COMMENT ON COLUMN SourcePackageRecipeData.recipe_format IS 'The format version of the recipe.';
COMMENT ON COLUMN SourcePackageRecipeData.deb_version_template IS 'The template for the revision number of the build.';
COMMENT ON COLUMN SourcePackageRecipeData.revspec IS 'The revision from base_branch to use.';
COMMENT ON COLUMN SourcePackageRecipeData.sourcepackage_recipe IS 'The recipe that this data is for.';
COMMENT ON COLUMN SourcePackageRecipeData.sourcepackage_recipe_build IS 'The build that resulted in this manifest.';

-- SourcePackageRecipeDataInstruction

COMMENT ON TABLE SourcePackageRecipeDataInstruction IS 'A line from the recipe, specifying a branch to nest or merge.';
COMMENT ON COLUMN SourcePackageRecipeDataInstruction.name IS 'The name of the instruction.';
COMMENT ON COLUMN SourcePackageRecipeDataInstruction.type IS 'The type of the instruction (MERGE == 1, NEST == 2).';
COMMENT ON COLUMN SourcePackageRecipeDataInstruction.comment IS 'The comment from the recipe about this instruction.';
COMMENT ON COLUMN SourcePackageRecipeDataInstruction.line_number IS 'The line number of the instruction in the recipe.';
COMMENT ON COLUMN SourcePackageRecipeDataInstruction.branch IS 'The branch being merged or nested.';
COMMENT ON COLUMN SourcePackageRecipeDataInstruction.revspec IS 'The revision of the branch to use.';
COMMENT ON COLUMN SourcePackageRecipeDataInstruction.directory IS 'The location to nest at, if this is a nest/nest-part instruction.';
COMMENT ON COLUMN SourcePackageRecipeDataInstruction.source_directory IS 'The location in the branch to nest, if this is a nest-part instruction.';
COMMENT ON COLUMN SourcePackageRecipeDataInstruction.recipe_data IS 'The SourcePackageRecipeData this instruction is part of.';
COMMENT ON COLUMN SourcePackageRecipeDataInstruction.parent_instruction IS 'The nested branch this instruction applies to, or NULL for a top-level instruction.';

-- SourcePackageRecipe

COMMENT ON TABLE SourcePackageRecipe IS 'A recipe for assembling a source package from branches.';
COMMENT ON COLUMN SourcePackageRecipe.registrant IS 'The person who created this recipe.';
COMMENT ON COLUMN SourcePackageRecipe.owner IS 'The person or team who can edit this recipe.';
COMMENT ON COLUMN SourcePackageRecipe.name IS 'The name of the recipe in the web/URL.';
COMMENT ON COLUMN SourcePackageRecipe.build_daily IS 'If true, this recipe should be built daily.';
COMMENT ON COLUMN SourcePackageRecipe.is_stale IS 'True if this recipe has not been built since a branch was updated.';

COMMENT ON COLUMN SourcePackageREcipe.daily_build_archive IS 'The archive to build into for daily builds.';

-- SourcePackageRecipeDistroSeries

COMMENT ON TABLE SourcePackageRecipeDistroSeries IS 'Link table for sourcepackagerecipe and distroseries.';
COMMENT ON COLUMN SourcePackageRecipeDistroSeries.distroseries IS 'The primary key of the DistroSeries.';
COMMENT ON COLUMN SourcePackageRecipeDistroSeries.sourcepackagerecipe IS 'The primary key of the SourcePackageRecipe.';

-- SourcePackageRecipeBuild

COMMENT ON TABLE SourcePackageRecipeBuild IS 'The build record for the process of building a source package as described by a recipe.';
COMMENT ON COLUMN SourcePackageRecipeBuild.distroseries IS 'The distroseries the build was for.';
COMMENT ON COLUMN SourcePackageRecipeBuild.requester IS 'Who requested the build.';
COMMENT ON COLUMN SourcePackageRecipeBuild.recipe IS 'The recipe being processed.';
COMMENT ON COLUMN SourcePackageRecipeBuild.manifest IS 'The evaluated recipe that was built.';

-- SourcePackageRecipeBuildJob

COMMENT ON TABLE SourcePackageRecipeBuildJob IS 'The link between a SourcePackageRecipeBuild row and a Job row to schedule a build of a source package recipe.';
COMMENT ON COLUMN SourcePackageRecipeBuildJob.sourcepackage_recipe_build IS 'The build record describing the package being built.';

-- Specification

COMMENT ON TABLE Specification IS 'A feature specification. At the moment we do not store the actual specification, we store a URL for the spec, which is managed in a wiki somewhere else. We store the overall state of the spec, as well as queueing information about who needs to review the spec, and why.';
COMMENT ON COLUMN Specification.information_type IS 'Enum describing what type of information is stored, such as type of private or security related data, and used to determine how to apply an access policy.';
COMMENT ON COLUMN Specification.assignee IS 'The person who has been assigned to implement this specification.';
COMMENT ON COLUMN Specification.drafter IS 'The person who has been asked to draft this specification. They are responsible for getting the spec to "approved" state.';
COMMENT ON COLUMN Specification.approver IS 'The person who is responsible for approving the specification in due course, and who will probably be required to review the code itself when it is being implemented.';
COMMENT ON COLUMN Specification.product IS 'The product for which this is a feature specification. The specification must be connected either to a product, or to a distribution.';
COMMENT ON COLUMN Specification.distribution IS 'The distribution for which this is a feature specification. The specification must be connected either to a product, or to a distribution.';
COMMENT ON COLUMN Specification.distroseries IS 'If this is not NULL, then it means that the release managers have targeted this feature to be released in the given distroseries. It is not necessary to target a distroseries, but this is a useful way of know which specifications are, for example, BreezyGoals.';
COMMENT ON COLUMN Specification.productseries IS 'This is an indicator that the specification is planned, or targeted, for implementation in a given product series. It is not necessary to target a spec to a series, but it is a useful way of showing which specs are planned to implement for a given series.';
COMMENT ON COLUMN Specification.milestone IS 'This is an indicator that the feature defined in this specification is expected to be delivered for a given milestone. Note that milestones are not necessarily releases, they are a way of identifying a point in time and grouping bugs and features around that.';
COMMENT ON COLUMN Specification.definition_status IS 'An enum called SpecificationDefinitionStatus that shows what the current status (new, draft, implemented etc) the spec is currently in.';
COMMENT ON COLUMN Specification.priority IS 'An enum that gives the implementation priority (low, medium, high, emergency) of the feature defined in this specification.';
COMMENT ON COLUMN Specification.specurl IS 'The URL where the specification itself can be found. This is usually a wiki page somewhere.';
COMMENT ON COLUMN Specification.whiteboard IS 'As long as the specification is somewhere else (i.e. not in Launchpad) it will be useful to have a place to hold some arbitrary message or status flags that have meaning to the project, not Launchpad. This whiteboard is just the place for it.';
COMMENT ON COLUMN Specification.superseded_by IS 'The specification which replaced this specification.';
COMMENT ON COLUMN Specification.implementation_status IS 'The implementation status of this specification. This field is used to track the actual delivery of the feature (implementing the spec), as opposed to the definition of expected behaviour (writing the spec).';
COMMENT ON COLUMN Specification.goalstatus IS 'Whether or not the drivers for the goal product series or distro release have accepted this specification as a goal.';
COMMENT ON COLUMN Specification.goal_proposer IS 'The person who proposed this spec as a goal for the productseries or distroseries.';
COMMENT ON COLUMN Specification.date_goal_proposed IS 'The date the spec was proposed as a goal.';
COMMENT ON COLUMN Specification.goal_decider IS 'The person who approved or declined this goal.';
COMMENT ON COLUMN Specification.date_goal_decided IS 'The date this goal was accepted or declined.';
COMMENT ON COLUMN Specification.completer IS 'The person who changed the state of the spec in such a way that it was determined to be completed.';
COMMENT ON COLUMN Specification.date_completed IS 'The date this specification was completed or marked obsolete. This lets us chart the progress of a project (or a release) over time in terms of features implemented.';
-- COMMENT ON CONSTRAINT specification_completion_recorded_chk ON Specification IS 'A constraint to ensure that we have recorded the date of completion if the specification is in fact considered completed. The SQL behind the completion test is repeated at a code level in database/specification.py: as Specification.completeness, please ensure that the constraint is kept in sync with the code.';
COMMENT ON CONSTRAINT specification_completion_fully_recorded_chk ON Specification IS 'A constraint that ensures, where we have a date_completed, that we also have a completer. This means that the resolution was fully recorded.';
COMMENT ON COLUMN Specification.private IS 'Specification is private.';

-- SpecificationBranch
COMMENT ON TABLE SpecificationBranch IS 'A branch related to a specification, most likely a branch for implementing the specification.  It is possible to have multiple branches for a given specification especially in the situation where the specification requires modifying multiple products.';
COMMENT ON COLUMN SpecificationBranch.specification IS 'The specification associated with this branch.';
COMMENT ON COLUMN SpecificationBranch.branch IS 'The branch associated to the specification.';
COMMENT ON COLUMN SpecificationBranch.registrant IS 'The person who linked the specification to the branch.';

-- SpecificationBug
COMMENT ON TABLE SpecificationBug IS 'A table linking a specification and a bug. This is used to provide for easy navigation from bugs to related specs, and vice versa.';

-- SpecificationSubscription
COMMENT ON TABLE SpecificationSubscription IS 'A table capturing a subscription of a person to a specification.';
COMMENT ON COLUMN SpecificationSubscription.essential IS 'A field that indicates whether or not this person is essential to discussions on the planned feature. This is used by the meeting scheduler to ensure that all the essential people are at any automatically scheduled BOFs discussing that spec.';

-- SpecificationDependency
COMMENT ON TABLE SpecificationDependency IS 'A table that stores information about which specification needs to be implemented before another specification can be implemented. We can create a chain of dependencies, and use that information for scheduling and prioritisation of work.';
COMMENT ON COLUMN SpecificationDependency.specification IS 'The spec for which we are creating a dependency.';
COMMENT ON COLUMN SpecificationDependency.dependency IS 'The spec on which it is dependant.';

-- SpecificationMessage
COMMENT ON TABLE SpecificationMessage IS 'Comments and discussion on a Specification.';

-- BinaryPackageRelease

COMMENT ON TABLE BinaryPackageRelease IS 'BinaryPackageRelease: A soyuz binary package representation. This table stores the records for each binary package uploaded into the system. Each sourcepackagerelease may build various binarypackages on various architectures.';
COMMENT ON COLUMN BinaryPackageRelease.binarypackagename IS 'A reference to the name of the binary package';
COMMENT ON COLUMN BinaryPackageRelease.version IS 'The version of the binary package. E.g. "1.0-2"';
COMMENT ON COLUMN BinaryPackageRelease.summary IS 'A summary of the binary package. Commonly used on listings of binary packages';
COMMENT ON COLUMN BinaryPackageRelease.description IS 'A longer more detailed description of the binary package';
COMMENT ON COLUMN BinaryPackageRelease.build IS 'The build in which this binarypackage was produced';
COMMENT ON COLUMN BinaryPackageRelease.binpackageformat IS 'The binarypackage format. E.g. RPM, DEB etc';
COMMENT ON COLUMN BinaryPackageRelease.component IS 'The archive component that this binarypackage is in. E.g. main, universe etc';
COMMENT ON COLUMN BinaryPackageRelease.section IS 'The archive section that this binarypackage is in. E.g. devel, libdevel, editors';
COMMENT ON COLUMN BinaryPackageRelease.priority IS 'The priority that this package has. E.g. Base, Standard, Extra, Optional';
COMMENT ON COLUMN BinaryPackageRelease.shlibdeps IS 'The shared library dependencies of this binary package';
COMMENT ON COLUMN BinaryPackageRelease.depends IS 'The list of packages this binarypackage depends on';
COMMENT ON COLUMN BinaryPackageRelease.recommends IS 'The list of packages this binarypackage recommends. Recommended packages often enhance the behaviour of a package.';
COMMENT ON COLUMN BinaryPackageRelease.suggests IS 'The list of packages this binarypackage suggests.';
COMMENT ON COLUMN BinaryPackageRelease.conflicts IS 'The list of packages this binarypackage conflicts with.';
COMMENT ON COLUMN BinaryPackageRelease.replaces IS 'The list of packages this binarypackage replaces files in. Often this is used to provide an upgrade path between two binarypackages of different names';
COMMENT ON COLUMN BinaryPackageRelease.provides IS 'The list of virtual packages (or real packages under some circumstances) which this binarypackage provides.';
COMMENT ON COLUMN BinaryPackageRelease.essential IS 'Whether or not this binarypackage is essential to the smooth operation of a base system';
COMMENT ON COLUMN BinaryPackageRelease.installedsize IS 'What the installed size of the binarypackage is. This is represented as a number of kilobytes of storage.';
COMMENT ON COLUMN BinaryPackageRelease.architecturespecific IS 'This field indicates whether or not a binarypackage is architecture-specific. If it is not specific to any given architecture then it can automatically be included in all the distroarchseries which pertain.';
COMMENT ON COLUMN BinaryPackageRelease.pre_depends IS 'The list of packages this binary requires to be installed beforehand in apt/dpkg format, as it is in control file "Pre-Depends:" field.';
COMMENT ON COLUMN BinaryPackageRelease.enhances IS 'The list of packages pointed as "enhanced" after the installation of this package, as it is in control file "Enhances:" field.';
COMMENT ON COLUMN BinaryPackageRelease.breaks IS 'The list of packages which will be broken by the installtion of this package, as it is in the control file "Breaks:" field.';
COMMENT ON COLUMN BinaryPackageRelease.debug_package IS 'The corresponding binary package release containing debug symbols for this binary, if any.';
COMMENT ON COLUMN BinaryPackageRelease.user_defined_fields IS 'A JSON struct containing a sequence of key-value pairs with user defined fields in the control file.';
COMMENT ON COLUMN BinaryPackageRelease.homepage IS 'Upstream project homepage URL, not checked for validity.';

-- BinaryPackageReleaseContents

COMMENT ON TABLE BinaryPackageReleaseContents IS 'BinaryPackageReleaseContents: Mapping table that maps from BinaryPackageReleases to path names.';
COMMENT ON COLUMN BinaryPackageReleaseContents.binarypackagerelease IS 'The BinaryPackageRelease that contains the path name.';
COMMENT ON COLUMN BinaryPackageReleaseContents.binarypackagepath IS 'The path name, via the BinaryPackagePath table.';

-- BinaryPackageFile

COMMENT ON TABLE BinaryPackageFile IS 'BinaryPackageFile: A soyuz <-> librarian link table. This table represents the ownership in the librarian of a file which represents a binary package';
COMMENT ON COLUMN BinaryPackageFile.binarypackagerelease IS 'The binary package which is represented by the file';
COMMENT ON COLUMN BinaryPackageFile.libraryfile IS 'The file in the librarian which represents the package';
COMMENT ON COLUMN BinaryPackageFile.filetype IS 'The "type" of the file. E.g. DEB, RPM';

-- BinaryPackageName

COMMENT ON TABLE BinaryPackageName IS 'BinaryPackageName: A soyuz binary package name.';

-- BinaryPackagePath

COMMENT ON TABLE BinaryPackagePath IS 'BinaryPackagePath: A table of filenames shipped in binary packages.';
COMMENT ON COLUMN BinaryPackagePath.path IS 'The full path of the file.';

-- Distribution

COMMENT ON TABLE Distribution IS 'Distribution: A soyuz distribution. A distribution is a collection of DistroSeries. Distributions often group together policy and may be referred to by a name such as "Ubuntu" or "Debian"';
COMMENT ON COLUMN Distribution.name IS 'The unique name of the distribution as a short lowercase name suitable for use in a URL.';
COMMENT ON COLUMN Distribution.title IS 'The title of the distribution. More a "display name" as it were. E.g. "Ubuntu" or "Debian GNU/Linux"';
COMMENT ON COLUMN Distribution.description IS 'A description of the distribution. More detailed than the title, this column may also contain information about the project this distribution is run by.';
COMMENT ON COLUMN Distribution.domainname IS 'The domain name of the distribution. This may be used both for linking to the distribution and for context-related stuff.';
COMMENT ON COLUMN Distribution.owner IS 'The person in launchpad who is in ultimate-charge of this distribution within launchpad.';
COMMENT ON COLUMN Distribution.upload_sender IS 'The email address (and name) of the default sender used by the upload processor. If NULL, we fall back to the default sender in the launchpad config.';
COMMENT ON COLUMN Distribution.upload_admin IS 'Person foreign key which have access to modify the queue ui. If NULL, we fall back to launchpad admin members';
COMMENT ON COLUMN Distribution.homepage_content IS 'A home page for this distribution in the Launchpad.';
COMMENT ON COLUMN Distribution.icon IS 'The library file alias to a small image to be used as an icon whenever we are referring to a distribution.';
COMMENT ON COLUMN Distribution.mugshot IS 'The library file alias of a mugshot image to display as the branding of a distribution, on its home page.';
COMMENT ON COLUMN Distribution.logo IS 'The library file alias of a smaller version of this distributions''s mugshot.';
COMMENT ON COLUMN Distribution.development_series_alias IS 'If set, an alias for the current development series in this distribution.';

-- DistroSeries

COMMENT ON TABLE DistroSeries IS 'DistroSeries: A soyuz distribution release. A DistroSeries is a given version of a distribution. E.g. "Warty" "Hoary" "Sarge" etc.';
COMMENT ON COLUMN DistroSeries.distribution IS 'The distribution which contains this distroseries.';
COMMENT ON COLUMN DistroSeries.name IS 'The unique name of the distroseries. This is a short name in lower case and would be used in sources.list configuration and in generated URLs. E.g. "warty" "sarge" "sid"';
COMMENT ON COLUMN DistroSeries.title IS 'The display-name title of the distroseries E.g. "Warty Warthog"';
COMMENT ON COLUMN DistroSeries.description IS 'The long detailed description of the release. This may describe the focus of the release or other related information.';
COMMENT ON COLUMN DistroSeries.version IS 'The version of the release. E.g. warty would be "4.10" and hoary would be "5.4"';
COMMENT ON COLUMN DistroSeries.releasestatus IS 'The current release status of this distroseries. E.g. "pre-release freeze" or "released"';
COMMENT ON COLUMN DistroSeries.datereleased IS 'The date on which this distroseries was released. (obviously only valid for released distributions)';
COMMENT ON COLUMN DistroSeries.parent_series IS 'The parent distroseries on which this distribution is based. This is related to the inheritance stuff.';
COMMENT ON COLUMN DistroSeries.registrant IS 'The user who registered this distroseries.';
COMMENT ON COLUMN DistroSeries.driver IS 'This is a person or team who can act as a driver for this specific release - note that the distribution drivers can also set goals for any release.';
COMMENT ON COLUMN DistroSeries.changeslist IS 'The email address (name name) of the changes announcement list for this distroseries. If NULL, no announcement mail will be sent.';
COMMENT ON COLUMN DistroSeries.defer_translation_imports IS 'Don''t accept PO imports for this release just now.';
COMMENT ON COLUMN DistroSeries.include_long_descriptions IS 'Include long descriptions in Packages rather than in Translation-en.';


-- DistroArchSeries

COMMENT ON TABLE DistroArchSeries IS 'DistroArchSeries: A soyuz distribution release for a given architecture. A distroseries runs on various architectures. The distroarchseries groups that architecture-specific stuff.';
COMMENT ON COLUMN DistroArchSeries.distroseries IS 'The distribution which this distroarchseries is part of.';


-- LibraryFileContent

COMMENT ON TABLE LibraryFileContent IS 'LibraryFileContent: A librarian file''s contents. The librarian stores files in a safe and transactional way. This table represents the contents of those files within the database.';
COMMENT ON COLUMN LibraryFileContent.datecreated IS 'The date on which this librarian file was created';
COMMENT ON COLUMN LibraryFileContent.filesize IS 'The size of the file';
COMMENT ON COLUMN LibraryFileContent.sha1 IS 'The SHA1 sum of the file''s contents';
COMMENT ON COLUMN LibraryFileContent.md5 IS 'The MD5 sum of the file''s contents';
COMMENT ON COLUMN LibraryFileContent.sha256 IS 'The SHA256 sum of the file''s contents';

-- LibraryFileAlias

COMMENT ON TABLE LibraryFileAlias IS 'LibraryFileAlias: A librarian file''s alias. The librarian stores, along with the file contents, a record stating the file name and mimetype. This table represents it.';
COMMENT ON COLUMN LibraryFileAlias.content IS 'The libraryfilecontent which is the data in this file.';
COMMENT ON COLUMN LibraryFileAlias.filename IS 'The name of the file. E.g. "foo_1.0-1_i386.deb"';
COMMENT ON COLUMN LibraryFileAlias.mimetype IS 'The mime type of the file. E.g. "application/x-debian-package"';
COMMENT ON COLUMN LibraryFileAlias.expires IS 'The expiry date of this file. If NULL, this item may be removed as soon as it is no longer referenced. If set, the item will not be removed until this date. Once the date is passed, the file may be removed from disk even if this item is still being referenced (in which case content.deleted will be true)';
COMMENT ON COLUMN LibraryFileAlias.date_created IS 'The timestamp when this alias was created.';
COMMENT ON COLUMN LibraryFileAlias.restricted IS 'Is this file available only from the restricted librarian?';
COMMENT ON COLUMN LibraryFileAlias.hits IS 'The number of times this file has been downloaded.';

COMMENT ON TABLE LibraryFileDownloadCount IS 'The number of daily downloads for a given LibraryFileAlias.';
COMMENT ON COLUMN LibraryFileDownloadCount.libraryfilealias IS 'The LibraryFileAlias.';
COMMENT ON COLUMN LibraryFileDownloadCount.day IS 'The day of the downloads.';
COMMENT ON COLUMN LibraryFileDownloadCount.count IS 'The number of downloads.';
COMMENT ON COLUMN LibraryFileDownloadCount.country IS 'The country from where the download requests came from.';

COMMENT ON TABLE ParsedApacheLog IS 'A parsed apache log file for librarian.';
COMMENT ON COLUMN ParsedApacheLog.first_line IS 'The first line of this log file, smashed to ASCII. This uniquely identifies the log file, even if its filename is changed by log rotation or archival.';
COMMENT ON COLUMN ParsedApacheLog.bytes_read IS 'The number of bytes from this log file that have been parsed.';

-- SourcePackageReleaseFile

COMMENT ON TABLE SourcePackageReleaseFile IS 'SourcePackageReleaseFile: A soyuz source package release file. This table links sourcepackagereleasehistory records to the files which comprise the input.';
COMMENT ON COLUMN SourcePackageReleaseFile.libraryfile IS 'The libraryfilealias embodying this file';
COMMENT ON COLUMN SourcePackageReleaseFile.filetype IS 'The type of the file. E.g. TAR, DIFF, DSC';
COMMENT ON COLUMN SourcePackageReleaseFile.sourcepackagerelease IS 'The sourcepackagerelease that this file belongs to';

COMMENT ON TABLE LoginToken IS 'LoginToken stores one time tokens used by Launchpad for validating email addresses and other tasks that require verifying an email address is valid such as password recovery and account merging. This table will be cleaned occasionally to remove expired tokens. Expiry time is not yet defined.';
COMMENT ON COLUMN LoginToken.requester IS 'The Person that made this request. This will be null for password recovery requests.';
COMMENT ON COLUMN LoginToken.requesteremail IS 'The email address that was used to login when making this request. This provides an audit trail to help the end user confirm that this is a valid request. It is not a link to the EmailAddress table as this may be changed after the request is made. This field will be null for password recovery requests.';
COMMENT ON COLUMN LoginToken.email IS 'The email address that this request was sent to.';
COMMENT ON COLUMN LoginToken.created IS 'The timestamp that this request was made.';
COMMENT ON COLUMN LoginToken.tokentype IS 'The type of request, as per dbschema.TokenType.';
COMMENT ON COLUMN LoginToken.token IS 'The token (not the URL) emailed used to uniquely identify this request. This token will be used to generate a URL that when clicked on will continue a workflow.';
COMMENT ON COLUMN LoginToken.fingerprint IS 'The GPG key fingerprint to be validated on this transaction, it means that a new register will be created relating this given key with the requester in question. The requesteremail still passing for the same usual checks.';
COMMENT ON COLUMN LoginToken.date_consumed IS 'The date and time when this token was consumed. It''s NULL if it hasn''t been consumed yet.';


COMMENT ON TABLE Milestone IS 'An identifier that helps a maintainer group together things in some way, e.g. "1.2" could be a Milestone that bazaar developers could use to mark a task as needing fixing in bazaar 1.2.';
COMMENT ON COLUMN Milestone.name IS 'The identifier text, e.g. "1.2."';
COMMENT ON COLUMN Milestone.product IS 'The product for which this is a milestone.';
COMMENT ON COLUMN Milestone.codename IS 'A fun or easier to remember name for the milestone/release.';
COMMENT ON COLUMN Milestone.distribution IS 'The distribution to which this milestone belongs, if it is a distro milestone.';
COMMENT ON COLUMN Milestone.distroseries IS 'The distroseries for which this is a milestone. A milestone on a distroseries is ALWAYS also a milestone for the same distribution. This is because milestones started out on products/distributions but are moving to being on series/distroseries.';
COMMENT ON COLUMN Milestone.productseries IS 'The productseries for which this is a milestone. A milestone on a productseries is ALWAYS also a milestone for the same product. This is because milestones started out on products/distributions but are moving to being on series/distroseries.';
COMMENT ON COLUMN Milestone.dateexpected IS 'If set, the date on which we expect this milestone to be delivered. This allows for optional sorting by date.';
COMMENT ON COLUMN Milestone.active IS 'Whether or not this milestone should be displayed in general listings. All milestones will be visible on the "page of milestones for product foo", but we want to be able to screen out obviously old milestones over time, for the general listings and vocabularies.';
COMMENT ON COLUMN Milestone.summary IS 'This can be used to summarize the changes included in past milestones and to document the status of current milestones.';

-- BuildFarmJob, and its related tables, PackageBuild, BinaryPackageBuild
COMMENT ON TABLE BuildFarmJob IS 'BuildFarmJob: This table stores the information common to all jobs on the Launchpad build farm.';
COMMENT ON COLUMN BuildFarmJob.date_created IS 'When the build farm job record was created.';
COMMENT ON COLUMN BuildFarmJob.date_finished IS 'When the build farm job finished being processed.';
COMMENT ON COLUMN BuildFarmJob.builder IS 'Points to the builder which processed this build farm job.';
COMMENT ON COLUMN BuildFarmJob.status IS 'Stores the current build status.';
COMMENT ON COLUMN BuildFarmJob.job_type IS 'The type of build farm job to which this record corresponds.';

-- BinaryPackageBuild
COMMENT ON TABLE BinaryPackageBuild IS 'BinaryPackageBuild: This table links a package build with a distroarchseries and sourcepackagerelease.';
COMMENT ON COLUMN BinaryPackageBuild.distro_arch_series IS 'Points the target DistroArchSeries for this build.';
COMMENT ON COLUMN BinaryPackageBuild.source_package_release IS 'SourcePackageRelease which originated this build.';

-- Builder
COMMENT ON TABLE Builder IS 'Builder: This table stores the build-slave registry and status information as: name, url, trusted, builderok, builderaction, failnotes.';
COMMENT ON COLUMN Builder.builderok IS 'Should a builder fail for any reason, from out-of-disk-space to not responding to the buildd master, the builderok flag is set to false and the failnotes column is filled with a reason.';
COMMENT ON COLUMN Builder.failnotes IS 'This column gets filled out with a textual description of how/why a builder has failed. If the builderok column is true then the value in this column is irrelevant and should be treated as NULL or empty.';
COMMENT ON COLUMN Builder.virtualized IS 'Whether or not the builder is a virtual Xen builder. Packages coming via ubuntu workflow are trusted to build on non-Xen and do not need facist behaviour to be built. Other packages like ppa/grumpy incoming packages can contain malicious code, so are unstrusted and build in a Xen virtual machine.';
COMMENT ON COLUMN Builder.url IS 'The url to the build slave. There may be more than one build slave on a given host so this url includes the port number to use. The default port number for a build slave is 8221';
COMMENT ON COLUMN Builder.manual IS 'Whether or not builder was manual mode, i.e., collect any result from the it, but do not dispach anything to it automatically.';
COMMENT ON COLUMN Builder.vm_host IS 'The virtual machine host associated to this builder. It should be empty for "native" builders (old fashion or architectures not yet supported by XEN).';
COMMENT ON COLUMN Builder.active IS 'Whether to present or not the builder in the public list of builders avaialble. It is used to hide transient or defunct builders while they get fixed.';
COMMENT ON COLUMN Builder.failure_count IS 'The number of consecutive failures on this builder.  Is reset to zero after a sucessful dispatch.';

-- BuildQueue
COMMENT ON TABLE BuildQueue IS 'BuildQueue: The queue of jobs in progress/scheduled to run on the Soyuz build farm.';
COMMENT ON COLUMN BuildQueue.builder IS 'The builder assigned to this build. Some builds will have a builder assigned to queue them up; some will be building on the specified builder already; others will not have a builder yet (NULL) and will be waiting to be assigned into a builder''s queue';
COMMENT ON COLUMN BuildQueue.logtail IS 'The tail end of the log of the current build. This is updated regularly as the buildd master polls the buildd slaves. Once the build is complete; the full log will be lodged with the librarian and linked into the build table.';
COMMENT ON COLUMN BuildQueue.lastscore IS 'The last score ascribed to this build record. This can be used in the UI among other places.';
COMMENT ON COLUMN BuildQueue.manual IS 'Indicates if the current record was or not rescored manually, if so it get skipped from the auto-score procedure.';
COMMENT ON COLUMN BuildQueue.job IS 'Foreign key to the `Job` table row with the generic job data.';
COMMENT ON COLUMN BuildQueue.job_type IS 'Type of job (enumeration value), enables us to find/query the correct table with the data specific to this type of job.';
COMMENT ON COLUMN BuildQueue.estimated_duration IS 'Estimated job duration, based on previous running times of comparable jobs.';
COMMENT ON COLUMN BuildQueue.processor IS 'The processor required by the associated build farm job.';
COMMENT ON COLUMN BuildQueue.virtualized IS 'The virtualization setting required by the associated build farm job.';

-- Mirrors

COMMENT ON TABLE Mirror IS 'Stores general information about mirror sites. Both regular pull mirrors and top tier mirrors are included.';
COMMENT ON COLUMN Mirror.baseurl IS 'The base URL to the mirror, including protocol and optional trailing slash.';
COMMENT ON COLUMN Mirror.country IS 'The country where the mirror is located.';
COMMENT ON COLUMN Mirror.name IS 'Unique name for the mirror, suitable for use in URLs.';
COMMENT ON COLUMN Mirror.description IS 'Description of the mirror.';
COMMENT ON COLUMN Mirror.freshness IS 'dbschema.MirrorFreshness enumeration indicating freshness.';
COMMENT ON COLUMN Mirror.lastcheckeddate IS 'UTC timestamp of when the last check for freshness and consistency was made. NULL indicates no check has ever been made.';
COMMENT ON COLUMN Mirror.approved IS 'True if this mirror has been approved by the Ubuntu/Canonical mirror manager, otherwise False.';

COMMENT ON TABLE MirrorContent IS 'Stores which distroarchseries and compoenents a given mirror has.';
COMMENT ON COLUMN MirrorContent.distroarchseries IS 'A distroarchseries that this mirror contains.';
COMMENT ON COLUMN MirrorContent.component IS 'What component of the distroarchseries that this mirror contains.';

COMMENT ON TABLE MirrorSourceContent IS 'Stores which distroseries and components a given mirror that includes source packages has.';
COMMENT ON COLUMN MirrorSourceContent.distroseries IS 'A distroseries that this mirror contains.';
COMMENT ON COLUMN MirrorSourceContent.component IS 'What component of the distroseries that this sourcepackage mirror contains.';

-- SourcePackagePublishingHistory

COMMENT ON TABLE SourcePackagePublishingHistory IS 'SourcePackagePublishingHistory: The history of a SourcePackagePublishing record. This table represents the lifetime of a publishing record from inception to deletion. Records are never removed from here and in time the publishing table may become a view onto this table. A column being NULL indicates there''s no data for that state transition. E.g. a package which is removed without being superseded won''t have datesuperseded or supersededby filled in.';
COMMENT ON COLUMN SourcePackagePublishingHistory.sourcepackagename IS 'Reference to a SourcePackageName.';
COMMENT ON COLUMN SourcePackagePublishingHistory.sourcepackagerelease IS 'The sourcepackagerelease being published.';
COMMENT ON COLUMN SourcePackagePublishingHistory.distroseries IS 'The distroseries into which the sourcepackagerelease is being published.';
COMMENT ON COLUMN SourcePackagePublishingHistory.status IS 'The current status of the publishing.';
COMMENT ON COLUMN SourcePackagePublishingHistory.component IS 'The component into which the publishing takes place.';
COMMENT ON COLUMN SourcePackagePublishingHistory.section IS 'The section into which the publishing takes place.';
COMMENT ON COLUMN SourcePackagePublishingHistory.datecreated IS 'The date/time on which the publishing record was created.';
COMMENT ON COLUMN SourcePackagePublishingHistory.datepublished IS 'The date/time on which the source was actually published into an archive.';
COMMENT ON COLUMN SourcePackagePublishingHistory.datesuperseded IS 'The date/time on which the source was superseded by a new source.';
COMMENT ON COLUMN SourcePackagePublishingHistory.supersededby IS 'The source which superseded this one.';
COMMENT ON COLUMN SourcePackagePublishingHistory.datemadepending IS 'The date/time on which this publishing record was made to be pending removal from the archive.';
COMMENT ON COLUMN SourcePackagePublishingHistory.scheduleddeletiondate IS 'The date/time at which the source is/was scheduled to be deleted.';
COMMENT ON COLUMN SourcePackagePublishingHistory.dateremoved IS 'The date/time at which the source was actually deleted.';
COMMENT ON COLUMN SourcePackagePublishingHistory.pocket IS 'The pocket into which this record is published. The RELEASE pocket (zero) provides behaviour as normal. Other pockets may append things to the distroseries name such as the UPDATES pocket (-updates), the SECURITY pocket (-security) and the PROPOSED pocket (-proposed)';
COMMENT ON COLUMN SourcePackagePublishingHistory.removed_by IS 'Person responsible for the removal.';
COMMENT ON COLUMN SourcePackagePublishingHistory.removal_comment IS 'Reason why the publication was removed.';
COMMENT ON COLUMN SourcePackagePublishingHistory.archive IS 'The target archive for this publishing record.';
COMMENT ON COLUMN SourcePackagePublishingHistory.ancestor IS 'The source package record published immediately before this one.';
COMMENT ON COLUMN SourcePackagePublishingHistory.packageupload IS 'The PackageUpload that caused this publication to be created.';

-- Packaging
COMMENT ON TABLE Packaging IS 'DO NOT JOIN THROUGH THIS TABLE. This is a set
of information linking upstream product series (branches) to distro
packages, but it''s not planned or likely to be complete, in the sense that
we do not attempt to have information for every branch in every derivative
distro managed in Launchpad. So don''t join through this table to get from
product to source package, or vice versa. Rather, use the
ProductSeries.sourcepackages attribute, or the
SourcePackage.productseries attribute. You may need to create a
SourcePackage with a given sourcepackagename and distroseries, then use its
.productrelease attribute. The code behind those methods does more than just
join through the tables, it is also smart enough to look at related
distro''s and parent distroseries, and at Ubuntu in particular.';
COMMENT ON COLUMN Packaging.productseries IS 'The upstream product series
that has been packaged in this distroseries sourcepackage.';
COMMENT ON COLUMN Packaging.sourcepackagename IS 'The source package name for
the source package that includes the upstream productseries described in
this Packaging record. There is no requirement that such a sourcepackage
actually be published in the distro.';
COMMENT ON COLUMN Packaging.distroseries IS 'The distroseries in which the
productseries has been packaged.';
COMMENT ON COLUMN Packaging.packaging IS 'A dbschema Enum (PackagingType)
describing the way the upstream productseries has been packaged. Generally
it will be of type PRIME, meaning that the upstream productseries is the
primary substance of the package, but it might also be INCLUDES, if the
productseries has been included as a statically linked library, for example.
This allows us to say that a given Source Package INCLUDES libneon but is a
PRIME package of tla, for example. By INCLUDES we mean that the code is
actually lumped into the package as ancilliary support material, rather
than simply depending on a separate packaging of that code.';
COMMENT ON COLUMN Packaging.owner IS 'This is not the "owner" in the sense
of giving the person any special privileges to edit the Packaging record,
it is simply a record of who told us about this packaging relationship. Note
that we do not keep a history of these, so if someone sets it correctly,
then someone else sets it incorrectly, we lose the first setting.';

COMMENT ON TABLE PackagingJob IS 'A Job related to a Packaging entry.';
COMMENT ON COLUMN PackagingJob.id IS '';
COMMENT ON COLUMN PackagingJob.job IS 'The Job related to this PackagingJob.';
COMMENT ON COLUMN PackagingJob.job_type IS 'An enumeration specifying the type of job to perform.';
COMMENT ON COLUMN PackagingJob.productseries IS 'The productseries of the Packaging.';
COMMENT ON COLUMN PackagingJob.sourcepackagename IS 'The sourcepackage of the Packaging.';
COMMENT ON COLUMN PackagingJob.distroseries IS 'The distroseries of the Packaging.';
COMMENT ON COLUMN PackagingJob.potemplate IS 'A POTemplate to restrict the job to or NULL if all templates need to be handled.';

-- Translator / TranslationGroup

COMMENT ON TABLE TranslationGroup IS 'This represents an organised translation group that spans multiple languages. Effectively it consists of a list of people (pointers to Person), and each Person is associated with a Language. So, for each TranslationGroup we can ask the question "in this TranslationGroup, who is responsible for translating into Arabic?", for example.';
COMMENT ON COLUMN TranslationGroup.translation_guide_url IS 'URL with documentation about general rules for translation work done by this translation group.';

COMMENT ON TABLE Translator IS 'A translator is a person in a TranslationGroup who is responsible for a particular language. At the moment, there can only be one person in a TranslationGroup who is the Translator for a particular language. If you want multiple people, then create a launchpad team and assign that team to the language.';
COMMENT ON COLUMN Translator.translationgroup IS 'The TranslationGroup for which this Translator is working.';
COMMENT ON COLUMN Translator.language IS 'The language for which this Translator is responsible in this TranslationGroup. Note that the same person may be responsible for multiple languages, but any given language can only have one Translator within the TranslationGroup.';
COMMENT ON COLUMN Translator.translator IS 'The Person who is responsible for this language in this translation group.';
COMMENT ON COLUMN Translator.style_guide_url IS 'URL with translation style guide of a particular translation team.';

-- PocketChroot
COMMENT ON TABLE PocketChroot IS 'PocketChroots: Which chroot belongs to which pocket of which distroarchseries. Any given pocket of any given distroarchseries needs a specific chroot in order to be built. This table links it all together.';
COMMENT ON COLUMN PocketChroot.distroarchseries IS 'Which distroarchseries this chroot applies to.';
COMMENT ON COLUMN PocketChroot.pocket IS 'Which pocket of the distroarchseries this chroot applies to. Valid values are specified in dbschema.PackagePublishingPocket';
COMMENT ON COLUMN PocketChroot.chroot IS 'The chroot used by the pocket of the distroarchseries.';

-- POExportRequest
COMMENT ON TABLE POExportRequest IS
'A request from a user that a PO template or a PO file be exported
asynchronously.';
COMMENT ON COLUMN POExportRequest.person IS
'The person who made the request.';
COMMENT ON COLUMN POExportRequest.potemplate IS
'The PO template being requested.';
COMMENT ON COLUMN POExportRequest.pofile IS
'The PO file being requested, or NULL.';
COMMENT ON COLUMN POExportRequest.format IS
'The format the user would like the export to be in. See the RosettaFileFormat DB schema for possible values.';

-- GPGKey
COMMENT ON TABLE GPGKey IS 'A GPG key belonging to a Person';
COMMENT ON COLUMN GPGKey.keyid IS 'The 8 character GPG key id, uppercase and no whitespace';
COMMENT ON COLUMN GPGKey.fingerprint IS 'The 40 character GPG fingerprint, uppercase and no whitespace';
COMMENT ON COLUMN GPGKey.active IS 'True if this key is active for use in Launchpad context, false could be deactivated by user or revoked in the global key ring.';
COMMENT ON COLUMN GPGKey.algorithm IS 'The algorithm used to generate this key. Valid values defined in dbschema.GPGKeyAlgorithms';
COMMENT ON COLUMN GPGKey.keysize IS 'Size of the key in bits, as reported by GPG. We may refuse to deal with keysizes < 768 bits in the future.';
COMMENT ON COLUMN GPGKey.can_encrypt IS 'Whether the key has been validated for use in encryption (as opposed to just signing)';

-- Poll
COMMENT ON TABLE Poll IS 'The polls belonging to teams.';
COMMENT ON COLUMN Poll.team IS 'The team this poll belongs to';
COMMENT ON COLUMN Poll.name IS 'The unique name of this poll.';
COMMENT ON COLUMN Poll.title IS 'The title of this poll.';
COMMENT ON COLUMN Poll.dateopens IS 'The date and time when this poll opens.';
COMMENT ON COLUMN Poll.datecloses IS 'The date and time when this poll closes.';
COMMENT ON COLUMN Poll.proposition IS 'The proposition that is going to be voted.';
COMMENT ON COLUMN Poll.type IS 'The type of this poll (Simple, Preferential, etc).';
COMMENT ON COLUMN Poll.allowspoilt IS 'If people can spoil their votes.';
COMMENT ON COLUMN Poll.secrecy IS 'If people votes are SECRET (no one can see), ADMIN (team administrators can see) or PUBLIC (everyone can see).';

-- PollOption
COMMENT ON TABLE PollOption IS 'The options belonging to polls.';
COMMENT ON COLUMN PollOption.poll IS 'The poll this options belongs to.';
COMMENT ON COLUMN PollOption.name IS 'The name of this option.';
COMMENT ON COLUMN PollOption.title IS 'A short title for this option.';
COMMENT ON COLUMN PollOption.active IS 'If TRUE, people will be able to vote on this option. Otherwise they don''t.';

-- Vote
COMMENT ON TABLE Vote IS 'The table where we store the actual votes of people.  It may or may not have a reference to the person who voted, depending on the poll''s secrecy.';
COMMENT ON COLUMN Vote.person IS 'The person who voted. It''s NULL for secret polls.';
COMMENT ON COLUMN Vote.poll IS 'The poll for which this vote applies.';
COMMENT ON COLUMN Vote.preference IS 'Used to identify in what order the options were chosen by a given user (in case of preferential voting).';
COMMENT ON COLUMN Vote.option IS 'The choosen option.';
COMMENT ON COLUMN Vote.token IS 'A unique token that''s give to the user so he can change his vote later.';

-- VoteCast
COMMENT ON TABLE VoteCast IS 'Here we store who has already voted in a poll, to ensure they do not vote again, and potentially to notify people that they may still vote.';
COMMENT ON COLUMN VoteCast.person IS 'The person who voted.';
COMMENT ON COLUMN VoteCast.poll IS 'The poll in which this person voted.';

-- Language
COMMENT ON TABLE Language IS 'A human language.';
COMMENT ON COLUMN Language.code IS 'The ISO 639 code for this language';
COMMENT ON COLUMN Language.uuid IS 'Mozilla language pack unique ID';
COMMENT ON COLUMN Language.englishname IS 'The english name for this language';
COMMENT ON COLUMN Language.nativename IS 'The name of this language in the language itself';
COMMENT ON COLUMN Language.pluralforms IS 'The number of plural forms this language has';
COMMENT ON COLUMN Language.pluralexpression IS 'The plural expression for this language, as used by gettext';
COMMENT ON COLUMN Language.visible IS 'Whether this language should usually be visible or not';
COMMENT ON COLUMN Language.direction IS 'The direction that text is written in this language';

-- Continent
COMMENT ON TABLE Continent IS 'A continent in this huge world.';
COMMENT ON COLUMN Continent.code IS 'A two-letter code for a continent.';
COMMENT ON COLUMN Continent.name IS 'The name of the continent.';

-- DistributionJob

COMMENT ON TABLE DistributionJob IS 'Contains references to jobs to be run on distributions.';
COMMENT ON COLUMN DistributionJob.distribution IS 'The distribution to be acted on.';
COMMENT ON COLUMN DistributionJob.distroseries IS 'The distroseries to be acted on.';
COMMENT ON COLUMN DistributionJob.job_type IS 'The type of job';
COMMENT ON COLUMN DistributionJob.json_data IS 'A JSON struct containing data for the job.';

-- DistributionMirror
COMMENT ON TABLE DistributionMirror IS 'A mirror of a given distribution.';
COMMENT ON COLUMN DistributionMirror.distribution IS 'The distribution to which the mirror refers to.';
COMMENT ON COLUMN DistributionMirror.name IS 'The unique name of the mirror.';
COMMENT ON COLUMN DistributionMirror.http_base_url IS 'The HTTP URL used to access the mirror.';
COMMENT ON COLUMN DistributionMirror.ftp_base_url IS 'The FTP URL used to access the mirror.';
COMMENT ON COLUMN DistributionMirror.rsync_base_url IS 'The Rsync URL used to access the mirror.';
COMMENT ON COLUMN DistributionMirror.displayname IS 'The displayname of the mirror.';
COMMENT ON COLUMN DistributionMirror.description IS 'A description of the mirror.';
COMMENT ON COLUMN DistributionMirror.owner IS 'The owner of the mirror.';
COMMENT ON COLUMN DistributionMirror.reviewer IS 'The person who reviewed the mirror.';
COMMENT ON COLUMN DistributionMirror.speed IS 'The speed of the mirror''s Internet link.';
COMMENT ON COLUMN DistributionMirror.country IS 'The country where the mirror is located.';
COMMENT ON COLUMN DistributionMirror.content IS 'The content that is mirrored.';
COMMENT ON COLUMN DistributionMirror.official_candidate IS 'Is the mirror a candidate for becoming an official mirror?';
COMMENT ON COLUMN DistributionMirror.enabled IS 'Is this mirror enabled?';
COMMENT ON COLUMN DistributionMirror.status IS 'This mirror''s status.';
COMMENT ON COLUMN DistributionMirror.whiteboard IS 'Notes on the current status of the mirror';
COMMENT ON COLUMN DistributionMirror.date_created IS 'The date and time the mirror was created.';
COMMENT ON COLUMN DistributionMirror.date_reviewed IS 'The date and time the mirror was reviewed.';
COMMENT ON COLUMN DistributionMirror.country_dns_mirror IS 'Is the mirror a country DNS mirror?';

-- MirrorDistroArchSeries
COMMENT ON TABLE MirrorDistroArchSeries IS 'The mirror of the packages of a given Distro Arch Release.';
COMMENT ON COLUMN MirrorDistroArchSeries.distribution_mirror IS 'The distribution mirror.';
COMMENT ON COLUMN MirrorDistroArchSeries.distroarchseries IS 'The distro arch series.';
COMMENT ON COLUMN MirrorDistroArchSeries.freshness IS 'The freshness of the mirror, that is, how up-to-date it is.';
COMMENT ON COLUMN MirrorDistroArchSeries.pocket IS 'The PackagePublishingPocket.';

-- MirrorDistroSeriesSource
COMMENT ON TABLE MirrorDistroSeriesSource IS 'The mirror of a given Distro Release';
COMMENT ON COLUMN MirrorDistroSeriesSource.distribution_mirror IS 'The distribution mirror.';
COMMENT ON COLUMN MirrorDistroSeriesSource.distroseries IS 'The Distribution Release.';
COMMENT ON COLUMN MirrorDistroSeriesSource.freshness IS 'The freshness of the mirror, that is, how up-to-date it is.';

-- MirrorCDImageDistroSeries
COMMENT ON TABLE MirrorCDImageDistroSeries IS 'The mirror of a given CD/DVD image.';
COMMENT ON COLUMN MirrorCDImageDistroSeries.distribution_mirror IS 'The distribution mirror.';
COMMENT ON COLUMN MirrorCDImageDistroSeries.distroseries IS 'The Distribution Release.';
COMMENT ON COLUMN MirrorCDImageDistroSeries.flavour IS 'The Distribution Release Flavour.';

-- MirrorProbeRecord
COMMENT ON TABLE MirrorProbeRecord IS 'Records stored when a mirror is probed.';
COMMENT ON COLUMN MirrorProbeRecord.distribution_mirror IS 'The DistributionMirror.';
COMMENT ON COLUMN MirrorProbeRecord.log_file IS 'The log file of the probe.';
COMMENT ON COLUMN MirrorProbeRecord.date_created IS 'The date and time the probe was performed.';

-- TranslationImportQueueEntry
COMMENT ON TABLE TranslationImportQueueEntry IS 'Queue with translatable resources pending to be imported into Rosetta.';
COMMENT ON COLUMN TranslationImportQueueEntry.path IS 'The path (included the filename) where this file was stored when we imported it.';
COMMENT ON COLUMN TranslationImportQueueEntry.content IS 'The file content that is being imported.';
COMMENT ON COLUMN TranslationImportQueueEntry.format IS 'The file format of the content that is being imported.';
COMMENT ON COLUMN TranslationImportQueueEntry.importer IS 'The person that did the import.';
COMMENT ON COLUMN TranslationImportQueueEntry.dateimported IS 'The timestamp when the import was done.';
COMMENT ON COLUMN TranslationImportQueueEntry.distroseries IS 'The distribution release related to this import.';
COMMENT ON COLUMN TranslationImportQueueEntry.sourcepackagename IS 'The source package name related to this import.';
COMMENT ON COLUMN TranslationImportQueueEntry.productseries IS 'The product series related to this import.';
COMMENT ON COLUMN TranslationImportQueueEntry.by_maintainer IS 'Notes whether this upload was done by the maintiner of the package or project.';
COMMENT ON COLUMN TranslationImportQueueEntry.pofile IS 'Link to the POFile where this import will end.';
COMMENT ON COLUMN TranslationImportQueueEntry.potemplate IS 'Link to the POTemplate where this import will end.';
COMMENT ON COLUMN TranslationImportQueueEntry.date_status_changed IS 'The date when the status of this entry was changed.';
COMMENT ON COLUMN TranslationImportQueueEntry.status IS 'The status of the import: 1 Approved, 2 Imported, 3 Deleted, 4 Failed, 5 Needs Review, 6 Blocked.';
COMMENT ON COLUMN TranslationImportQueueEntry.error_output IS 'Error output from last import attempt.';

-- Archive
COMMENT ON TABLE Archive IS 'A package archive. Commonly either a distribution''s main_archive or a ppa''s archive.';
COMMENT ON COLUMN Archive.owner IS 'Identifies the PPA owner when it has one.';
COMMENT ON COLUMN Archive.displayname IS 'User defined displayname for this archive.';
COMMENT ON COLUMN Archive.description IS 'Allow users to describe their PPAs content.';
COMMENT ON COLUMN Archive.enabled IS 'Whether or not the PPA is enabled for accepting uploads.';
COMMENT ON COLUMN Archive.authorized_size IS 'Size, in MiB, allowed for this PPA.';
COMMENT ON COLUMN Archive.distribution IS 'The distribution that uses this archive.';
COMMENT ON COLUMN Archive.purpose IS 'The purpose of this archive, e.g. COMMERCIAL.  See the ArchivePurpose DBSchema item.';
COMMENT ON COLUMN Archive.status IS 'The status of this archive, e.g. ACTIVE.  See the ArchiveState DBSchema item.';
COMMENT ON COLUMN Archive.private IS 'Whether or not the archive is private. This affects the global visibility of the archive.';
COMMENT ON COLUMN Archive.package_description_cache IS 'Text blob containing all source and binary names and descriptions concatenated. Used to to build the tsearch indexes on this table.';
COMMENT ON COLUMN Archive.sources_cached IS 'Number of sources already cached for this archive.';
COMMENT ON COLUMN Archive.binaries_cached IS 'Number of binaries already cached for this archive.';
COMMENT ON COLUMN Archive.require_virtualized IS 'Whether this archive has binaries that should be built on a virtual machine, e.g. PPAs';
COMMENT ON COLUMN Archive.name IS 'The name of the archive.';
COMMENT ON COLUMN Archive.publish IS 'Whether this archive should be published.';
COMMENT ON COLUMN Archive.date_updated IS 'When were the rebuild statistics last updated?';
COMMENT ON COLUMN Archive.total_count IS 'How many source packages are in the rebuild archive altogether?';
COMMENT ON COLUMN Archive.pending_count IS 'How many packages still need building?';
COMMENT ON COLUMN Archive.succeeded_count IS 'How many source packages were built sucessfully?';
COMMENT ON COLUMN Archive.failed_count IS 'How many packages failed to build?';
COMMENT ON COLUMN Archive.building_count IS 'How many packages are building at present?';
COMMENT ON COLUMN Archive.signing_key IS 'The GpgKey used for signing this archive.';
COMMENT ON COLUMN Archive.removed_binary_retention_days IS 'The number of days before superseded or deleted binary files are expired in the librarian, or zero for never.';
COMMENT ON COLUMN Archive.num_old_versions_published IS 'The number of versions of a package to keep published before older versions are superseded.';
COMMENT ON COLUMN Archive.relative_build_score IS 'A delta to the build score that is applied to all builds in this archive.';
COMMENT ON COLUMN Archive.external_dependencies IS 'Newline-separated list of repositories to be used to retrieve any external build dependencies when building packages in this archive, in the format: deb http[s]://[user:pass@]<host>[/path] %(series)s[-pocket] [components]  The series variable is replaced with the series name of the context build.  This column is specifically and only intended for OEM migration to Launchpad and should be re-examined in October 2010 to see if it is still relevant.';
COMMENT ON COLUMN Archive.suppress_subscription_notifications IS 'Whether to suppress notifications about subscriptions.';
COMMENT ON COLUMN Archive.build_debug_symbols IS 'Whether builds for this archive should create debug symbol packages.';

-- ArchiveAuthToken

COMMENT ON TABLE ArchiveAuthToken IS 'Authorisation tokens to use in .htaccess for published archives.';
COMMENT ON COLUMN ArchiveAuthToken.archive IS 'The archive to which this token refers.';
COMMENT ON COLUMN ArchiveAuthToken.person IS 'The person to which this token applies.';
COMMENT ON COLUMN ArchiveAuthToken.date_created IS 'The date and time this token was created.';
COMMENT ON COLUMN ArchiveAuthToken.date_deactivated IS 'The date and time this token was deactivated.';
COMMENT ON COLUMN ArchiveAuthToken.token IS 'The token text for this authorisation.';

-- ArchiveDependency
COMMENT ON TABLE ArchiveDependency IS 'This table maps a given archive to all other archives it should depend on.';
COMMENT ON COLUMN ArchiveDependency.date_created IS 'Instant when the dependency was created.';
COMMENT ON COLUMN ArchiveDependency.archive IS 'The archive where the dependency should be applied.';
COMMENT ON COLUMN ArchiveDependency.dependency IS 'The archive to depend on.';

-- ArchivePermission

COMMENT ON TABLE ArchivePermission IS 'ArchivePermission: A record of who has permission to upload and approve uploads to an archive (and hence a distribution)';
COMMENT ON COLUMN ArchivePermission.date_created IS 'The date that this permission was created.';
COMMENT ON COLUMN ArchivePermission.archive IS 'The archive to which this permission applies.';
COMMENT ON COLUMN ArchivePermission.permission IS 'The permission type being granted.';
COMMENT ON COLUMN ArchivePermission.person IS 'The person or team to whom the permission is being granted.';
COMMENT ON COLUMN ArchivePermission.component IS 'The component to which this upload permission applies.';
COMMENT ON COLUMN ArchivePermission.sourcepackagename IS 'The source package name to which this permission applies.  This can be used to provide package-level permissions to single users.';
COMMENT ON COLUMN ArchivePermission.packageset IS 'The package set to which this permission applies.';
COMMENT ON COLUMN ArchivePermission.explicit IS 'This flag is set for package sets containing high-profile packages that must not break and/or require specialist skills for proper handling e.g. the kernel.';
COMMENT ON COLUMN ArchivePermission.distroseries IS 'An optional distroseries to which this permission applies.';

-- ArchiveSubscriber

COMMENT ON TABLE ArchiveSubscriber IS 'An authorised person or team subscription to an archive.';
COMMENT ON COLUMN ArchiveSubscriber.archive IS 'The archive that the subscriber is authorised to see.';
COMMENT ON COLUMN ArchiveSubscriber.registrant IS 'The person who authorised this subscriber.';
COMMENT ON COLUMN ArchiveSubscriber.date_created IS 'The date and time this subscription was created.';
COMMENT ON COLUMN ArchiveSubscriber.subscriber IS 'The person or team that this subscription refers to.';
COMMENT ON COLUMN ArchiveSubscriber.date_expires IS 'The date and time this subscription will expire. If NULL, it does not expire.';
COMMENT ON COLUMN ArchiveSubscriber.status IS 'The status of the subscription, e.g. PENDING, ACTIVE, CANCELLING, CANCELLED.';
COMMENT ON COLUMN ArchiveSubscriber.description IS 'An optional note for the archive owner to describe the subscription.';
COMMENT ON COLUMN ArchiveSubscriber.date_cancelled IS 'The date and time this subscription was revoked.';
COMMENT ON COLUMN ArchiveSubscriber.cancelled_by IS 'The person who revoked this subscription.';

-- PackageCopyRequest

COMMENT ON TABLE PackageCopyRequest IS 'PackageCopyRequest: A table that captures the status and the details of an inter-archive package copy operation.';
COMMENT ON COLUMN PackageCopyRequest.requester IS 'The person who requested the archive operation.';
COMMENT ON COLUMN PackageCopyRequest.source_archive IS 'The archive from which packages are to be copied.';
COMMENT ON COLUMN PackageCopyRequest.source_distroseries IS 'The distroseries to which the packages to be copied belong in the source archive.';
COMMENT ON COLUMN PackageCopyRequest.source_component IS 'The component to which the packages to be copied belong in the source archive.';
COMMENT ON COLUMN PackageCopyRequest.source_pocket IS 'The pocket for the packages to be copied.';
COMMENT ON COLUMN PackageCopyRequest.target_archive IS 'The archive to which packages will be copied.';
COMMENT ON COLUMN PackageCopyRequest.target_distroseries IS 'The target distroseries.';
COMMENT ON COLUMN PackageCopyRequest.target_component IS 'The target component.';
COMMENT ON COLUMN PackageCopyRequest.target_pocket IS 'The target pocket.';
COMMENT ON COLUMN PackageCopyRequest.status IS 'Archive operation status, may be one of: new, in-progress, complete, failed, cancelling, cancelled.';
COMMENT ON COLUMN PackageCopyRequest.reason IS 'The reason why this copy operation was requested.';
COMMENT ON COLUMN PackageCopyRequest.date_created IS 'Date of creation for this archive operation.';
COMMENT ON COLUMN PackageCopyRequest.date_started IS 'Start date/time of this archive operation.';
COMMENT ON COLUMN PackageCopyRequest.date_completed IS 'When did this archive operation conclude?';

-- ArchiveArch

COMMENT ON TABLE ArchiveArch IS 'ArchiveArch: A table that allows a user to specify which architectures an archive requires or supports.';
COMMENT ON COLUMN ArchiveArch.archive IS 'The archive for which an architecture is specified.';
COMMENT ON COLUMN ArchiveArch.processor IS 'The architecture specified for the archive on hand.';

-- Component
COMMENT ON TABLE Component IS 'Known components in Launchpad';
COMMENT ON COLUMN Component.name IS 'Component name text';
COMMENT ON COLUMN Component.description IS 'Description of this component.';


-- Section
COMMENT ON TABLE Section IS 'Known sections in Launchpad';
COMMENT ON COLUMN Section.name IS 'Section name text';


-- ComponentSelection
COMMENT ON TABLE ComponentSelection IS 'Allowed components in a given distroseries.';
COMMENT ON COLUMN ComponentSelection.distroseries IS 'Refers to the distroseries in question.';
COMMENT ON COLUMN ComponentSelection.component IS 'Refers to the component in qestion.';


-- SectionSelection
COMMENT ON TABLE SectionSelection IS 'Allowed sections in a given distroseries.';
COMMENT ON COLUMN SectionSelection.distroseries IS 'Refers to the distroseries in question.';
COMMENT ON COLUMN SectionSelection.section IS 'Refers to the section in question.';

-- PillarName
COMMENT ON TABLE PillarName IS 'A cache of the names of our "Pillar''s" (distribution, product, project) to ensure uniqueness in this shared namespace. This is a materialized view maintained by database triggers.';
COMMENT ON COLUMN PillarName.alias_for IS 'An alias for another pillarname. Rows with this column set are not maintained by triggers.';

-- POFileTranslator
COMMENT ON TABLE POFileTranslator IS 'A materialized view caching who has translated what pofile.';
COMMENT ON COLUMN POFileTranslator.person IS 'The person who submitted the translation.';
COMMENT ON COLUMN POFileTranslator.pofile IS 'The pofile the translation was submitted for.';
COMMENT ON COLUMN POFileTranslator.date_last_touched IS 'When was added latest
translation message.';

-- NameBlacklist
COMMENT ON TABLE NameBlacklist IS 'A list of regular expressions used to blacklist names.';
COMMENT ON COLUMN NameBlacklist.regexp IS 'A Python regular expression. It will be compiled with the IGNORECASE, UNICODE and VERBOSE flags. The Python search method will be used rather than match, so ^ markers should be used to indicate the start of a string.';
COMMENT ON COLUMN NameBlacklist.comment IS 'An optional comment on why this regexp was entered. It should not be displayed to non-admins and its only purpose is documentation.';
COMMENT ON COLUMN NameBlacklist.admin IS 'The person who can override the blacklisted name.';

-- ScriptActivity
COMMENT ON TABLE ScriptActivity IS 'Records of successful runs of scripts ';
COMMENT ON COLUMN ScriptActivity.name IS 'The name of the script';
COMMENT ON COLUMN ScriptActivity.hostname IS 'The hostname of the machine where the script was run';
COMMENT ON COLUMN ScriptActivity.date_started IS 'The date at which the script started';
COMMENT ON COLUMN ScriptActivity.date_completed IS 'The date at which the script completed';

-- RevisionProperty
COMMENT ON TABLE RevisionProperty IS 'A collection of name and value pairs that appear on a revision.';
COMMENT ON COLUMN RevisionProperty.revision IS 'The revision which has properties.';
COMMENT ON COLUMN RevisionProperty.name IS 'The name of the property.';
COMMENT ON COLUMN RevisionProperty.value IS 'The value of the property.';

-- ProductSubscription
-- COMMENT ON TABLE ProductSubscription IS 'Defines the support contacts for a given product. The support contacts will be automatically subscribed to every support request filed on the product.';

-- LanguagePack
COMMENT ON TABLE LanguagePack IS 'Store exported language packs for DistroSeries.';
COMMENT ON COLUMN LanguagePack.file IS 'Librarian file where the language pack is stored.';
COMMENT ON COLUMN LanguagePack.date_exported IS 'When was exported the language pack.';
COMMENT ON COLUMN LanguagePack.date_last_used IS 'When did we stop using the language pack. It''s used to decide whether we can remove it completely from the system. When it''s being used, its value is NULL';
COMMENT ON COLUMN LanguagePack.distroseries IS 'The distribution series from where this language pack was exported.';
COMMENT ON COLUMN LanguagePack.type IS 'Type of language pack. There are two types available, 1: Full export, 2: Update export based on language_pack_that_updates export.';
COMMENT ON COLUMN LanguagePack.updates IS 'The LanguagePack that this one updates.';

-- HWSubmission
COMMENT ON TABLE HWSubmission IS 'Raw HWDB submission data';
COMMENT ON COLUMN HWSubmission.date_created IS 'Date and time of the submission (generated by the client).';
COMMENT ON COLUMN HWSubmission.date_submitted IS 'Date and time of the submission (generated by the server).';
COMMENT ON COLUMN HWSubmission.format IS 'The format version of the submitted data, as given by the HWDB client. See HWSubmissionFormat for valid values.';
COMMENT ON COLUMN HWSubmission.status IS 'The status of the submission. See HWSubmissionProcessingStatus for valid values.';
COMMENT ON COLUMN HWSubmission.private IS 'If false, the submitter allows public access to the data. If true, the data may be used only for statistical purposes.';
COMMENT ON COLUMN HWSubmission.contactable IS 'If True, the submitter agrees to be contacted by upstream developers and package maintainers for tests etc.';
COMMENT ON COLUMN HWSubmission.submission_key IS 'A unique submission ID.';
COMMENT ON COLUMN HWSubmission.owner IS 'A reference to the Person table: The owner/submitter of the data.';
COMMENT ON COLUMN HWSubmission.distroarchseries IS 'A reference to the distroarchseries of the submission. This value is null, if the submitted values for distribution, distroseries and architecture do not match an existing entry in the Distroarchseries table.';
COMMENT ON COLUMN HWSubmission.raw_submission IS 'A reference to a row of LibraryFileAlias. The library file contains the raw submission data.';
COMMENT ON COLUMN HWSubmission.system_fingerprint IS 'A reference to an entry of the HWDBSystemFingerPrint table. This table stores the system name as returned by HAL (system.vendor, system.product)';
COMMENT ON COLUMN HWSubmission.raw_emailaddress IS 'The email address of the submitter.';

COMMENT ON TABLE HWSubmissionBug IS 'Link bugs to HWDB submissions';

COMMENT ON TABLE HWSystemFingerprint IS 'A distinct list of "fingerprints" (HAL system.name, system.vendor) from raw submission data';
COMMENT ON COLUMN HWSystemFingerprint.fingerprint IS 'The fingerprint';

COMMENT ON TABLE HWDriver IS 'Information about a driver for a device';
COMMENT ON COLUMN HWDriver.package_name IS 'The Debian package name a driver is a part of';
COMMENT ON COLUMN HWDriver.name IS 'The name of a driver.';

COMMENT ON VIEW HWDriverNames IS 'A view returning the distinct driver names stored in HWDriver.';
COMMENT ON COLUMN HWDriverNames.name IS 'The name of a driver.';

COMMENT ON VIEW HWDriverPackageNames IS 'A view returning the distinct Debian package names stored in HWDriver.';
COMMENT ON COLUMN HWDriverPackageNames.package_name IS 'The Debian package name a driver is a part of.';

COMMENT ON TABLE HWVendorName IS 'A list of hardware vendor names.';
COMMENT ON COLUMN HWVendorName.name IS 'The name of a vendor.';

COMMENT ON TABLE HWVendorId IS 'Associates tuples (bus, vendor ID for this bus) with vendor names.';
COMMENT ON COLUMN HWVendorId.bus IS 'The bus.';
COMMENT ON COLUMN HWVendorId.vendor_id_for_bus IS 'The ID of a vendor for the bus given by column `bus`';

COMMENT ON TABLE HWDevice IS 'Basic information on devices.';
COMMENT ON COLUMN HWDevice.bus_vendor_id IS 'A reference to a HWVendorID record.';
COMMENT ON COLUMN HWDevice.bus_product_id IS 'The bus product ID of a device';
COMMENT ON COLUMN HWDevice.variant IS 'An optional additional description for a device that shares its vendor and product ID with another, technically different, device.';
COMMENT ON COLUMN HWDevice.name IS 'The human readable product name of the device.';
COMMENT ON COLUMN HWDevice.submissions IS 'The number of submissions that contain this device.';

COMMENT ON TABLE HWDeviceClass IS 'Capabilities of a device.';
COMMENT ON COLUMN HWDeviceClass.device IS 'A reference to a device.';
COMMENT ON COLUMN HWDeviceClass.main_class IS 'The main class of a device. Legal values are defined by the HWMainClass enumeration.';
COMMENT ON COLUMN HWDeviceClass.sub_class IS 'The sub-class of a device. Legal values are defined by the HWSubClass enumeration.';

COMMENT ON TABLE HWDeviceNameVariant IS 'Alternative vendor and product names of devices.';
COMMENT ON COLUMN HWDeviceNameVariant.vendor_name IS 'The alternative vendor name.';
COMMENT ON COLUMN HWDeviceNameVariant.product_name IS 'The alternative product name.';
COMMENT ON COLUMN HWDeviceNameVariant.device IS 'The device named by this alternative vendor and product names.';
COMMENT ON COLUMN HWDeviceNameVariant.submissions IS 'The number of submissions containing this alternative vendor and product name.';

COMMENT ON TABLE HWDeviceDriverLink IS 'Combinations of devices and drivers mentioned in submissions.';
COMMENT ON COLUMN HWDeviceDriverLink.device IS 'The device controlled by the driver.';
COMMENT ON COLUMN HWDeviceDriverLink.driver IS 'The driver controlling the device.';

COMMENT ON TABLE HWSubmissionDevice IS 'Links between devices and submissions.';
COMMENT ON COLUMN HWSubmissionDevice.device_driver_link IS 'The combination (device, driver) mentioned in a submission.';
COMMENT ON COLUMN HWSubmissionDevice.submission IS 'The submission mentioning this (device, driver) combination.';
COMMENT ON COLUMN HWSubmissionDevice.parent IS 'The parent device of this device.';
COMMENT ON COLUMN HWSubmissionDevice.hal_device_id IS 'The ID of the HAL node of this device in the submitted data.';

COMMENT ON TABLE HWTest IS 'General information about a device test.';
COMMENT ON COLUMN HWTest.namespace IS 'The namespace of a test.';
COMMENT ON COLUMN HWTest.name IS 'The name of a test.';

COMMENT ON TABLE HWTestAnswerChoice IS 'Choice values of multiple choice tests/questions.';
COMMENT ON COLUMN HWTestAnswerChoice.choice IS 'The choice value.';
COMMENT ON COLUMN HWTestAnswerChoice.test IS 'The test this choice belongs to.';

COMMENT ON TABLE HWTestAnswer IS 'The answer for a test from a submission. This can be either a multiple choice selection or a numerical value. Exactly one of the columns choice, intval, floatval must be non-null.';
COMMENT ON COLUMN HWTestAnswer.test IS 'The test answered by this answer.';
COMMENT ON COLUMN HWTestAnswer.choice IS 'The selected value of a multiple choice test.';
COMMENT ON COLUMN HWTestAnswer.intval IS 'The integer result of a test with a numerical result.';
COMMENT ON COLUMN HWTestAnswer.floatval IS 'The double precision floating point number result of a test with a numerical result.';
COMMENT ON COLUMN HWTestAnswer.unit IS 'The physical unit of a test with a numerical result.';

COMMENT ON TABLE HWTestAnswerCount IS 'Accumulated results of tests. Either the column choice or the columns average and sum_square must be non-null.';
COMMENT ON COLUMN HWTestAnswerCount.test IS 'The test.';
COMMENT ON COLUMN HWTestAnswerCount.distroarchseries IS 'The distroarchseries for which results are accumulated,';
COMMENT ON COLUMN HWTestAnswerCount.choice IS 'The choice value of a multiple choice test.';
COMMENT ON COLUMN HWTestAnswerCount.average IS 'The average value of the result of a numerical test.';
COMMENT ON COLUMN HWTestAnswerCount.sum_square IS 'The sum of the squares of the results of a numerical test.';
COMMENT ON COLUMN HWTestAnswerCount.unit IS 'The physical unit of a numerical test result.';
COMMENT ON COLUMN HWTestAnswerCount.num_answers IS 'The number of submissions from which the result is accumulated.';

COMMENT ON TABLE HWTestAnswerDevice IS 'Association of test results and device/driver combinations.';
COMMENT ON COLUMN HWTestAnswerDevice.answer IS 'The test answer.';
COMMENT ON COLUMN HWTestAnswerDevice.device_driver IS 'The device/driver combination.';

COMMENT ON TABLE HWTestAnswerCountDevice IS 'Association of accumulated test results and device/driver combinations.';
COMMENT ON COLUMN HWTestAnswerCountDevice.answer IS 'The test answer.';
COMMENT ON COLUMN HWTestAnswerCountDevice.device_driver IS 'The device/driver combination.';


COMMENT ON TABLE HWDMIHandle IS 'A DMI Handle appearing in the DMI data of a submission.';
COMMENT ON COLUMN HWDMIHandle.handle IS 'The ID of the handle.';
COMMENT ON COLUMN HWDMIHandle.type IS 'The type of the handle.';


COMMENT ON TABLE HWDMIValue IS 'Key/value pairs of DMI data of a handle.';
COMMENT ON COLUMN HWDMIValue.key IS 'The key.';
COMMENT ON COLUMN HWDMIValue.value IS 'The value';
COMMENT ON COLUMN HWDMIValue.handle IS 'The handle to which this key/value pair belongs.';

-- IncrementalDiff
COMMENT ON TABLE IncrementalDiff IS 'Incremental diffs for merge proposals.';
COMMENT ON COLUMN IncrementalDiff.diff IS 'The contents of the diff.';
COMMENT ON COLUMN IncrementalDiff.branch_merge_proposal IS 'The merge proposal the diff is for.';
COMMENT ON COLUMN IncrementalDiff.old_revision IS 'The revision the diff is from.';
COMMENT ON COLUMN IncrementalDiff.new_revision IS 'The revision the diff is to.';


-- Job

COMMENT ON TABLE Job IS 'Common info about a job.';
COMMENT ON COLUMN Job.requester IS 'Ther person who requested this job (if applicable).';
COMMENT ON COLUMN Job.reason IS 'The reason that this job was created (if applicable)';
COMMENT ON COLUMN Job.status IS 'An enum (JobStatus) indicating the job status, one of: new, in-progress, complete, failed, cancelling, cancelled.';
COMMENT ON COLUMN Job.progress IS 'The percentage complete.  Can be NULL for some jobs that do not report progress.';
COMMENT ON COLUMN Job.last_report_seen IS 'The last time the progress was reported.';
COMMENT ON COLUMN Job.next_report_due IS 'The next time a progress report is expected.';
COMMENT ON COLUMN Job.attempt_count IS 'The number of times this job has been attempted.';
COMMENT ON COLUMN Job.max_retries IS 'The maximum number of retries valid for this job.';
COMMENT ON COLUMN Job.log IS 'If provided, this is the tail of the log file being generated by the running job.';
COMMENT ON COLUMN Job.scheduled_start IS 'The time when the job should start';
COMMENT ON COLUMN Job.lease_expires IS 'The time when the lease expires.';
COMMENT ON COLUMN Job.date_created IS 'The time when the job was created.';
COMMENT ON COLUMN Job.date_started IS 'If the job has started, the time when the job started.';
COMMENT ON COLUMN Job.date_finished IS 'If the job has finished, the time when the job finished.';


-- StructuralSubscription
COMMENT ON TABLE StructuralSubscription IS 'A subscription to notifications about a Launchpad structure';
COMMENT ON COLUMN StructuralSubscription.product IS 'The subscription\`s target, when it is a product.';
COMMENT ON COLUMN StructuralSubscription.productseries IS 'The subscription\`s target, when it is a product series.';
COMMENT ON COLUMN StructuralSubscription.project IS 'The subscription\`s target, when it is a project.';
COMMENT ON COLUMN StructuralSubscription.milestone IS 'The subscription\`s target, when it is a milestone.';
COMMENT ON COLUMN StructuralSubscription.distribution IS 'The subscription\`s target, when it is a distribution.';
COMMENT ON COLUMN StructuralSubscription.distroseries IS 'The subscription\`s target, when it is a distribution series.';
COMMENT ON COLUMN StructuralSubscription.sourcepackagename IS 'The subscription\`s target, when it is a source-package';
COMMENT ON COLUMN StructuralSubscription.subscriber IS 'The person subscribed.';
COMMENT ON COLUMN StructuralSubscription.subscribed_by IS 'The person initiating the subscription.';
COMMENT ON COLUMN StructuralSubscription.date_created IS 'The date on which this subscription was created.';
COMMENT ON COLUMN StructuralSubscription.date_last_updated IS 'The date on which this subscription was last updated.';

-- OAuth
COMMENT ON TABLE OAuthConsumer IS 'A third part application that will access Launchpad on behalf of one of our users.';
COMMENT ON COLUMN OAuthConsumer.key IS 'The unique key for this consumer.';
COMMENT ON COLUMN OAuthConsumer.secret IS 'The secret used by this consumer (together with its key) to identify itself with Launchpad.';
COMMENT ON COLUMN OAuthConsumer.date_created IS 'The creation date.';
COMMENT ON COLUMN OAuthConsumer.disabled IS 'Is this consumer disabled?';

COMMENT ON TABLE OAuthRequestToken IS 'A request token which, once authorized by the user, is exchanged for an access token.';
COMMENT ON COLUMN OAuthRequestToken.consumer IS 'The consumer which is going to access the protected resources.';
COMMENT ON COLUMN OAuthRequestToken.person IS 'The person who authorized this token.';
COMMENT ON COLUMN OAuthRequestToken.permission IS 'The permission given by the
person to the consumer.';
COMMENT ON COLUMN OAuthRequestToken.key IS 'This token''s unique key.';
COMMENT ON COLUMN OAuthRequestToken.secret IS 'The secret used by the consumer (together with the token''s key) to get an access token once the user has authorized its use.';
COMMENT ON COLUMN OAuthRequestToken.date_created IS 'The date/time in which the token was created.';
COMMENT ON COLUMN OAuthRequestToken.date_expires IS 'When the authorization is to expire.';
COMMENT ON COLUMN OAuthRequestToken.date_reviewed IS 'When the authorization request was authorized or rejected by the person.';
COMMENT ON COLUMN OAuthRequestToken.product IS 'The product associated with this token.';
COMMENT ON COLUMN OAuthRequestToken.project IS 'The project associated with this token.';
COMMENT ON COLUMN OAuthRequestToken.distribution IS 'The distribution associated with this token.';
COMMENT ON COLUMN OAuthRequestToken.sourcepackagename IS 'The sourcepackagename associated with this token.';

COMMENT ON TABLE OAuthAccessToken IS 'An access token used by the consumer to act on behalf of one of our users.';
COMMENT ON COLUMN OAuthAccessToken.consumer IS 'The consumer which is going to access the protected resources.';
COMMENT ON COLUMN OAuthAccessToken.person IS 'The person on whose behalf the
consumer will access Launchpad.';
COMMENT ON COLUMN OAuthAccessToken.permission IS 'The permission given by that person to the consumer.';
COMMENT ON COLUMN OAuthAccessToken.key IS 'This token''s unique key.';
COMMENT ON COLUMN OAuthAccessToken.secret IS 'The secret used by the consumer (together with the token''s key) to access Launchpad on behalf of the person.';
COMMENT ON COLUMN OAuthAccessToken.date_created IS 'The date/time in which the token was created.';
COMMENT ON COLUMN OAuthAccessToken.date_expires IS 'The date/time in which this token will stop being accepted by Launchpad.';
COMMENT ON COLUMN OAuthAccessToken.product IS 'The product associated with this token.';
COMMENT ON COLUMN OAuthAccessToken.project IS 'The project associated with this token.';
COMMENT ON COLUMN OAuthAccessToken.distribution IS 'The distribution associated with this token.';
COMMENT ON COLUMN OAuthAccessToken.sourcepackagename IS 'The sourcepackagename associated with this token.';

COMMENT ON TABLE OAuthNonce IS 'The unique nonce for any request with a given timestamp and access token. This is generated by the consumer.';
COMMENT ON COLUMN OAuthNonce.access_token IS 'The access token.';
COMMENT ON COLUMN OAuthNonce.nonce IS 'The nonce itself.';
COMMENT ON COLUMN OAuthNonce.request_timestamp IS 'The date and time (as a timestamp) in which the request was made.';

COMMENT ON TABLE UserToUserEmail IS 'A log of all direct user-to-user email contacts that have gone through Launchpad.';
COMMENT ON COLUMN UserToUserEmail.sender IS 'The person sending this email.';
COMMENT ON COLUMN UserToUserEmail.recipient IS 'The person receiving this email.';
COMMENT ON COLUMN UserToUserEmail.date_sent IS 'The date the email was sent.';
COMMENT ON COLUMN UserToUserEmail.subject IS 'The Subject: header.';
COMMENT ON COLUMN UserToUserEmail.message_id IS 'The Message-ID: header.';

-- Packageset

COMMENT ON TABLE Packageset IS 'Package sets facilitate the grouping of packages (in a given distro series) for purposes like the control of upload permissions, etc.';
COMMENT ON COLUMN Packageset.date_created IS 'Date and time of creation.';
COMMENT ON COLUMN Packageset.owner IS 'The Person or team who owns the package set';
COMMENT ON COLUMN Packageset.name IS 'The name for the package set on hand.';
COMMENT ON COLUMN Packageset.description IS 'The description for the package set on hand.';
COMMENT ON COLUMN Packageset.packagesetgroup IS 'The group this package set is affiliated with.';
COMMENT ON COLUMN Packageset.distroseries IS 'The distro series this package set belongs to.';

-- PackagesetGroup

COMMENT ON TABLE PackagesetGroup IS 'Package set groups keep track of equivalent package sets across distro series boundaries.';
COMMENT ON COLUMN Packageset.date_created IS 'Date and time of creation.';
COMMENT ON COLUMN Packageset.owner IS 'The Person or team who owns the package
set group.';

-- PackagesetSources

COMMENT ON TABLE PackagesetSources IS 'This table associates package sets and source package names.';
COMMENT ON COLUMN PackagesetSources.packageset IS 'The associated package set.';
COMMENT ON COLUMN PackagesetSources.sourcepackagename IS 'The associated source package name.';

-- PackagesetInclusion
COMMENT ON TABLE PackagesetInclusion IS 'sets may form a set-subset hierarchy; this table facilitates the definition of these set-subset relationships.';
COMMENT ON COLUMN PackagesetInclusion.parent IS 'The package set that is including a subset.';
COMMENT ON COLUMN PackagesetInclusion.child IS 'The package set that is being included as a subset.';

-- FlatPackagesetInclusion
COMMENT ON TABLE FlatPackagesetInclusion IS 'In order to facilitate the querying of set-subset relationships an expanded or flattened representation of the set-subset hierarchy is provided by this table.';
COMMENT ON COLUMN FlatPackagesetInclusion.parent IS 'The package set that is (directly or indirectly) including a subset.';
COMMENT ON COLUMN FlatPackagesetInclusion.child IS 'The package set that is being included as a subset.';

-- SourcePackageFormatSelection
COMMENT ON TABLE SourcePackageFormatSelection IS 'Allowed source package formats for a given distroseries.';
COMMENT ON COLUMN SourcePackageFormatSelection.distroseries IS 'Refers to the distroseries in question.';
COMMENT ON COLUMN SourcePackageFormatSelection.format IS 'The SourcePackageFormat to allow.';

COMMENT ON TABLE DatabaseReplicationLag IS 'A cached snapshot of database replication lag between our master Slony node and its slaves.';
COMMENT ON COLUMN DatabaseReplicationLag.node IS 'The Slony node number identifying the slave database.';
COMMENT ON COLUMN DatabaseReplicationLag.lag IS 'lag time.';
COMMENT ON COLUMN DatabaseReplicationLag.updated IS 'When this value was updated.';

-- DatabaseTableStats
COMMENT ON TABLE DatabaseTableStats IS 'Snapshots of pg_stat_user_tables to let us calculate arbitrary deltas';

-- DatabaseCpuStats
COMMENT ON TABLE DatabaseCpuStats IS 'Snapshots of CPU utilization per database username.';
COMMENT ON COLUMN DatabaseCpuStats.cpu IS '% CPU utilization * 100, as reported by ps -o cp';

-- SuggestivePOTemplate
COMMENT ON TABLE SuggestivePOTemplate IS
'Cache of POTemplates that can provide external translation suggestions.';

-- OpenIdIdentifier
COMMENT ON TABLE OpenIdIdentifier IS
'OpenId Identifiers that can be used to log into an Account.';
COMMENT ON COLUMN OpenIdIdentifier.identifier IS
'OpenId Identifier. This should be a URL, but is currently just a token that can be used to generate the Identity URL for the Canonical SSO OpenId Provider.';

-- MilestoneTag
COMMENT ON TABLE milestonetag IS 'Attaches simple text tags to a milestone.';
COMMENT ON COLUMN milestonetag.milestone IS 'The milestone the tag is attached to.';
COMMENT ON COLUMN milestonetag.tag IS 'The text representation of the tag.';
