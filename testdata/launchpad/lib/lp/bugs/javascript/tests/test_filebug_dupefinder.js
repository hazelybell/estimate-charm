/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */
YUI.add('lp.bugs.filebug_dupefinder.test', function (Y) {
    var module = Y.lp.bugs.filebug_dupefinder;

    /*
     * A wrapper for the Y.Event.simulate() function.  The wrapper accepts
     * CSS selectors and Node instances instead of raw nodes.
     */
    function simulate(widget, selector, evtype, options) {
        var node_to_use = widget;
        if (selector !== undefined) {
            node_to_use = widget.one(selector);
        }
        var rawnode = Y.Node.getDOMNode(node_to_use);
        Y.Event.simulate(rawnode, evtype, options);
    }

    /**
     * A stub io handler.
     */
    function IOStub(test_case){
        if (!(this instanceof IOStub)) {
            throw new Error("Constructor called as a function");
        }
        this.calls = [];
        this.io = function(url, config) {
            this.calls.push(url);
            var response = {responseText: ''};
            // We may have been passed text to use in the response.
            if (Y.Lang.isValue(arguments.callee.responseText)) {
                response.responseText = arguments.callee.responseText;
            }
            // We currently only support calling the success handler.
            config.on.success(undefined, response, arguments.callee.args);
            // After calling the handler, resume the test.
            if (Y.Lang.isFunction(arguments.callee.doAfter)) {
                test_case.resume(arguments.callee.doAfter);
            }
        };
    }

    // Configure the javascript module under test. In production, the
    // setup_dupe_finder() is called from the page template. We need to pass
    // in a stub io handler here so that the XHR call made during set up is
    // ignored.
    var config = {};
    config.yio = new IOStub();
    module.setup_config(config);
    module.setup_dupe_finder();

    var tests = Y.namespace('lp.bugs.filebug_dupefinder.test');
    tests.suite = new Y.Test.Suite('bugs.filebug_dupefinder Tests');

    tests.suite.add(new Y.Test.Case({
        name: 'Test filebug form manipulation.',

        setUp: function() {
            // Reset the HTML elements.
            Y.one("#possible-duplicates").set('innerHTML', '');
            Y.one(Y.DOM.byId('field.comment')).set('value', '');
            var node = Y.one(Y.DOM.byId('field.search'));
            if (node !== null) {
                node.set('value', '');
            }
            node = Y.one(Y.DOM.byId('field.title'));
            if (node !== null) {
                node.set('value', '');
            }
            Y.one('#filebug-form-container').addClass('transparent')
                    .setStyles({opacity: '0', display: 'none'});

            this.config = {};
            this.config.yio = new IOStub(this);
            module.setup_config(this.config);
        },

        tearDown: function() {
            Y.one('#filebug-form').set(
                    'action', 'https://bugs.launchpad.dev/foo/+filebug');
        },

        /**
         * Some helper functions
         */
        selectNode: function(node, selector) {
            if (!Y.Lang.isValue(node)) {
                node = Y.one('#test-root');
            }
            var node_to_use = node;
            if (Y.Lang.isValue(selector)) {
                node_to_use = node.one(selector);
            }
            return node_to_use;
        },

        assertIsVisible: function(node, selector) {
            node = this.selectNode(node, selector);
            Y.Assert.areNotEqual('none', node.getStyle('display'));
        },

        assertIsNotVisible: function(node, selector) {
            node = this.selectNode(node, selector);
            Y.Assert.areEqual('none', node.getStyle('display'));
        },

        assertNodeText: function(node, selector, text) {
            node = this.selectNode(node, selector);
            Y.Assert.areEqual(text, node.get('innerHTML'));
        },


        /**
         * A user first searches for duplicate bugs. If there are no duplicates
         * the file bug form should be visible for bug details to be entered.
         */
        test_no_dups_search_shows_filebug_form: function() {
            // filebug container should not initially be visible
            this.assertIsNotVisible(null, '#filebug-form-container');
            var search_text = Y.one(Y.DOM.byId('field.search'));
            search_text.set('value', 'foo');
            var search_button = Y.one(Y.DOM.byId('field.actions.search'));
            // The search button should initially say 'Next'
            Y.Assert.areEqual('Next', search_button.get('value'));
            this.config.yio.io.responseText = 'No similar bug reports.';
            this.config.yio.io.doAfter = function() {
                // Check the expected io calls have been made.
                Y.ArrayAssert.itemsAreEqual(
                    ['https://bugs.launchpad.dev/' +
                     'foo/+filebug-show-similar?title=foo'],
                    this.config.yio.calls);
                // filebug container should be visible after the dup search
                this.assertIsVisible(null, '#filebug-form-container');
                var dups_node = Y.one("#possible-duplicates");
                this.assertNodeText(
                        dups_node, undefined, 'No similar bug reports.');
            };
            simulate(search_button, undefined, 'click');
            this.wait();
        },

        /**
         * A user first searches for duplicate bugs. If there are duplicates
         * the dups should be listed and the file bug form should not be
         * visible.
         */
        test_dups_search_shows_dup_info: function() {
            // filebug container should not initially be visible
            this.assertIsNotVisible(null, '#filebug-form-container');
            var search_text = Y.one(Y.DOM.byId('field.search'));
            search_text.set('value', 'foo');
            var search_button = Y.one(Y.DOM.byId('field.actions.search'));
            this.config.yio.io.responseText = ([
                    '<table><tr><td id="bug-details-expander" ',
                    'class="bug-already-reported-expander"></td></tr></table>',
                    '<input type="button" value="No, I need to report a new',
                    ' bug" name="field.bug_already_reported_as"',
                    ' id="bug-not-already-reported" style="display: block">'
                    ].join(''));
            this.config.yio.io.doAfter = function() {
                // filebug container should not be visible when there are dups
                this.assertIsNotVisible(null, '#filebug-form-container');
                // we should have a 'new bug' button
                this.assertIsVisible(null, '#bug-not-already-reported');
                // The search button should say 'Check again'
                Y.Assert.areEqual('Check again', search_button.get('value'));
            };
            simulate(search_button, undefined, 'click');
            this.wait();
        },

        /**
         * A user first searches for duplicate bugs. They can start typing in
         * some detail. They can search again for dups and their input should
         * be retained.
         */
        test_dups_search_retains_user_input_when_no_dups: function() {
            // filebug container should not initially be visible
            this.assertIsNotVisible(null, '#filebug-form-container');
            var search_text = Y.one(Y.DOM.byId('field.search'));
            search_text.set('value', 'foo');
            var search_button = Y.one(Y.DOM.byId('field.actions.search'));
            this.config.yio.io.responseText = 'No similar bug reports.';
            this.config.yio.io.doAfter = function() {
                var comment_text = Y.one(Y.DOM.byId('field.comment'));
                comment_text.set('value', 'an error occurred');
                this.config.yio.io.doAfter = function() {
                    // The user input should be retained
                    Y.Assert.areEqual(
                        'an error occurred', comment_text.get('value'));
                };
                simulate(search_button, undefined, 'click');
                this.wait();
            };
            simulate(search_button, undefined, 'click');
            this.wait();
        },

        /**
         * A user first searches for duplicate bugs and there are none.
         * They can start typing in some detail. They can search again for dups
         * and their input should be retained even when there are dups and they
         * have to click the "No, this is a new bug" button.
         */
        test_dups_search_retains_user_input_when_dups: function() {
            // filebug container should not initially be visible
            this.assertIsNotVisible(null, '#filebug-form-container');
            var search_text = Y.one(Y.DOM.byId('field.search'));
            search_text.set('value', 'foo');
            var search_button = Y.one(Y.DOM.byId('field.actions.search'));
            this.config.yio.io.responseText = 'No similar bug reports.';
            this.config.yio.io.doAfter = function() {
                var comment_text = Y.one(Y.DOM.byId('field.comment'));
                comment_text.set('value', 'an error occurred');
                this.config.yio.io.responseText = ([
                        '<img id="bug-details-expander" ',
                        'class="bug-already-reported-expander" ',
                        'src="/@@/treeCollapsed">',
                        '<input type="button" value="No, I need to report a',
                        ' bug" name="field.bug_already_reported_as"',
                        ' id="bug-not-already-reported" style="display: block">'
                        ].join(''));
                this.config.yio.io.doAfter = function() {
                    var new_bug_button = Y.one('#bug-not-already-reported');
                    simulate(new_bug_button, undefined, 'click');
                    // filebug container should be visible
                    this.assertIsVisible(null, '#filebug-form-container');
                    // The user input should be retained
                    Y.Assert.areEqual(
                        'an error occurred', comment_text.get('value'));
                };
                simulate(search_button, undefined, 'click');
                this.wait();
            };
            simulate(search_button, undefined, 'click');
            this.wait();
        },

        /**
         * The filebug form url is correctly set when the page loads.
         */
        test_project_initial_filebug_form_action: function() {
            Y.Assert.areEqual(
                'https://bugs.launchpad.dev/foo/+filebug',
                Y.one('#filebug-form').get('action'));
        }

    }));


}, '0.1', {
    requires: ['test', 'lp.testing.helpers', 'test-console',
        'lp.bugs.filebug_dupefinder', 'node-event-simulate']
});
