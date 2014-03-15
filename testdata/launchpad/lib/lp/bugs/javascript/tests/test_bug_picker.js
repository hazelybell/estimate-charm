/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.bugs.bug_picker.test', function (Y) {

    var tests = Y.namespace('lp.bugs.bug_picker.test');
    tests.suite = new Y.Test.Suite('lp.bugs.bug_picker Tests');

    tests.common_bug_picker_tests = {
        // The search form renders and submits the expected data.
        _assert_search_form_submission: function(bug_id) {
            Y.Assert.isFalse(this.widget.get('visible'));
            Y.one('.pick-bug').simulate('click');
            Y.Assert.isTrue(this.widget.get('visible'));
            Y.one('.yui3-picker-search').set('value', bug_id);
            Y.one('.lazr-search').simulate('click');
            if (bug_id !== '') {
                Y.Assert.areEqual(
                    'file:///api/devel/bugs',
                    this.mockio.last_request.url);
                var expected_data =
                    'ws.accept=application.json&ws.op=getBugData&' +
                    'bug_id=' + bug_id;
                if (Y.Lang.isValue(LP.cache.bug)) {
                    var bug_uri = encodeURIComponent('api/devel/bugs/1');
                    expected_data += '&related_bug=' + bug_uri;
                }
                Y.Assert.areEqual(
                    this.mockio.last_request.config.data, expected_data);
            } else {
                Y.Assert.areEqual(
                    '/api/devel/bugs/1', this.mockio.last_request.url);
            }
        },

        // The specified error message is displayed.
        _assert_error_display: function(message) {
            var error_msg = Y.one('.yui3-picker-error');
            Y.Assert.areEqual(message, error_msg.get('text').trim());
        },

        // The bug entry form is visible visible or not.
        _assert_form_state: function(bug_details_visible) {
            var bug_info = Y.one('.yui3-picker-results ' +
                    '.bug-details-node #client-listing');
            if (bug_details_visible) {
                Y.Assert.isNotNull(bug_info);
            } else {
                Y.Assert.isNull(bug_info);
            }
        },

        // Invoke a successful search operation and check the form state.
        _assert_search_form_success: function(bug_id) {
            var is_private = bug_id === 4;
            var expected_updated_entry = [{
                id: bug_id,
                uri: 'api/devel/bugs/' + bug_id,
                bug_summary: 'dupe title',
                is_private: is_private,
                duplicate_of_link: 'api/devel/bugs/' + bug_id,
                self_link: 'api/devel/bugs/' + bug_id,
                different_pillars: this.different_pillars}];
            this.mockio.last_request.successJSON(expected_updated_entry);
            this._assert_form_state(true);
        },

        // Attempt to enter an empty bug number and an error is displayed.
        test_no_bug_id_entered: function() {
            this.widget = this._createWidget();
            Y.one('.pick-bug').simulate('click');
            this.mockio.last_request = null;
            Y.one('.yui3-picker-search').set('value', '');
            Y.one('.lazr-search').simulate('click');
            Y.Assert.isNull(this.mockio.last_request);
            this._assert_error_display(
                'Please enter a valid bug number.');
            this._assert_form_state(false);
        },

        // A successful search for a bug displays the search results.
        test_initial_bug_search_success: function() {
            this.widget = this._createWidget();
            this._assert_search_form_submission(3);
            this._assert_search_form_success(3);
        },

        // No privacy warning when marking a bug as a dupe a public one.
        test_public_dupe: function() {
            this.widget = this._createWidget();
            this._assert_search_form_submission(3);
            this._assert_search_form_success(3);
            Y.Assert.isNull(Y.one('#privacy-warning'));
        },

        // Privacy warning when marking a public bug as a dupe of private one.
        test_public_bug_private_dupe: function() {
            this.widget = this._createWidget();
            this._assert_search_form_submission(4);
            this._assert_search_form_success(4);
            var privacy_message = Y.one('#privacy-warning');
            Y.Assert.areEqual(
                'You are selecting a private bug.',
                privacy_message.get('text').trim());
        },

        // No privacy warning when marking a private bug as a dupe of another
        // private bug.
        test_private_bug_private_dupe: function() {
            Y.one(document.body).addClass('private');
            this.widget = this._createWidget();
            this._assert_search_form_submission(4);
            this._assert_search_form_success(4);
            Y.Assert.isNull(Y.one('#privacy-warning'));
        },

        // After a successful search, hitting the Search button submits
        // a new search.
        test_initial_bug_search_try_again: function() {
            this.widget = this._createWidget();
            this._assert_search_form_submission(3);
            this._assert_search_form_success(3);
            Y.one('.lazr-search').simulate('click');
            this._assert_search_form_success(3);
        },

        // After a successful search, hitting the Save button fires a Save
        // event.
        test_save_bug: function() {
            this.widget = this._createWidget();
            this._assert_search_form_submission(3);
            this._assert_search_form_success(3);
            var save_bug_called = false;
            this.widget.subscribe(
                    Y.lp.bugs.bug_picker.BugPicker.SAVE,
                    function(e) {
                e.preventDefault();
                var bug_data = e.details[0];
                Y.Assert.areEqual(3, bug_data.id);
                Y.Assert.areEqual('dupe title', bug_data.bug_summary);
                save_bug_called = true;
            });
            Y.one(
                '.yui3-picker-footer-slot [name="field.actions.save"]')
                .simulate('click');
            this._assert_form_state(true);
            Y.Assert.isTrue(save_bug_called);
        },


        // The error is displayed as expected when the initial bug search
        // fails with a generic error.
        test_initial_bug_search_generic_failure: function() {
            this.widget = this._createWidget();
            this._assert_search_form_submission(3);
            var response = {
                status: 500,
                responseText: 'An error occurred'
            };
            this.mockio.respond(response);
            this._assert_error_display('An error occurred');
        },

        // The error is displayed as expected when the initial bug search
        // fails with an empty bug list.
        test_initial_bug_search_invalid_bug_failure: function() {
            this.widget = this._createWidget();
            this._assert_search_form_submission(3);
            this.mockio.last_request.successJSON([]);
            this._assert_error_display('3 is not a valid bug number.');
        },

        // Hitting the Remove button fires a Remove event.
        test_remove_bug: function() {
            this.widget = this._createWidget();
            var remove_bug_called = false;
            this.widget.subscribe(
                    Y.lp.bugs.bug_picker.BugPicker.REMOVE,
                    function(e) {
                e.preventDefault();
                remove_bug_called = true;
            });
            Y.one('.yui3-bugpickerwidget a.remove').simulate('click');
            Y.Assert.isTrue(remove_bug_called);
        }
    };

    tests.suite.add(new Y.Test.Case(Y.merge(
        tests.common_bug_picker_tests,
        {
        name: 'lp.bugs.bug_picker_tests',

        setUp: function () {
            window.LP = {
                links: {},
                cache: {
                    bug: {
                        id: 1,
                        self_link: 'api/devel/bugs/1'
                    }
                }
            };
            this.mockio = new Y.lp.testing.mockio.MockIo();
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
                "Could not locate the lp.bugs.bug_picker module");
        },

        _createWidget: function() {
            Y.one('#fixture').appendChild(
                Y.Node.create(Y.one('#bug-picker').getContent()));
            var widget = new Y.lp.bugs.bug_picker.BugPicker({
                io_provider: this.mockio,
                picker_activator: '.pick-bug',
                use_animation: false
            });
            widget.render();
            widget.hide();
            return widget;
        },

        // The widget is created when there are no bug duplicates.
        test_widget_creation: function() {
            this.widget = this._createWidget();
            Y.Assert.isInstanceOf(
                Y.lp.bugs.bug_picker.BugPicker,
                this.widget,
                "Bug picker failed to be instantiated");
            Y.Assert.isFalse(this.widget.get('visible'));
            Y.one('.pick-bug').simulate('click');
            Y.Assert.isTrue(this.widget.get('visible'));
        }
    })));

}, '0.1', {
    requires: [
        'test', 'lp.testing.helpers', 'event', 'node-event-simulate',
        'test-console', 'lp.client', 'lp.testing.mockio', 'lp.anim',
        'lp.ui.picker-base', 'lp.bugs.bug_picker', 'lp.mustache']
});
