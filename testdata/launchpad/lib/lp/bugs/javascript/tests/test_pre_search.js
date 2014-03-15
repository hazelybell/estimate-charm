/* Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.bugs.bugtask_index.test_pre_search', function (Y) {
    var module = Y.lp.bugs.bugtask_index;
    // Local aliases
    var Assert = Y.Assert,
        ArrayAssert = Y.ArrayAssert;

    // A picker implementation that records method calls for testing.
    function FauxPicker() {
        this.events = [];
    }

    FauxPicker.prototype.get = function(name) {
        this.events.push('get ' + name);
        return 47;
    };

    FauxPicker.prototype.set = function(name, value) {
        this.events.push('set ' + name + ' = ' + value);
    };

    FauxPicker.prototype.fire = function(name, value) {
        this.events.push('fire ' + name + ' with ' + value);
    };

    var tests = Y.namespace('lp.bugs.bugtask_index.test_pre_search');
    tests.suite = new Y.Test.Suite('Pre Search Tests');
    tests.suite.add(new Y.Test.Case({

        name: 'pre_search',

        /**
         * A loading message is added to the footer slot.
         */
        test_loading_message: function() {
            picker = new FauxPicker();
            module._do_pre_search(picker, 'BUG-ID');
            ArrayAssert.contains(
                'set footer_slot = Loading suggestions...',
                picker.events);
        },

        /**
         * Because some bug numbers are short strings, the minimum search
         * character limit has to be set to zero and then reset to its original
         * value.
         */
        test_min_search_length: function() {
            picker = new FauxPicker();
            module._do_pre_search(picker, 'BUG-ID');
            ArrayAssert.contains(
                'get min_search_chars',
                picker.events);
            ArrayAssert.contains(
                'set min_search_chars = 47',
                picker.events);
        },

        /**
         * After the search event is fired, search_mode has to be (immediately)
         * disbled so the user can enter a search.
         */
        test_disable_search_mode: function() {
            picker = new FauxPicker();
            module._do_pre_search(picker, 'BUG-ID');
            ArrayAssert.contains(
                'fire search with BUG-ID',
                picker.events);
            ArrayAssert.contains(
                'set search_mode = false',
                picker.events);
        }

    }));

}, '0.1', {
    requires: ['test', 'lp.testing.helpers', 'test-console', 'event',
    'lp.bugs.bugtask_index', 'lp.client', 'node', 'widget-stack']
});
