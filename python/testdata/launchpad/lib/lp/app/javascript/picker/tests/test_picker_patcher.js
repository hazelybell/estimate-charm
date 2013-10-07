/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.app.picker.test', function (Y) {

    var tests = Y.namespace('lp.app.picker.test');
    var Assert = Y.Assert;
    tests.suite = new Y.Test.Suite('picker patcher Tests');

    /*
     * A wrapper for the Y.Event.simulate() function.  The wrapper accepts
     * CSS selectors and Node instances instead of raw nodes.
     */
    function simulate(widget, selector, evtype, options) {
        var rawnode = Y.Node.getDOMNode(widget.one(selector));
        Y.Event.simulate(rawnode, evtype, options);
    }

    /* Helper function to clean up a dynamically added widget instance. */
    function cleanup_widget(widget) {
        // Nuke the boundingBox, but only if we've touched the DOM.
        if (widget.get('rendered')) {
            var bb = widget.get('boundingBox');
            bb.get('parentNode').removeChild(bb);
        }
        // Kill the widget itself.
        widget.destroy();
        var data_box = Y.one('#picker_id .yui3-activator-data-box');
        var link = data_box.one('a');
        if (link) {
            link.get('parentNode').removeChild(link);
        }
    }

    tests.suite.add(new Y.Test.Case({
        name: 'picker_yesyno_validation',

        setUp: function() {
            this.vocabulary = [
                {"value": "fred", "title": "Fred", "css": "sprite-person",
                    "description": "fred@example.com", "api_uri": "~/fred",
                    "metadata": "person"},
                {"value": "frieda", "title": "Frieda", "css": "sprite-team",
                    "description": "frieda@example.com", "api_uri": "~/frieda",
                    "metadata": "team"}
            ];
            this.picker = null;
            this.text_input = null;
            this.select_menu = null;
            this.saved_picker_value = null;
            this.validation_namespace =
                Y.namespace('lp.app.picker.validation');
        },

        tearDown: function() {
            if (this.select_menu !== null) {
                Y.one('body').removeChild(this.select_menu);
                }
            if (this.text_input !== null) {
                Y.one('body').removeChild(this.text_input);
                }
            if (this.picker !== null) {
                cleanup_widget(this.picker);
                }
            this.validation_namespace.show_picker_id = undefined;
        },

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.app.picker,
                "Could not locate the lp.app.picker module");
        },

        create_picker: function(validate_callback, extra_config) {
            var config = {
                    "use_animation": false,
                    "step_title": "Choose someone",
                    "header": "Pick Someone",
                    "null_display_value": "No one",
                    "show_widget_id": "show_picker_id",
                    "validate_callback": validate_callback
            };
            if (extra_config !== undefined) {
               config = Y.merge(extra_config, config);
            }
            this.picker = Y.lp.app.picker.addPickerPatcher(
                this.vocabulary,
                "foo/bar",
                "test_link",
                "picker_id",
                config);
            var self = this;
            this.picker.subscribe('save', function(e) {
                self.saved_picker_value =
                     e.details[Y.lp.ui.picker.Picker.SAVE_RESULT].api_uri;
            });
        },

        create_picker_direct: function(associated_field) {
            this.picker = Y.lp.app.picker.create(
                this.vocabulary,
                {use_animation: false},
                associated_field);
            var self = this;
            this.picker.subscribe('save', function(e) {
                 self.saved_picker_value =
                     e.details[Y.lp.ui.picker.Picker.SAVE_RESULT].api_uri;
            });
        },

        test_picker_can_be_instantiated: function() {
            // The picker can be instantiated.
            this.create_picker();
            Assert.isInstanceOf(
                Y.lp.ui.picker.Picker, this.picker,
                "Picker failed to be instantiated");
        },

        // A validation callback stub. Instead of going to the server to see if
        // a picker value requires confirmation, we compare it to a known value.
        yesno_validate_callback: function(expected_value) {
            return function(picker, value, save_fn, cancel_fn) {
                Assert.areEqual(
                    expected_value,
                    value.api_uri, "unexpected picker value");
                if (value === null) {
                    return true;
                }
                var requires_confirmation = value.api_uri !== "~/fred";
                if (requires_confirmation) {
                    var yesno_content = "<p>Confirm selection</p>";
                    Y.lp.app.picker.yesno_save_confirmation(
                            picker, yesno_content, "Yes", "No",
                            save_fn, cancel_fn);
                } else {
                    save_fn();
                }
            };
        },

        test_no_confirmation_required: function() {
            // The picker saves the selected value if no confirmation
            // is required.
            this.create_picker(this.yesno_validate_callback("~/fred"));
            this.picker.set('results', this.vocabulary);
            this.picker.render();

            simulate(
                this.picker.get('boundingBox').one('.yui3-picker-results'),
                    'li:nth-child(1)', 'click');
            Assert.areEqual('~/fred', this.saved_picker_value);
        },

        test_TextFieldPickerPlugin_selected_item_is_saved: function () {
            // The picker saves the selected value to its associated
            // textfield if one is defined.
            this.text_input = Y.Node.create(
                    '<input id="field.testfield" value="foo" />');
            Y.one(document.body).appendChild(this.text_input);
            this.create_picker_direct('field.testfield');
            this.picker.set('results', this.vocabulary);
            this.picker.render();
            var got_focus = false;
            this.text_input.on('focus', function(e) {
                got_focus = true;
            });
            simulate(
                this.picker.get('boundingBox').one('.yui3-picker-results'),
                    'li:nth-child(2)', 'click');
            Assert.areEqual(
                'frieda', Y.one('[id="field.testfield"]').get("value"));
            Assert.areEqual('team', this.picker.get('selected_value_metadata'));
            Assert.isTrue(got_focus, "focus didn't go to the search input.");
        },

        test_navigation_renders_after_results: function () {
            // We modify the base picker to show the batch navigation below the
            // picker results.
            this.create_picker();
            this.picker.set('results', this.vocabulary);
            var results_box = this.picker._results_box;
            var batch_box = this.picker._batches_box;
            Assert.areEqual(results_box.next(), batch_box);
        },

        test_extra_no_results_message: function () {
            // If "extra_no_results_message" is defined, it is rendered in the
            // footer slot when there are no results.
            this.create_picker(
                undefined, {'extra_no_results_message': 'message'});
            this.picker.set('results', []);
            var footer_slot = this.picker.get('footer_slot');
            Assert.areEqual('message', footer_slot.get('text'));
        },

        test_footer_node_preserved_without_extra_no_results_message:
            function () {
            // If "extra_no_results_message" is not defined, the footer slot
            // node should be preserved.
            this.create_picker();
            var footer_node = Y.Node.create("<span>foobar</span>");
            this.picker.set('footer_slot', footer_node);
            this.picker.set('results', []);
            var footer_slot = this.picker.get('footer_slot');
            Assert.areEqual('foobar', footer_slot.get('text'));
        },

        test_confirmation_yes: function() {
            // The picker saves the selected value if the user answers
            // "Yes" to a confirmation request.
            // The validator is specified using the picker's config object.
            this.create_picker(this.yesno_validate_callback("~/frieda"));
            this.picker.set('results', this.vocabulary);
            this.picker.render();

            simulate(
                this.picker.get('boundingBox').one('.yui3-picker-results'),
                    'li:nth-child(2)', 'click');
            var yesno = this.picker.get('contentBox')
                .one('.extra-form-buttons');

            simulate(
                    yesno, 'button:nth-child(1)', 'click');
            Assert.areEqual('~/frieda', this.saved_picker_value);
        },

        test_confirmation_yes_namespace_validator: function() {
            // The picker saves the selected value if the user answers
            // "Yes" to a confirmation request.
            // The validator is specified using the validation namespace.
            this.validation_namespace.show_picker_id =
                [this.yesno_validate_callback("~/frieda")];

            this.create_picker();
            this.picker.set('results', this.vocabulary);
            this.picker.render();

            simulate(
                this.picker.get('boundingBox').one('.yui3-picker-results'),
                    'li:nth-child(2)', 'click');
            var yesno = this.picker.get('contentBox')
                .one('.extra-form-buttons');

            simulate(
                    yesno, 'button:nth-child(1)', 'click');
            Assert.areEqual('~/frieda', this.saved_picker_value);
        },

        test_confirmation_no: function() {
            // The picker doesn't save the selected value if the user answers
            // "No" to a confirmation request.
            this.create_picker(this.yesno_validate_callback("~/frieda"));
            this.picker.set('results', this.vocabulary);
            this.picker.render();

            simulate(
                this.picker.get('boundingBox').one('.yui3-picker-results'),
                    'li:nth-child(2)', 'click');
            var yesno = this.picker.get('contentBox')
                .one('.extra-form-buttons');
            simulate(
                yesno, 'button:nth-child(2)', 'click');
            Assert.isNull(this.saved_picker_value);
        },

        // Helper function for multiple (2) validators.
        choose_all_yes: function() {
            simulate(
                this.picker.get('boundingBox').one('.yui3-picker-results'),
                    'li:nth-child(2)', 'click');
            var yesno = this.picker.get('contentBox')
                .one('.extra-form-buttons');
            // Click the Yes button.
            simulate(yesno, 'button:nth-child(1)', 'click');
            yesno = this.picker.get('contentBox').one('.extra-form-buttons');
            // Click the Yes button.
            simulate(yesno, 'button:nth-child(1)', 'click');
            Assert.areEqual('~/frieda', this.saved_picker_value);
        },

        test_multi_validators_config_and_ns_all_yes: function() {
            // Set up a picker with 2 validators, one via the config and one via
            // the namespace.

            // The picker saves the selected value if the user answers
            // "Yes" to all confirmation request.
            this.validation_namespace.show_picker_id =
                this.yesno_validate_callback("~/frieda");
            this.create_picker(this.yesno_validate_callback("~/frieda"));
            this.picker.set('results', this.vocabulary);
            this.picker.render();
            this.choose_all_yes();
        },

        test_multi_validators_via_ns_all_yes: function() {
            // Set up a picker with 2 validators, both configured via the
            // namespace.

            // The picker saves the selected value if the user answers
            // "Yes" to all confirmation request.
            this.validation_namespace.show_picker_id = [
                this.yesno_validate_callback("~/frieda"),
                this.yesno_validate_callback("~/frieda")
                ];
            this.create_picker();
            this.picker.set('results', this.vocabulary);
            this.picker.render();
            this.choose_all_yes();
        },

        test_multi_validators_via_config_all_yes: function() {
            // Set up a picker with 2 validators, both configured via the picker
            // config.

            // The picker saves the selected value if the user answers
            // "Yes" to all confirmation request.
            var validators = [
                this.yesno_validate_callback("~/frieda"),
                this.yesno_validate_callback("~/frieda")
                ];
            this.create_picker(validators);
            this.picker.set('results', this.vocabulary);
            this.picker.render();
            this.choose_all_yes();
        },

        test_chained_validators_one_no: function() {
            // The picker doesn't save the selected value if the user answers
            // "No" to any one of the confirmation requests.
            this.validation_namespace.show_picker_id = [
                this.yesno_validate_callback("~/frieda"),
                this.yesno_validate_callback("~/frieda")];

            this.create_picker();
            this.picker.set('results', this.vocabulary);
            this.picker.render();

            simulate(
                this.picker.get('boundingBox').one('.yui3-picker-results'),
                    'li:nth-child(2)', 'click');
            var yesno = this.picker.get('contentBox')
                .one('.extra-form-buttons');
            // Click the Yes button.
            simulate(yesno, 'button:nth-child(1)', 'click');
            yesno = this.picker.get('contentBox').one('.extra-form-buttons');
            // Click the No button.
            simulate(yesno, 'button:nth-child(2)', 'click');
            Assert.isNull(this.saved_picker_value);
        },

        test_connect_select_menu: function() {
            // connect_select_menu() connects the select menu's onchange event
            // to copy the selected value to the text input field.
            this.text_input = Y.Node.create(
                    '<input id="field.testfield" value="foo" />');
            var node = Y.one(document.body).appendChild(this.text_input);
            this.select_menu = Y.Node.create(
                '<select id="field.testfield-suggestions"> ' +
                '    <option value="">Did you mean...</option>' +
                '    <option value="fnord">Fnord Snarf (fnord)</option>' +
                '</select>');
            Y.one('body').appendChild(this.select_menu);
            var select_menu = Y.DOM.byId('field.testfield-suggestions');
            var text_input = Y.DOM.byId('field.testfield');
            Y.lp.app.picker.connect_select_menu(select_menu, text_input);
            select_menu.selectedIndex = 1;
            Y.Event.simulate(select_menu, 'change');
            Assert.areEqual(
                'fnord', text_input.value,
                "Select menu's onchange handler failed.");
        },

        test_privacy_warning: function () {
            //tests that the specific public_private warning version of yesno
            //works.
            var overridden_privacy_callback = function (
                picker, value, save_fn, cancel_fn) {
                window.LP = { cache: {} };
                LP.cache.context = { private: false };
                Y.lp.client.Launchpad = function() {};
                Y.lp.client.Launchpad.prototype.get = function(uri, config) {
                    var person = {
                        get: function (key) {
                            return true;
                        }
                    };
                    config.on.success(person);
                };

                Y.lp.app.picker.public_private_warning(
                    picker, value, save_fn, cancel_fn);
            };

            this.create_picker(overridden_privacy_callback);
            this.picker.set('results', this.vocabulary);
            this.picker.render();

            simulate(
                this.picker.get('boundingBox').one('.yui3-picker-results'),
                    'li:nth-child(2)', 'click');
            // expected_text is a little weird since breaks between p tags and
            // buttons are lost.
            var expected_text =
                'This action will reveal this team\'s name to ' +
                'the public.ContinueChoose Again';
            var text = Y.one(".validation-node").get('text');
            Assert.areEqual(expected_text, text);
        }

    }));

    /*
     * Test cases for a picker with a large vocabulary.
     */
    tests.suite.add(new Y.Test.Case({

        name: 'picker_large_vocabulary',

        setUp: function() {
            var i;
            this.vocabulary = new Array(121);
            for (i = 0; i < 121; i++) {
                this.vocabulary[i] = {
                    "value": "value-" + i,
                    "title": "title-" + i,
                    "css": "sprite-person",
                    "description": "description-" + i,
                    "api_uri": "~/fred-" + i};
            }
        },

        tearDown: function() {
            cleanup_widget(this.picker);
        },

        create_picker: function(show_search_box, extra_config) {
            var config = {
                "step_title": "Choose someone",
                "header": "Pick Someone",
                "validate_callback": null
                };
            if (show_search_box !== undefined) {
                config.show_search_box = show_search_box;
            }
            if (extra_config !== undefined) {
               config = Y.merge(extra_config, config);
            }
            this.picker = Y.lp.app.picker.addPickerPatcher(
                    this.vocabulary,
                    "foo/bar",
                    "test_link",
                    "picker_id",
                    config);
        },

        test_filter_options_initialisation: function() {
            // Filter options are correctly used to set up the picker.
            this.picker = Y.lp.app.picker.create(
                this.vocabulary, undefined, undefined, ['a', 'b', 'c']);
            Y.ArrayAssert.itemsAreEqual(
                ['a', 'b', 'c'], this.picker.get('filter_options'));
        },

        test_picker_displays_empty_list: function() {
            // With too many results, the results will be empty.
            this.create_picker(true);
            this.picker.render();
            this.picker.set('min_search_chars', 0);
            this.picker.fire('search', '');
            var result_text = this.picker.get('contentBox')
                .one('.yui3-picker-results').get('text');
            Assert.areEqual('', result_text);
        },

        test_picker_displays_warning: function() {
            // With a search box the picker will refuse to display more than
            // 120 values.
            this.create_picker(true);
            this.picker.set('min_search_chars', 0);
            this.picker.fire('search', '');
            Assert.areEqual(
                'Too many matches. Please try to narrow your search.',
                this.picker.get('error'));
        },

        test_picker_displays_warning_by_default: function() {
            // If show_search_box is not supplied in config, it defaults to
            // true. Thus the picker will refuse to display more than 120
            // values.
            this.create_picker();
            this.picker.set('min_search_chars', 0);
            this.picker.fire('search', '');
            Assert.areEqual(
                'Too many matches. Please try to narrow your search.',
                this.picker.get('error'));
        },

        test_picker_no_warning: function() {
            // Without a search box the picker will also display more than
            // 120 values.
            this.create_picker(false);
            this.picker.set('min_search_chars', 0);
            this.picker.fire('search', '');
            Assert.areEqual(null, this.picker.get('error'));
        },

        test_vocab_filter_config: function () {
            // The vocab filter config is correctly used to create the picker.
            var filters = [{name: 'ALL', title: 'All', description: 'All'}];
            this.create_picker(undefined,  {'vocabulary_filters': filters});
            var filter_options = this.picker.get('filter_options');
            Assert.areEqual(filters, filter_options);
        }
    }));

    tests.suite.add(new Y.Test.Case({

        name: 'picker_error_handling',

        setUp: function() {
            this.create_picker();
            this.picker.fire('search', 'foo');
        },

        tearDown: function() {
            cleanup_widget(this.picker);
        },

        create_picker: function() {
            this.mock_io = new Y.lp.testing.mockio.MockIo();
            this.picker = Y.lp.app.picker.addPickerPatcher(
                "Foo",
                "foo/bar",
                "test_link",
                "picker_id",
                {yio: this.mock_io});
        },

        get_oops_headers: function(oops) {
            var headers = {};
            headers['X-Lazr-OopsId'] = oops;
            return headers;
        },

        test_oops: function() {
            // A 500 (ISE) with an OOPS ID informs the user that we've
            // logged it, and gives them the OOPS ID.
            this.mock_io.failure(
                {responseHeaders: this.get_oops_headers('OOPS')});
            Assert.areEqual(
                "Sorry, something went wrong with your search. " +
                "We've recorded what happened, and we'll fix it as soon " +
                "as possible. (Error ID: OOPS)",
                this.picker.get('error'));
        },

        test_timeout: function() {
            // A 503 (timeout) or 502/504 (proxy error) informs the user
            // that they should retry, and gives them the OOPS ID.
            this.mock_io.failure(
                {status: 503, responseHeaders: this.get_oops_headers('OOPS')});
            Assert.areEqual(
                "Sorry, something went wrong with your search. Trying again " +
                "in a couple of minutes might work. (Error ID: OOPS)",
                this.picker.get('error'));
        },

        test_other_error: function() {
            // Any other type of error just displays a generic failure
            // message, with no OOPS ID.
            this.mock_io.failure({status: 400});
            Assert.areEqual(
                "Sorry, something went wrong with your search.",
                this.picker.get('error'));
        }
    }));

    tests.suite.add(new Y.Test.Case({

        name: 'picker_automated_search',

        create_picker: function(yio) {
            var config = {yio: yio};
            return Y.lp.app.picker.addPickerPatcher(
                "Foo",
                "foo/bar",
                "test_link",
                "picker_id",
                config);
        },

        make_response: function(status, oops, responseText) {
            if (oops === undefined) {
                oops = null;
            }
            return {
                status: status,
                responseText: responseText,
                getResponseHeader: function(header) {
                    if (header === 'X-Lazr-OopsId') {
                        return oops;
                    }
                }
            };
        },

        test_automated_search_results_ignored_if_user_has_searched: function() {
            // If an automated search (like loading branch suggestions) returns
            // results and the user has submitted a search, then the results of
            // the automated search are ignored so as not to confuse the user.
            var mock_io = new Y.lp.testing.mockio.MockIo();
            var picker = this.create_picker(mock_io);
            // First an automated search is run.
            picker.fire('search', 'guess', undefined, true);
            // Then the user initiates their own search.
            picker.fire('search', 'test');
            // Two requests have been sent out.
            Y.Assert.areEqual(2, mock_io.requests.length);
            // Respond to the automated request.
            mock_io.requests[0].respond({responseText: '{"entries": 1}'});
            // ... the results are ignored.
            Assert.areNotEqual(1, picker.get('results'));
            // Respond to the user request.
            mock_io.requests[1].respond({responseText: '{"entries": 2}'});
            Assert.areEqual(2, picker.get('results'));
            cleanup_widget(picker);
        },

        test_automated_search_error_ignored_if_user_has_searched: function() {
            // If an automated search (like loading branch suggestions) returns
            // an error and the user has submitted a search, then the error
            // from the automated search is ignored so as not to confuse the
            // user.
            var mock_io = new Y.lp.testing.mockio.MockIo();
            var picker = this.create_picker(mock_io);
            picker.fire('search', 'test');
            picker.fire('search', 'guess', undefined, true);
            mock_io.failure();
            Assert.areEqual(null, picker.get('error'));
            cleanup_widget(picker);
        }

    }));

}, '0.1', {'requires': ['test', 'test-console', 'lp.app.picker', 'node',
        'event-focus', 'event-simulate', 'lp.ui.picker-base',
        'lp.ui.picker-person', 'lp.app.picker', 'node-event-simulate',
        'escape', 'event', 'lp.testing.mockio', 'lp', 'lp.client']});
