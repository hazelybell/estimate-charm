/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.autocomplete.test', function (Y) {
    var tests = Y.namespace('lp.autocomplete.test');
    tests.suite = new Y.Test.Suite('autocomplete Tests');

    /*****************************
     *
     *  Helper methods and aliases
     *
     */
    var Assert = Y.Assert;

    /* Helper function to clean up a dynamically added widget instance. */
    function cleanup_widget(widget) {
        // Nuke the boundingBox, but only if we've touched the DOM.
        if (widget.get('rendered')) {
            var bb = widget.get('boundingBox');
            bb.get('parentNode').removeChild(bb);
        }
        // Kill the widget itself.
        widget.destroy();
    }

    /* A helper to create a simple text input box */
    function make_input(value) {
        var input = document.createElement('input');
        input.setAttribute('type', 'text');
        input.setAttribute('value', value || '');
        Y.one('body').appendChild(input);
        return input;
    }

    /* A helper to destroy a generic input: make_input()'s inverse */
    function kill_input(input) {
        Y.one('body').removeChild(input);
    }

    tests.suite.add(new Y.Test.Case({
        name:'test widget setup',

        setUp: function() {
            this.input = make_input();
        },

        tearDown: function() {
            kill_input(this.input);
        },

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.ui.AutoComplete,
                "Could not locate the lp.ui.autocomplete module");
        },

        test_widget_starts_hidden: function() {
            var autocomp = new Y.lp.ui.AutoComplete({ input: this.input });
            autocomp.render();
            Assert.isFalse(
                autocomp.get('visible'),
                "The widget should start out hidden.");
        }
    }));

    tests.suite.add(new Y.Test.Case({

        name:'test display of matching results',

        setUp: function() {
            this.input = make_input();
            this.autocomp = new Y.lp.ui.AutoComplete({
                input: this.input
            });
        },

        tearDown: function() {
            cleanup_widget(this.autocomp);
            kill_input(this.input);
        },

        /* A helper to option the completions list for a given input string. */
        complete_input: function(value) {
            this.input.value = value;
            var last_charcode = value.charCodeAt(value.length - 1);
            Y.Event.simulate(this.input, 'keyup', { keyCode: last_charcode });
        },

        /* Extract the matching text from the widget's autocompletion list. */
        get_completions: function() {
            if (!this.autocomp.get('rendered')) {
                Y.fail("Tried find matches for an unrendered widget.");
                return;
            }

            var matches = [];
            this.autocomp
                .get('boundingBox')
                .all('.item')
                .each(function(item) {
                    matches.push(item.get('text'));
                });
            return matches;
        },

        test_autocomplete_is_visible_if_results_match: function() {
            this.autocomp.set('data', ['aaa']);
            this.autocomp.render();

            // We want to match the one and only data set element.
            this.complete_input('aa');
            Assert.isTrue(
                this.autocomp.get('visible'),
                "The widget should be visible if matching input was found.");
        },

        test_autocomplete_is_hidden_if_no_query_is_given: function() {
            this.autocomp.set('data', ['aaa']);
            this.autocomp.render();

            // We want to simulate an empty input field, but some action
            // triggers matching.
            this.complete_input('');
            Assert.isFalse(
                this.autocomp.get('visible'),
                "The widget should be hidden if the input field is empty.");
        },

        test_autocomplete_is_hidden_if_results_do_not_match: function() {
            this.autocomp.set('data', ['bbb']);
            this.autocomp.render();

            if (this.autocomp.get('visible')) {
                Y.fail("The autocomplete widget should start out hidden.");
            }


            // 'aa' shouldn't match any of the data.
            this.complete_input('aa');
            Assert.isFalse(
                this.autocomp.get('visible'),
                "The widget should be hidden if the query doesn't match any " +
                "possible completions.");
        },

        test_display_should_contain_all_matches: function() {
            var data = [
                'aaa',
                'baa'
            ];

            this.autocomp.set('data', data);
            this.autocomp.render();

            // Trigger autocompletion, should match all data items.
            this.complete_input('aa');

            // Grab the now-open menu
            var option_list = Y.one('.yui3-autocomplete-list');
            Assert.isObject(option_list,
                "The list of completion options should be open.");

            Y.ArrayAssert.itemsAreEqual(
                this.get_completions(),
                data,
                "Every autocomplete item should be present in the available " +
                "match keys.");
        },

        test_display_is_updated_with_new_completions: function() {
            // Create two pieces of data, each narrower than the other.
            this.autocomp.set('data', ['aaa', 'aab']);
            this.autocomp.render();

            // Trigger autocompletion for the loosest matches
            this.complete_input('aa');
            // Complete the narrower set
            this.complete_input('aaa');

            var completions = this.get_completions();

            Y.ArrayAssert.itemsAreEqual(
                ['aaa'],
                completions,
                "'aaa' should be the data item displayed after narrowing the " +
                "search with the query 'aaa'.");
        },

        test_matching_text_in_item_is_marked: function() {
            this.autocomp.set('data', ['aaa']);
            this.autocomp.render();

            // Display the matching input.
            var query = 'aa';
            this.complete_input(query);

            // Grab the matching item
            var matching_text = this.autocomp
                .get('boundingBox')
                .one('.item .matching-text');

            Assert.isNotNull(matching_text,
                "Some of the matching item's text should be marked matching.");

            Assert.areEqual(
                query,
                matching_text.get('text'),
                "The matching text should be the same as the query text.");
        },

        test_escape_key_should_close_completions_list: function() {
            this.autocomp.set('data', ['aaa']);
            this.autocomp.render();

            // Open the completions list
            this.complete_input('aa');

            // Hit the escape key to close the list
            Y.Event.simulate(this.input, 'keydown', { keyCode: 27 });

            Assert.isFalse(
                this.autocomp.get('visible'),
                "The list of completions should be closed after pressing the " +
                "escape key.");
        }
    }));

    tests.suite.add(new Y.Test.Case({

        name:'test result text marking method',

        test_match_at_beginning_should_be_marked: function() {
            var autocomp    = new Y.lp.ui.AutoComplete();
            var marked_text = autocomp.markMatchingText('aabb', 'aa', 0);

            Assert.areEqual(
                '<span class="matching-text">aa</span>bb',
                marked_text,
                "The text at the beginning of the result should have been " +
                "marked.");
        },

        test_match_in_middle_should_be_marked: function() {
            var autocomp    = new Y.lp.ui.AutoComplete();
            var marked_text = autocomp.markMatchingText('baab', 'aa', 1);

            Assert.areEqual(
                'b<span class="matching-text">aa</span>b',
                marked_text,
                "The text in the middle of the result should have been " +
                "marked.");
        },

        test_match_at_end_should_be_marked: function() {
            var autocomp    = new Y.lp.ui.AutoComplete();
            var marked_text = autocomp.markMatchingText('bbaa', 'aa', 2);

            Assert.areEqual(
                'bb<span class="matching-text">aa</span>',
                marked_text,
                "The text at the end of the result should have been " +
                "marked.");
        }
    }));


    tests.suite.add(new Y.Test.Case({

        name:'test query parsing',

        setUp: function() {
            this.autocomplete = new Y.lp.ui.AutoComplete({
                delimiter: ' '
            });
        },

        test_space_for_delimiter: function() {
            Assert.areEqual(
                'b',
                this.autocomplete.parseQuery('a b').text,
                "Input should be split around the 'space' character.");
            Assert.isNull(
                this.autocomplete.parseQuery(' '),
                "Space for input and delimiter should not parse.");
        },

        test_parsed_query_is_stripped_of_leading_whitespace: function() {
            this.autocomplete.set('delimiter', ',');

            Assert.areEqual(
                'a',
                this.autocomplete.parseQuery(' a').text,
                "Leading whitespace at the start of the input string should " +
                "be stripped.");

            Assert.areEqual(
                'b',
                this.autocomplete.parseQuery('a, b').text,
                "Leading whitespace between the last separator and the " +
                "current query should be stripped.");
        },

        test_query_is_taken_from_middle_of_input: function() {
            // Pick a caret position that is in the middle of the second result.
            var input = "aaa bbb ccc";
            var caret = 6;

            Assert.areEqual(
                'bbb',
                this.autocomplete.parseQuery(input, caret).text,
                "The current query should be picked out of the middle of the " +
                "text input if the caret has been positioned there.");
        },

        test_query_is_taken_from_beginning_of_input: function() {
            // Pick a caret position that is in the first input's query
            var input = "aaa bbb";
            var caret = 2;

            Assert.areEqual(
                'aaa',
                this.autocomplete.parseQuery(input, caret).text,
                "The first block of text should become the current query if " +
                "the caret is positioned within it.");
        }
    }));

    tests.suite.add(new Y.Test.Case({

        name:'test results matching algorithm',

        /* A helper function to determine if two match result items are equal */
        matches_are_equal: function(a, b) {
            if (Y.Lang.isUndefined(a)) {
                Assert.fail("Match set 'a' is of type 'undefined'!");
            }
            if (Y.Lang.isUndefined(b)) {
                Assert.fail("Match set 'b' is of type 'undefined'!");
            }
            return (a.text === b.text) && (a.offset === b.offset);
        },

        test_no_matches_returns_an_empty_array: function() {
            var autocomplete = new Y.lp.ui.AutoComplete({
                data: ['ccc']
            });

            var matches = autocomplete.findMatches('aa');
            Y.ArrayAssert.isEmpty(matches,
                "No data should have matched the query 'aa'");
        },

        test_match_last_item: function() {
            var autocomplete = new Y.lp.ui.AutoComplete({
                data: [
                    'ccc',
                    'bbb',
                    'aaa'
                ]
            });

            var matches = autocomplete.findMatches('aa');

            Y.ArrayAssert.itemsAreEquivalent(
                [{text: 'aaa', offset: 0}],
                matches,
                this.matches_are_equal,
                "One row should have matched the query 'aa'.");
        },

        test_match_ordering: function() {
            // Matches, in reverse order.
            var autocomplete = new Y.lp.ui.AutoComplete({
                data: [
                    'bbaa',
                    'baab',
                    'aabb'
                ]
            });

            var matches = autocomplete.findMatches('aa');

            Y.ArrayAssert.itemsAreEquivalent(
                [{text: 'aabb', offset: 0},
                 {text: 'baab', offset: 1},
                 {text: 'bbaa', offset: 2}],
                matches,
                this.matches_are_equal,
                "The match array should have all of it's keys in order.");
        },

        test_mixed_case_text_matches: function() {
            var autocomplete = new Y.lp.ui.AutoComplete({
                data: ['aBc']
            });

            var matches = autocomplete.findMatches('b');

            Y.ArrayAssert.itemsAreEquivalent(
                [{text:'aBc', offset: 1}],
                matches,
                this.matches_are_equal,
                "The match algorithm should be case insensitive.");
        },

        test_mixed_case_matches_come_in_stable_order: function() {
            // Data with the mixed-case coming first in order.
            var autocomplete = new Y.lp.ui.AutoComplete({
                data: ['aBc', 'aaa', 'abc']
            });

            var matches = autocomplete.findMatches('b');

            Y.ArrayAssert.itemsAreEquivalent(
                [{text: 'aBc', offset: 1},
                 {text: 'abc', offset: 1}],
                matches,
                this.matches_are_equal,
                "Mixed-case matches should arrive in stable order.");
        }
    }));


    tests.suite.add(new Y.Test.Case({

        name:'test selecting results',

        setUp: function() {
            this.input = make_input();
            this.autocomp = new Y.lp.ui.AutoComplete({
                input: this.input
            });
            this.autocomp.render();
        },

        tearDown: function() {
            cleanup_widget(this.autocomp);
            kill_input(this.input);
        },

        // A helper to option the completions list for a given input string.
        complete_input: function(value) {
            this.input.value = value;
            var last_charcode = value.charCodeAt(value.length - 1);
            Y.Event.simulate(this.input, 'keyup', { keyCode: last_charcode });
        },

        // A helper to select the selected completion result with the Tab key.
        press_selection_key: function() {
            Y.Event.simulate(this.input, "keydown", { keyCode: 9 });
        },

        test_pressing_matching_key_raises_menu: function() {
            this.autocomp.set('data', ['aaaa', 'aabb']);
            this.complete_input('aa');
            var box = this.autocomp.get('boundingBox');
            Assert.areEqual(
                '31000',
                box.getStyle('z-index'),
                "The menu z-index should be 31000; above it's overlay.");
        },

        test_pressing_enter_completes_current_input: function() {
            this.autocomp.set('data', ['aaaa', 'aabb']);

            // Open the completion options
            this.complete_input('aa');

            // Press 'Enter'
            Y.Event.simulate(this.input, "keydown", { keyCode: 13 });

            Assert.areEqual(
                'aaaa ',
                this.input.value,
                "The first completion should have been appended to the " +
                "input's value after pressing the 'Enter' key.");
        },

        test_pressing_tab_completes_current_input: function() {
            this.autocomp.set('data', ['aaaa', 'aabb']);

            // Open the completion options
            this.complete_input('aa');

            // Press 'Tab'
            Y.Event.simulate(this.input, "keydown", { keyCode: 9 });

            Assert.areEqual(
                'aaaa ',
                this.input.value,
                "The first completion should have been appended to the " +
                "input's value after pressing the 'Enter' key.");
        },

        test_clicking_on_first_result_completes_input: function() {
            this.autocomp.set('data', ['aaaa', 'aabb']);
            this.complete_input('aa');

            // Click on the first displayed result
            var options = this.autocomp.get('contentBox').all('.item');
            var first_item = Y.Node.getDOMNode(options.item(0));
            Y.Event.simulate(first_item, 'click');

            Assert.areEqual(
                'aaaa ',
                this.input.value,
                "The first completion should have been appended to the " +
                "input's value after clicking it's list node.");
        },

        test_selecting_results_hides_completion_list: function() {
            this.autocomp.set('data', 'aaa');
            this.complete_input('a');
            this.press_selection_key();

            Assert.isFalse(
                this.autocomp.get('visible'),
                "The completion list should be hidden after a result is " +
                "selected.");
        },

        test_completed_input_replaces_current_input: function() {
            this.autocomp.set('data', ['abba']);

            // Match the one and only result, but match the second character in
            // it.  Throw in some pre-existing user input just to be sure things
            // work.
            this.complete_input('xxx b');
            this.press_selection_key();

            Assert.areEqual(
               'xxx abba ',
               this.input.value,
               "The user's current query should have been replaced with the " +
               "selected value.");
        },

        test_completed_input_has_delimiter_appended_to_it: function() {
            var delimiter = ' ';
            this.autocomp.set('data', ['aaaa']);
            this.autocomp.set('delimiter', delimiter);

            this.complete_input('a');
            this.press_selection_key();

            Assert.areEqual(
                delimiter,
                this.input.value.charAt(this.input.value.length - 1),
                "The last character of the input should be the current " +
                "query delimiter.");
        },

        test_down_arrow_selects_second_result_in_list: function() {
            this.autocomp.set('data', ['first_item', 'second_item']);

            // Match the first result.  It should be selected by default.
            this.complete_input('item');

            // Simulate pressing the down arrow key.
            Y.Event.simulate(this.input, 'keydown', { keyCode: 40 });

            // Now, select the second result.
            this.press_selection_key();

            Assert.areEqual(
                'second_item ',
                this.input.value,
                "Pressing the down-arrow key should select the second option " +
                "in the completions list.");
        }
    }));

}, '0.1', {
    'requires': ['test', 'test-console', 'lp.autocomplete', 'node', 'event',
        'event-simulate', 'lp.ui.autocomplete']
});
