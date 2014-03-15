/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.app.confirmationoverlay.test', function (Y) {

    var tests = Y.namespace('lp.app.confirmationoverlay.test');
    tests.suite = new Y.Test.Suite('app.confirmationoverlay Tests');

    var form_html = Y.one('#form-template').getContent();

    tests.suite.add(new Y.Test.Case({
        name: 'app.confirmationoverlay_tests',

        setUp: function() {
            Y.one("#placeholder")
                .empty()
                .append(Y.Node.create(form_html));
            this.button = Y.one('#submit');
            this.overlay = new Y.lp.app.confirmationoverlay.ConfirmationOverlay(
                {button: this.button});
        },

        tearDown: function() {
            this.overlay.destroy();
        },

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.app.confirmationoverlay,
                "Could not locate the lp.app.confirmationoverlay module");
        },

        test_button_set: function() {
            Y.ObjectAssert.areEqual(this.button, this.overlay.get('button'));
        },

        test_form_set: function() {
            var form = Y.one("#placeholder").one('form');
            Y.ObjectAssert.areEqual(form, this.overlay.get('submit_form'));
        },

        test_not_visible_by_default: function() {
            Y.Assert.isFalse(this.overlay.get('visible'));
        },

        test_shown_when_button_clicked: function() {
            this.button.simulate('click');
            Y.Assert.isTrue(this.overlay.get('visible'));
        },

        test_hidden_field_added_on_ok: function() {
            // When 'ok' (i.e. confirmation) is clicked, the Confirmation Overlay
            // adds an additional field to the form to simulate the click on the
            // right button.
            this.button.simulate('click');

            this.overlay.form_node.one('.ok-btn').simulate('click');
            var hidden_input = this.overlay.get(
                'submit_form').one('input.hidden-input');
            var real_input = this.overlay.get('submit_form').one('input#submit');

            Y.Assert.areEqual(
                real_input.get('name'),
                hidden_input.get('name'));
            Y.Assert.areEqual(
                real_input.get('value'),
                hidden_input.get('value'));
         },

        test_call_submit_on_ok: function() {
            // When 'ok' (i.e. confirmation) is clicked, the Confirmation Overlay
            // submits the form.
            // (Since we don't use YUI to make the request, we have to patch the
            // form object to test it's submission (and prevent the form to be
            // actually submitted.)
            this.button.simulate('click');

            var mockForm = Y.Mock();
            Y.Mock.expect(mockForm, {
                method: "submit"
            });
            Y.Mock.expect(mockForm, {
                method: "append",
                args: [Y.Mock.Value.Object]
            });
            this.overlay.set('submit_form', mockForm);
            this.overlay.form_node.one('.ok-btn').simulate('click');

            Y.Mock.verify(mockForm);
        }
    }));

    tests.suite.add(new Y.Test.Case({

        name: 'confirmation_overlay_content_functions',

        setUp: function() {
            Y.one("#placeholder")
                .empty()
                .append(Y.Node.create(form_html));
            this.button = Y.one('#submit');
            this.getTestContent = function() {
                return Y.one('span#test').get('text');
            };
            this.isTestNotEmpty = function() {
                return Y.one('span#test').get('text') !== '';
            };
            this.overlay = null;
         },

        tearDown: function() {
            // Each test is responsible for creating it's own overlay
            // but the cleanup is done in a centralized fashion.
            if (this.overlay !== null) {
                this.overlay.destroy();
            }
        },

        test_form_content_fn: function() {
            this.overlay = new Y.lp.app.confirmationoverlay.ConfirmationOverlay({
                button: this.button,
                form_content_fn: this.getTestContent
            });

            Y.one('span#test').set('innerHTML', 'random content');
            Y.Assert.areEqual('', this.overlay.get('form_content'));
            this.button.simulate('click');
            Y.Assert.areEqual('random content', this.overlay.get('form_content'));
        },

        test_header_content_fn: function() {
            this.overlay = new Y.lp.app.confirmationoverlay.ConfirmationOverlay({
                button: this.button,
                header_content_fn: this.getTestContent
            });

            Y.one('span#test').set('innerHTML', 'random content');
            Y.Assert.areEqual('', this.overlay.get('form_header'));
            this.button.simulate('click');
            Y.Assert.areEqual(
                'random content',
                this.overlay.get('headerContent').get('text').join(''));
        },

        test_do_not_display_fn: function() {
            // The parameter display_confirmation_fn can be used
            // to prevent the Confirmation Overlay from popping up.
            this.overlay = new Y.lp.app.confirmationoverlay.ConfirmationOverlay({
                button: this.button,
                display_confirmation_fn: this.isTestNotEmpty
            });

            // Hack the form to prevent real submission.
            Y.one('form').on('submit', function(e) {
                e.preventDefault();
            });

            Y.one('span#test').set('innerHTML', '');
            Y.Assert.isFalse(this.overlay.get('visible'));
            this.button.simulate('click');

            // The Overlay was not displayed.
            Y.Assert.isFalse(this.overlay.get('visible'));
        },

        test_callback_called: function() {
            // If submit_fn is passed to the constructor, call this function
            // when the 'ok' is clicked instead of submitting the form.
            var called = false;
            var callback = function() {
                called = true;
            };
            // Hack the form to record form submission.
            var form_submitted = false;
            Y.one('form').on('submit', function(e) {
                form_submitted = true;
                e.preventDefault();
            });

            this.overlay = new Y.lp.app.confirmationoverlay.ConfirmationOverlay({
                button: this.button,
                submit_fn: callback
            });
            this.button.simulate('click');
            Y.Assert.isTrue(this.overlay.get('visible'));
            this.overlay.form_node.one('.ok-btn').simulate('click');
            Y.Assert.isFalse(this.overlay.get('visible'));
            // The callback has been called.
            Y.Assert.isTrue(called);
            // The form has not been submitted.
            Y.Assert.isFalse(form_submitted);
        }

    }));

    tests.suite.add(new Y.Test.Case({

        name: 'confirmation_overlay_buttonless',

        tearDown: function() {
            if (this.overlay !== null) {
                this.overlay.destroy();
            }
        },

        test_callback_called: function() {
            // A ConfirmationOverlay can be constructed without passing a button.
            // The creator is responsible for calling show() manually.
            var called = false;
            var callback = function() {
                called = true;
            };

            this.overlay = new Y.lp.app.confirmationoverlay.ConfirmationOverlay({
                submit_fn: callback
            });
            Y.Assert.isFalse(this.overlay.get('visible'));
            this.overlay.show();
            Y.Assert.isTrue(this.overlay.get('visible'));
            this.overlay.form_node.one('.ok-btn').simulate('click');
            Y.Assert.isFalse(this.overlay.get('visible'));
            // The callback has been called.
            Y.Assert.isTrue(called);
        }

    }));

}, '0.1', {
    'requires': ['test', 'test-console', 'lp.app.confirmationoverlay',
        'dump', 'node', 'event', 'event-simulate', 'node-event-simulate']
});
