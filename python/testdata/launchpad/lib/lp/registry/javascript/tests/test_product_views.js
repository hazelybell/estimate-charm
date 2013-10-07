/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('registry.product-views.test', function (Y) {
    var tests = Y.namespace('registry.product-views.test');

    var ns = Y.namespace('registry.views');
    tests.suite = new Y.Test.Suite('registry.product-views Tests');

    // Share methods used in various test suites for the Views.
    var shared = {
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
                        EMBARGOED: {
                            value: 'EMBARGOED', name: 'Embargoed',
                            is_private: true, order: 2,
                            description: 'Something embargoed'
                        },
                        PROPRIETARY: {
                            value: 'PROPRIETARY', name: 'Proprietary',
                            is_private: true, order: 3,
                            description: 'Private Description'
                        }
                    }
                }
            };

            var tpl = Y.one('#tpl_information_type');
            var html = Y.lp.mustache.to_html(tpl.getContent());
            Y.one('#testdom').setContent(html);
        },

        tearDown: function () {
            Y.one('#testdom').empty();
            LP.cache = {};
        },

        assert_license_updates: function () {
            var licenses = Y.one('input[name="field.licenses"]');
            var licenses_cont = licenses.ancestor('td').ancestor('td');
            Y.Assert.areEqual('none',
                              licenses_cont.getComputedStyle('display'),
                              'License is hidden when EMBARGOED is selected.');

            var new_license = Y.one('input[name="field.licenses"]');
            Y.Assert.areEqual('OTHER_PROPRIETARY', new_license.get('value'),
                              'License is updated to a commercial selection');

            // license_info must also be filled in to ensure we don't
            // get form validation errors.
            var license_info = Y.one('textarea[name="field.license_info"]');
            Y.Assert.areEqual(
                'Launchpad 30-day trial commercial license',
                license_info.get('value'));
        }
    };

    tests.suite.add(new Y.Test.Case({
        name: 'registry.product-views.new_tests',
        setUp: shared.setUp,
        tearDown: shared.tearDown,

        test_library_exists: function () {
            Y.Assert.isObject(ns.NewProduct,
                "Could not locate the registry.views.NewProduct module");
        },

        test_url_autofill_sync: function () {
            var view = new ns.NewProduct();
            view.render();

            var name_field = Y.one('input[id="field.displayname"]');
            name_field.set('value', 'test');
            name_field.simulate('keyup');

            Y.Assert.areEqual(
                'test',
                Y.one('input[name="field.name"]').get('value'),
                'The url field should be updated based on the display name');
        },

        test_url_autofill_disables: function () {
            var view = new ns.NewProduct();
            view.render();

            var name_field = Y.one('input[id="field.displayname"]');
            var url_field = Y.one('input[id="field.name"]');
            name_field.set('value', 'test');
            name_field.simulate('keyup');
            Y.Assert.areEqual( 'test', url_field.get('value'),
                'The url field should be updated based on the display name');

            // Now setting the url field manually should detach the event for
            // the sync.
            url_field.set('value', 'test2');
            url_field.simulate('keyup');

            // Changing the value back should fail horribly.
            name_field.set('value', 'test');
            name_field.simulate('keyup');

            Y.Assert.areEqual(
                'test2',
                url_field.get('value'),
                'The url field should not be updated.');
        },

        test_information_type_widget: function () {
            // Render will give us a pretty JS choice widget.
            var view = new ns.NewProduct();
            view.render();
            Y.Assert.isNotNull(Y.one('#testdom .yui3-ichoicesource'));
        },

        test_information_type_choose_non_public: function () {
            // Selecting an information type not-public hides the license,
            // sets it to commercial, and shows the bug supervisor and driver
            // fields.
            var view = new ns.NewProduct();
            view.render();

            var widget = view._information_type_widget;

            // Force the value to change to a private value and make sure the
            // UI is updated.
            widget._saveData('EMBARGOED');
            shared.assert_license_updates();

            var bug_super = Y.one('input[name="field.bug_supervisor"]');
            var bug_super_cont = bug_super.ancestor('td');
            Y.Assert.areNotEqual(
                'none',
                bug_super_cont.getComputedStyle('display'),
                'Bug Supervisor is shown when EMBARGOED is selected.');

            var driver = Y.one('input[name="field.driver"]');
            var driver_cont = driver.ancestor('td');
            Y.Assert.areNotEqual(
                'none',
                driver_cont.getComputedStyle('display'),
                'Driver is shown when EMBARGOED is selected.');
        }
    }));


    tests.suite.add(new Y.Test.Case({
        name: 'registry.product-views.edit_tests',
        setUp: shared.setUp,
        tearDown: shared.tearDown,

        test_library_exists: function () {
            Y.Assert.isObject(ns.EditProduct,
                "Could not locate the registry.views.EditProduct module");
        },

        test_information_type_widget: function () {
            // Render will give us a pretty JS choice widget.
            var view = new ns.EditProduct();
            view.render();
            Y.Assert.isNotNull(Y.one('#testdom .yui3-ichoicesource'));
        },

        test_information_type_choose_non_public: function () {
            // Selecting an information type not-public hides the license,
            // sets it to commercial
            var view = new ns.EditProduct();
            view.render();

            var widget = view._information_type_widget;

            // Force the value to change to a private value and make sure the
            // UI is updated.
            widget._saveData('EMBARGOED');
            shared.assert_license_updates();
        }
    }));

}, '0.1', {
    requires: ['test', 'event-simulate', 'node-event-simulate', 'test-console',
               'lp.mustache', 'registry.product-views']
});
