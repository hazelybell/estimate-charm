/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Grantee table widget.
 *
 * @module lp.registry.sharing.granteetable
 */

YUI.add('lp.registry.sharing.granteetable', function(Y) {

var namespace = Y.namespace('lp.registry.sharing.granteetable');

var
    NAME = "granteeTableWidget",
    // Events
    UPDATE_GRANTEE = 'updateGrantee',
    UPDATE_PERMISSION = 'updatePermission',
    REMOVE_GRANTEE = 'removeGrantee';


/*
 * Grantee table widget.
 * This widget displays the grantees and their level of access to a product.
 */
function GranteeTableWidget(config) {
    GranteeTableWidget.superclass.constructor.apply(this, arguments);
}

GranteeTableWidget.ATTRS = {
    // The duration for various animations eg row deletion.
    anim_duration: {
        value: 1
    },
    // The display name of the pillar.
    pillar_name: {
        value: null
    },
    // The list of grantees to display.
    grantees: {
        value: [],
        // We clone the data passed in so external modifications do not
        // interfere.
        setter: function(value) {
            if (!Y.Lang.isArray(value)) {
                return value;
            }
            return Y.JSON.parse(Y.JSON.stringify(value));
        }
    },
    // The information types: public, embargoedsecurity, userdata etc.
    information_types: {
        value: {}
    },
    // The sharing permission choices: all, some, nothing etc.
    sharing_permissions: {
        value: {}
    },
    // The node holding the grantee table.
    grantee_table: {
        getter: function() {
            return Y.one('#grantee-table');
        }
    },
    // The handlebars template for the grantee table.
    grantee_table_template: {
        value: null
    },
    // The handlebars template for the grantee table rows.
    grantee_row_template: {
        value: null
    },
    // The node to display if there are no grantees.
    grantee_table_empty_row: {
        value: null
    },
    // The handlebars template for the each access policy item.
    grantee_policy_template: {
        value: null
    },

    write_enabled: {
        value: false
    }
};

Y.extend(GranteeTableWidget, Y.Widget, {

    initializer: function(config) {
        this.set(
            'grantee_table_template', this._grantee_table_template());
        this.set(
            'grantee_row_template', this._grantee_row_template());
        this.set(
            'grantee_table_empty_row', this._grantee_table_empty_row());
        this.set(
            'grantee_policy_template', this._grantee_policy_template());
        this.navigator = this.make_navigator();
        var self = this;
        var ns = Y.lp.registry.sharing.granteelisting_navigator;
        this.navigator.subscribe(
            ns.GranteeListingNavigator.UPDATE_CONTENT, function(e) {
                self._replace_content(e.details[0]);
        });
        this.publish(UPDATE_GRANTEE);
        this.publish(UPDATE_PERMISSION);
        this.publish(REMOVE_GRANTEE);
    },

    make_navigator: function() {
        var target = Y.one('#grantee-table');
        var container = target.get('parentNode');
        var navigation_indices = Y.all('.batch-navigation-index');
        var ns = Y.lp.registry.sharing.granteelisting_navigator;
        var cache = LP.cache;
        cache.total = this.get('grantees').length;
        var navigator = new ns.GranteeListingNavigator({
            current_url: window.location,
            cache: cache,
            target: target,
            container: container,
            navigation_indices: navigation_indices,
            batch_info_template: '<div></div>'
        });
        navigator.set('backwards_navigation',
                      container.all('.first,.previous'));
        navigator.set('forwards_navigation',
                      container.all('.last,.next'));
        navigator.clickAction('.first', navigator.first_batch);
        navigator.clickAction('.next', navigator.next_batch);
        navigator.clickAction('.previous', navigator.prev_batch);
        navigator.clickAction('.last', navigator.last_batch);
        navigator.update_navigation_links();
        return navigator;
    },

    _grantee_table_template: function() {
        return [
            '<table class="sharing listing" id="grantee-table">',
            '    <thead>',
            '        <tr><th style="width: 33%" ',
            '            colspan="2">User or Team</th>',
            '            <th colspan="2">',
            '                Sharing',
            '                <a class="sprite maybe action-icon"',
            '                    target="help"',
            '                    href="/+help-registry/sharing.html">(?)</a>',
            '            </th>',
            '            <th colspan="1">Shared items</th>',
            '        </tr>',
            '    </thead>',
            '    <tbody id="grantee-table-body">',
            '        {{#grantees}}',
            '        {{>grantee_row}}',
            '        {{/grantees}}',
            '    </tbody>',
            '</table>'].join(' ');
    },

    _grantee_row_template: function() {
        return [
            '<tr id="permission-{{name}}" data-name="{{name}}"><td>',
            '{{#icon_url}}',
            '    <a href="{{web_link}}"><img src="{{icon_url}}"/>',
            '{{/icon_url}}',
            '{{^icon_url}}',
            '    <a href="{{web_link}}" class="{{sprite_css}}">',
            '{{/icon_url}}',
            '    {{display_name}} ({{name}})',
            '    <span class="formHelp">{{role}}</span></a>',
            '</td>',
            '<td class="action-icons nowrap">',
            '<span id="remove-{{name}}">',
            '    <a title="Stop sharing with {{display_name}}"',
            '       href="#" class="sprite remove action-icon"',
            '        data-self_link="{{self_link}}"',
            '        data-person_name="{{display_name}}">Remove</a>',
            '</span>',
            '<span id="update-{{name}}">',
            '    <a title="Update sharing for {{display_name}}"',
            '       href="#" class="sprite add action-icon"',
            '        data-self_link="{{self_link}}"',
            '        data-person_name="{{display_name}}">Add</a>',
            '</span>',
            '</td>',
            '<td id="td-permission-{{name}}">',
            '    <span class="sortkey">1</span>',
            '    <ul class="horizontal">',
            '       {{>grantee_access_policies}}',
            '    </ul>',
            '</td>',
            '<td></td>',
            '<td>',
            '{{#shared_items_exist}}',
            '<a href="+sharing/{{name}}">View shared items.</a>',
            '{{/shared_items_exist}}',
            '{{^shared_items_exist}}',
            '<span class="formHelp">No items shared through subscriptions.',
            '</span>',
            '{{/shared_items_exist}}',
            '</td>',
            '</tr>'].join(' ');
    },

    _grantee_table_empty_row: function() {
        var row_template = [
            '<tr id="grantee-table-not-shared">',
            '<td colspan="5" style="padding-left: 0.25em">',
            '<span></span> private information is not shared with anyone.',
            '</td></tr>'].join('');
        var row = Y.Node.create(row_template);
        row.one('td span').set('text', this.get('pillar_name') + "'s");
        return row;
    },

    _grantee_policy_template: function() {
        return [
           '{{#information_types}}',
           '<li class="nowrap">',
           '<span id="{{policy}}-permission-{{grantee_name}}">',
           '  <span class="value"></span>',
           '  <a class="editicon sprite edit action-icon hidden"',
           '  href="#">Edit</a>',
           '</span></li>',
           '{{/information_types}}'].join(' ');
    },

    // Render the popup widget to pick the sharing permission for an
    // access policy.
    render_grantee_policy: function(
            grantee, policy, current_value) {
        var information_types = this.get('information_types');
        var sharing_permissions = this.get('sharing_permissions');
        var choice_items = [];
        Y.each(sharing_permissions, function(title, value) {
            var source_name =
                '<strong>{policy_name}:</strong> {permission_name}';
            choice_items.push({
                value: value,
                name: title,
                source_name: Y.Lang.sub(source_name,
                    {policy_name: information_types[policy],
                     permission_name: title})
            });
        });

        var id = 'permission-'+grantee.name;
        var grantee_row = this.get('grantee_table').one('[id="' + id + '"]');
        var contentBox = grantee_row.one(
            '[id="' + policy + '-' + id + '"]');
        var value_location = contentBox.one('.value');
        var editable = LP.cache.has_edit_permission;
        var editicon = contentBox.one('a.editicon');
        if (editable) {
            editicon.removeClass('hidden');
        }
        var clickable_content = (this.get('write_enabled') && editable);
        var permission_edit = new Y.ChoiceSource({
            clickable_content: clickable_content,
            contentBox: contentBox,
            value_location: value_location,
            editicon: editicon,
            value: current_value,
            title: "Share " + information_types[policy] + " with "
                + grantee.display_name,
            items: choice_items,
            elementToFlash: contentBox,
            backgroundColor: '#FFFF99'
        });
        permission_edit.render();
        var self = this;
        permission_edit.on('save', function(e) {
            var permission = permission_edit.get('value');
            self.fire(
                UPDATE_PERMISSION, grantee.self_link, policy, permission);
        });
    },

    // Render the access policy values for the grantees.
    render_sharing_info: function(grantees) {
        var self = this;
        Y.Array.forEach(grantees, function(grantee) {
            self.render_grantee_sharing_info(grantee);
        });
    },

    // Render the access policy values for a grantee.
    render_grantee_sharing_info: function(grantee) {
        var grantee_policies = grantee.permissions;
        var self = this;
        Y.each(grantee_policies, function(policy_value, policy) {
            self.render_grantee_policy(grantee, policy, policy_value);
        });
    },

    _replace_content: function(grantees) {
        LP.cache.grantee_data = grantees;
        this._render_grantees(grantees);
        this.bindUI();
    },

    renderUI: function() {
        this._render_grantees(this.get('grantees'));
    },

    _render_grantees: function(grantees) {
        var grantee_table = this.get('grantee_table');
        var partials = {
            grantee_access_policies:
                this.get('grantee_policy_template'),
            grantee_row: this.get('grantee_row_template')
        };
        this._prepareGranteeDisplayData(grantees);
        var html = Y.lp.mustache.to_html(
            this.get('grantee_table_template'),
            {grantees: grantees}, partials);
        var table_node = Y.Node.create(html);
        if (grantees.length === 0) {
            table_node.one('tbody').appendChild(
                this.get('grantee_table_empty_row'));
        }
        grantee_table.replace(table_node);
        this.render_sharing_info(grantees);
        this._update_editable_status();
        this.set('grantees', grantees);
    },

    bindUI: function() {
        var grantee_table = this.get('grantee_table');
        // Bind the update and delete grantee links.
        if (!this.get('write_enabled')) {
            return;
        }
        var self = this;
        grantee_table.delegate('click', function(e) {
            e.halt();
            var delete_link = e.currentTarget;
            var grantee_link = delete_link.getAttribute('data-self_link');
            var person_name = delete_link.getAttribute('data-person_name');
            self.fire(REMOVE_GRANTEE, delete_link, grantee_link, person_name);
        }, 'span[id^=remove-] a');
        grantee_table.delegate('click', function(e) {
            e.halt();
            var update_link = e.currentTarget;
            var grantee_link = update_link.getAttribute('data-self_link');
            var person_name = update_link.getAttribute('data-person_name');
            self.fire(UPDATE_GRANTEE, update_link, grantee_link, person_name);
        }, 'span[id^=update-] a');
    },

    syncUI: function() {
        // Examine the widget's data model and add any new grantees and delete
        // any which have been removed.
        var existing_grantees = this.get('grantees');
        var new_grantees = LP.cache.grantee_data;
        this._prepareGranteeDisplayData(new_grantees);
        var new_or_updated_grantees = [];
        var deleted_grantees = [];
        var self = this;
        Y.Array.each(new_grantees, function(grantee) {
            var existing_grantee =
                self._get_grantee_from_model(grantee.name, existing_grantees);
            if (!Y.Lang.isValue(existing_grantee)) {
                new_or_updated_grantees.push(grantee);
            } else {
                if (!self._permissions_equal(
                        grantee.permissions, existing_grantee.permissions)) {
                    new_or_updated_grantees.push(grantee);
                }
            }
        });
        Y.Array.each(existing_grantees, function(grantee) {
            var new_grantee =
                self._get_grantee_from_model(grantee.name, new_grantees);
            if (!Y.Lang.isValue(new_grantee)) {
                deleted_grantees.push(grantee);
            }
        });
        if (new_or_updated_grantees.length > 0) {
            this.update_grantees(new_or_updated_grantees);
        }
        if (deleted_grantees.length > 0) {
            this.delete_grantees(deleted_grantees, new_grantees.length === 0);
        }
        var current_total = existing_grantees.length;
        var total_delta = new_grantees.length - current_total;
        this.navigator.update_batch_totals(new_grantees, total_delta);
        this.set('grantees', new_grantees);
    },

    /**
     * Return true if the permission values in left do not match those in right.
     * @param left
     * @param right
     * @return {Boolean}
     * @private
     */
    _permissions_equal: function(left, right) {
        var result = true;
        Y.some(left, function(sharing_value, info_type) {
            var right_value = right[info_type];
            if (sharing_value !== right_value) {
                result = false;
                return true;
            }
            return false;
        });
        if (!result) {
            return false;
        }
        Y.some(right, function(sharing_value, info_type) {
            var _value = left[info_type];
            if (!Y.Lang.isValue(left[info_type])) {
                result = false;
                return true;
            }
            return false;
        });
        return result;
    },

    /**
     * The the named grantee exists in the model, return it.
     * @param grantee_name
     * @param model
     * @return {*}
     * @private
     */
    _get_grantee_from_model: function(grantee_name, model) {
        var grantee_data = null;
        Y.Array.some(model, function(grantee) {
            if (grantee.name === grantee_name) {
                grantee_data = grantee;
                return true;
            }
            return false;
        });
        return grantee_data;
    },

    // Transform the grantee information type data from the model into a form
    // that can be used with the handlebars template.
    _prepareGranteeDisplayData: function(grantees) {
        Y.Array.forEach(grantees, function(grantee) {
            var grantee_policies = grantee.permissions;
            var info_types = [];
            Y.each(grantee_policies, function(policy_value, policy) {
                info_types.push({policy: policy,
                                    grantee_name: grantee.name});
            });
            grantee.information_types = info_types;
        });
    },

    _update_editable_status: function() {
        var grantee_table = this.get('grantee_table');
        if (!this.get('write_enabled')) {
            grantee_table.all(
                '.sprite.add, .sprite.edit, .sprite.remove')
                .each(function(node) {
                    node.addClass('hidden');
            });
        }
    },

    // Add or update new grantees in the table.
    update_grantees: function(grantees) {
        this._prepareGranteeDisplayData(grantees);
        var update_node_selectors = [];
        var partials = {
            grantee_access_policies:
                this.get('grantee_policy_template')
        };
        var grantee_table = this.get('grantee_table');
        var self = this;
        Y.Array.each(grantees, function(grantee) {
            var row_html = Y.lp.mustache.to_html(
                self.get('grantee_row_template'), grantee, partials);
            var new_table_row = Y.Node.create(row_html);
            var row_node = grantee_table
                .one('tr[id=permission-' + grantee.name + ']');
            if (Y.Lang.isValue(row_node)) {
                row_node.replace(new_table_row);
            } else {
                // Remove the "No grantees..." row if it's there.
                var not_shared_row = grantee_table.one(
                    'tr#grantee-table-not-shared');
                if (Y.Lang.isValue(not_shared_row)) {
                    not_shared_row.remove(true);
                }
                var first_row = grantee_table.one('tbody>:first-child');
                if (Y.Lang.isValue(first_row)) {
                    first_row.insertBefore(new_table_row, first_row);
                } else {
                    grantee_table.one('tbody').appendChild(new_table_row);
                }
            }
            update_node_selectors.push(
                'tr[id=permission-' + grantee.name + ']');
            self.render_grantee_sharing_info(grantee);
        });
        this._update_editable_status();
        var anim_duration = this.get('anim_duration');
        if (anim_duration === 0) {
            return;
        }
        var anim = Y.lp.anim.green_flash(
            {node: grantee_table.all(
                update_node_selectors.join(',')), duration:anim_duration});
        anim.run();
    },

    // Delete the specified grantees from the table.
    delete_grantees: function(grantees, all_rows_deleted) {
        var deleted_row_selectors = [];
        var grantee_table = this.get('grantee_table');
        var that = this;
        Y.Array.each(grantees, function(grantee) {
            var selector = 'tr[id=permission-' + grantee.name + ']';
            var table_row = grantee_table.one(selector);
            if (Y.Lang.isValue(table_row)) {
                deleted_row_selectors.push(selector);
            }
        });
        if (deleted_row_selectors.length === 0) {
            return;
        }
        var rows_to_delete = grantee_table.all(deleted_row_selectors.join(','));
        var delete_rows = function() {
            rows_to_delete.remove(true);
            if (all_rows_deleted === true) {
                var empty_table_row = that.get('grantee_table_empty_row');
                grantee_table.one('tbody')
                    .appendChild(empty_table_row);
            }
        };
        var anim_duration = this.get('anim_duration');
        if (anim_duration === 0 ) {
            delete_rows();
            return;
        }
        var anim = Y.lp.anim.green_flash(
            {node: rows_to_delete, duration:anim_duration});
        anim.on('end', function() {
            delete_rows();
        });
        anim.run();
    },

    // An error occurred performing an operation on a grantee.
    display_error: function(grantee_name, error_msg) {
        var grantee_table = this.get('grantee_table');
        var grantee_row = null;
        if (Y.Lang.isValue(grantee_name)) {
            grantee_row = grantee_table.one('tr[id=permission-'
                + grantee_name + ']');
        }
        Y.lp.app.errors.display_error(grantee_row, error_msg);
    }
});

GranteeTableWidget.NAME = NAME;
GranteeTableWidget.UPDATE_GRANTEE = UPDATE_GRANTEE;
GranteeTableWidget.UPDATE_PERMISSION = UPDATE_PERMISSION;
GranteeTableWidget.REMOVE_GRANTEE = REMOVE_GRANTEE;
namespace.GranteeTableWidget = GranteeTableWidget;

}, "0.1", { "requires": [
    'node', 'event', 'collection', 'json', 'lp.ui.choiceedit',
    'lp.app.errors', 'lp.mustache', 'lp.registry.sharing.granteepicker',
    'lp.registry.sharing.granteelisting_navigator'
] });

