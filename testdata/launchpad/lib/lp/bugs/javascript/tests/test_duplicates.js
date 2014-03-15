/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.bugs.duplicates.test', function (Y) {

    var tests = Y.namespace('lp.bugs.duplicates.test');
    tests.suite = new Y.Test.Suite('lp.bugs.duplicates Tests');

    tests.suite.add(new Y.Test.Case(Y.merge(
        Y.lp.bugs.bug_picker.test.common_bug_picker_tests,
        {
        name: 'lp.bugs.duplicates_tests',

        setUp: function () {
            window.LP = {
                links: {},
                cache: {
                    bug: {
                        id: 1,
                        self_link: 'api/devel/bugs/1',
                        duplicate_of_link: ''
                    },
                    context: {
                        web_link: '/foobar/bug/1'
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
            delete this.lp_client;
        },

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.bugs.bug_picker,
                "Could not locate the lp.bugs.duplicates module");
        },

        _createWidget: function(existing_duplicate) {
            var fixture_id;
            if (existing_duplicate) {
                fixture_id = "existing-duplicate";
            } else {
                fixture_id = "no-existing-duplicate";
            }
            Y.one('#fixture').appendChild(
                Y.Node.create(Y.one('#' + fixture_id).getContent()));
            var widget = new Y.lp.bugs.duplicates.DuplicateBugPicker({
                picker_activator: '.pick-bug',
                use_animation: false,
                io_provider: this.mockio,
                private_warning_message:
                    'You are selecting a private bug.'
            });
            widget.render();
            widget.hide();
            return widget;
        },

        // The expected data is submitted after searching for and selecting a
        // bug.
        _assert_dupe_submission: function(bug_id) {
            this._assert_search_form_submission(bug_id);
            this._assert_search_form_success(bug_id);
            Y.one(
                '.yui3-picker-footer-slot [name="field.actions.save"]')
                .simulate('click');
            this._assert_form_state(true);
            Y.Assert.areEqual(
                '/foobar/bug/1/+duplicate',
                this.mockio.last_request.url);
            var expected_link =
                    'field.actions.change=Set%20Duplicate' +
                    '&field.duplicateof=3';
            Y.Assert.areEqual(
                expected_link, this.mockio.last_request.config.data);
        },

        // The widget is created when there are no bug duplicates.
        test_widget_creation_no_duplicate_exists: function() {
            this.widget = this._createWidget(false);
            Y.Assert.isInstanceOf(
                Y.lp.bugs.duplicates.DuplicateBugPicker,
                this.widget,
                "Mark bug duplicate picker failed to be instantiated");
            Y.Assert.isNotNull(
                Y.one('#mark-duplicate-text a.menu-link-mark-dupe'));
            Y.Assert.isFalse(this.widget.get('visible'));
            Y.one('.pick-bug').simulate('click');
            Y.Assert.isTrue(this.widget.get('visible'));
            var remove_dupe = Y.one('.yui3-bugpickerwidget a.remove');
            Y.Assert.isTrue(remove_dupe.hasClass('hidden'));
        },

        // The widget is created when there are bug duplicates.
        test_widget_creation_duplicate_exists: function() {
            window.LP.cache.bug.duplicate_of_link = 'bug/5';
            this.widget = this._createWidget(true);
            Y.Assert.isInstanceOf(
                Y.lp.bugs.duplicates.DuplicateBugPicker,
                this.widget,
                "Mark bug duplicate picker failed to be instantiated");
            Y.Assert.isFalse(this.widget.get('visible'));
            Y.one('.pick-bug').simulate('click');
            Y.Assert.isTrue(this.widget.get('visible'));
            var remove_dupe = Y.one('.yui3-bugpickerwidget a.remove');
            Y.Assert.isFalse(remove_dupe.hasClass('hidden'));
        },

        // Attempt to make a bug as a duplicate of itself is detected and an
        // error is displayed immediately.
        test_mark_bug_as_dupe_of_self: function() {
            this.widget = this._createWidget(false);
            Y.one('.pick-bug').simulate('click');
            this.mockio.last_request = null;
            Y.one('.yui3-picker-search').set('value', '1');
            Y.one('.lazr-search').simulate('click');
            Y.Assert.isNull(this.mockio.last_request);
            this._assert_error_display(
                'A bug cannot be marked as a duplicate of itself.');
            this._assert_form_state(false);
        },

        // Attempt to make a bug as a duplicate of it's existing dupe is
        // detected and an error is displayed immediately.
        test_mark_bug_as_dupe_of_existing_dupe: function() {
            this.widget = this._createWidget(false);
            Y.one('.pick-bug').simulate('click');
            this.mockio.last_request = null;
            window.LP.cache.bug.duplicate_of_link
                = 'file:///api/devel/bugs/4';
            Y.one('.yui3-picker-search').set('value', '4');
            Y.one('.lazr-search').simulate('click');
            Y.Assert.isNull(this.mockio.last_request);
            this._assert_error_display(
                'This bug is already marked as a duplicate of bug 4.');
            this._assert_form_state(false);
        },

        // A warning is displayed for search results which are not targeted to
        // the same project.
        test_different_pillars: function() {
            this.widget = this._createWidget(false);
            this.different_pillars = true;
            this._assert_search_form_submission(4);
            this._assert_search_form_success(4);
            var privacy_message = Y.one('#different-project-warning');
            Y.Assert.areEqual(
                'This bug affects a different project to the bug ' +
                'you are specifying here.',
                privacy_message.get('text').trim());
        },

        // Submitting a bug dupe works as expected.
        test_picker_form_submission_success: function() {
            this.widget = this._createWidget(false);
            this._assert_dupe_submission(3);
            var success_called = false;
            this.widget._submit_bug_success =
                function(response, new_dup_url, new_dup_id,
                         new_dup_title) {
                    Y.Assert.areEqual(
                        '<table>New Table</table>', response.responseText);
                    Y.Assert.areEqual('api/devel/bugs/3', new_dup_url);
                    Y.Assert.areEqual(3, new_dup_id);
                    Y.Assert.areEqual('dupe title', new_dup_title);
                    success_called = true;
                };
            this.mockio.success({
                responseText: '<table>New Table</table>',
                responseHeaders: {'Content-Type': 'text/html'}
            });
            Y.Assert.isTrue(success_called);
        },

        // A submission failure is handled as expected.
        test_picker_form_submission_failure: function() {
            this.widget = this._createWidget(false);
            this._assert_dupe_submission(3);
            var failure_called = false;
            this.mockio.respond({
                status: 400,
                responseText:
                    '{"error_summary": "There is 1 error.",' +
                    '"errors":' +
                    '{"field.duplicateof": "There was an error"}, ' +
                    '"form_wide_errors": []}',
                responseHeaders: {'Content-Type': 'application/json'}});
            var error = this.widget.get('error');
            Y.Assert.areEqual('There was an error', error);
        },

        // Submitting a dupe removal request works as expected.
        test_picker_form_submission_remove_dupe: function() {
            this.widget = this._createWidget(false);
            var success_called = false;
            this.widget._submit_bug_success =
                function(response, new_dup_url, new_dup_id,
                         new_dupe_title) {
                    Y.Assert.areEqual(
                        response.responseText, '<table>New Table</table>');
                    Y.Assert.areEqual(null, new_dup_url);
                    Y.Assert.areEqual('', new_dup_id);
                    success_called = true;
                };
            Y.one('.yui3-bugpickerwidget a.remove').simulate('click');
            this.mockio.success({
                responseText: '<table>New Table</table>',
                responseHeaders: {'Content-Type': 'text/html'}
            });
            Y.Assert.isTrue(success_called);
        },

        // The mark bug duplicate success function works as expected.
        test_submit_bug_success: function() {
            this.widget = this._createWidget(false);
            var response = {
                responseText: '<table id="affected-software">' +
                    '<tbody><tr><td>Bug tasks</td></tr></tbody></table>',
                responseHeaders: {'Content-Type': 'text/html'}};
            this.widget._submit_bug_success(
                response, 'api/devel/bugs/3', 3, 'dupe title');
            // Test the updated bug entry.
            Y.Assert.areEqual(
                'api/devel/bugs/3', LP.cache.bug.duplicate_of_link);
            // Test the Change Duplicate link.
            Y.Assert.isNotNull(Y.one('#mark-duplicate-text a'));
            // Test the duplicate warning message.
            var dupe_warning = Y.one('#warning-comment-on-duplicate');
            Y.Assert.isNotNull(dupe_warning);
            Y.Assert.areEqual(
                'Remember, this bug report is a duplicate of bug #3.' +
                'Comment here only if you think the duplicate status ' +
                'is wrong.',
                dupe_warning.get('text').trim());
            // The duplicate info message
            Y.Assert.isNotNull(
                Y.one('#bug-is-duplicate span.bug-duplicate-details'));
            // Any previously listed duplicates are removed.
            Y.Assert.isNull(Y.one('#portlet-duplicates'));
            // The bug dupe table is updated.
            Y.Assert.areEqual(
                'Bug tasks', Y.one('#affected-software').get('text'));
        },

        // The remove bug duplicate success function works as expected.
        test_remove_bug_duplicate_success: function() {
            this.widget = this._createWidget(true);
            var response = {
                responseText: '<table id="affected-software">' +
                    '<tbody><tr><td>Bug tasks</td></tr></tbody></table>',
                responseHeaders: {'Content-Type': 'text/html'}};
            this.widget._submit_bug_success(response, null, '');
            // Test the updated bug entry.
            Y.Assert.isNull(LP.cache.bug.duplicate_of_link);
            // Test the Mark as Duplicate link.
            Y.Assert.isNotNull(
                Y.one('#mark-duplicate-text .menu-link-mark-dupe'));
            // Test the duplicate warning message is gone.
            Y.Assert.isNull(Y.one('#warning-comment-on-duplicate'));
            // The duplicate info message is gone.
            Y.Assert.isNull(
                Y.one('#bug-is-duplicate p.bug-duplicate-details'));
            // The bug dupe table is updated.
            Y.Assert.areEqual(
                'Bug tasks', Y.one('#affected-software').get('text'));
        }
    })));

}, '0.1', {
    requires: [
        'test', 'lp.testing.helpers', 'event', 'node-event-simulate',
        'test-console', 'lp.client', 'lp.testing.mockio', 'lp.anim',
        'lp.bugs.bug_picker', 'lp.bugs.duplicates',
        'lp.bugs.bug_picker.test', 'lp.bugs.bugtask_index']
});
