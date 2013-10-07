/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.app.choice.test', function (Y) {

    // Shortcut to the namespace we're testing against.
    var choice = Y.namespace('lp.app.choice');

    var tests = Y.namespace('lp.app.choice.test');
    tests.suite = new Y.Test.Suite('app.choice Tests');

    tests.suite.add(new Y.Test.Case({
        name: 'app.choice_tests',

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.app.choice,
                "Could not locate the lp.app.choice module");
        }
    }));


    tests.suite.add(new Y.Test.Case({
        name: 'radio_popup_choice',

        _should: {
            error: {
                test_error_undefined_data: true,
                test_error_empty_array: true
            }
        },

        setUp: function () {
            window.LP = {
                cache: {
                    context: {
                        web_link: ''
                    },
                    information_type_data: {
                        PUBLIC: {
                            value: 'PUBLIC', name: 'Public',
                            is_private: false, order: 1,
                            description: 'Public Description'
                        },
                        PUBLICSECURITY: {
                            value: 'PUBLICSECURITY', name: 'Public Security',
                            is_private: false, order: 2,
                            description: 'Public Security Description'
                        },
                        PROPRIETARY: {
                            value: 'PROPRIETARY', name: 'Proprietary',
                            is_private: true, order: 3,
                            description: 'Private Description'
                        },
                        USERDATA: {
                            value: 'USERDATA', name: 'Private',
                            is_private: true, order: 4,
                            description: 'Private Description'
                        }
                    }
                }
            };
        },

        tearDown: function () {
            window.LP = {};
        },

        test_error_undefined_data: function () {
            // An exception should be raised if you create a button with
            // undefined options.
            choice.addPopupChoiceForRadioButtons('information_type',
                                                 undefined);
        },

        test_error_empty_array: function () {
            // An exception should be raised if you create a button with no
            // options.
            choice.addPopupChoiceForRadioButtons('information_type',
                                                 []);
        }
    }));

}, '0.1', {
    requires: ['test', 'test-console', 'lp.app.choice']
});
