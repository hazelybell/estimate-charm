/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Disclosure infrastructure.
 *
 * @module lp.registry.sharing
 */

YUI.add('lp.registry.sharing.pillarsharingview', function(Y) {

var namespace = Y.namespace('lp.registry.sharing.pillarsharingview');

function PillarSharingView(config) {
    PillarSharingView.superclass.constructor.apply(this, arguments);
}

PillarSharingView.ATTRS = {
    lp_client: {
        value: new Y.lp.client.Launchpad()
    },

    grantee_picker: {
        value: null
    },

    grantee_table: {
        value: null
    },

    information_types_by_value: {
        value: null
    },

    sharing_permissions_by_value: {
        value: null
    },

    legacy_sharing_policy_description: {
        value: "Legacy project sharing policy will " +
            "continue to be used until a new policy is configured."
    }
};

Y.extend(PillarSharingView, Y.Widget, {

    initializer: function(config) {
        var information_types_by_value = {};
        Y.Array.each(LP.cache.information_types, function(info_type) {
            information_types_by_value[info_type.value] = info_type.title;
        });
        this.set(
            'information_types_by_value', information_types_by_value);
        var sharing_permissions_by_value = {};
        Y.Array.each(LP.cache.sharing_permissions, function(permission) {
            sharing_permissions_by_value[permission.value] = permission.title;
        });
        this.set(
            'sharing_permissions_by_value', sharing_permissions_by_value);

        var vocab;
        var header;
        var steptitle;
        if (Y.Lang.isValue(config)) {
            if (Y.Lang.isValue(config.header)) {
                header = config.header;
            } else {
                throw new Error(
                    "Missing header config value for grantee picker");
            }
            if (Y.Lang.isValue(config.steptitle)) {
                steptitle = config.steptitle;
            } else {
                throw new Error(
                    "Missing steptitle config value for grantee picker");
            }
            if (Y.Lang.isValue(config.vocabulary)) {
                vocab = config.vocabulary;
            } else {
                throw new Error(
                    "Missing vocab config value for grantee picker");
            }
        } else {
            throw new Error("Missing config for grantee picker");
        }
        var self = this;
        var new_config = Y.merge(config, {
            align: {
                points: [Y.WidgetPositionAlign.CC,
                         Y.WidgetPositionAlign.CC]
            },
            progressbar: true,
            progress: 50,
            headerContent: Y.Node.create("<h2></h2>").set('text', header),
            steptitle: steptitle,
            zIndex: 1000,
            visible: false,
            information_types: LP.cache.information_types,
            sharing_permissions: LP.cache.sharing_permissions,
            save: function(result) {
                self.save_sharing_selection(
                    result.api_uri, result.selected_permissions);
            }
        });
        var ns = Y.lp.registry.sharing.granteepicker;
        var picker = new ns.GranteePicker(new_config);
        Y.lp.app.picker.setup_vocab_picker(picker, vocab, new_config);
        this.set('grantee_picker', picker);
    },

    renderUI: function() {
        var grantee_data = LP.cache.grantee_data;
        var otns = Y.lp.registry.sharing.granteetable;
        var grantee_table = new otns.GranteeTableWidget({
            pillar_name: LP.cache.context.display_name,
            grantees: grantee_data,
            sharing_permissions:
                this.get('sharing_permissions_by_value'),
            information_types: this.get('information_types_by_value'),
            write_enabled: true
        });
        this.set('grantee_table', grantee_table);
        grantee_table.render();
        Y.one('#add-grantee-link').removeClass('hidden');
        this.bug_sharing_policy_widget
                = this._render_sharing_policy('bug', 'Bug');
        this.branch_sharing_policy_widget
                = this._render_sharing_policy('branch', 'Branch');
        this.specification_sharing_policy_widget
                = this._render_sharing_policy('specification', 'Specification');
    },

    // Render the sharing policy choice popup.
    _render_sharing_policy: function(artifact_type, artifact_title) {
        var sharing_policy_row = Y.one(
                '#' + artifact_type + '-sharing-policy-row');
        if (!Y.Lang.isValue(sharing_policy_row)) {
            return null;
        }
        sharing_policy_row.removeClass('hidden');
        var current_value
                = LP.cache.context[artifact_type + '_sharing_policy'];
        this._update_policy_portlet(artifact_type, current_value);
        var contentBox = sharing_policy_row.one(
                '#' + artifact_type + '-sharing-policy');
        var value_location = contentBox.one('.value');
        var editicon = contentBox.one('a.editicon');
        editicon.removeClass('hidden');
        var choice_items = [];
        if (!Y.Lang.isValue(current_value)) {
            choice_items.push({
                value: 'LEGACY',
                name: 'Legacy policy',
                description: this.get('legacy_sharing_policy_description'),
                description_css_class: 'choice-description'
            });
        }
        choice_items.push.apply(
                choice_items, this.getSharingPolicyInformation(artifact_type));
        var edit_permission = LP.cache.has_edit_permission;
        var editable = (edit_permission && choice_items.length> 1);
        var policy_edit = new Y.ChoiceSource({
            flashEnabled: false,
            clickable_content: editable,
            contentBox: contentBox,
            value_location: value_location,
            editicon: editicon,
            value: current_value || 'LEGACY',
            title: artifact_title + " sharing policy",
            items: choice_items,
            elementToFlash: contentBox,
            backgroundColor: '#FFFF99'
        });
        policy_edit.render();
        if (!editable && Y.Lang.isValue(editicon)) {
            editicon.addClass('hidden');
        }
        return policy_edit;
    },

    bindUI: function() {
        var self = this;
        var share_link = Y.one('#add-grantee-link');
        share_link.on('click', function(e) {
            e.preventDefault();
            self.get('grantee_picker').show();
        });
        var grantee_table = this.get('grantee_table');
        var otns = Y.lp.registry.sharing.granteetable;
        grantee_table.subscribe(
            otns.GranteeTableWidget.REMOVE_GRANTEE, function(e) {
                self.confirm_grantee_removal(
                    e.details[0], e.details[1], e.details[2]);
        });
        grantee_table.subscribe(
            otns.GranteeTableWidget.UPDATE_GRANTEE, function(e) {
                self.update_grantee_interaction(
                    e.details[0], e.details[1], e.details[2]);
        });
        grantee_table.subscribe(
            otns.GranteeTableWidget.UPDATE_PERMISSION, function(e) {
                var permissions = {};
                permissions[e.details[1]] = e.details[2];
                self.save_sharing_selection(e.details[0], permissions);
        });
        // Hook up the sharing policy popups.
        if (this.bug_sharing_policy_widget !== null) {
            this.bug_sharing_policy_widget.on('save', function(e) {
                var policy = self.bug_sharing_policy_widget.get('value');
                self.save_sharing_policy(
                    self.bug_sharing_policy_widget, 'bug', policy);
            });
        }
        if (this.branch_sharing_policy_widget !== null) {
            this.branch_sharing_policy_widget.on('save', function(e) {
                var policy = self.branch_sharing_policy_widget.get('value');
                self.save_sharing_policy(
                    self.branch_sharing_policy_widget, 'branch', policy);
            });
        }
        if (this.specification_sharing_policy_widget !== null) {
            this.specification_sharing_policy_widget.on('save', function(e) {
                var policy = self.specification_sharing_policy_widget.get(
                    'value');
                self.save_sharing_policy(
                    self.specification_sharing_policy_widget, 'specification',
                    policy);
            });
        }
    },

    syncUI: function() {
        var grantee_table = this.get('grantee_table');
        grantee_table.syncUI();
        var invisible_info_types = LP.cache.invisible_information_types;
        var exiting_warning = Y.one('#sharing-warning');
        if (Y.Lang.isObject(exiting_warning)) {
            exiting_warning.remove(true);
        }
        if (Y.Lang.isArray(invisible_info_types)
            && invisible_info_types.length > 0) {
            var warning_node = Y.Node.create(
                this._make_invisible_artifacts_warning(invisible_info_types));
            var sharing_header = Y.one('#sharing-header');
            sharing_header.insert(warning_node, 'after');
        }
    },

    /**
     * Extract from the request cache the sharing policies for the artifact
     * type.
     * @param artifact_type
     * @return {Array}
     */
    getSharingPolicyInformation: function(artifact_type) {
        var info = [];
        Y.each(LP.cache[artifact_type + '_sharing_policies'],
            function(policy) {
                info.push({
                    value: policy.title,
                    name: policy.title,
                    description: policy.description,
                    description_css_class: 'choice-description'
                });
        });
        return info;
    },

    _make_invisible_artifacts_warning: function(information_types) {
        return Y.lp.mustache.to_html([
        "<div id='sharing-warning'",
        "class='block-sprite large-warning' style='margin-top: 1em'>",
        "<p>",
        "These information types are not shared with anyone:</p>",
        "<ul class='bulleted'>",
        "    {{#information_types}}",
        "        <li>{{.}}</li>",
        "    {{/information_types}}",
        "</ul>",
        "<p>These information types should be shared with someone to ",
        "ensure there can be no invisible bugs or branches.</p>",
        "</div>"
        ].join(''), {
            information_types: information_types
        });
    },

    /**
     * Ensure the sharing policy portlet for the artifact type is up-to-date.
     * @param artifact_type
     * @param value
     * @private
     */
    _update_policy_portlet: function(artifact_type, value) {
        var desc_node = Y.one(
                '#' + artifact_type + '-sharing-policy-description');
        var desc_text = this.get('legacy_sharing_policy_description');
        if (Y.Lang.isValue(value)) {
            Y.Array.some(LP.cache[artifact_type + '_sharing_policies'],
                    function(policy_info) {
                if (policy_info.title === value) {
                    desc_text = policy_info.description;
                    return true;
                }
                return false;
            });
        }
        desc_node.set('text', desc_text);
    },

    /**
     * A new sharing policy has been selected so save it.
     * @param widget
     * @param artifact_type
     * @param value
     */
    save_sharing_policy: function(widget, artifact_type, value) {
        var value_key = artifact_type + '_sharing_policy';
        var error_handler = new Y.lp.client.ErrorHandler();
        error_handler.showError = function(error_msg) {
            actionicon.addClass('edit');
            actionicon.removeClass('spinner');
            var portlet_id = '#' + artifact_type + 'sharing-policy-portlet';
            Y.lp.app.errors.display_error(
                Y.one(portlet_id), error_msg);
        };
        var self = this;
        error_handler.handleError = function(ioId, response) {
            var orig_value = LP.cache.context[value_key];
            if (!Y.Lang.isValue(orig_value)) {
                orig_value = 'LEGACY';
            }
            widget.set('value', orig_value);
            widget._showFailed();
            self._update_policy_portlet(artifact_type, orig_value);
            return false;
        };
        this._update_policy_portlet(artifact_type, value);
        var pillar_uri = LP.cache.context.self_link;
        var actionicon = widget.get("actionicon");
        var parameters = {
            pillar: pillar_uri};
        parameters[value_key] = value;
        var y_config =  {
            on: {
                start: function() {
                    actionicon.removeClass('edit');
                    actionicon.addClass('spinner');
                },
                success: function() {
                    self._reload();
                },
                failure: error_handler.getFailureHandler()
            },
            parameters: parameters
        };
        this.get('lp_client').named_post(
            '/+services/sharing', 'updatePillarSharingPolicies',
            y_config);
    },

    // Override for testing.
    _reload: function() {
        window.location.reload();
    },

    // A common error handler for XHR operations.
    _error_handler: function(person_uri) {
        var grantee_data = LP.cache.grantee_data;
        var error_handler = new Y.lp.client.ErrorHandler();
        var grantee_name = null;
        Y.Array.some(grantee_data, function(grantee) {
            if (grantee.self_link === person_uri) {
                grantee_name = grantee.name;
                return true;
            }
        });
        var self = this;
        error_handler.showError = function(error_msg) {
            self.get('grantee_table').display_error(grantee_name, error_msg);
        };
        return error_handler;
    },

    /**
     * Show a spinner next to the delete icon.
     *
     * @method _show_delete_spinner
     */
    _show_delete_spinner: function(delete_link) {
        var spinner_node = Y.Node.create(
        '<img class="spinner" src="/@@/spinner" alt="Removing..." />');
        delete_link.insertBefore(spinner_node, delete_link);
        delete_link.addClass('hidden');
    },

    /**
     * Hide the delete spinner.
     *
     * @method _hide_delete_spinner
     */
    _hide_delete_spinner: function(delete_link) {
        delete_link.removeClass('hidden');
        var spinner = delete_link.get('parentNode').one('.spinner');
        if (Y.Lang.isValue(spinner)) {
            spinner.remove();
        }
    },

    /**
     * Prompt the user to confirm the removal of the selected grantee.
     *
     * @method confirm_grantee_removal
     */
    confirm_grantee_removal: function(delete_link, person_uri, person_name) {
        var confirm_text_template = [
            '<p class="block-sprite large-warning">',
            '    Do you really want to stop sharing',
            '    "{pillar}" with {person_name}?',
            '</p>'
            ].join('');
        var confirm_text = Y.Lang.sub(confirm_text_template,
                {pillar: LP.cache.context.display_name,
                 person_name: person_name});
        var self = this;
        var co = new Y.lp.app.confirmationoverlay.ConfirmationOverlay({
            submit_fn: function() {
                self.perform_remove_grantee(delete_link, person_uri);
            },
            form_content: confirm_text,
            headerContent: '<h2>Stop sharing</h2>',
            submit_text: 'Yes',
            cancel_text: 'No'
        });
        co.show();
    },

    /**
     * The server call to remove the specified grantee has succeeded.
     * Update the model and view.
     * @method remove_grantee_success
     * @param person_uri
     */
    remove_grantee_success: function(person_uri) {
        var grantee_data = LP.cache.grantee_data;
        var self = this;
        Y.Array.some(grantee_data, function(grantee, index) {
            if (grantee.self_link === person_uri) {
                grantee_data.splice(index, 1);
                self.syncUI();
                return true;
            }
        });
    },

    /**
     * Make a server call to remove the specified grantee.
     * @method perform_remove_grantee
     * @param delete_link
     * @param person_uri
     */
    perform_remove_grantee: function(delete_link, person_uri) {
        var error_handler = this._error_handler(person_uri);
        var pillar_uri = LP.cache.context.self_link;
        var self = this;
        var y_config =  {
            on: {
                start: Y.bind(
                    self._show_delete_spinner, namespace, delete_link),
                end: Y.bind(self._hide_delete_spinner, namespace, delete_link),
                success: function(invisible_information_types) {
                    LP.cache.invisible_information_types =
                        invisible_information_types;
                    self.remove_grantee_success(person_uri);
                },
                failure: error_handler.getFailureHandler()
            },
            parameters: {
                pillar: pillar_uri,
                grantee: person_uri
            }
        };
        this.get('lp_client').named_post(
            '/+services/sharing', 'deletePillarGrantee', y_config);
    },

    /**
     * Show a spinner for a sharing update operation.
     *
     * @method _show_sharing_spinner
     */
    _show_sharing_spinner: function() {
        var spinner_node = Y.Node.create(
        '<img class="spinner" src="/@@/spinner" alt="Saving..." />');
        var sharing_header = Y.one('#grantee-table th:nth-child(2)');
        sharing_header.appendChild(spinner_node, sharing_header);
    },

    /**
     * Hide the sharing spinner.
     *
     * @method _hide_hiding_spinner
     */
    _hide_hiding_spinner: function() {
        var spinner = Y.one('#grantee-table th .spinner');
        if (spinner !== null) {
            spinner.remove();
        }
    },

    /**
     * The server call to add the specified grantee has succeeded.
     * Update the model and view.
     * @method save_sharing_selection_success
     * @param updated_grantee
     */
    save_sharing_selection_success: function(updated_grantee) {
        var grantee_data = LP.cache.grantee_data;
        var grantee_replaced = false;
        Y.Array.some(grantee_data, function(grantee, index) {
            if (updated_grantee.name === grantee.name) {
                grantee_replaced = true;
                grantee_data.splice(index, 1, updated_grantee);
                return true;
            }
            return false;
        });
        if (!grantee_replaced) {
            grantee_data.splice(0, 0, updated_grantee);
        }
        this.syncUI();
    },

    /**
     * Make a server call to add the specified grantee and access policy.
     * @method save_sharing_selection
     * @param person_uri
     * @param permissions
     */
    save_sharing_selection: function(person_uri, permissions) {
        var error_handler = this._error_handler(person_uri);
        var pillar_uri = LP.cache.context.self_link;
        person_uri = Y.lp.client.normalize_uri(person_uri);
        person_uri = Y.lp.client.get_absolute_uri(person_uri);
        var information_types_by_value =
            this.get('information_types_by_value');
        var sharing_permissions_by_value =
            this.get('sharing_permissions_by_value');
        var permission_params = [];
        Y.each(permissions, function(permission, info_type) {
            permission_params.push(
                [information_types_by_value[info_type],
                sharing_permissions_by_value[permission]]);
        });
        var self = this;
        var y_config =  {
            on: {
                start: Y.bind(self._show_sharing_spinner, namespace),
                end: Y.bind(self._hide_hiding_spinner, namespace),
                success: function(result_data) {
                    LP.cache.invisible_information_types =
                        result_data.invisible_information_types;
                    var grantee_entry = result_data.grantee_entry;
                    if (!Y.Lang.isValue(grantee_entry)) {
                        self.remove_grantee_success(person_uri);
                    } else {
                        self.save_sharing_selection_success(grantee_entry);
                    }
                },
                failure: error_handler.getFailureHandler()
            },
            parameters: {
                pillar: pillar_uri,
                grantee: person_uri,
                permissions: permission_params
            }
        };
        this.get('lp_client').named_post(
            '/+services/sharing', 'sharePillarInformation', y_config);
    },

    /**
     * The user has clicked the (+) icon for a grantee. We display the sharing
     * picker to allow the sharing permissions to be updated.
     * @param update_link
     * @param person_uri
     * @param person_name
     */
    update_grantee_interaction: function(update_link, person_uri, person_name) {
        var grantee_data = LP.cache.grantee_data;
        var grantee_permissions = {};
        var disabled_some_types = [];
        Y.Array.some(grantee_data, function(grantee) {
            var full_person_uri = Y.lp.client.normalize_uri(person_uri);
            full_person_uri = Y.lp.client.get_absolute_uri(full_person_uri);
            if (grantee.self_link !== full_person_uri) {
                return false;
            }
            grantee_permissions = grantee.permissions;
            // Do not allow the user to choose 'Some' unless there are shared
            // artifacts of that type.
            Y.Array.each(LP.cache.information_types, function(info_type) {
                if (Y.Array.indexOf(
                    grantee.shared_artifact_types, info_type.value) < 0) {
                    disabled_some_types.push(info_type.value);
                }
            });
            return true;
        });
        var allowed_permissions = [];
        Y.Array.each(LP.cache.sharing_permissions, function(permission) {
            allowed_permissions.push(permission.value);
        });
        this.get('grantee_picker').show({
            first_step: 2,
            grantee: {
                person_uri: person_uri,
                person_name: person_name
            },
            grantee_permissions: grantee_permissions,
            allowed_permissions: allowed_permissions,
            disabled_some_types: disabled_some_types
        });
    }
});

PillarSharingView.NAME = 'pillarSharingView';
namespace.PillarSharingView = PillarSharingView;

}, "0.1", { "requires": [
    'node', 'selector-css3', 'lp.client', 'lp.mustache', 'lp.ui.picker-base',
    'lp.app.picker', 'lp.mustache', 'lp.registry.sharing.granteepicker',
    'lp.registry.sharing.granteetable', 'lp.app.confirmationoverlay'
    ]});

