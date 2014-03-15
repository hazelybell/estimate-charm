/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Disclosure infrastructure.
 *
 * @module lp.registry.sharing
 */

YUI.add('lp.registry.sharing.granteepicker', function(Y) {

var namespace = Y.namespace('lp.registry.sharing.granteepicker');

var GranteePicker;
GranteePicker = function() {
    GranteePicker.superclass.constructor.apply(this, arguments);

};

GranteePicker.ATTRS = {
   /**
    * The available information types.
    *
    * @attribute information_types
    * @type Object
    * @default []
    */
    information_types: {
        value: []
    },
    sharing_permissions: {
        value: []
    }
};


Y.extend(GranteePicker, Y.lp.ui.picker.Picker, {
    initializer: function(config) {
        GranteePicker.superclass.initializer.apply(this, arguments);
        var information_types = [];
        var sharing_permissions = [];
        if (config !== undefined) {
            if (config.information_types !== undefined) {
                information_types = config.information_types;
            }
            if (config.sharing_permissions !== undefined) {
                sharing_permissions = config.sharing_permissions;
            }
        }
        this.set('information_types', information_types);
        this.set('sharing_permissions', sharing_permissions);
        this.step_one_header = this.get('headerContent');
        var self = this;
        this.subscribe('save', function (e) {
            e.halt();
            // The step number indicates which picker step has just fired.
            var step_nr = e.details[1];
            if (!Y.Lang.isNumber(step_nr)) {
                step_nr = 1;
            }
            var data = e.details[Y.lp.ui.picker.Picker.SAVE_RESULT];
            switch(step_nr) {
                case 1:
                    data.grantee_name = data.title;
                    delete data.title;
                    self._display_step_two(data);
                    break;
                case 2:
                    self._publish_result(data);
                    break;
                default:
                    return;
            }
        });
    },

    _display_step_one: function() {
        this.set('headerContent', this.step_one_header);
        this.set(
            'steptitle',
            'Search for user or exclusive team with whom to share');
        this.set('progress', 50);
        var contentBox = this.get('contentBox');
        var step_one_content = contentBox.one('.yui3-widget-bd');
        var step_two_content = contentBox.one('.picker-content-two');
        this._fade_in(step_one_content, step_two_content);
    },

    _render_step_two: function(back_enabled, allowed_permissions,
                               disabled_some_types) {
        var step_two_html = [
            '<div class="picker-content-two transparent">',
            '<div class="step-links">',
            '<button class="prev">Back</a>',
            '<button class="next">Update</button>',
            '</div></div>'
            ].join(' ');
        var self = this;
        var step_two_content = Y.Node.create(step_two_html);
        // Remove the back link if required.
        if (Y.Lang.isBoolean(back_enabled) && !back_enabled ) {
            step_two_content.one('.prev').remove(true);
        } else {
            step_two_content.one('.next').setContent('Share');
            step_two_content.one('.prev').on('click', function(e) {
                e.halt();
                self._display_step_one();
            });
        }
        // By default, we only show All or Nothing.
        if (!Y.Lang.isValue(allowed_permissions)) {
            allowed_permissions = ['ALL', 'NOTHING'];
        }
        var sharing_permissions = [];
        Y.Array.each(this.get('sharing_permissions'),
                function(permission) {
            if (Y.Array.indexOf(
                    allowed_permissions, permission.value) >=0) {
                sharing_permissions.push(permission);
            }
        });
        var policy_selector = self._make_policy_selector(
            sharing_permissions, disabled_some_types);
        step_two_content.one('div.step-links')
            .insert(policy_selector, 'before');
        step_two_content.all('input[name^="field.permission"]')
                .on('click', function(e) {
            self._disable_select_if_all_info_choices_nothing(step_two_content);
        });
        return step_two_content;
    },

    _display_step_two: function(data) {
        if (Y.Lang.isValue(data.title)) {
            this.set(
                'headerContent',
                Y.Node.create('<h2></h2>').set('text', data.title));
        }
        var steptitle = data.steptitle;
        if (!Y.Lang.isValue(steptitle)) {
            steptitle = Y.Lang.sub(
                'Select sharing policies for {name}',
                {name: data.grantee_name});
        }
        this.set('steptitle', steptitle);
        this.set('progress', 75);
        var contentBox = this.get('contentBox');
        var step_one_content = contentBox.one('.yui3-widget-bd');
        var step_two_content = contentBox.one('.picker-content-two');
        if (step_two_content === null) {
            step_two_content = this._render_step_two(
                data.back_enabled, data.allowed_permissions,
                data.disabled_some_types);
            step_one_content.insert(step_two_content, 'after');
        }
        // Wire up the next (ie submit) links.
        step_two_content.detach('click');
        step_two_content.delegate('click', function(e) {
            e.halt();
            // Only submit if at least one info type is selected.
            if (!this._all_info_choices_nothing(step_two_content)) {
                this.fire('save', data, 2);
            }
        }, '.next', this);
        // Initially set all radio buttons to Nothing.
        step_two_content.all('input[name^="field.permission"][value="NOTHING"]')
                .each(function(radio_button) {
            radio_button.set('checked', true);
        });
        // Ensure the correct radio buttons are ticked according to the
        // grantee_permissions.
        if (Y.Lang.isObject(data.grantee_permissions)) {
            Y.each(data.grantee_permissions, function(perm, type) {
                var cb = step_two_content.one(
                    'input[name="field.permission.'+type+'"]' +
                    '[value="' + perm + '"]');
                if (Y.Lang.isValue(cb)) {
                    cb.set('checked', true);
                }
            });
        }
        this._disable_select_if_all_info_choices_nothing(step_two_content);
        this._fade_in(step_two_content, step_one_content);
    },

    /**
     * Are all the radio buttons set to Nothing?
     * @param content
     * @return {Boolean}
     * @private
     */
    _all_info_choices_nothing: function(content) {
        var all_unticked = true;
        content.all('input[name^="field.permission"]')
                .each(function(info_node) {
            if (info_node.get('value') !== 'NOTHING') {
                all_unticked &= !info_node.get('checked');
            }
        });
        return all_unticked;
    },

    /**
     * Disable the select button if no info type checkboxes are ticked.
     * @param content
     * @private
     */
    _disable_select_if_all_info_choices_nothing: function(content) {
        var disable_btn = this._all_info_choices_nothing(content);
        content.all('.next').each(function(node) {
            if (disable_btn) {
                node.set('disabled', true);
            } else {
                node.set('disabled', false);
            }
        });
    },

    _publish_result: function(data) {
        // Determine the selected permissions. 'data' already contains the
        // selected person due to the base picker behaviour.
        var contentBox = this.get('contentBox');
        var selected_permissions = {};
        Y.Array.each(this.get('information_types'), function(info_type) {
            contentBox.all('input[name="field.permission.'+info_type.value+'"]')
                    .each(function(node) {
                if (node.get('checked')) {
                    selected_permissions[info_type.value] = node.get('value');
                }
            });
        });
        data.selected_permissions = selected_permissions;
        // Publish the result with step_nr 0 to indicate we have finished.
        this.fire('save', data, 0);
    },

    _sharing_permission_template: function() {
        return [
            '<table class="radio-button-widget"><tbody>',
            '{{#permissions}}',
            '<tr>',
            '      <input type="radio"',
            '        value="{{value}}"',
            '        name="field.permission.{{info_type}}"',
            '        id="field.permission.{{info_type}}.{{index}}"',
            '        class="radioType">',
            '    <label for="field.permission.{{info_type}}.{{index}}"',
            '        title="{{description}}">',
            '        {{title}}',
            '    </label>',
            '</tr>',
            '{{/permissions}}',
            '</tbody></table>'
        ].join('');
    },

    _make_policy_selector: function(allowed_permissions,
                                    disabled_some_types) {
        // The policy selector is a set of radio buttons.
        var sharing_permissions_template = this._sharing_permission_template();
        var html = Y.lp.mustache.to_html([
            '<div class="selection-choices">',
            '<table><tbody>',
            '{{#policies}}',
            '<tr>',
            '      <td><strong>',
            '        <span class="accessPolicy{{value}}">{{title}}',
            '        </span>',
            '      </strong></td>',
            '</tr>',
            '<tr>',
            '    <td>',
            '    {{#sharing_permissions}} {{/sharing_permissions}}',
            '    </td>',
            '</tr>',
            '<tr>',
            '    <td class="formHelp">',
            '        {{description}}',
            '    </td>',
            '</tr>',
            '{{/policies}}',
            '</tbody></table></div>'
        ].join(''), {
            policies: this.get('information_types'),
            sharing_permissions: function() {
                return function(text, render) {
                    return Y.lp.mustache.to_html(sharing_permissions_template, {
                        permissions: allowed_permissions,
                        info_type: render('{{value}}')
                    });
                };
            }
        });
        var policies = Y.Node.create(html);

        // Disable the radio buttons 'Some' for selected info types.
        var disable_some_button = function(info_type) {
            var selector =
                'input[name="field.permission.' + info_type + '"]' +
                '[value="SOME"]';
            policies.all(selector).each(function(permission_node) {
                    permission_node.set('disabled', true);
                    permission_node.set(
                        'title', 'There are no shared bugs or branches.');
                });
        };

        if (Y.Lang.isArray(disabled_some_types)) {
            Y.Array.each(disabled_some_types, function(info_type) {
                disable_some_button(info_type);
            });
        }
        return policies;
    },

    _syncProgressUI: function() {
        // The base picker behaviour is to set the progress bar to 100% once
        // the search results are displayed. We want to control the progress
        // bar as the user steps through the picker screens.
    },

    hide: function() {
        this.get('boundingBox').setStyle('display', 'none');
        var contentBox = this.get('contentBox');
        var step_two_content = contentBox.one('.picker-content-two');
        if (step_two_content !== null) {
            step_two_content.remove(true);
        }
        this.constructor.superclass.hide.call(this);
    },

    /**
     * Show the picker. We can pass in config which allows us to tell the
     * picker to show a screen other than the first, and whether to disable
     * the back link.
     * @param state_config
     */
    show: function(state_config) {
        var config = {
            first_step: 1
        };
        if (Y.Lang.isValue(state_config)) {
            config = Y.merge(config, state_config);
        }
        switch (config.first_step) {
            case 2:
                var steptitle = Y.Lang.sub(
                    'Update sharing policies for {name}',
                    {name: config.grantee.person_name});
                var data = {
                    title: 'Update sharing policies',
                    steptitle: steptitle,
                    api_uri: config.grantee.person_uri,
                    grantee_permissions: config.grantee_permissions,
                    allowed_permissions: config.allowed_permissions,
                    disabled_some_types: config.disabled_some_types,
                    back_enabled: false
                };
                this._display_step_two(data);
                break;
            default:
                this._display_step_one();
                break;
        }
        this.get('boundingBox').setStyle('display', 'block');
        this.constructor.superclass.show.call(this);
    }

});

GranteePicker.NAME = 'grantee_picker';
namespace.GranteePicker = GranteePicker;

}, "0.1", { "requires": ['node', 'lp.mustache', 'lp.ui.picker-base'] });

