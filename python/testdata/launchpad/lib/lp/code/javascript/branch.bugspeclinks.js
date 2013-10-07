/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Provide functionality for picking a bug.
 *
 * @module bugs
 * @submodule bug_picker
 */
YUI.add('lp.code.branch.bugspeclinks', function(Y) {

var namespace = Y.namespace('lp.code.branch.bugspeclinks');
var superclass = Y.lp.bugs.bug_picker.BugPicker;

/*
 * Extract the best candidate for a bug number from the branch name.
 */
namespace.extract_candidate_bug_id = function(branch_name) {
    // Extract all the runs of numbers in the branch name and sort by
    // descending length.
    var chunks = branch_name.split(/\D/g).sort(function (a, b) {
        return b.length - a.length;
    });
    var chunk, i;
    for (i=0; i<chunks.length; i++) {
        chunk = chunks[i];
        // Bugs with fewer than six digits aren't being created any more (by
        // Canonical's LP at least), but there are lots of open five digit
        // bugs so ignore runs of fewer than five digits in the branch name.
        if (chunk.length < 5) {
            break;
        }
        // Bug IDs don't start with a zero.
        if (chunk[0] !== '0') {
            return chunk;
        }
    }
    return null;
};


/**
 * A widget to allow a user to choose a bug to link to a branch.
 */
namespace.LinkedBugPicker = Y.Base.create(
    "linkedBugPickerWidget", Y.lp.bugs.bug_picker.BugPicker, [], {
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
            that._link_bug_to_branch(bug_id, this.save_button);
        });
        this.after('visibleChange', function() {
            if (this.get('visible')) {
                var guessed_bug_id =
                    namespace.extract_candidate_bug_id(LP.cache.context.name);
                if (Y.Lang.isValue(guessed_bug_id)) {
                    this._search_input.set('value', guessed_bug_id);
                    // Select the pre-filled bug number (if any) so that it will
                    // be replaced by anything the user types (getting the
                    // guessed bug number out of the way quickly if we guessed
                    // incorrectly).
                    this._search_input.set('selectionStart', 0);
                    this._search_input.set('selectionEnd', 999);
                }
            }
        });
        this._connect_remove_links();
    },

    /**
     * Wire up the links to remove a bug link.
     * @private
     */
    _connect_remove_links: function() {
        var that = this;
        Y.on('click', function(e) {
            e.halt();
            var bug_id = that._get_bug_id_from_remove_link(e.currentTarget);
            var bug_link =
                Y.lp.client.get_absolute_uri("/api/devel/bugs/" + bug_id);
            that._unlink_bug_from_branch(bug_id, bug_link);
        }, '#buglinks.actions .delete-buglink');
    },

    /*
     * Get the bug id for the link element.
     *
     * Since we control the element id, we don't have to use crazy reqexes or
     * something.
     */
    _get_bug_id_from_remove_link: function(link) {
        var dom_id = link.get('id');
        return dom_id.substr('delete-buglink-'.length, dom_id.length);
    },

    /**
     * Link a specified bug to the branch.
     * @param bug_id
     * @param widget
     * @private
     */
     _link_bug_to_branch: function(bug_id, widget) {
        var existing = Y.one('#buglink-' + bug_id);
        if (Y.Lang.isValue(existing)) {
            // Bug is already linked, don't do unnecessary requests.
            this._performDefaultSave();
            Y.lp.anim.green_flash({node: existing}).run();
            return;
        }
        var bug_link =
            Y.lp.client.get_absolute_uri("/api/devel/bugs/" + bug_id);
        var that = this;
        var error_handler = new Y.lp.client.ErrorHandler();
        error_handler.clearProgressUI = function() {
            that._hide_bug_spinner(widget);
            that._hide_temporary_spinner();
        };
        error_handler.showError = function(error_msg) {
            that.set('error', error_msg);
        };
        var config = {
            on: {
                start: function() {
                    that.set('error', null);
                    that._show_bug_spinner(widget);
                    that._show_temporary_spinner();
                },
                success: function() {
                    that._update_bug_links(bug_id, widget);
                },
                failure: error_handler.getFailureHandler()
            },
            parameters: {
                bug: bug_link
            }
        };
        this.lp_client.named_post(
            LP.cache.context.self_link, 'linkBug', config);
    },

    /**
     * Update the list of bug links.
     * @param bug_id
     * @param widget
     * @private
     */
    _update_bug_links: function(bug_id, widget) {
        var error_handler = new Y.lp.client.ErrorHandler();
        error_handler.showError = function(error_msg) {
            that.set('error', error_msg);
        };
        var that = this;
        this.lp_client.io_provider.io('++bug-links', {
            on: {
                end: function() {
                    that._hide_temporary_spinner();
                },
                success: function(id, response) {
                    that._link_bug_success(bug_id, response.responseText);
                },
                failure: error_handler.getFailureHandler()
            }
        });
    },

    /**
     * A bug was linked successfully.
     * @param bug_id
     * @param buglink_content
     * @private
     */
    _link_bug_success: function(bug_id, buglink_content) {
        this._performDefaultSave();
        Y.one('#linkbug').setContent('Link to another bug report');
        Y.one('#buglink-list').setContent(buglink_content);
        this._connect_remove_links();
        var new_buglink = Y.one('#buglink-' + bug_id);
        var anim = Y.lp.anim.green_flash({node: new_buglink});
        anim.run();
    },

    /**
     * Unlink a bug from the branch.
     * @param bug_id
     * @param bug_link
     * @private
     */
    _unlink_bug_from_branch: function(bug_id, bug_link) {
        var error_handler = new Y.lp.client.ErrorHandler();
        error_handler.showError = Y.bind(function (error_msg) {
            Y.lp.app.errors.display_error(
                Y.one('#buglink-' + bug_id), error_msg);
        }, this);
        var that = this;
        var config = {
            on: {
                start: function() {
                    Y.one('#delete-buglink-' + bug_id).get('children').set(
                        'src', '/@@/spinner');
                },
                end: function() {
                    Y.one('#delete-buglink-' + bug_id).get('children').set(
                        'src', '/@@/remove');
                },
                success: function() {
                    that._unlink_bug_success(bug_id);
                },
                failure: error_handler.getFailureHandler()
            },
            parameters: {
                bug: bug_link
            }
        };
        this.lp_client.named_post(
            LP.cache.context.self_link, 'unlinkBug', config);
    },

    /**
     * A bug was unlinked successfully.
     * @param bug_id
     * @private
     */
    _unlink_bug_success: function(bug_id) {
        var element = Y.one('#buglink-' + bug_id);
        var parent_element = element.get('parentNode');
        var anim = Y.lp.anim.green_flash({node: element});
        var finish_update = function() {
            parent_element.removeChild(element);
            // Check to see if that was the only bug linked.
            var buglinks = Y.all(".bug-branch-summary");
            if (!buglinks.size()) {
                Y.one('#linkbug')
                    .setContent('Link to a bug report');
            }
        };
        if (this.get('use_animation')) {
            anim.on('end', finish_update);
        } else {
            finish_update();
        }
        anim.run();
    },

    /*
     * Show the temporary "Linking..." text.
     */
    _show_temporary_spinner: function() {
        var temp_spinner = Y.Node.create([
            '<div id="temp-spinner">',
            '<img src="/@@/spinner"/>Linking...',
            '</div>'].join(''));
        var buglinks = Y.one('#buglinks');
        var last = Y.one('#linkbug').get('parentNode');
        if (last) {
            buglinks.insertBefore(temp_spinner, last);
        }
    },

    /*
     * Destroy the temporary "Linking..." text.
     */
    _hide_temporary_spinner: function() {
        var temp_spinner = Y.one('#temp-spinner');
        var spinner_parent = temp_spinner.get('parentNode');
        spinner_parent.removeChild(temp_spinner);

    }
}, {
    ATTRS: {
        header_text: {
            value: 'Select bug to link'
        },
        save_link_text: {
            value: "Link Bug"
        },
        private_warning_message: {
            value:
                'Linking this public branch to a private bug means ' +
                'that some contributors may not see the bug fixed '+
                'by this branch.'
        }
    }
});
}, "0.1", {"requires": ["base", "lp.anim", "lp.bugs.bug_picker",
                        "lp.client", "lp.client.plugins"]});
