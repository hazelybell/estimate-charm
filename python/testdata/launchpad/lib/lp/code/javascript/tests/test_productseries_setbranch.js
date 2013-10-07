/* Copyright 2010 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Test driver for productseries_setbranch.js.
 *
 */
YUI.add('lp.productseries_setbranch.test', function (Y) {
    var tests = Y.namespace('lp.productseries_setbranch.test');
    var module = Y.lp.code.productseries_setbranch;
    tests.suite = new Y.Test.Suite("productseries_setbranch Tests");

    tests.suite.add(new Y.Test.Case({
        // Test the onclick results.
        name: 'select_branchtype',

        _should: {
            error: {
                //test_config_undefined: true,
                //test_missing_tbody_is_an_error: true
                }
        },

        setUp: function() {
           this.tbody = Y.one('#productseries-setbranch');

           // Get the individual branch type radio buttons.
           this.link_lp_bzr = Y.DOM.byId('field.branch_type.0');
           this.import_external = Y.DOM.byId('field.branch_type.1');

           // Get the input widgets.
           this.branch_location = Y.DOM.byId('field.branch_location');
           this.cvs_module = Y.DOM.byId('field.cvs_module');
           this.repo_url = Y.DOM.byId('field.repo_url');
           this.branch_name = Y.DOM.byId('field.branch_name');
           this.branch_owner = Y.DOM.byId('field.branch_owner');

           // Get the individual rcs type radio buttons.
           this.cvs = Y.DOM.byId('field.rcs_type.1');
           this.svn = Y.DOM.byId('field.rcs_type.3');
           this.git = Y.DOM.byId('field.rcs_type.4');
           this.bzr = Y.DOM.byId('field.rcs_type.6');
        },

        tearDown: function() {
            delete this.tbody;
        },

        test_handlers_connected: function() {
           // Manually invoke the setup function to ensure the handlers are
           // set.
           module.setup();

           var check_handler = function(field, expected) {
              var custom_events = Y.Event.getListeners(field, 'click');
              var click_event = custom_events[0];
              var subscribers = click_event.subscribers;
              Y.each(subscribers, function(sub) {
                 Y.Assert.isTrue(sub.contains(expected),
                                 'branch_type_onclick handler setup');
              });
           };

           check_handler(this.link_lp_bzr, module.onclick_branch_type);
           check_handler(this.import_external, module.onclick_branch_type);

           check_handler(this.cvs, module.onclick_rcs_type);
           check_handler(this.svn, module.onclick_rcs_type);
           check_handler(this.git, module.onclick_rcs_type);
           check_handler(this.bzr, module.onclick_rcs_type);
        },

        test_select_link_lp_bzr: function() {
           this.link_lp_bzr.checked = true;
           module.onclick_branch_type();
           // The branch location is enabled.
           Y.Assert.isFalse(this.branch_location.disabled,
                            'branch_location disabled');
           module.onclick_rcs_type();
           // The CVS module and repo url are disabled.
           Y.Assert.isTrue(this.cvs_module.disabled,
                           'cvs_module not disabled');
           Y.Assert.isTrue(this.repo_url.disabled,
                           'repo_url not disabled');
           // The branch name and owner are disabled.
           Y.Assert.isTrue(this.branch_name.disabled,
                           'branch_name not disabled');
           Y.Assert.isTrue(this.branch_owner.disabled,
                           'branch_owner not disabled');
           // All of the radio buttons are disabled.
           Y.Assert.isTrue(this.cvs.disabled,
                           'cvs button not disabled');
           Y.Assert.isTrue(this.svn.disabled,
                           'svn button not disabled');
           Y.Assert.isTrue(this.git.disabled,
                           'git button not disabled');
           Y.Assert.isTrue(this.bzr.disabled,
                           'bzr button not disabled');
        },

        test_select_import_external: function() {
           this.import_external.checked = true;
           module.onclick_branch_type();
           // The branch location is disabled.
           Y.Assert.isTrue(this.branch_location.disabled,
                           'branch_location not disabled');
           // The repo url is enabled.
           Y.Assert.isFalse(this.repo_url.disabled,
                           'repo_url disabled');
           module.onclick_rcs_type();
           // The branch name and owner are enabled.
           Y.Assert.isFalse(this.branch_name.disabled,
                           'branch_name disabled');
           Y.Assert.isFalse(this.branch_owner.disabled,
                           'branch_owner disabled');
           // All of the radio buttons are disabled.
           Y.Assert.isFalse(this.cvs.disabled,
                           'cvs button disabled');
           Y.Assert.isFalse(this.svn.disabled,
                           'svn button disabled');
           Y.Assert.isFalse(this.git.disabled,
                           'git button disabled');
           Y.Assert.isFalse(this.bzr.disabled,
                           'bzr button disabled');

        },

        test_select_import_external_bzr: function() {
           this.import_external.checked = true;
           module.onclick_branch_type();
           Y.Assert.isFalse(this.repo_url.disabled,
                           'repo_url disabled');
           this.bzr.checked = true;
           module.onclick_rcs_type();
           // The CVS module input is disabled.
           Y.Assert.isTrue(this.cvs_module.disabled,
                           'cvs_module disabled');
        },

        test_select_import_external_hg: function() {
           this.import_external.checked = true;
           module.onclick_branch_type();
           Y.Assert.isFalse(this.repo_url.disabled,
                           'repo_url disabled');
           module.onclick_rcs_type();
           // The CVS module input is disabled.
           Y.Assert.isTrue(this.cvs_module.disabled,
                           'cvs_module disabled');
        },

        test_select_import_external_git: function() {
           this.import_external.checked = true;
           module.onclick_branch_type();
           Y.Assert.isFalse(this.repo_url.disabled,
                           'repo_url disabled');
           this.git.checked = true;
           module.onclick_rcs_type();
           // The CVS module input is disabled.
           Y.Assert.isTrue(this.cvs_module.disabled,
                           'cvs_module disabled');
        },

        test_select_import_external_svn: function() {
           this.import_external.checked = true;
           module.onclick_branch_type();
           Y.Assert.isFalse(this.repo_url.disabled,
                           'repo_url disabled');
           this.svn.checked = true;
           module.onclick_rcs_type();
           // The CVS module input is disabled.
           Y.Assert.isTrue(this.cvs_module.disabled,
                           'cvs_module disabled');
        },

        test_select_import_external_cvs: function() {
           this.import_external.checked = true;
           module.onclick_branch_type();
           Y.Assert.isFalse(this.repo_url.disabled,
                           'repo_url disabled');
           this.cvs.checked = true;
           module.onclick_rcs_type();
           // The CVS module input is enabled
           Y.Assert.isFalse(this.cvs_module.disabled,
                           'cvs_module disabled');
        }

        }));

}, '0.1', {
    requires: ['lp.testing.runner', 'node-event-simulate', 'test', 'test-console',
               'Event', 'CustomEvent',
               'lp.code.productseries_setbranch']
});
