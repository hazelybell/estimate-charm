/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.formoverlay.test', function (Y) {

    var tests = Y.namespace('lp.formoverlay.test');
    var Assert = Y.Assert;
    tests.suite = new Y.Test.Suite('formoverlay Tests');

    /*
     * A wrapper for the Y.Event.simulate() function.  The wrapper accepts
     * CSS selectors and Node instances instead of raw nodes.
     */
    function simulate(widget, selector, evtype, options) {
        var rawnode = Y.Node.getDOMNode(widget.one(selector));
        Y.Event.simulate(rawnode, evtype, options);
    }

    /* Helper function to cleanup and destroy a form overlay instance */
    function cleanup_form_overlay(form_overlay) {
        if (form_overlay.get('rendered')) {
            var bb = form_overlay.get('boundingBox');
            if (Y.Node.getDOMNode(bb)){
                bb.get('parentNode').removeChild(bb);
            }
        }

        // Kill the widget itself.
        form_overlay.destroy();
    }

    /* Helper function that creates a new form overlay instance. */
    function make_form_overlay(cfg) {
        var form_overlay = new Y.lp.ui.FormOverlay(cfg);
        form_overlay.render();
        return form_overlay;
    }

    tests.suite.add(new Y.Test.Case({
        name: 'formoverlay_basics',

        setUp: function() {
            this.form_overlay = make_form_overlay({
                headerContent: 'Form for testing',
                form_content: [
                    'Here is an input: ',
                    '<input type="text" name="field1" id="field1" />',
                    'Here is another input: ',
                    '<input type="text" name="field2" id="field2" />'].join(""),
                xy: [0, 0]
            });

            // Ensure window size is constant for tests
            this.width = window.top.outerWidth;
            this.height = window.top.outerHeight;
            window.top.resizeTo(800, 600);
        },

        tearDown: function() {
            window.top.resizeTo(this.width, this.height);
            cleanup_form_overlay(this.form_overlay);
        },

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.ui.FormOverlay,
                "Could not locate the lp.ui.FormOverlay module");
        },

        test_form_overlay_can_be_instantiated: function() {
            var overlay = new Y.lp.ui.FormOverlay();
            Assert.isInstanceOf(
                Y.lp.ui.FormOverlay,
                overlay,
                "Form overlay could not be instantiated.");
            cleanup_form_overlay(overlay);
        },

        test_body_content_is_single_node: function() {
            Assert.areEqual(
                1,
                new Y.NodeList(this.form_overlay.getStdModNode("body")).size(),
                "The body content should be a single node, not a node list.");
        },

        test_form_content_in_body_content: function() {
            // The form_content should be included in the body of the
            // overlay during initialization.
            var body_content = this.form_overlay.getStdModNode("body");

            // Ensure the body_content contains our form node.
            Assert.isTrue(
                body_content.contains(this.form_overlay.form_node),
                "The form node is part of the body content.");

            // And then make sure that the user-supplied form_content is
            // included in the form node:
            Assert.areNotEqual(
                body_content.get("innerHTML").search(
                    this.form_overlay.get("form_content")));
        },

        test_first_input_has_focus: function() {
            // The first input element in the form content should have
            // focus.
            var first_input = this.form_overlay.form_node.one('#field1');

            // Hide the overlay and ensure that the first input does not
            // have the focus.
            this.form_overlay.hide();
            first_input.blur();

            var test = this;
            var focused = false;

            var onFocus = function(e) {
                focused = true;
            };

            first_input.on('focus', onFocus);

            this.form_overlay.show();
            Assert.isTrue(focused,
                "The form overlay's first input field receives focus " +
                "when the overlay is shown.");
        },

        test_close_button_has_focus: function() {
            // The close button has focus if the form is not loaded,
            // or the form is removed.
            this.form_overlay.form_node.empty();
            var close_button = this.form_overlay.get(
                'boundingBox').one('.close-button');
            var focused = false;
            close_button.on('focus', function(e) {
                focused = true;
            });
            this.form_overlay.hide();
            close_button.blur();
            this.form_overlay.show();
            Assert.isTrue(focused, "The close-button was not focused.");
        },
        test_focusChild_form_with_hidden_inputs: function() {
            // When focusing a form element, the method skips non-visible
            // form elements
            this.form_overlay.form_node.empty();
            this.form_overlay.form_node.append(
                '<input type="hidden" name="a" />' +
                '<input type="text" name="b" style="display:none" />' +
                '<input type="text" name="c" id="c" />'
                );
            var visible_input = this.form_overlay.get('boundingBox').one('#c');
            var focused = false;
            visible_input.on('focus', function(e) {
                focused = true;
            });
            this.form_overlay._focusChild();
            Assert.isTrue(focused, "The visble input was not focused.");
        },

        test_form_submit_in_body_content: function() {
            // The body content should include the submit button.
            var body_content = this.form_overlay.getStdModNode("body");
            Assert.isTrue(
                body_content.contains(
                    this.form_overlay.get("form_submit_button")),
                "The body content includes the form_submit_button.");
        },

        test_users_submit_button_in_body_content: function() {
            // If a user supplies a custom submit button, it should be included
            // in the form instead of the default one.
            var submit_button = Y.Node.create(
                '<input type="submit" value="Hit me!" />');
            var form_overlay = new Y.lp.ui.FormOverlay({
                form_content: 'Here is an input: ' +
                              '<input type="text" name="field1" id="field1" />',
                form_submit_button: submit_button
            });
            form_overlay.render();

            // Ensure the button has been used in the form:
            Assert.isTrue(
                form_overlay.form_node.contains(submit_button),
                "The form should include the users submit button.");

            cleanup_form_overlay(form_overlay);
        },

        test_form_cancel_in_body_content: function() {
            // The body content should include the cancel button.
            var body_content = this.form_overlay.getStdModNode("body");
            Assert.isTrue(
                body_content.contains(
                    this.form_overlay.get("form_cancel_button")),
                "The body content includes the form_cancel_button.");
        },

        test_users_cancel_button_in_body_content: function() {
            // If a user supplies a custom cancel button, it should be included
            // in the form instead of the default one.
            var cancel_button = Y.Node.create(
                '<button type="" value="cancel" />');
            var form_overlay = new Y.lp.ui.FormOverlay({
                form_content: 'Here is an input: ' +
                              '<input type="text" name="field1" id="field1" />',
                form_cancel_button: cancel_button
            });
            form_overlay.render();

            // Ensure the button has been used in the form:
            Assert.isTrue(
                form_overlay.form_node.contains(cancel_button),
                "The form should include the users cancel button.");

            cleanup_form_overlay(form_overlay);
        },

        test_hide_when_cancel_clicked: function() {
            // The form overlay should hide when the cancel button is clicked.

            var bounding_box = this.form_overlay.get('boundingBox');
            Assert.isFalse(
                bounding_box.hasClass('yui3-lazr-formoverlay-hidden'),
                "The form is not hidden initially.");

            simulate(
                this.form_overlay.form_node,
                "button[type=button]",
                'click');

            Assert.isTrue(
                bounding_box.hasClass('yui3-lazr-formoverlay-hidden'),
                "The form is hidden after cancel is clicked.");
        },

        test_error_displayed_on_showError: function() {
            // The error message should be in the body content.

            this.form_overlay.showError("My special error");

            var body_content = this.form_overlay.getStdModNode("body");
            Assert.areNotEqual(
                body_content.get("innerHTML").search("My special error"),
                -1,
                "The error text was included in the body content.");
        },

        test_tags_stripped_from_errors: function() {
            // Any tags in error messages will be stripped out.
            // That is, as long as they begin and end with ascii '<' and '>'
            // chars. Not sure what to do about unicode, for eg.
            this.form_overlay.showError("<h2>My special error</h2>");

            var body_content = this.form_overlay.getStdModNode("body");
            Assert.areEqual(
                -1,
                body_content.get("innerHTML").search("<h2>"),
                "The tags were stripped from the error message.");
        },

        test_error_cleared_on_clearError: function() {
            // The error message should be cleared from the body content.
            this.form_overlay.showError("My special error");
            this.form_overlay.clearError();
            var body_content = this.form_overlay.getStdModNode("body");
            Assert.areEqual(
                body_content.get("innerHTML").search("My special error"),
                -1,
                "The error text is cleared from the body content.");
        },

        test_form_overlay_centered_when_shown: function() {
            // If the 'centered' attribute is set, the overlay should be
            // centered in the viewport when shown.
            Assert.areEqual('[0, 0]', Y.dump(this.form_overlay.get('xy')),
                            "Position is initially 0,0.");
            this.form_overlay.show();
            Assert.areEqual('[0, 0]', Y.dump(this.form_overlay.get('xy')),
                            "Position is not updated if widget not centered.");
            this.form_overlay.hide();

            this.form_overlay.set('centered', true);
            this.form_overlay.show();
            var centered_pos_before_resize = this.form_overlay.get('xy');
            Assert.areNotEqual('[0, 0]', Y.dump(centered_pos_before_resize),
                               "Position is updated when centered attr set.");
            this.form_overlay.hide();

            var centered = false;
            function watch_centering() {
                centered = true;
            }
            Y.Do.after(watch_centering, this.form_overlay, 'centered');

            // The position is updated after resizing the window and re-showing:
            window.top.resizeTo(850, 550);
            this.form_overlay.show();

            Assert.isTrue(centered,
                "The overlay centers itself when it is shown with the " +
                "centered attribute set.");
        },

        test_destroy_on_hide: function() {
            this.destroy_form_overlay = make_form_overlay({
                destroy_on_hide: true,
                headerContent: 'Form for testing',
                form_content: [
                    'Here is an input: ',
                    '<input type="text" name="field1" id="field1" />',
                    'Here is another input: ',
                    '<input type="text" name="field2" id="field2" />'].join(""),
                xy: [0, 0]
            });

            var destroy_fired = false;
            var onDestroy = function(e) {
                destroy_fired = true;
            };
            this.destroy_form_overlay.on('destroy', onDestroy);

            this.destroy_form_overlay.hide();

            Assert.isTrue(
                destroy_fired,
                "The destroy event should have been fired.");
        }

    }));

    tests.suite.add(new Y.Test.Case({

        name: 'form_overlay_data',

        test_submit_callback_called_on_submit: function() {
            // Set an expectation that the form_submit_callback will be
            // called with the correct data:
            var callback_called = false;
            var submit_callback = function(ignore){
                callback_called = true;
            };
            var form_overlay = make_form_overlay({
                form_content:
                    '<input type="text" name="field1" value="val1" />',
                form_submit_callback: submit_callback
            });
            simulate(
                form_overlay.form_node,
                "input[type=submit]",
                'click');

            Assert.isTrue(
                callback_called,
                "The form_submit_callback should be called.");
            cleanup_form_overlay(form_overlay);
        },

        test_submit_with_callback_prevents_propagation: function() {
            // The onsubmit event is not propagated when user provides
            // a callback.

            var form_overlay = make_form_overlay({
                form_content:
                    '<input type="text" name="field1" value="val1" />',
                form_submit_callback: function() {}
            });

            var event_was_propagated = false;
            var test = this;
            var onSubmit = function(e) {
                event_was_propagated = true;
                e.preventDefault();
            };
            Y.on('submit', onSubmit, form_overlay.form_node);

            simulate(form_overlay.form_node, "input[type=submit]", 'click');

            Assert.isFalse(
                event_was_propagated,
                "The onsubmit event should not be propagated.");
            cleanup_form_overlay(form_overlay);
        },

        test_submit_without_callback: function() {
            // The form should submit as a normal form if no callback
            // was provided.
            var form_overlay = make_form_overlay({
                form_content: '<input type="text" name="field1" value="val1" />'
            });

            var event_was_propagated = false;
            var test = this;
            var onSubmit = function(e) {
                event_was_propagated = true;
                e.preventDefault();
            };

            Y.on('submit', onSubmit, form_overlay.form_node);

            simulate(
                form_overlay.form_node,
                "input[type=submit]",
                'click');
            Assert.isTrue(event_was_propagated,
                          "The normal form submission event is propagated as " +
                          "normal when no callback is provided.");
            cleanup_form_overlay(form_overlay);
        },

        test_getFormData_returns_correct_data_for_simple_inputs: function() {
            // The getFormData method should return the values of simple
            // inputs correctly.

            var form_overlay = make_form_overlay({
                headerContent: 'Form for testing',
                form_content: [
                    'Here is an input: ',
                    '<input type="text" name="field1" value="val1" />',
                    '<input type="text" name="field2" value="val2" />',
                    '<input type="text" name="field3" value="val3" />'].join("")
            });
            Assert.areEqual(
                '{field1 => [val1], field2 => [val2], field3 => [val3]}',
                Y.dump(form_overlay.getFormData()),
                "The getFormData method returns simple input data correctly.");
            cleanup_form_overlay(form_overlay);
        },

        test_getFormData_returns_inputs_nested_several_levels: function() {
            // The getFormData method should return the values of inputs
            // even when they are several levels deep in the form node
            var form_overlay = make_form_overlay({
                headerContent: 'Form for testing',
                form_content: [
                    'Here is an input: ',
                    '<div>',
                    '  <input type="text" name="field1" value="val1" />',
                    '  <div>',
                    '    <input type="text" name="field2" value="val2" />',
                    '    <div>',
                    '      <input type="text" name="field3" value="val3" />',
                    '    </div>',
                    '  </div>',
                    '</div>'].join("")
            });

            Assert.areEqual(
                '{field1 => [val1], field2 => [val2], field3 => [val3]}',
                Y.dump(form_overlay.getFormData()),
                "The getFormData method returns simple input data correctly.");
            cleanup_form_overlay(form_overlay);

        },

        test_form_content_as_node: function() {
            // The form content can also be passed as a node, rather than
            // a string of HTML.
            var form_content_div = Y.Node.create("<div />");
            var input_node = Y.Node.create(
                '<input type="text" name="field1" value="val1" />');
            form_content_div.appendChild(input_node);

            var form_overlay = make_form_overlay({
                headerContent: 'Form for testing',
                form_content: form_content_div
                });

            Assert.isTrue(
                form_overlay.form_node.contains(input_node),
                "Failed to pass the form content as a Y.Node instance.");
            cleanup_form_overlay(form_overlay);
        },

        test_io_provider_default: function() {
            // If no io_provider is configured, the form will use Y.
            var form_overlay = make_form_overlay({});
            Assert.areSame(Y, form_overlay.get("io_provider"));
        },

        test_io_provider_mockio: function() {
            // If an io_provider is configured, the form will use that.
            var mock_io = new Y.lp.testing.mockio.MockIo(),
                form_overlay = make_form_overlay({
                    io_provider: mock_io
                });
            Assert.areSame(mock_io, form_overlay.get("io_provider"));
        },

        test_form_content_loaded_from_url_success: function() {
            // The form content can also be loaded from a URL, using
            // loadFormContentAndRender().
            var external_form_content = '<div id="loaded-content"></div>';

            var mock_io = new Y.lp.testing.mockio.MockIo();
            var form_overlay = make_form_overlay({
                headerContent: 'Form for testing',
                io_provider: mock_io
                });
            form_overlay.loadFormContentAndRender('http://example.com/form');

            // loadFormContentAndRender calls .io() to issue an XHR. Simulate a
            // successful response, to make sure that the form content gets
            // set and rendered.
            mock_io.success({responseText: external_form_content});

            Assert.areEqual(
                external_form_content, form_overlay.get('form_content'),
                "The form content wasn't loaded.");
            // Next we make sure that render was actually called by
            // checking the form content is present in the HTML.
            var form_node_text = form_overlay.form_node.get('innerHTML');
            Assert.areEqual(
                external_form_content,
                form_node_text.match(external_form_content),
                "Failed to render the form.");
            cleanup_form_overlay(form_overlay);
        },

        test_form_content_loaded_from_url_failure: function() {
            // If something goes wrong when loading the form contents, an
            // error message is displayed.
            var mock_io = new Y.lp.testing.mockio.MockIo();
            var form_overlay = make_form_overlay({
                headerContent: 'Form for testing',
                io_provider: mock_io
                });
            form_overlay.loadFormContentAndRender('http://example.com/form');

            // loadFormContentAndRender calls .io() to issue an XHR. Simulate a
            // failed response, to make sure that the error message gets set
            // and rendered.
            mock_io.failure();

            var error_message = "Sorry, an error occurred " +
                                "while loading the form.";
            Assert.areEqual(
                error_message, form_overlay.get('form_content'),
                "Failure to set form content.");
            var form_node_text = form_overlay.form_node.get('innerHTML');
            Assert.areEqual(
                error_message, form_node_text.match(error_message),
                "Failed to render the error message.");
            cleanup_form_overlay(form_overlay);
        },

        test_form_content_loaded_from_url_bind_submit: function() {
            // After the form content is loaded, the submit button is hooked
            // up to the supplied callback. The callback receibes the
            // io_provider.
            var callback_called = false,
                callback_io_provider;
            var submit_callback = function(ignore, io_provider){
                callback_called = true;
                callback_io_provider = io_provider;
            };
            var mock_io = new Y.lp.testing.mockio.MockIo();
            var form_overlay = make_form_overlay({
                headerContent: 'Form for testing',
                form_submit_callback: submit_callback,
                io_provider: mock_io
                });
            form_overlay.loadFormContentAndRender('http://example.com/form');

            // loadFormContentAndRender calls .io() to issue an XHR. Simulate a
            // successful response, to make sure that the submit button get
            // hooked up to the form_submit_call.
            var external_form_content = '<div id="loaded-content"></div>';
            mock_io.success({responseText: external_form_content});
            simulate(
                form_overlay.form_node,
                "input[type=submit]",
                'click');
            Assert.isTrue(callback_called,
                "Submit button didn't get hooked up.");
            Assert.areSame(mock_io, callback_io_provider);
            cleanup_form_overlay(form_overlay);
        }
    }));


}, '0.1', {'requires': ['test', 'test-console', 'lp.formoverlay',  'dump',
    'node', 'lp.ui.formoverlay', 'event', 'event-simulate',
    'lp.testing.mockio']});
