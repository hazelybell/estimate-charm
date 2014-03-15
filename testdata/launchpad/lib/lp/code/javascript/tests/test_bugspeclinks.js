/* Copyright 2012-2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.code.branch.bugspeclinks.test', function (Y) {
    var module = Y.lp.code.branch.bugspeclinks;
    var extract_candidate_bug_id = module.extract_candidate_bug_id;

    var tests = Y.namespace('lp.code.branch.bugspeclinks.test');
    tests.suite = new Y.Test.Suite('code.branch.bugspeclinks Tests');

    tests.suite.add(new Y.Test.Case({
        name: 'Test bug ID guessing',

        test_no_bug_id_present: function() {
            // If nothing that looks like a bug ID is present, null is
            // returned.
            Y.Assert.isNull(extract_candidate_bug_id('no-id-here'));
        },

        test_short_digit_rund_ignored: function() {
            Y.Assert.isNull(extract_candidate_bug_id('foo-1234-bar'));
        },

        test_leading_zeros_disqualify_potential_ids: function() {
            // Since bug IDs can't start with zeros, any string of numbers
            // with a leading zero are not considered as a potential ID.
            Y.Assert.isNull(extract_candidate_bug_id('foo-0123456-bar'));
            Y.Assert.areEqual(
                extract_candidate_bug_id('foo-0123456-999999-bar'), '999999');
        },

        test_five_digit_bug_ids_are_extracted: function() {
            Y.Assert.areEqual(
                extract_candidate_bug_id('foo-12345-bar'), '12345');
        },

        test_six_digit_bug_ids_are_extracted: function() {
            Y.Assert.areEqual(
                extract_candidate_bug_id('foo-123456-bar'), '123456');
        },

        test_seven_digit_bug_ids_are_extracted: function() {
            Y.Assert.areEqual(
                extract_candidate_bug_id('foo-1234567-bar'), '1234567');
        },

        test_eight_digit_bug_ids_are_extracted: function() {
            Y.Assert.areEqual(
                extract_candidate_bug_id('foo-12345678-bar'), '12345678');
        },

        test_longest_potential_id_is_extracted: function() {
            // Since there may be numbers other than a bug ID in a branch
            // name, we want to extract the longest string of digits.
            Y.Assert.areEqual(
                extract_candidate_bug_id('bug-123456-take-2'), '123456');
            Y.Assert.areEqual(
                extract_candidate_bug_id('123456-1234567'), '1234567');
        }

    }));

    tests.suite.add(new Y.Test.Case(Y.merge(
        Y.lp.bugs.bug_picker.test.common_bug_picker_tests,
        {
        name: 'Linked Bug Picker Tests',

        setUp: function () {
            window.LP = {
                links: {},
                cache: {
                    context: {
                        name: 'abranch',
                        self_link:
                            'https://foo/api/devel/~fred/firefox/abranch'
                    }
                }
            };
            this.mockio = new Y.lp.testing.mockio.MockIo();
            this.lp_client = new Y.lp.client.Launchpad({
                io_provider: this.mockio
            });
        },

        tearDown: function () {
            Y.one('#fixture').empty(true);
            if (Y.Lang.isValue(this.widget)) {
                this.widget.destroy();
            }
            delete this.mockio;
            delete window.LP;
        },

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.bugs.bug_picker,
                "Could not locate the lp.code.branch.bugspeclinks module");
        },

        _createWidget: function() {
            Y.one('#fixture').appendChild(
                Y.Node.create(Y.one('#bugspec-links').getContent()));
            var widget = new Y.lp.code.branch.bugspeclinks.LinkedBugPicker({
                picker_activator: '.pick-bug',
                private_warning_message:
                    'You are selecting a private bug.',
                use_animation: false,
                io_provider: this.mockio
            });
            widget.render();
            widget.hide();
            return widget;
        },

        // The widget is created as expected.
        test_create_widget: function() {
            this.widget = this._createWidget();
            Y.Assert.isInstanceOf(
                Y.lp.code.branch.bugspeclinks.LinkedBugPicker,
                this.widget,
                "Linked bug picker failed to be instantiated");
            Y.Assert.isFalse(this.widget.get('visible'));
            Y.one('.pick-bug').simulate('click');
            Y.Assert.isTrue(this.widget.get('visible'));
            var remove_dupe = Y.one('.yui3-bugpickerwidget a.remove');
            Y.Assert.isTrue(remove_dupe.hasClass('hidden'));
        },

        // The expected data is submitted after searching for and selecting a
        // bug.
        _assert_link_bug_submission: function(bug_id) {
            this._assert_search_form_submission(bug_id);
            this._assert_search_form_success(bug_id);
            Y.one(
                '.yui3-picker-footer-slot [name="field.actions.save"]')
                .simulate('click');
            this._assert_form_state(true);
            Y.Assert.areEqual(
                '/api/devel/~fred/firefox/abranch',
                this.mockio.last_request.url);
            var bug_uri = encodeURIComponent(
                'file:///api/devel/bugs/' + bug_id);
            var expected_data =
                    'ws.op=linkBug&bug=' + bug_uri;
            Y.Assert.areEqual(
                expected_data, this.mockio.last_request.config.data);
        },

        // Linking a bug works as expected.
        test_picker_form_submission_success: function() {
            this.widget = this._createWidget();
            this._assert_link_bug_submission(3);
            var success_called = false;
            this.widget._link_bug_success =
                function(bug_id, link_bug_content) {
                    Y.Assert.areEqual(3, bug_id);
                    Y.Assert.areEqual('<html></html>', link_bug_content);
                    success_called = true;
                };
            var bug_data = {
                bug_link: "api/devel/bugs/3"
            };
            this.mockio.last_request.successJSON(bug_data);
            Y.Assert.areEqual('++bug-links', this.mockio.last_request.url);
            this.mockio.last_request.respond({
                responseText: '<html></html>',
                responseHeaders: {'Content-Type': 'text/html'}
            });
            Y.Assert.isTrue(success_called);
        },

        // A link failure is handled as expected.
        test_picker_form_submission_failure: function() {
            this.widget = this._createWidget();
            this._assert_link_bug_submission(3);
            this.mockio.respond({
                status: 400,
                responseText: 'There was an error',
                responseHeaders: {'Content-Type': 'text/html'}});
            Y.Assert.areEqual(
                'There was an error', this.widget.get('error'));
        },

        // Submitting an unlink request works as expected.
        test_picker_form_submission_remove_buglink: function() {
            this.widget = this._createWidget();
            var success_called = false;
            this.widget._unlink_bug_success =
                function(bug_id) {
                    Y.Assert.areEqual(6, bug_id);
                    success_called = true;
                };
            Y.one('#delete-buglink-6').simulate('click');
            this.mockio.success({
                responseText: null,
                responseHeaders: {'Content-Type': 'text/html'}});
            Y.Assert.isTrue(success_called);
        },

        // The link bug success function works as expected.
        test_link_bug_success: function() {
            this.widget = this._createWidget();
            var data = {
                self_link: 'api/devel/bugs/1'};
            var new_bug_entry = new Y.lp.client.Entry(
                this.lp_client, data, data.self_link);
            var link_html = '<div id="buglink-3"></div>';
            this.widget._link_bug_success(3, link_html);
            Y.Assert.areEqual(
                'Link to another bug report',
                Y.one('#linkbug').get('text'));
            Y.Assert.areEqual(
                link_html, Y.one('#buglink-list').getContent());
        },

        // The unlink bug success function works as expected.
        test_unlink_bug_success: function() {
            this.widget = this._createWidget();
            // Set up the bug data on the page.
            Y.one('#linkbug').setContent('Link to another');
            Y.one('#buglink-list').appendChild(
                Y.Node.create('<div id="buglink-3"></div>'));
            this.widget._unlink_bug_success(3);
            Y.Assert.areEqual(
                'Link to a bug report', Y.one('#linkbug').getContent());
        }
    })));

}, '0.1', {
    requires: ['test', 'lp.testing.helpers', 'test-console',
        'lp.code.branch.bugspeclinks', 'node-event-simulate',
        'lp.bugs.bug_picker', 'lp.bugs.bug_picker.test']
});
