/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.app.licence.test', function (Y) {

    var tests = Y.namespace('lp.app.licence.test');
    var ns = Y.lp.app.licence;
    tests.suite = new Y.Test.Suite(
        'lp.app.licence Tests');

    tests.suite.add(new Y.Test.Case({
        name: 'lp.app.licence_tests',

        setUp: function () {
            this.fixture = Y.one('#fixture');
            var form = Y.Node.create(Y.one('#licence-fixture').getContent());
            this.fixture.appendChild(form);
        },

        tearDown: function () {
            if (Y.Lang.isValue(this.widget)) {
                delete this.widget;
            }
            if (Y.Lang.isValue(this.fixture)) {
                this.fixture.empty(true);
                delete this.fixture;
            }
        },

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.app.licence,
                "Could not locate the lp.app.licence module");
        },

        makeWidget: function() {
            this.widget = new Y.lp.app.licence.LicenceWidget({
                use_animation: false
            });
            this.widget.render();
            var finish = function() {};
            this.wait(finish, 20);
        },

        // Test the visibility of the element for the given css selector.
        _assert_animated_state: function(showing, selector) {
            var check = function() {
                var licence_details = Y.one(selector);
                if (showing) {
                    Y.Assert.isTrue(licence_details.hasClass('lazr-opened'));
                    Y.Assert.areEqual(
                            'visible', licence_details.getStyle('overflow'));
                } else {
                    Y.Assert.isTrue(licence_details.hasClass('lazr-closed'));
                    Y.Assert.areEqual(
                            'hidden', licence_details.getStyle('overflow'));
                }
            };
            this.wait(check, 20);
        },

        _assert_animated_state_licence_details: function(showing) {
            this._assert_animated_state(showing, '#license-details');
        },

        _assert_animated_state_proprietary: function(showing) {
            this._assert_animated_state(showing, '#proprietary');
        },

        // The widget is created as expected.
        test_create_widget: function() {
            this.makeWidget();
            Y.Assert.isInstanceOf(
                ns.LicenceWidget, this.widget,
                "Licence widget failed to be instantiated");
            this._assert_animated_state_licence_details(false);
            this._assert_animated_state_proprietary(false);
        },

        // When a licence is selected, the pending/complete radio buttons
        // are correctly toggled.
        test_click_licence_selects_license_complete: function() {
            this.makeWidget();
            Y.one('#license_pending').simulate('click');
            Y.one('[id="field.licenses.1"]').simulate('click');
            Y.Assert.isFalse(Y.one('#license_pending').get('checked'));
            Y.Assert.isTrue(Y.one('#license_complete').get('checked'));
            this._assert_animated_state_licence_details(false);
            this._assert_animated_state_proprietary(false);
        },

        // Any selected licences are unselected when the pending radio button
        // is clicked.
        test_click_license_pending_unselects_licences: function() {
            this.makeWidget();
            // Click once to select.
            Y.one('[id="field.licenses.3"]').simulate('click');
            // Click again to unselect.
            Y.one('[id="field.licenses.3"]').simulate('click');
            Y.one('#license_pending').simulate('click');
            Y.Assert.isFalse(Y.one('[id="field.licenses.1"]').get('checked'));
            this._assert_animated_state_licence_details(false);
            this._assert_animated_state_proprietary(false);
        },

        // The licence details field is shown when a licence type of 'other'
        // is selected..
        test_other_license_shows_details: function() {
            this.makeWidget();
            Y.each(['OTHER_PROPRIETARY', 'OTHER_OPEN_SOURCE'],
                function(licence_type) {
                    var licence = Y.one('input[value="' + licence_type + '"]');
                    // Click once to select.
                    licence.simulate('click');
                    this._assert_animated_state_licence_details(true);
                    // Click again to unselect.
                    licence.simulate('click');
                    this._assert_animated_state_licence_details(false);
            });
        },

        // The proprietary help text is shown when a licence type of 'other
        // proprietary' is selected..
        test_proprietary_license_shows_proprietary_help: function() {
            this.makeWidget();
            var licence = Y.one('input[value="OTHER_PROPRIETARY"]');
            // Click once to select.
            licence.simulate('click');
            this._assert_animated_state_proprietary(true);
            // Click again to unselect.
            licence.simulate('click');
            this._assert_animated_state_proprietary(false);
        }
    }));

}, '0.1', {'requires': [
    'test', 'test-console', 'event', 'node-event-simulate', 'lp.app.licence']});
