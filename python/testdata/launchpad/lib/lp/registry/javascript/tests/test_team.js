/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.registry.team.test', function (Y) {

    var namespace = Y.lp.registry.team;

    var tests = Y.namespace('lp.registry.team.test');
    tests.suite = new Y.Test.Suite('Team Tests');

    tests.suite.add(new Y.Test.Case({
        name: 'team_tests',

        setUp: function () {
            var template = Y.one('#visibility_setup');
            var visibility_widget = Y.Node.create(template.getContent());
            this.placeholder = Y.one('#placeholder');
            this.placeholder.appendChild(visibility_widget);
        },
        tearDown: function () {
            this.placeholder.empty();
        },

        test_library_exists: function() {
            Y.Assert.isObject(Y.lp.registry.team,
                "Could not locate the lp.registry.team module");
        },

        // The initialise_team_edit() method invokes the visibility_changed()
        // callback with the initial value of the visibility field.
        test_initialise_team_edit: function() {
            var orig_visibility_changed = namespace.visibility_changed;
            var visibility_changed_called = false;
            namespace.visibility_changed = function(visibility) {
                Y.Assert.areEqual('PUBLIC', visibility);
                visibility_changed_called = true;
            };
            namespace.initialise_team_edit();
            Y.Assert.isTrue(visibility_changed_called);
            namespace.visibility_changed = orig_visibility_changed;
        },

        // When the visibility field changes value, the visibility_changed
        // callback is invoked with the new value.
        test_visibility_change_trigger: function() {
            namespace.initialise_team_edit();
            var orig_visibility_changed = namespace.visibility_changed;
            var visibility_changed_called = false;
            namespace.visibility_changed = function(visibility) {
                Y.Assert.areEqual('PRIVATE', visibility);
                visibility_changed_called = true;
            };
            Y.Assert.isFalse(visibility_changed_called);
            var visibility_field = Y.one('[name="field.visibility"]');
            visibility_field.set('value', 'PRIVATE');
            visibility_field.simulate('change');
            Y.Assert.isTrue(visibility_changed_called);
            namespace.visibility_changed = orig_visibility_changed;
        },

        // When the visibility becomes private, only the restricted
        // membership policy is shown and the extra help message informs
        // the user of this fact.
        test_visibility_change_private: function() {
            namespace.visibility_changed('PRIVATE');
            var nr_radio_buttons = 0;
            Y.all('input[type="radio"]').each(function(radio_button) {
                if (radio_button.ancestor('tr').hasClass('hidden')
                        || !radio_button.get('checked')) {
                    return;
                }
                Y.Assert.areEqual(
                    'RESTRICTED', radio_button.get('value'));
                var help_row = radio_button.ancestor('tr', function (node) {
                        return node.one('td.formHelp') !== null;
                }).next();
                Y.Assert.isFalse(help_row.hasClass('hidden'));
                nr_radio_buttons++;
            });
            Y.Assert.isTrue(nr_radio_buttons === 1);
            var extra_help = Y.one('[for="field.membership_policy"]')
                .ancestor('div').one('.info');
            Y.Assert.areEqual(
                'Private teams must have a restricted membership policy.',
                extra_help.get('text'));
            var extra_visibility_help = Y.one('#visibility-extra-help');
            Y.Assert.isFalse(extra_visibility_help.hasClass('hidden'));
            Y.Assert.areEqual(
                'Private teams cannot become public later.',
                extra_visibility_help.get('text'));
        },

        // When the visibility field becomes public, all subscription policies
        // are visible again.
        test_visibility_change_public: function() {
            namespace.visibility_changed('PRIVATE');
            var extra_help = Y.one('[for="field.membership_policy"]')
                .ancestor('div').one('.info');
            Y.Assert.areEqual(
                'Private teams must have a restricted membership policy.',
                extra_help.get('text'));

            namespace.visibility_changed('PUBLIC');
            var nr_radio_buttons = 0;
            Y.all('input[type="radio"]').each(function(radio_button) {
                Y.Assert.isFalse(
                    radio_button.ancestor('tr').hasClass('hidden'));
                var help_row = radio_button.ancestor('tr')
                    .next(function (node) {
                        return node.one('td.formHelp') !== null;
                });
                Y.Assert.isFalse(help_row.hasClass('hidden'));
                nr_radio_buttons++;
            });
            Y.Assert.isTrue(nr_radio_buttons === 4);
            extra_help = Y.one('[for="field.membership_policy"]')
                .ancestor('div').one('.info');
            Y.Assert.isNull(extra_help);
            var extra_visibility_help = Y.one('#visibility-extra-help');
            Y.Assert.isTrue(extra_visibility_help.hasClass('hidden'));
        },

        // When the membership policy changes to private and back to public,
        // any original extra help text that was there is restored.
        test_visibility_change_public_restores_extra_help: function() {
            var widget = Y.one('[for="field.membership_policy"]')
                .ancestor('div').one('.radio-button-widget');
            var extra_help = Y.Node.create('<div>Help Me</div>')
                .addClass('sprite')
                .addClass('info');
            widget.insert(extra_help, 'before');

            namespace.visibility_changed('PRIVATE');
            extra_help = Y.one('[for="field.membership_policy"]')
                .ancestor('div').one('.info');
            Y.Assert.areEqual(
                'Private teams must have a restricted membership policy.',
                extra_help.get('text'));

            namespace.visibility_changed('PUBLIC');
            extra_help = Y.one('[for="field.membership_policy"]')
                .ancestor('div').one('.info');
            Y.Assert.areEqual('Help Me', extra_help.get('text'));
        }
    }));

}, '0.1', {'requires': ['test', 'test-console', 'node', 'event',
    'node-event-simulate', 'lp.registry.team']});
