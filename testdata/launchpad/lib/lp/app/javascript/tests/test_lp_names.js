/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */
YUI.add('lp.names.test', function (Y) {
    var names = Y.lp.names;

    var tests = Y.namespace('lp.names.test');
    tests.suite = new Y.Test.Suite('LP Name Tests');

    /**
     * Test conversion of Launchpad names to CSS classes.
     */
    tests.suite.add(new Y.Test.Case({
        name: 'lp.names.launchpad_to_css() test',

        _should: {
            error: {
                test_not_lp_name_error:
                    'Passed value "~" is not a valid Launchpad name.',
                test_start_with_plus_error:
                    'Passed value "+name" is not a valid Launchpad name.',
                test_start_with_dot_error:
                    'Passed value ".name" is not a valid Launchpad name.',
                test_start_with_dash_error:
                    'Passed value "-name" is not a valid Launchpad name.'
            }
        },

        test_not_lp_name_error: function() {
            // Anything but a-z0-9+-. is not allowed in a LP name.
            // This triggers an exception.
            names.launchpad_to_css('~');
        },

        test_start_with_plus_error: function() {
            // Strings starting with plus character are
            // invalid LP names and throw an exception.
            names.launchpad_to_css('+name');
        },

        test_start_with_dot_error: function() {
            // Strings starting with dot character are
            // invalid LP names and throw an exception.
            names.launchpad_to_css('.name');
        },

        test_start_with_dash_error: function() {
            // Strings starting with dash character are
            // invalid LP names and throw an exception.
            names.launchpad_to_css('-name');
        },

        test_valid_in_both: function() {
            // If a name is both a valid LP name and CSS class name,
            // it is returned unmodified.
            var name = 'name123-today';
            var expected = name;
            Y.Assert.areEqual(expected,
                              names.launchpad_to_css(name));
        },

        test_starts_with_digits: function() {
            var name = '2name';
            var expected = '_2name';
            Y.Assert.areEqual(expected,
                              names.launchpad_to_css(name));
        },

        test_middle_digits: function() {
            // Digits in the middle and end of string are not touched.
            var name = 'na2me4';
            var expected = name;
            Y.Assert.areEqual(expected,
                              names.launchpad_to_css(name));
        },

        test_plus_sign: function() {
            // Plus sign is allowed in the Launchpad name, but
            // not in the CSS class name.  It is replaced with '_y'.
            var name = 'name+lastname';
            var expected = 'name_ylastname';
            Y.Assert.areEqual(expected,
                              names.launchpad_to_css(name));
        },

        test_multiple_pluses: function() {
            // Even multiple plus characters are replaced with '_y'.
            var name = 'name+middle+lastname';
            var expected = 'name_ymiddle_ylastname';
            Y.Assert.areEqual(expected,
                              names.launchpad_to_css(name));
        },

        test_dot_sign: function() {
            // Dot sign is allowed in the Launchpad name, but
            // not in the CSS class name.  It is replaced with '_z'.
            var name = 'name.lastname';
            var expected = 'name_zlastname';
            Y.Assert.areEqual(expected,
                              names.launchpad_to_css(name));
        },

        test_multiple_dots: function() {
            // Even multiple dot characters are replaced with '_z'.
            var name = 'name.middle.lastname';
            var expected = 'name_zmiddle_zlastname';
            Y.Assert.areEqual(expected,
                              names.launchpad_to_css(name));
        }
    }));

    /**
     * Test conversion of CSS class names as gotten by launchpad_to_css back
     * to Launchpad names.
     */
    tests.suite.add(new Y.Test.Case({
        name: 'lp.names.css_to_launchpad() test',

        _should: {
            error: {
                test_not_css_class_error:
                    'Passed value "+" is not a valid CSS class name.',
                test_start_with_digit_error:
                    'Passed value "1name" is not a valid CSS class name.',
                test_non_lp_converted_name_error:
                    'Passed value "_name" is not produced by launchpad_to_css.',
                test_non_lp_converted_name_error2:
                    'Passed value "na_me" is not produced by launchpad_to_css.'
            }
        },

        test_not_css_class_error: function() {
            // Anything but a-z0-9_-. is not allowed in a LP name.
            // This triggers an exception.
            names.css_to_launchpad('+');
        },

        test_start_with_digit_error: function() {
            // Strings starting with underscore are not valid CSS class names.
            names.css_to_launchpad('1name');
        },

        test_non_lp_converted_name_error: function() {
            // Strings which are otherwise valid CSS class names, but
            // could not be the result of the launchpad_to_css conversion
            // are rejected with an exception.
            names.css_to_launchpad('_name');
        },

        test_non_lp_converted_name_error2: function() {
            // Strings which are otherwise valid CSS class names, but
            // could not be the result of the launchpad_to_css conversion
            // are rejected with an exception.
            names.css_to_launchpad('na_me');
        },

        test_valid_in_both: function() {
            // If a name is both a valid LP name and CSS class name,
            // it is returned unmodified.
            var name = 'name123-today';
            var expected = name;
            Y.Assert.areEqual(expected,
                              names.css_to_launchpad(name));
        },

        test_starts_with_digits: function() {
            var name = '_2name';
            var expected = '2name';
            Y.Assert.areEqual(expected,
                              names.css_to_launchpad(name));
        },

        test_middle_digits: function() {
            // Digits in the middle and end of string are not touched.
            var name = 'na2me4';
            var expected = name;
            Y.Assert.areEqual(expected,
                              names.css_to_launchpad(name));
        },

        test_plus_sign: function() {
            // Plus sign is represented as '_y' in the CSS class name.
            var name = 'name_ylastname';
            var expected = 'name+lastname';
            Y.Assert.areEqual(expected,
                              names.css_to_launchpad(name));
        },

        test_multiple_pluses: function() {
            // Even multiple plus characters ('_y' strings) are handled.
            var name = 'name_ymiddle_ylastname';
            var expected = 'name+middle+lastname';
            Y.Assert.areEqual(expected,
                              names.css_to_launchpad(name));
        },

        test_dot_sign: function() {
            // Dot sign is represented as '_z' in the CSS class name.
            var name = 'name_zlastname';
            var expected = 'name.lastname';
            Y.Assert.areEqual(expected,
                              names.css_to_launchpad(name));
        },

        test_multiple_dots: function() {
            // Even multiple dot characters ('_z' strings) are handled.
            var name = 'name_zmiddle_zlastname';
            var expected = 'name.middle.lastname';
            Y.Assert.areEqual(expected,
                              names.css_to_launchpad(name));
        }
    }));

    /**
     * Test idempotency of css_to_launchpad(launchpad_to_css()).
     */
    tests.suite.add(new Y.Test.Case({
        name: 'Combined idempotency css_to_launchpad(launchpad_to_css()) test',

        test_simple_name: function() {
            var name = 'name';
            Y.Assert.areEqual(
                name,
                names.css_to_launchpad(names.launchpad_to_css(name)));
        },

        test_complex_name: function() {
            var name = '0+name.lastname-44-';
            Y.Assert.areEqual(
                name,
                names.css_to_launchpad(names.launchpad_to_css(name)));
        }
    }));

}, '0.1', {'requires': ['test', 'test-console', 'lp.names']});
