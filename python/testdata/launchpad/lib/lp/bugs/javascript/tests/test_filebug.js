/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.bugs.filebug.test', function (Y) {

    var tests = Y.namespace('lp.bugs.filebug.test');
    var info_type = Y.lp.app.information_type;

    tests.suite = new Y.Test.Suite(
        'lp.bugs.filebug Tests');

    tests.suite.add(new Y.Test.Case({
        name: 'lp.bugs.filebug_tests',

        setUp: function () {
            window.LP = {
                links: {},
                cache: {
                    information_type_data: {
                        PUBLIC: {
                            name: 'Public', value: 'PUBLIC',
                            is_private: false,
                            order: 1,
                            description: 'Public bug'
                        },
                        PRIVATESECURITY: {
                            name: 'Private Security',
                            value: 'PRIVATESECURITY',
                            order: 2,
                            is_private: true,
                            description: 'private security bug'
                        },
                        USERDATA: {
                            name: 'Private', value: 'USERDATA',
                            is_private: true,
                            order: 3,
                            description: 'Private bug'
                        }
                    },
                    bugtask_status_data: [
                        {name: 'New', value: 'New'},
                        {name: 'Incomplete', value: 'Incomplete'}
                    ],
                    bugtask_importance_data: [
                        {name: 'Undecided', value: 'Undecided'},
                        {name: 'High', value: 'High'}
                    ]
                }
            };
        },

        setupForm: function(bugsupervisor_version) {
            this.fixture = Y.one('#fixture');
            var form_id = 'filebug-template';
            if (bugsupervisor_version) {
                form_id = 'bugsupervisor-' + form_id;
            }
            var form = Y.Node.create(Y.one('#' + form_id).getContent());
            this.fixture.appendChild(form);
            Y.lp.bugs.filebug.setup_filebug(true);
        },

        tearDown: function () {
            if (Y.Lang.isValue(this.fixture)) {
                this.fixture.empty(true);
                delete this.fixture;
            }
            delete window.LP;
        },

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.bugs.filebug,
                "Could not locate the " +
                "lp.bugs.filebug module");
        },

        // Filing a public bug does not show the privacy banner.
        test_setup_filebug_public: function () {
            // Watch out for the event that showing a privacy banner would
            // fire.
            var fired = false;
            var ev = Y.on(info_type.EV_ISPRIVATE, function (ev) {
                fired = true;
            });
            this.setupForm(true);
            Y.Assert.isFalse(fired);
            ev.detach();
        },

        // Filing a bug for a project with private bugs shows the privacy
        // banner.
        test_setup_filebug_private: function () {
            var fired = false;
            var ev = Y.on(info_type.EV_ISPRIVATE, function (ev) {
                fired = true;
                Y.Assert.areEqual(
                    'This report will be private. ' +
                    'You can disclose it later.', ev.text);
            });

            window.LP.cache.bug_private_by_default = true;
            this.setupForm(true);
            Y.Assert.isTrue(fired);
            ev.detach();
        },

        // Selecting a private info type using the legacy radio buttons
        // turns on the privacy banner.
        test_legacy_select_private_info_type: function () {
            var fired = false;
            var ev = Y.on(info_type.EV_ISPRIVATE, function (ev) {
                fired = true;
                Y.Assert.areEqual(
                    'This report will be private because it is a security ' +
                    'vulnerability. You can disclose it later.', ev.text);
            });

            this.setupForm(true);
            Y.Assert.isFalse(fired);

            Y.one('[id="field.information_type.2"]').simulate('click');
            // And the event should be fired and caught.
            Y.Assert.isTrue(fired);
            ev.detach();
        },

        // Selecting a public info type using the legacy radio buttons
        // turns off the privacy banner.
        test_legacy_select_public_info_type: function () {
            var fired = false;
            var ev = Y.on(info_type.EV_ISPUBLIC, function (ev) {
                fired = true;
            });

            window.LP.cache.bug_private_by_default = true;
            this.setupForm(true);

            // This will fire ISPRIVATE and a banner shows.
            Y.one('[id="field.information_type.2"]').simulate('click');

            // The second one will fire ISPUBLIC and the banner disappears.
            Y.one('[id="field.information_type.0"]').simulate('click');
            Y.Assert.isTrue(fired);
        },

        // When non bug supervisors select a security related bug the privacy
        // banner is turned on.
        test_select_security_related: function () {
            var fired = false;
            var ev = Y.on(info_type.EV_ISPRIVATE, function (ev) {
                fired = true;
                Y.Assert.areEqual(
                    'This report will be private because it is a security ' +
                    'vulnerability. You can disclose it later.', ev.text);
            });

            this.setupForm(false);
            Y.Assert.isFalse(fired);

            Y.one('[id="field.security_related"]').simulate('click');
            // And the event should be fired and caught.
            Y.Assert.isTrue(fired);
            ev.detach();
        },

        // When non bug supervisors unselect a security related bug the privacy
        // banner is turned off.
        test_unselect_security_related: function () {
            var fired = false;
            var ev = Y.on(info_type.EV_ISPUBLIC, function (ev) {
                fired = true;
            });

            this.setupForm(false);

            Y.one('[id="field.security_related"]').simulate('click');
            Y.Assert.isFalse(fired);

            Y.one('[id="field.security_related"]').simulate('click');
            Y.Assert.isTrue(fired);
        },

        // When non bug supervisors unselect a security related bug the privacy
        // banner remains on for private_by_default bugs.
        test_unselect_security_related_default_private: function () {
            window.LP.cache.bug_private_by_default = true;
            var public = 0;
            var private = 0;
            var ev = Y.on(info_type.EV_ISPUBLIC, function (ev) {
                public = public + 1;
            });

            var ev = Y.on(info_type.EV_ISPRIVATE, function (ev) {
                private = private + 1;
            });


            this.setupForm(false);
            Y.Assert.areEqual(1, private, 'Private is the default state.');

            Y.one('[id="field.security_related"]').simulate('click');
            Y.Assert.areEqual(2, private, 'The first click fires ISPRIVATE');

            Y.one('[id="field.security_related"]').simulate('click');
            Y.Assert.areEqual(1, public, 'The second click fires ISPUBLIC');
            Y.Assert.areEqual(
                3, private,
                "It also fires an ISPRIVATE since that's the default state.");
        },

        // The dupe finder functionality is setup.
        test_dupe_finder_setup: function () {
            window.LP.cache.enable_bugfiling_duplicate_search = true;
            var orig_setup_dupe_finder =
                Y.lp.bugs.filebug_dupefinder.setup_dupe_finder;
            var orig_setup_dupes =
                Y.lp.bugs.filebug_dupefinder.setup_dupes;
            var setup_dupe_finder_called = false;
            var setup_dupes_called = false;
            Y.lp.bugs.filebug_dupefinder.setup_dupe_finder = function() {
                setup_dupe_finder_called = true;
            };
            Y.lp.bugs.filebug_dupefinder.setup_dupes = function() {
                setup_dupes_called = true;
            };
            this.setupForm(true);
            Y.Assert.isTrue(setup_dupe_finder_called);
            Y.Assert.isTrue(setup_dupes_called);
            Y.lp.bugs.filebug_dupefinder.setup_dupes = orig_setup_dupes;
            Y.lp.bugs.filebug_dupefinder.setup_dupe_finder
                = orig_setup_dupe_finder;
        },

        // The bugtask status choice popup is rendered.
        test_status_setup: function () {
            this.setupForm(true);
            var status_node = Y.one('.status-content .value');
            Y.Assert.areEqual('New', status_node.get('text'));
            var status_edit_node = Y.one('.status-content a.sprite.edit');
            Y.Assert.isNotNull(status_edit_node);
            var legacy_dropdown = Y.one('[id="field.status"]');
            Y.Assert.isTrue(legacy_dropdown.hasClass('hidden'));
        },

        _perform_test_importance: function() {
            var importance_node = Y.one('.importance-content .value');
            Y.Assert.areEqual('Undecided', importance_node.get('text'));
            var importance_edit_node =
                Y.one('.importance-content a.sprite.edit');
            Y.Assert.isNotNull(importance_edit_node);
            var legacy_dropdown = Y.one('[id="field.importance"]');
            Y.Assert.isTrue(legacy_dropdown.hasClass('hidden'));
        },

        // The bugtask importance choice popup is rendered.
        test_importance_setup: function () {
            this.setupForm(true);
            this._perform_test_importance();
        },

        // The choice popup wiring works even if the field is missing.
        // This is so fields which the user does not have permission to see
        // can be missing and everything still works as expected.
        test_missing_fields: function () {
            this.setupForm(true);
            Y.one('[id="field.status"]').remove(true);
            this._perform_test_importance();
        },

        // The bugtask status choice popup updates the form.
        test_status_selection: function() {
            this.setupForm(true);
            var status_popup = Y.one('.status-content a');
            status_popup.simulate('click');
            var status_choice = Y.one(
                '.yui3-ichoicelist-content a[href="#Incomplete"]');
            status_choice.simulate('click');
            var legacy_dropdown = Y.one('[id="field.status"]');
            Y.Assert.areEqual('Incomplete', legacy_dropdown.get('value'));
        },

        // The bugtask importance choice popup updates the form.
        test_importance_selection: function() {
            this.setupForm(true);
            var status_popup = Y.one('.importance-content a');
            status_popup.simulate('click');
            var status_choice = Y.one(
                '.yui3-ichoicelist-content a[href="#High"]');
            status_choice.simulate('click');
            var legacy_dropdown = Y.one('[id="field.importance"]');
            Y.Assert.areEqual('High', legacy_dropdown.get('value'));
        },

        // The bugtask information_type choice popup is rendered.
        test_information_type_setup: function () {
            this.setupForm(true);
            var information_type_node =
                Y.one('.information_type-content .value');
            Y.Assert.areEqual('Public', information_type_node.get('text'));
            var information_type_node_edit_node =
                Y.one('.information_type-content a.sprite.edit');
            Y.Assert.isNotNull(information_type_node_edit_node);
            var legacy_field = Y.one('table.radio-button-widget');
            Y.Assert.isTrue(legacy_field.hasClass('hidden'));
        },

        // The bugtask information_type choice popup updates the form.
        test_information_type_selection: function() {
            this.setupForm(true);
            var information_type_popup = Y.one('.information_type-content a');
            information_type_popup.simulate('click');
            var header_text =
                Y.one('.yui3-ichoicelist-focused .yui3-widget-hd h2')
                    .get('text');
            Y.Assert.areEqual('Set information type as', header_text);
            var information_type_choice = Y.one(
                '.yui3-ichoicelist-content a[href="#USERDATA"]');
            information_type_choice.simulate('click');
            var legacy_radio_button = Y.one('[id="field.information_type.3"]');
            Y.Assert.isTrue(legacy_radio_button.get('checked'));
        },

        // Selecting a private info type using the popup choice widget
        // turns on the privacy banner.
        test_select_private_info_type: function () {
            var fired = false;
            var ev = Y.on(info_type.EV_ISPRIVATE, function (ev) {
                fired = true;
                Y.Assert.areEqual(
                    'This report contains Private information. ' +
                    'You can change the information type later.', ev.text);
            });

            this.setupForm(true);
            Y.Assert.isFalse(fired);

            var information_type_popup = Y.one('.information_type-content a');
            information_type_popup.simulate('click');
            var information_type_choice = Y.one(
                '.yui3-ichoicelist-content a[href="#USERDATA"]');
            information_type_choice.simulate('click');

            // And the event should be fired and caught.
            Y.Assert.isTrue(fired);
            ev.detach();
        },

        // Selecting a public info type using the popup choice widget
        // turns off the privacy banner.
        test_select_public_info_type: function () {
            var fired = false;
            var ev = Y.on(info_type.EV_ISPUBLIC, function (ev) {
                fired = true;
            });

            window.LP.cache.bug_private_by_default = true;
            this.setupForm(true);

            // This will fire ISPRIVATE and a banner shows.
            var information_type_popup = Y.one('.information_type-content a');
            information_type_popup.simulate('click');
            var information_type_choice = Y.one(
                '.yui3-ichoicelist-content a[href="#USERDATA"]');
            information_type_choice.simulate('click');

            // The second one will fire ISPUBLIC and the banner disappears.
            information_type_popup.simulate('click');
            information_type_choice = Y.one(
                '.yui3-ichoicelist-content a[href="#PUBLIC"]');
            information_type_choice.simulate('click');

            Y.Assert.isTrue(fired);
        }
    }));

}, '0.1', {
    requires: [
        'test', 'test-console', 'event', 'node-event-simulate',
        'lp.app.banner.privacy', 'lp.app.choice', 'lp.app.information_type',
        'lp.bugs.filebug_dupefinder', 'lp.bugs.filebug' ]
});
