/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Provide functionality for picking a bug.
 *
 * @module bugs
 * @submodule bug_picker
 */
YUI.add('lp.bugs.duplicates', function(Y) {

var namespace = Y.namespace('lp.bugs.duplicates');
var superclass = Y.lp.bugs.bug_picker.BugPicker;

/**
 * A widget to allow a user to choose a bug.
 * This widget does no rendering itself; it is used to enhance existing HTML.
 */
namespace.DuplicateBugPicker = Y.Base.create(
    "duplicateBugPickerWidget", Y.lp.bugs.bug_picker.BugPicker, [], {
    initializer: function(cfg) {
        this.lp_client = new Y.lp.client.Launchpad(cfg);
    },

    bindUI: function() {
        superclass.prototype.bindUI.apply(this, arguments);
        var that = this;
        this.subscribe(
            Y.lp.bugs.bug_picker.BugPicker.SAVE, function(e) {
            e.halt();
            that.set('progress', 100);
            var bug_data = e.details[0];
            var bug_id = bug_data.id;
            var bug_title = bug_data.bug_summary;
            that._submit_bug(bug_id, bug_title, that.save_button);
        });
        this.subscribe(
            Y.lp.bugs.bug_picker.BugPicker.REMOVE, function(e) {
            e.halt();
            that.set('progress', 100);
            that._submit_bug('', null, that.remove_link);
        });
        this._connect_links();
    },

    // Wire up the edit and remove links.
    _connect_links: function() {
        Y.all(
            '.change-duplicate-bug, .menu-link-mark-dupe, ' +
            '.remove-duplicate-bug').detachAll();
        var that = this;
        Y.all(
            '.remove-duplicate-bug').on('click', function(e) {
                e.halt();
                that._submit_bug('', null, e.currentTarget);
            });
        Y.all(
            '.change-duplicate-bug, .menu-link-mark-dupe').on('click',
            function(e) {
                e.halt();
                that.show();
            });
    },

    _syncResultsUI: function() {
        Y.lp.bugs.bug_picker.BugPicker.prototype._syncResultsUI.call(this);
        // Display warning about different project if required.
        var bug_data = this.get('results');
        if (!bug_data.length) {
            this._hide_bug_results();
            return;
        }
        bug_data = bug_data[0];
        if (!bug_data.different_pillars) {
            return;
        }
        var bug_details_table = this._results_box.one(
            'table.confirm-bug-details tbody');
        var different_project_warning =
            '<p id="different-project-warning" ' +
            'class="block-sprite large-warning">' +
            'This bug affects a different project to the bug you ' +
            'are specifying here.' +
            '</p>';
        var warning_node_row = Y.Node.create('<tr></tr>');
        warning_node_row.appendChild(
            Y.Node.create('<td></td>').setContent(different_project_warning));
        bug_details_table.appendChild(warning_node_row);
    },

    _bug_search_header: function() {
        var search_header = '<p class="search-header">' +
            'Marking this bug as a duplicate will, ' +
            'by default, hide it from search results listings.</p>';

        var duplicatesNode = this.get('duplicatesNode');
        if (Y.Lang.isValue(duplicatesNode)) {
            search_header +=
                '<p class="block-sprite large-warning">' +
                '<strong>Note:</strong> ' +
                'This bug has duplicates of its own. ' +
                'If you go ahead, they too will become duplicates of ' +
                'the bug you specify here.  This cannot be undone.' +
                '</p>';
        }
        return search_header +
            superclass.prototype._bug_search_header.call(this);
    },

    /**
     * Look up the selected bug and get the user to confirm that it is the one
     * they want.
     *
     * @param data
     * @private
     */
    _find_bug: function(data) {
        var new_dup_id = Y.Lang.trim(data.id);
        // Do some quick checks before we submit.
        var error = false;
        if (new_dup_id === LP.cache.bug.id.toString()) {
            this._hide_bug_results();
            this.set('error',
                'A bug cannot be marked as a duplicate of itself.');
            error = true;
        }
        var duplicate_of_link = LP.cache.bug.duplicate_of_link;
        var new_dupe_link
            = Y.lp.client.get_absolute_uri("/api/devel/bugs/" + new_dup_id);
        if (new_dupe_link === duplicate_of_link) {
            this._hide_bug_results();
            this.set('error',
                'This bug is already marked as a duplicate of bug ' +
                new_dup_id + '.');
            error = true;
        }
        if (error) {
            this.set('search_mode', false);
            return;
        }
        Y.lp.bugs.bug_picker.BugPicker.prototype._find_bug.call(this, data);
    },

    // A common error handler for XHR operations.
    _error_handler: function(widget) {
        var that = this;
        var error_handler = new Y.lp.client.ErrorHandler();
        error_handler.handleError = function(id, response) {
            var error_msg = response.responseText;
            if (response.status === 400) {
                var response_info = Y.JSON.parse(response.responseText);
                var dup_error = response_info.errors['field.duplicateof'];
                if (Y.Lang.isString(dup_error)) {
                    var error_info = dup_error.split('\n');
                    if (error_info.length === 1) {
                        error_msg = error_info;
                    } else {
                        error_msg = error_info.slice(1).join(' ');
                    }
                    that.set('error', error_msg);
                    return true;
                }
            }
            return false;
        };
        error_handler.showError = function(error_msg) {
            that.set('error', error_msg);
        };
        error_handler.clearProgressUI = function() {
            that._hide_bug_spinner(widget);
            var dupe_span = that.get('dupe_span');
            dupe_span.removeClass('update-in-progress-message');
            Y.all('.remove-duplicate-bug').each(function(node) {
                node.removeClass('update-in-progress-message');
                node.addClass('remove');
            });
            if (Y.Lang.isValue(this.remove_link)) {
                this.remove_link.removeClass('update-in-progress-message');
                this.remove_link.addClass('remove');
            }
        };
        return error_handler;
    },

    // Render the new bug task table.
    _render_bugtask_table: function(new_table) {
        var bugtask_table = Y.one('#affected-software');
        bugtask_table.replace(new_table);
        Y.lp.bugs.bugtask_index.setup_bugtask_table();
    },

    // Create the duplicate edit anchor.
    _dupe_edit_link: function(link_id, url, dup_id) {
        var template = [
                '<a id="{link_id}" ',
                'title="Edit or remove linked duplicate bug" ',
                'href={url} ',
                'class="sprite edit action-icon change-duplicate-bug"',
                'style="margin-left: 0">Edit</a>',
                '<span id="mark-duplicate-text">',
                'Duplicate of <a href="/bugs/{dup_id}">bug #{dup_id}</a>',
                '</span>'].join("");
        return Y.Lang.sub(template, {
            link_id: link_id,
            url: url,
            dup_id: dup_id
        });
    },

    // Create the duplicate removal anchor.
    _dupe_remove_link: function(link_id, url) {
        var template = [
                '<a id="{link_id}" ',
                'title="Edit or remove linked duplicate bug" ',
                'href={url} ',
                'class="sprite remove action-icon remove-duplicate-bug"',
                'style="float: right;">Remove</a>'].join("");
        return Y.Lang.sub(template, {
            link_id: link_id,
            url: url
        });
    },

    /**
     * Bug was successfully marked as a duplicate, update the UI.
     *
     * @method _submit_bug_success
     * @param response
     * @param new_dup_url
     * @param new_dup_id
     * @param new_dupe_title
     * @private
     */
    _submit_bug_success: function(response, new_dup_url,
                                           new_dup_id, new_dupe_title) {
        this._performDefaultSave();
        // Render the new bug tasks table.
        LP.cache.bug.duplicate_of_link = new_dup_url;
        this._render_bugtask_table(response.responseText);

        if (Y.Lang.isValue(new_dup_url)) {
            this._render_dupe_information(new_dup_id, new_dupe_title);
        } else {
            Y.all('.remove-duplicate-bug').each(function(node) {
                node.removeClass('update-in-progress-message');
                node.addClass('remove');
            });
            if (Y.Lang.isValue(this.remove_link)) {
                this.remove_link.removeClass('update-in-progress-message');
                this.remove_link.addClass('remove');
            }
            this._remove_dupe_information();
        }
        var dupe_portlet_node =
            this.get('portletNode').one('#mark-duplicate-text');
        this.set('dupe_portlet_node', dupe_portlet_node);
        this._connect_links();
    },

    // Render the new duplicate information.
    _render_dupe_information: function(new_dup_id, new_dupe_title) {
        var dupe_portlet_node = this.get('dupe_span').ancestor('li');
        var update_dup_url = dupe_portlet_node.one('a').get('href');
        dupe_portlet_node.empty(true);
        dupe_portlet_node.removeClass('sprite bug-dupe');
        var edit_link = this._dupe_edit_link(
            'change-duplicate-bug', update_dup_url, new_dup_id);
        dupe_portlet_node.appendChild(edit_link);
        var remove_link = this._dupe_remove_link(
            'remove-duplicate-bug', update_dup_url);
        dupe_portlet_node.appendChild(remove_link);
        var duplicatesNode = this.get('duplicatesNode');
        if (Y.Lang.isValue(duplicatesNode)) {
            duplicatesNode.remove(true);
        }
        this._show_comment_on_duplicate_warning(new_dup_id, new_dupe_title);
        this._show_bugtasks_duplicate_message(new_dup_id, new_dupe_title);
        var anim_duration = 1;
        if (!this.get('use_animation')) {
            anim_duration = 0;
        }
        Y.lp.anim.green_flash({
            node: '.bug-duplicate-details',
            duration: anim_duration
            }).run();
    },

    // Remove the old duplicate information.
    _remove_dupe_information: function() {
        var dupe_portlet_node = this.get('dupe_span').ancestor('li');
        var update_dup_url = dupe_portlet_node.one('a').get('href');
        dupe_portlet_node.addClass('sprite bug-dupe');
        dupe_portlet_node.setContent([
            '<span id="mark-duplicate-text">',
            '<a class="menu-link-mark-dupe js-action">',
            'Mark as duplicate</a></span>'].join(""));
        var edit_link = dupe_portlet_node.one('a');
        edit_link.set('href', update_dup_url);
        this._hide_comment_on_duplicate_warning();
        var that = this;
        var hide_dupe_message = function() {
            that._hide_bugtasks_duplicate_message();
        };
        if (!this.get('use_animation')) {
            hide_dupe_message();
            return;
        }
        var anim = Y.lp.anim.green_flash({
            node: '.bug-duplicate-details',
            duration: 1
            });
        anim.on('end', hide_dupe_message);
        anim.run();
    },

    /**
     * Update the bug duplicate via the LP API
     *
     * @method _submit_bug
     * @param new_dup_id
     * @param new_dupe_title
     * @param widget
     * @private
     */
    _submit_bug: function(new_dup_id, new_dupe_title, widget) {
        var dupe_span = this.get('dupe_span');
        var new_dup_url = null;

        var qs;
        var setting_dupe = new_dup_id !== '';
        if (setting_dupe) {
            var bug_link = LP.cache.bug.self_link;
            var last_slash_index = bug_link.lastIndexOf('/');
            new_dup_url = bug_link.slice(0, last_slash_index+1) + new_dup_id;
            qs = Y.lp.client.append_qs(
                '', 'field.actions.change', 'Set Duplicate');
            qs = Y.lp.client.append_qs(qs, "field.duplicateof", new_dup_id);
        } else {
            qs = Y.lp.client.append_qs(
                '', 'field.actions.remove', 'Remove Duplicate');
        }

        var that = this;
        var spinner = null;
        var error_handler = this._error_handler(widget);
        var submit_url = LP.cache.context.web_link + '/+duplicate';
        var y_config = {
            method: "POST",
            headers: {'Accept': 'application/json; application/xhtml'},
            on: {
                start: function() {
                    var dupe_span = that.get('dupe_span');
                    dupe_span.removeClass('sprite bug-dupe');
                    dupe_span.addClass('update-in-progress-message');
                    if (!setting_dupe) {
                        Y.all('.remove-duplicate-bug').each(function(node) {
                            node.removeClass('remove');
                            node.addClass('update-in-progress-message');
                        });
                        if (Y.Lang.isValue(that.remove_link)) {
                            that.remove_link.removeClass('remove');
                            that.remove_link
                                .addClass('update-in-progress-message');
                        }
                    }
                    that.set('error', null);
                    spinner = that._show_bug_spinner(widget);
                },
                success: function(id, response) {
                    that._submit_bug_success(
                        response, new_dup_url, new_dup_id, new_dupe_title);
                },
                failure: error_handler.getFailureHandler()
            },
            data: qs
        };
        var io_provider = this.lp_client.io_provider;
        io_provider.io(submit_url, y_config);
    },

    // Create the informational message to go at the top of the bug tasks
    // table.
    _duplicate_bug_info_message: function(dup_id, dup_title) {
        return Y.lp.mustache.to_html([
            '<span class="bug-duplicate-details ellipsis ',
            'single-line wide">',
            '<span class="sprite info"></span>',
            'This bug report is a duplicate of:&nbsp;',
            '<a href="/bugs/{{dup_id}}">Bug #{{dup_id}} {{dup_title}}',
            '</a></span>',
            '<a id="change-duplicate-bug-bugtasks"',
            '    href="+duplicate"',
            '    title="Edit or remove linked duplicate bug"',
            '    class="sprite edit action-icon standalone ',
            '    change-duplicate-bug">Edit</a>',
            '<a id="remove-duplicate-bug-bugtasks"',
            '    href="+duplicate"',
            '    title="Remove linked duplicate bug"',
            '    class="sprite remove action-icon standalone ',
            '    remove-duplicate-bug">Remove</a>'].join(" "),
            {dup_id: dup_id, dup_title: dup_title});
    },

    // Render the duplicate message at the top of the bug tasks table.
    _show_bugtasks_duplicate_message: function(dup_id, dup_title) {
        var dupe_info = Y.one("#bug-is-duplicate");
        if (Y.Lang.isValue(dupe_info)) {
            dupe_info.setContent(Y.Node.create(
                this._duplicate_bug_info_message(dup_id, dup_title)));
        }
    },

    // Hide the duplicate message at the top of the bug tasks table.
    _hide_bugtasks_duplicate_message: function() {
        var dupe_info = Y.one("#bug-is-duplicate");
        if (Y.Lang.isValue(dupe_info)) {
            dupe_info.empty();
        }
    },

    /*
     * Ensure that a warning about adding a comment to a duplicate bug
     * is displayed.
     *
     * @method _show_comment_on_duplicate_warning
     * @param bug_id
     * @param title
     * @private
     */
    _show_comment_on_duplicate_warning: function(bug_id, title) {
        var dupe_link = Y.lp.mustache.to_html(
            '<a title="{{title}}" id="duplicate-of-warning-link" ' +
            'href="/bugs/{{id}}" style="margin-right: 4px">bug #{{id}}.</a>',
            {id: bug_id, title: title});
        var new_duplicate_warning = Y.Node.create(
            ['<div class="block-sprite large-warning"',
             'id="warning-comment-on-duplicate">',
             'Remember, this bug report is a duplicate of ',
             dupe_link,
             '<br/>Comment here only if you think the duplicate status ',
             'is wrong.',
             '</div>'].join(''));
        var duplicate_warning = Y.one('#warning-comment-on-duplicate');
        if (!Y.Lang.isValue(duplicate_warning)) {
            var container = Y.one('#add-comment-form');
            var first_node = container.get('firstChild');
            container.insertBefore(new_duplicate_warning, first_node);
        } else {
            duplicate_warning.replace(new_duplicate_warning);
        }
    },

    /*
     * Ensure that no warning about adding a comment to a duplicate bug
     * is displayed.
     *
     * @method _hide_comment_on_duplicate_warning
     * @private
     */
    _hide_comment_on_duplicate_warning: function() {
        var duplicate_warning = Y.one('#warning-comment-on-duplicate');
        if (duplicate_warning !== null) {
            duplicate_warning.ancestor().removeChild(duplicate_warning);
        }
    }
}, {
    ATTRS: {
        // The rendered duplicate information.
        dupe_span: {
            getter: function() {
                return Y.one('#mark-duplicate-text');
            }
        },
        // Div containing duplicates of this bug.
        duplicatesNode: {
            getter: function() {
                return Y.one('#portlet-duplicates');
            }
        },
        portletNode: {
            getter: function() {
                return Y.one('#duplicate-actions');
            }
        },
        header_text: {
           value: 'Mark bug report as duplicate'
        },
        save_link_text: {
            value: 'Save Duplicate'
        },
        remove_link_text: {
            value: 'Bug is not a duplicate'
        },
        remove_link_visible: {
            getter: function() {
                var existing_dupe = LP.cache.bug.duplicate_of_link;
                return Y.Lang.isString(existing_dupe) && existing_dupe !== '';
            }
        },
        private_warning_message: {
            value:
            'Marking this bug as a duplicate of a private bug means '+
            'that it won\'t be visible to contributors and encourages '+
            'the reporting of more duplicate bugs.<br/>' +
            'Perhaps there is a public bug that can be used instead.'
        }
    }
});

}, "0.1", {"requires": [
    "base", "io", "oop", "node", "event", "json", "lp.app.errors",
    "lp.mustache", "lp.bugs.bug_picker", "lp.bugs.bugtask_index"]});
