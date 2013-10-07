/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */
YUI.add('lp.code.util.test', function (Y) {
var tests = Y.namespace('lp.code.util.test');

tests.suite = new Y.Test.Suite("lp.code.util Tests");
var module = Y.lp.code.util;

tests.suite.add(new Y.Test.Case({
    name: "lp.code.util",

    setUp: function() {
        this.fixture = Y.one("#fixture");
        this.listener = {event_fired: false};
    },

    tearDown: function () {
        if (this.fixture !== null) {
            this.fixture.empty();
        }
        delete this.fixture;
    },

    _setup_fixture: function(template_selector) {
        var template =Y.one(template_selector).getContent();
        var test_node = Y.Node.create(template);
        this.fixture.append(test_node);
    },

    _add_submit_listener: function(form_selector) {
        // prevent submission when the form's method is directly invoked
        // and record that the methods was called.
        var listener = this.listener;
        Y.one(form_selector).submit = function(e) {
            listener.event_fired = true;
            // YUI 3.5 doesn't have an EventFacade passed into the simulated
            // event.
            if (e) {
                e.halt();
            }
        };
    },

    test_hookUpDailyBuildsFilterSubmission: function() {
        this._setup_fixture('#daily-builds-form');
        module.hookUpDailyBuildsFilterSubmission();
        this._add_submit_listener('#filter_form');
        Y.one('[id="field.when_completed_filter"]').simulate('change');
        Y.Assert.isTrue(this.listener.event_fired);
        Y.Assert.isTrue(
            Y.one('#filter_form_submit').hasClass('hidden'));
    },

    test_hookUpBranchFilterSubmission: function() {
        this._setup_fixture('#branch-listing-form');
        module.hookUpBranchFilterSubmission();
        this._add_submit_listener('#filter_form');
        Y.one('[id="field.lifecycle"]').simulate('change');
        Y.Assert.isTrue(this.listener.event_fired);
        this.listener.event_fired = false;
        Y.one('[id="field.sort_by"]').simulate('change');
        Y.Assert.isTrue(this.listener.event_fired);
        Y.Assert.isTrue(
            Y.one('#filter_form_submit').hasClass('hidden'));
    },

    test_hookUpMergeProposalFilterSubmission: function() {
        this._setup_fixture('#merge-proposal-form');
        module.hookUpMergeProposalFilterSubmission();
        this._add_submit_listener('#filter_form');
        Y.one('[id="field.status"]').simulate('change');
        Y.Assert.isTrue(this.listener.event_fired);
        Y.Assert.isTrue(
            Y.one('#filter_form_submit').hasClass('hidden'));
    },

    test_hookUpRetyImportSubmission: function() {
        this._setup_fixture('#retry-import-form');
        module.hookUpRetyImportSubmission();
        this._add_submit_listener('#tryagain');
        var try_again_link = Y.one("#tryagainlink");
        try_again_link.simulate('click');
        Y.Assert.isTrue(this.listener.event_fired);
        Y.Assert.isFalse(try_again_link.hasClass('hidden'));
        Y.Assert.isTrue(
            Y.one('[id="tryagain.actions.tryagain"]').hasClass('hidden'));
    }

}));

}, '0.1', {
    requires: ['test', 'test-console', 'node-event-simulate', 'lp.testing.runner',
               'lp.code.util']
});
