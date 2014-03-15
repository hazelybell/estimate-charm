/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Disclosure infrastructure.
 *
 * @module lp.registry.sharing
 */

YUI.add('lp.registry.sharing.sharingdetailsview', function(Y) {

var namespace = Y.namespace('lp.registry.sharing.sharingdetailsview');

function SharingDetailsView(config) {
    SharingDetailsView.superclass.constructor.apply(this, arguments);
}

SharingDetailsView.ATTRS = {
    lp_client: {
        value: new Y.lp.client.Launchpad()
    },

    sharing_details_table: {
        value: null
    }
};

Y.extend(SharingDetailsView, Y.Widget, {

    renderUI: function() {
        var ns = Y.lp.registry.sharing.sharingdetails;
        var details_table = new ns.SharingDetailsTable({
            bugs: LP.cache.bugs,
            branches: LP.cache.branches,
            person_name: LP.cache.grantee.displayname,
            specifications: LP.cache.specifications,
            write_enabled: true
        });
        this.set('sharing_details_table', details_table);
        details_table.render();
    },

    bindUI: function() {
        var self = this;
        var sharing_details_table = this.get('sharing_details_table');
        var ns = Y.lp.registry.sharing.sharingdetails;
        sharing_details_table.subscribe(
            ns.SharingDetailsTable.REMOVE_GRANT, function(e) {
                self.confirm_grant_removal(
                    e.details[0], e.details[1], e.details[2], e.details[3]);
        });
    },

    syncUI: function() {
        var sharing_details_table = this.get('sharing_details_table');
        sharing_details_table.syncUI();
    },

    // A common error handler for XHR operations.
    _error_handler: function(artifact_uri, artifact_type) {
        var artifact_id;
        switch (artifact_type) {
            case 'bug':
                Y.Array.some(LP.cache.bugs, function(bug) {
                    if (bug.self_link === artifact_uri) {
                        artifact_id = bug.bug_id;
                        return true;
                    }
                });
                break;
            case 'branch':
                Y.Array.some(LP.cache.branches, function(branch) {
                    if (branch.self_link === artifact_uri) {
                        artifact_id = branch.branch_id;
                        return true;
                    }
                });
                break;
            case 'spec':
                Y.Array.some(LP.cache.specifications, function(spec) {
                    if (spec.self_link === artifact_uri) {
                        artifact_id = spec.id;
                        return true;
                    }
                });
                break;
            default:
                throw('Invalid artifact type.' + artifact_type);
        }

        var error_handler = new Y.lp.client.ErrorHandler();
        var self = this;
        error_handler.showError = function(error_msg) {
            self.get('sharing_details_table')
                .display_error(artifact_id, artifact_type, error_msg);
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
     * Prompt the user to confirm the removal of access to the selected
     * artifact.
     *
     * @method confirm_grant_removal
     * @param delete_link
     * @param artifact_uri
     * @param artifact_name
     * @param artifact_type
     */
    confirm_grant_removal: function(delete_link, artifact_uri,
                                    artifact_name, artifact_type) {
        var confirm_text_template = [
            '<p class="block-sprite large-warning">',
            '    Do you really want to stop sharing',
            '    "{artifact}" with {person_name}?',
            '</p>'
            ].join('');
        var person_name = LP.cache.grantee.displayname;
        var confirm_text = Y.Lang.sub(confirm_text_template,
                {artifact: artifact_name,
                 person_name: person_name});
        var self = this;
        var co = new Y.lp.app.confirmationoverlay.ConfirmationOverlay({
            submit_fn: function() {
                self.perform_remove_grant(
                    delete_link, artifact_uri, artifact_type);
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
     * @method remove_grant_success
     * @param artifact_uri
     */
    remove_grant_success: function(artifact_uri) {
        var bugs_data = LP.cache.bugs;
        var self = this;
        Y.Array.some(bugs_data, function(bug, index) {
            if (bug.self_link === artifact_uri) {
                bugs_data.splice(index, 1);
                self.syncUI();
                return true;
            }
        });
        var branch_data = LP.cache.branches;
        Y.Array.some(branch_data, function(branch, index) {
            if (branch.self_link === artifact_uri) {
                branch_data.splice(index, 1);
                self.syncUI();
                return true;
            }
        });
        var spec_data = LP.cache.specifications;
        Y.Array.some(spec_data, function(spec, index) {
            if (spec.self_link === artifact_uri) {
                spec_data.splice(index, 1);
                self.syncUI();
                return true;
            }
        });
    },

    /**
     * Make a server call to remove access to the specified artifact.
     * @method perform_remove_grantee
     * @param delete_link
     * @param artifact_uri
     * @param artifact_type
     */
    perform_remove_grant: function(delete_link, artifact_uri, artifact_type) {
        var self = this;
        var error_handler = this._error_handler(artifact_uri, artifact_type);
        var bugs = [];
        var branches = [];
        var specifications = [];
        switch (artifact_type) {
            case 'bug':
                bugs = [artifact_uri];
                break;
            case 'branch':
                branches = [artifact_uri];
                break;
            case 'spec':
                specifications = [artifact_uri];
                break;
            default:
                throw('Invalid artifact type.' + artifact_type);
        }

        var y_config =  {
            on: {
                start: Y.bind(
                    self._show_delete_spinner, namespace, delete_link),
                end: Y.bind(self._hide_delete_spinner, namespace, delete_link),
                success: function() {
                    self.remove_grant_success(artifact_uri);
                },
                failure: error_handler.getFailureHandler()
            },
            parameters: {
                pillar: LP.cache.pillar.self_link,
                grantee: LP.cache.grantee.self_link,
                bugs: bugs,
                branches: branches,
                specifications: specifications
            }
        };
        this.get('lp_client').named_post(
            '/+services/sharing', 'revokeAccessGrants', y_config);
    }
});

SharingDetailsView.NAME = 'sharingDetailsView';
namespace.SharingDetailsView = SharingDetailsView;

}, "0.1", {
    requires: ['node', 'selector-css3', 'lp.client', 'lp.mustache',
               'lp.registry.sharing.sharingdetails',
               'lp.app.confirmationoverlay']
});

