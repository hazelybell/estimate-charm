/* Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.buglisting_utils.test', function(Y) {

var buglisting_utils = Y.namespace('lp.buglisting_utils.test');

var suite = new Y.Test.Suite('BugListingConfigUtil Tests');

var Assert = Y.Assert;
var ArrayAssert = Y.ArrayAssert;
var ObjectAssert = Y.ObjectAssert;


var running_in_webkit = function() {
    // AppleWebKit/531 is the Lucid html5 test browser.
    // AppleWebKit/535 is Chromium 13-17 in Lucid through Oneric.
    return (/AppleWebKit.53[157]/).test(navigator.userAgent);
};


var buglisting_display_utils_tests = new Y.Test.Case({

    name: 'buglisting_display_utils_tests',

    _should: {ignore: []},


    setUp: function() {
        // Default values for model config.
        this.defaults = {
            field_visibility: {
                show_title: true,
                show_id: false,
                show_importance: false,
                show_status: true,
                show_information_type: false,
                show_heat: true,
                show_targetname: true,
                show_datecreated: false,
                show_date_last_updated: false,
                show_assignee: false,
                show_reporter: false,
                show_milestone_name: false,
                show_tag: false
            },

            field_visibility_defaults: {
                show_title: true,
                show_id: true,
                show_importance: true,
                show_status: true,
                show_information_type: false,
                show_heat: true,
                show_targetname: true,
                show_datecreated: false,
                show_date_last_updated: false,
                show_assignee: false,
                show_reporter: false,
                show_milestone_name: false,
                show_tag: false
            }
        };
        // _setDoc is required for tests using cookies to pass.
        if (running_in_webkit()){
            Y.Cookie._setDoc({cookie: ""});
        }
        // Simulate LP.cache.field_visibility which will be
        // present in the actual page.
        window.LP = {
            links: {
                me: '/~foobar'
            },

            cache: {
                cbl_cookie_name: 'foobar-buglist-fields'
            }
        };

        this.cookie_name = LP.cache.cbl_cookie_name;
    },

    tearDown: function() {
        if (Y.Lang.isValue(this.list_util)) {
            this.list_util.destroy();
        }
        // Cleanup cookies.
        Y.Cookie.remove(this.cookie_name, {path: "/"});
        if (running_in_webkit()){
            Y.Cookie._setDoc(Y.config.doc);
        }
        Y.lp.testing.helpers.reset_history();
    },

    /**
     * Test helper to see what the form actually looks
     * like on the page.
     *
     * It builds a list of show_xxx names and another
     * list of booleans representing checked value.
     */
    getActualInputData: function() {
        var actual_names = [];
        var actual_checked = [];
        var inputs = Y.one(
            '.yui3-lazr-formoverlay-content form').all('input');
        inputs.each(function(el) {
            if (el.get('type') === 'checkbox') {
                actual_names.push(el.get('name'));
                actual_checked.push(el.get('checked'));
            }
        });
        return [actual_names, actual_checked];
    },

    test_bug_listing_util_extends_base_util: function() {
        // BugListingConfigUtil extends from BaseConfigUtil.
        this.list_util = new Y.lp.buglisting_utils.BugListingConfigUtil();
        Assert.isInstanceOf(Y.lp.configutils.BaseConfigUtil, this.list_util);
    },

    test_cookie_name_attribute: function() {
        // cookie_name is taken from the cache.
        this.list_util = new Y.lp.buglisting_utils.BugListingConfigUtil();
        Assert.areEqual(this.cookie_name, this.list_util.get('cookie_name'));
    },

    test_field_visibility_form_reference: function() {
        // The form created from field_visibility defaults is referenced
        // via BugListingConfigUtil.get('form')
        this.list_util = new Y.lp.buglisting_utils.BugListingConfigUtil();
        Assert.isNotUndefined(this.list_util.get('form'));
    },

    test_field_visibility_form_shows_initial: function() {
        // The form should have a checkbox for every field_visibility item,
        // and the checked value should match true or false values.
        this.list_util = new Y.lp.buglisting_utils.BugListingConfigUtil(
            this.defaults);
        this.list_util.render();
        var expected_names = [
            'show_title',
            'show_id',
            'show_importance',
            'show_status',
            'show_information_type',
            'show_heat',
            'show_targetname',
            'show_datecreated',
            'show_date_last_updated',
            'show_assignee',
            'show_reporter',
            'show_milestone_name',
            'show_tag'
        ];
        var expected_checked = [
            true,
            false,
            false,
            true,
            false,
            true,
            true,
            false,
            false,
            false,
            false,
            false,
            false
        ];
        var actual_inputs = this.getActualInputData();
        ArrayAssert.itemsAreSame(expected_names, actual_inputs[0]);
        ArrayAssert.itemsAreSame(expected_checked, actual_inputs[1]);
    },

    test_field_visibility_form_shows_supplied_defaults: function() {
        // The form checkboxes should also match the user supplied
        // config values.
        var field_visibility = Y.merge(
            this.defaults.field_visibility_defaults, {
            show_status: false,
            show_heat: false
        });
        this.list_util = new Y.lp.buglisting_utils.BugListingConfigUtil({
            field_visibility: field_visibility,
            field_visibility_defaults: this.defaults.field_visibility_defaults
        });
        this.list_util.render();
        var expected_names = [
            'show_title',
            'show_id',
            'show_importance',
            'show_status',
            'show_information_type',
            'show_heat',
            'show_targetname',
            'show_datecreated',
            'show_date_last_updated',
            'show_assignee',
            'show_reporter',
            'show_milestone_name',
            'show_tag'
        ];
        var expected_checked = [
            true,
            true,
            true,
            false,
            false,
            false,
            true,
            false,
            false,
            false,
            false,
            false,
            false
        ];
        var actual_inputs = this.getActualInputData();
        ArrayAssert.itemsAreSame(expected_names, actual_inputs[0]);
        ArrayAssert.itemsAreSame(expected_checked, actual_inputs[1]);
    },

    test_click_icon_reveals_overlay: function() {
        // Clicking the settings icon should reveal the form overlay.
        this.list_util = new Y.lp.buglisting_utils.BugListingConfigUtil(
            this.defaults);
        this.list_util.render();
        var overlay = this.list_util.get('form').get('boundingBox');
        Assert.isTrue(overlay.hasClass('yui3-lazr-formoverlay-hidden'));
        var config = Y.one('.config');
        config.simulate('click');
        Assert.isFalse(overlay.hasClass('yui3-lazr-formoverlay-hidden'));
    },

    test_field_visibility_form_update_config: function() {
        // Changing elements on the form also updates the field_visibility
        // config values.
        this.list_util = new Y.lp.buglisting_utils.BugListingConfigUtil(
            this.defaults);
        this.list_util.render();
        var config = Y.one('.config');
        config.simulate('click');
        var show_targetname = Y.one('.show_targetname');
        var show_heat = Y.one('.show_heat');
        show_targetname.simulate('click');
        show_heat.simulate('click');
        var update = Y.one('.update-buglisting');
        update.simulate('click');
        var expected_config = {
            show_title: true,
            show_id: false,
            show_importance: false,
            show_status: true,
            show_information_type: false,
            show_heat: false,
            show_targetname: false,
            show_datecreated: false,
            show_date_last_updated: false,
            show_assignee: false,
            show_reporter: false,
            show_milestone_name: false,
            show_tag: false
        };
        var model = this.list_util.get('model');
        var actual_config = model.get_field_visibility();
        ObjectAssert.areEqual(expected_config, actual_config);
    },

    test_form_update_hides_overlay: function() {
        // Updating the form overlay hides the overlay.
        this.list_util = new Y.lp.buglisting_utils.BugListingConfigUtil(
            this.defaults);
        this.list_util.render();
        var config = Y.one('.config');
        config.simulate('click');
        var show_targetname = Y.one('.show_targetname');
        show_targetname.simulate('click');
        var update = Y.one('.update-buglisting');
        update.simulate('click');
        var overlay = this.list_util.get('form').get('boundingBox');
        Assert.isTrue(overlay.hasClass('yui3-lazr-formoverlay-hidden'));
    },

    test_update_from_form_updates_cookie: function() {
        // When the form is submitted, a cookie is set to match
        // your preferred field_visibility.
        this.list_util = new Y.lp.buglisting_utils.BugListingConfigUtil(
            this.defaults);
        this.list_util.render();
        // Now poke at the page to set the cookie.
        var config = Y.one('.config');
        config.simulate('click');
        var show_targetname = Y.one('.show_targetname');
        show_targetname.simulate('click');
        var update = Y.one('.update-buglisting');
        update.simulate('click');
        var expected_config = {
            show_title: true,
            show_id: false,
            show_importance: false,
            show_status: true,
            show_information_type: false,
            show_heat: true,
            show_targetname: false,
            show_datecreated: false,
            show_date_last_updated: false,
            show_assignee: false,
            show_reporter: false,
            show_milestone_name: false,
            show_tag: false
        };
        var expected_cookie = Y.Cookie._createCookieHashString(
            expected_config);
        var actual_cookie = Y.Cookie.get(this.cookie_name);
        Assert.areEqual(expected_cookie, actual_cookie);
    },

    test_fields_visibility_form_reset: function() {
        // Clicking "reset to defaults" on the form returns
        // field_visibility to its default values.
        var field_visibility = {
            show_targetname: true,
            show_heat: false
        };
        this.list_util = new Y.lp.buglisting_utils.BugListingConfigUtil({
            field_visibility: field_visibility,
            field_visibility_defaults: this.defaults.field_visibility_defaults
        });
        this.list_util.setCookie(field_visibility);
        this.list_util.render();
        // Poke at the page to reset the form.
        var config = Y.one('.config');
        config.simulate('click');
        Y.one('.reset-buglisting').simulate('click');
        var model = this.list_util.get('model');
        var defaults = model.get('field_visibility_defaults');
        var fields = model.get_field_visibility();
        ObjectAssert.areEqual(defaults, fields);
    },

    test_fields_visibility_form_reset_hides_overlay: function() {
        // Reseting to defaults should hide the form overlay.
        var field_visibility = {
            show_targetname: true,
            show_heat: false
        };
        this.list_util = new Y.lp.buglisting_utils.BugListingConfigUtil({
            field_visibility: field_visibility,
            field_visibility_defaults: this.defaults.field_visibility_defaults
        });
        this.list_util.render();
        // Poke at the form to reset defaults.
        var config = Y.one('.config');
        config.simulate('click');
        Y.one('.reset-buglisting').simulate('click');
        var overlay = this.list_util.get('form').get('boundingBox');
        Assert.isTrue(overlay.hasClass('yui3-lazr-formoverlay-hidden'));
    },

    test_fields_visibility_form_reset_updates_form: function() {
        // Reseting to defaults should reset the form inputs, too.
        var field_visibility = Y.merge(
            this.defaults.field_visibility_defaults, {
            show_targetname: false,
            show_heat: false
        });
        this.list_util = new Y.lp.buglisting_utils.BugListingConfigUtil({
            field_visibility: field_visibility,
            field_visibility_defaults: this.defaults.field_visibility_defaults
        });
        this.list_util.render();
        var expected_names = [
            'show_title',
            'show_id',
            'show_importance',
            'show_status',
            'show_information_type',
            'show_heat',
            'show_targetname',
            'show_datecreated',
            'show_date_last_updated',
            'show_assignee',
            'show_reporter',
            'show_milestone_name',
            'show_tag'
        ];
        var expected_checked = [
            true,
            true,
            true,
            true,
            false,
            true,
            true,
            false,
            false,
            false,
            false,
            false,
            false
        ];
        // Poke at the form to reset defaults.
        var config = Y.one('.config');
        config.simulate('click');
        Y.one('.reset-buglisting').simulate('click');
        var actual_inputs = this.getActualInputData();
        ArrayAssert.itemsAreSame(expected_names, actual_inputs[0]);
        ArrayAssert.itemsAreSame(expected_checked, actual_inputs[1]);
    },

    test_form_reset_removes_cookie: function() {
        // Clicking "reset to defaults" on the overlay will
        // remove any cookie added.

        Y.Cookie.remove(this.cookie_name, {path: "/"});
        Assert.isNull(Y.Cookie.get(this.cookie_name));
        this.list_util = new Y.lp.buglisting_utils.BugListingConfigUtil(
            this.defaults);
        this.list_util.render();
        // Now poke at the page to set the cookie.
        var config = Y.one('.config');
        config.simulate('click');
        var show_targetname = Y.one('.show_targetname');
        show_targetname.simulate('click');
        var update = Y.one('.update-buglisting');
        update.simulate('click');
        // Now reset from the form.
        config.simulate('click');
        Assert.isNotNull(Y.Cookie.get(this.cookie_name));
        Y.one('.reset-buglisting').simulate('click');
        Assert.isNull(Y.Cookie.get(this.cookie_name));
    },

    getDefaultDataVisibility: function() {
        return {
                show_title: true,
                show_id: false,
                show_importance: true,
                show_status: true,
                show_information_type: false,
                show_heat: true,
                show_targetname: true,
                show_datecreated: false,
                show_date_last_updated: false,
                show_assignee: false,
                show_reporter: false,
                show_milestone_name: false,
                show_tag: true
        };
    },

    SORT_KEYS: [
        ['id', 'Number'],
        ['title', 'Title'],
        ['importance', 'Importance'],
        ['status', 'Status'],
        ['information_type', 'Information Type'],
        ['heat', 'Heat'],
        ['reporter', 'Reporter'],
        ['assignee', 'Assignee'],
        ['targetname', 'Package/Project/Series name'],
        ['milestone_name', 'Milestone'],
        ['datecreated', 'Age'],
        ['date_last_updated', 'Date last updated'],
        ['tag', 'Tags'],
        ['date_closed', 'Date closed'],
        ['dateassigned', 'Date when the bug task was assigned'],
        ['number_of_duplicates', 'Number of duplicates'],
        ['latest_patch_uploaded', 'Date latest patch uploaded'],
        ['message_count', 'Number of comments'],
        ['milestone', 'Milestone ID'],
        ['specification', 'Linked blueprint'],
        ['task', 'Bug task ID'],
        ['users_affected_count', 'Number of affected users']
    ],

    test_update_sort_button_visibility: function() {
        // update_sort_button_visibility() hides sort buttons for
        // data that is not displayed and shown sort buttons for other
        // data.
        var orderby = new Y.lp.ordering.OrderByBar({
            sort_keys: this.SORT_KEYS,
            active: 'importance',
            sort_order: 'desc'
        });
        orderby.render();
        var data_visibility = this.getDefaultDataVisibility();
        Y.lp.buglisting_utils.update_sort_button_visibility(
            orderby, data_visibility);
        Y.each(orderby.get('li_nodes'), function(li_node) {
            var sort_key = li_node.get('id').replace('sort-', '');
            if (data_visibility['show_' + sort_key]) {
                Assert.isFalse(li_node._isHidden());
            } else {
                Assert.isTrue(li_node._isHidden());
            }
        });
    },

    test_update_sort_button_visibility_current_sort_order: function() {
        // The current sort order (importance for this test) is
        // never hidden, even if the bug importance is not displayed.
        var orderby = new Y.lp.ordering.OrderByBar({
            sort_keys: this.SORT_KEYS,
            active: 'importance',
            sort_order: 'desc'
        });
        orderby.render();
        var data_visibility = this.getDefaultDataVisibility();
        data_visibility.show_importance = false;
        Y.lp.buglisting_utils.update_sort_button_visibility(
            orderby, data_visibility);
        var importance_button = Y.one('#sort-importance');
        Assert.isFalse(importance_button._isHidden());
    },

    test_update_sort_button_visibility_extra_sort_order: function() {
        // If the orderby widget has a property "always_display",
        // the button for this sort order is never hidden.
        var orderby = new Y.lp.ordering.OrderByBar({
            sort_keys: this.SORT_KEYS,
            active: 'importance',
            sort_order: 'desc'
        });
        orderby.render();
        orderby.always_display = ['users_affected_count'];
        var data_visibility = this.getDefaultDataVisibility();
        Y.lp.buglisting_utils.update_sort_button_visibility(
            orderby, data_visibility);
        var users_affected_button = Y.one('#sort-users_affected_count');
        Assert.isFalse(users_affected_button._isHidden());
    }
});


/**
 * The Chrome workaround breaks Y.Cookie.remove behaviour
 */
if (running_in_webkit()){
    var ignore = buglisting_display_utils_tests._should.ignore;
    ignore.test_form_reset_removes_cookie = true;
    ignore.test_update_from_form_updates_cookie = true;
}

suite.add(buglisting_display_utils_tests);

buglisting_utils.suite = suite;

}, '0.1', {
    'requires': [ 'test', 'lp.testing.helpers', 'node-event-simulate',
        'cookie', 'lp.buglisting_utils', 'lp.ordering']
});
