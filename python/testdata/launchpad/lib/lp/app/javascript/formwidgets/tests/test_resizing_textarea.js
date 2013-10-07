/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.resizing_textarea.test', function (Y) {

    var tests = Y.namespace('lp.resizing_textarea.test');
    tests.suite = new Y.Test.Suite('resizing_textarea Tests');

    var test_text = ["Lorem ipsum dolor sit amet, consectetur adipiscing.",
        "Maecenas ut viverra nibh. Morbi sit amet tellus accumsan justo ",
        "blandit sit amet ac augue. Pellentesque eget diam at purus suscipit",
        "venenatis. Proin non neque lacus. Curabitur venenatis tempus sem, ",
        "porttitor magna fringilla vel. Cras dignissim egestas lacus nec",
        "hendrerit. Proin pharetra, felis ac auctor dapibus, neque orci ",
        "lorem, sit amet posuere erat quam euismod arcu. Nulla pharetra ",
        "enim tempus faucibus. Sed dictum tristique nisl sed rhoncus. Etiam ",
        "tristique nisl eget risus blandit iaculis. Lorem ipsum dolor sit ,",
        "consectetur adipiscing elit."].join("");

    /**
     * Helper function to turn the string from getComputedStyle to int.
     *
     */
    function clean_size(val) {
        return parseInt(val.replace('px', ''), 10);
    }

    /**
     * Helper to extract the computed height of the element.
     *
     */
    function get_height(target) {
        return clean_size(target.getComputedStyle('height'));
    }

    /**
     * In order to update the content we need to change the text, but also to
     * fire the event that the content has changed since we're modifying it
     * programatically.
     *
     */
    function update_content(target, val) {
        target.set('value', val);

        // Instead of hitting the changed event directly, we'll just manually
        // call into the hook for the event itself.
        target.resizing_textarea._run_change(val);
    }

    tests.suite.add(new Y.Test.Case({
        name: 'resizing_textarea_tests',

        setUp: function () {},
        tearDown: function () {},

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.app.formwidgets.ResizingTextarea,
                "Could not locate the " +
                "lp.app.formwidgets.ResizingTextarea module");
        },

        test_initial_resizable: function() {
            var target = Y.one('#init');

            Y.Assert.areEqual('Initial text', target.get('value'));

            target.plug(Y.lp.app.formwidgets.ResizingTextarea, {
                skip_animations: true
            });

            // Get the current sizes so we can pump text into it and make sure
            // it grows.
            var orig_height = get_height(target);
            update_content(target, test_text);

            var new_height = get_height(target);
            Y.Assert.isTrue(new_height > orig_height,
                "The height should increase with content");

        },

        test_max_height: function() {
            var target = Y.one('#with_defaults');

            target.plug(Y.lp.app.formwidgets.ResizingTextarea, {
                skip_animations: true,
                max_height: 200,
                min_height: 100
            });

            var min_height = get_height(target);
            Y.Assert.areSame(100, min_height,
                "The height should be no smaller than 100px");

            update_content(target, test_text);

            var new_height = get_height(target);
            Y.Assert.areSame(200, new_height,
                "The height should only get to 200px");
        },

        test_removing_content: function() {
            var target = Y.one('#shrinkage');

            target.plug(Y.lp.app.formwidgets.ResizingTextarea, {
                skip_animations: true,
                min_height: 100
            });

            update_content(target, test_text);
            var max_height = get_height(target);
            Y.Assert.isTrue(max_height > 100,
                "The height should be larger than our min with content");

            update_content(target, "shrink");

            var min_height = get_height(target);
            Y.Assert.areSame(100, min_height,
                "The height should shrink back to our min");
        },

        test_multiple: function() {
            var target = Y.all('.test_multiple');

            target.plug(Y.lp.app.formwidgets.ResizingTextarea, {
                skip_animations: true,
                min_height: 100
            });

            target.each(function(node) {
                var min_height = get_height(node);
                Y.Assert.areSame(100, min_height,
                    "The height of the node should be 100");
            });

            // Now set the content in the first one and check it's unique.
            update_content(Y.one('.first'), test_text);

            var first = Y.one('.first');
            var second = Y.one('.second');

            var first_height = get_height(first);
            Y.Assert.isTrue(first_height > 100,
                "The height of the first should now be > 100");

            var second_height = get_height(second);
            Y.Assert.areSame(100, second_height,
                "The height of the second should still be 100");
        },

        test_css_height_preset: function() {
            var target = Y.one('#css_height');

            target.plug(Y.lp.app.formwidgets.ResizingTextarea, {
                skip_animations: true
            });

            var current_height = get_height(target);
            Y.Assert.areSame(120, current_height,
                "The height should match the css property at 120px");
        },

        test_initial_min_height_after_hidden: function() {
            // If we pass in a min height, the text area should resize on init
            // to that min height.
            var target = Y.one('#config_height');
            target.plug(Y.lp.app.formwidgets.ResizingTextarea, {
                skip_animations: true,
                min_height: 300
            });

            target.show();
            var current_height = get_height(target);
            Y.Assert.areSame(300, current_height,
                "The height should start out at 300px per the min_height cfg");
        },

        test_height_stays_consistant: function () {
            // Once we adjust the height, another keystroke shouldn't move the
            // height on us again, see bug #919299.
            var target = Y.one('#no_change');
            target.plug(Y.lp.app.formwidgets.ResizingTextarea, {
                skip_animations: true,
                max_height: 200,
                min_height: 100
            });

            update_content(target, test_text);
            var new_height = get_height(target);
            Y.Assert.areSame(200, new_height,
                "The height should hit max at 200px");

            update_content(target, test_text + "3");
            var adjusted_height = get_height(target);
            Y.Assert.areSame(200, adjusted_height,
                "The height should still be at 200px");

            update_content(target, test_text + "34");
            var adjusted_height2 = get_height(target);
            Y.Assert.areSame(200, adjusted_height2,
                "The height should still be at 200px");
        },

        test_oneline_should_size_to_single_em: function() {
            // Passing a one line in the cfg should limit the height to 1em even
            // though a normal textarea would be two lines tall.
            var sample_height = get_height(Y.one('#one_line_sample')),
                target = Y.one('#one_line');

            target.plug(Y.lp.app.formwidgets.ResizingTextarea, {
                skip_animations: true,
                single_line: true
            });

            var initial_height = get_height(target);
            Y.Assert.areSame(sample_height, initial_height,
                "The initial height should be 1em");

            // After adding a bunch of text and removing it, we should be back
            // at one em height.
            update_content(target, test_text);
            Y.Assert.isTrue(get_height(target) > initial_height,
                'Verify that we did change the height');

            update_content(target, "");
            Y.Assert.areSame(sample_height, get_height(target),
                "The updated final height should be 1em");
        }

    }));

}, '0.1', {'requires': ['test', 'test-console', 'plugin', 'event-valuechange',
    'node-event-simulate', 'event', 'node',
    'lp.app.formwidgets.resizing_textarea']});
