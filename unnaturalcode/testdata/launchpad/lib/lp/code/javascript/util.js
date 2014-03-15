/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Control enabling/disabling form elements on Code domain pages.
 *
 * @module Y.lp.code.util
 * @requires node
 */
YUI.add('lp.code.util', function(Y) {
var ns = Y.namespace('lp.code.util');

var update_branch_unique_location = function() {
    var unique_location = Y.one("#branch-unique-location");
    var owner = Y.one("[id='field.owner']").get('value');
    var name = Y.one("[id='field.name']").get('value');
    if (name === '') {
        name = '<name>';
    }
    var branch_location = "lp:~" + owner + "/" + target_name + "/" + name;
    unique_location.set('text', branch_name);
};

var hookUpBranchFieldFunctions = function () {
    var owner = Y.one("[id='field.owner']");
    owner.on('keyup', update_branch_unique_name);
    owner.on('change', update_branch_unique_name);
    var name = Y.one("[id='field.name']");
    name.on('keyup', update_branch_unique_name);
    name.on('change', update_branch_unique_name);
    Y.one('#branch-unique-name-div').setStyle('display', 'block');
    update_branch_unique_name();
};

var submit_filter = function (e) {
    Y.one('#filter_form').submit();
};

var hookUpBranchFilterSubmission = function() {
    Y.one("[id='field.lifecycle']").on('change', submit_filter);
    var sortby = Y.one("[id='field.sort_by']");
    if (Y.Lang.isValue(sortby)) {
        sortby.on('change', submit_filter);
    }
    Y.one('#filter_form_submit').addClass('hidden');
};

var hookUpDailyBuildsFilterSubmission = function() {
    Y.one("[id='field.when_completed_filter']").on(
        'change', submit_filter);
    Y.one('#filter_form_submit').addClass('hidden');
};

var hookUpMergeProposalFilterSubmission = function() {
    Y.one("[id='field.status']").on('change', submit_filter);
    Y.one('#filter_form_submit').addClass('hidden');
};

var hookUpRetyImportSubmission = function() {
    var try_again_link = Y.one("#tryagainlink");
    try_again_link.on('click', function (e) {
        Y.one('#tryagain').submit();
    });
    try_again_link.removeClass('hidden');
    Y.one('[id="tryagain.actions.tryagain"]').addClass('hidden');
};

ns.hookUpBranchFieldFunctions = hookUpBranchFieldFunctions;
ns.hookUpBranchFilterSubmission = hookUpBranchFilterSubmission;
ns.hookUpDailyBuildsFilterSubmission = hookUpDailyBuildsFilterSubmission;
ns.hookUpMergeProposalFilterSubmission = hookUpMergeProposalFilterSubmission;
ns.hookUpRetyImportSubmission = hookUpRetyImportSubmission;

}, "0.1", {"requires": ["node", "dom"]});

