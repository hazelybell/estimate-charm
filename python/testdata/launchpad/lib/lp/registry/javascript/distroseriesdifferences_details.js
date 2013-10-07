/* Copyright 2010 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Enhancements for the distroseries differences page.
 *
 * @module registry
 * @submodule distroseriesdifferences_details
 * @requires  io-base, lp.soyuz.base
 */
YUI.add('lp.registry.distroseriesdifferences_details', function(Y) {

var namespace = Y.namespace('lp.registry.distroseriesdifferences_details');

/**
 * Create one Launchpad client that will be used with multiple requests.
 */
namespace.lp_client = new Y.lp.client.Launchpad();

// Our MockIo() needs to be called and then .io() called on it. To keep scope
// of this in the io() mock method we need to not just pass the method, but
// the object. In this way the call to namespace.io will be:
// Y.io()
// MockIo.io()
namespace.io = Y;

function ExpandableRowWidget(config) {
    ExpandableRowWidget.superclass.constructor.apply(this, arguments);
}

ExpandableRowWidget.NAME = "expandableRowWidget";

Y.extend(ExpandableRowWidget, Y.Base, {
    initializer: function(cfg) {
        this._toggle = cfg.toggle;
        this._row = this._toggle.ancestor('tr');
        this._toggle.addClass('treeCollapsed').addClass('sprite');
        this._toggle.on("click", this.expander_handler, this);
    },

    parse_row_data: function() {
        var source_name = this._row.one('a.toggle-extra').get('text');
        var rev_link = this._row
            .one('a.toggle-extra').get('href').split('/').reverse();
        var parent_series_name = rev_link[0];
        var parent_distro_name = rev_link[1];
        var nb_columns = this._row.all('td').size();
        return {
            source_name: source_name,
            parent_series_name: parent_series_name,
            parent_distro_name: parent_distro_name,
            nb_columns: nb_columns
        };
    },

    expander_handler: function(e) {
        e.halt();
        var parsed = this.parse_row_data();
        this._toggle.toggleClass('treeCollapsed').toggleClass('treeExpanded');

        // Only insert if there isn't already a container row there.
        var detail_row = this._row.next();
        if (detail_row === null ||
            !detail_row.hasClass('diff-extra')) {
            details_row = Y.Node.create([
                '<table><tr class="diff-extra hidden ',
                parsed.source_name + '">',
                '  <td colspan="'+parsed.nb_columns+'">',
                '    <div class="diff-extra-container"></div>',
                '  </td></tr></table>'
                ].join('')).one('tr');
            this._row.insert(details_row, 'after');
            var uri = this._toggle.get('href');
            this.get_extra_diff_info(
                uri, this._row, details_row.one('td'), parsed.source_name,
                parsed.parent_distro_name, parsed.parent_series_name);
        }
        details_row.toggleClass('hidden');
    },

    setup_extra_diff_info: function(master_container, container,
                                    source_name, parent_distro_name,
                                    parent_series_name, response) {
        container.one('div.diff-extra-container').insert(
            response.responseText, 'replace');
        var api_uri = [
            LP.cache.context.self_link,
            '+source',  source_name, '+difference',
            parent_distro_name, parent_series_name
           ].join('/');
        var latest_comment_container =
            master_container.one('td.latest-comment-fragment');
        // The add comment slot is only available when the user has the
        // right to add comments.
        var add_comment_placeholder =
            container.one('div.add-comment-placeholder');
        var comment_widget = null;
        if (add_comment_placeholder !== null) {
            comment_widget = new AddCommentWidget({
                latestCommentContainer: latest_comment_container,
                addCommentPlaceholder: add_comment_placeholder,
                apiUri: api_uri});
            comment_widget.render(add_comment_placeholder);
        }
        // The blacklist slot with a class 'blacklist-options' is only
        // available when the user has the right to blacklist.
        var blacklist_slot = container.one('div.blacklist-options');

        if (blacklist_slot !== null) {
            var blacklist_widget = new BlacklistWidget(
                {srcNode: blacklist_slot,
                 sourceName: source_name,
                 dsdLink: api_uri,
                 commentWidget: comment_widget
                });
        }
        // If the user has not the right to blacklist, we disable
        // the blacklist slot.
        var disabled_blacklist_slot = container.one(
            'div.blacklist-options-disabled');
        if (disabled_blacklist_slot !== null) {
            disabled_blacklist_slot
                .all('input').set('disabled', 'disabled');
        }
        // Set-up diffs and the means to request them.
        namespace.setup_packages_diff_states(container, api_uri);
    },

    /**
     * Get the extra information for this diff to display.
     *
     * @param uri {string} The uri for the extra diff info.
     * @param master_container {Node}
     *     The node that triggered the load of the extra info.
     * @param container {Node}
     *     A node which must contain a div with the class
     *     'diff-extra-container' into which the results are inserted.
     * @param source_name {String}
     *     The name of the source package for which diff info is desired.
     * @param parent_distro_name {String}
     *     The name of the distribution in which a different version of
     *     the source package exists.
     * @param parent_series_name {String}
     *     The name of the distroseries in which a different version of
     *     the source package exists.
     */
    get_extra_diff_info: function(uri, master_container, container,
                                  source_name, parent_distro_name,
                                  parent_series_name) {
        var in_progress_message = Y.lp.soyuz.base.makeInProgressNode(
            'Fetching difference details ...');
        container.one('div.diff-extra-container').insert(
            in_progress_message, 'replace');
        var success_cb = function(transaction_id, response, args) {
            this.setup_extra_diff_info(
                master_container, container, source_name, parent_distro_name,
                parent_series_name, response);
        };

        var failure_cb = function(transaction_id, response, args) {
            var retry_handler = function(e) {
                e.preventDefault();
                this.get_extra_diff_info(
                    args.uri, args.master_container, args.container,
                    args.source_name, args.parent_distro_name,
                    args.parent_series_name);
            };
            var failure_message = Y.lp.soyuz.base.makeFailureNode(
                'Failed to fetch difference details.', retry_handler);
            container.insert(failure_message, 'replace');

            var anim = Y.lp.anim.red_flash({
                 node: args.container
                 });
            anim.run();
        };

        var config = {
            headers: {'Accept': 'application/json;'},
            context: this,
            on: {
                'success': success_cb,
                'failure': failure_cb
            },
            "arguments": {
                'master_container': master_container,
                'container': container,
                'uri': uri,
                'source_name': source_name
            }
        };
        namespace.io.io(uri, config);

    }
});

namespace.ExpandableRowWidget = ExpandableRowWidget;

/**
 * BlacklistWidget: the widget used by each row to control the
 * 'blacklisted' status of the DSD.
 */
function BlacklistWidget(config) {
    BlacklistWidget.superclass.constructor.apply(this, arguments);
}

BlacklistWidget.NAME = "blacklistWidget";

BlacklistWidget.HTML_PARSER = {
    relatedRows: function(srcNode) {
        return [
            srcNode.ancestor('tr').previous(),
            srcNode.ancestor('tr')
            ];
    }
};

Y.extend(BlacklistWidget, Y.Widget, {
    initializer: function(cfg) {
        this.sourceName = cfg.sourceName;
        this.dsdLink = cfg.dsdLink;
        this.commentWidget = cfg.commentWidget;
        this.relatedRows = cfg.relatedRows;
        this.container = cfg.container;
        // We call bindUI directly here because the BlacklistWidgets
        // are built from existing HTML code and hence we don't
        // use the full potential of YUI'Widget to manage the
        // display of the widgets.
        // http://developer.yahoo.com/yui/3/widget/#progressive
        this.bindUI();
    },

    /**
     * Wire the widget methods/events together.
     *
     */
    bindUI: function() {
        // Wire the click on blacklist form.
        var handleClick = function(e) {
            e.preventDefault();
            var target = e.target;
            this.show_comment_overlay(target);
        };
        Y.on("click", handleClick, this.get('srcNode').all('input'), this);

        // Wire the ok event from the comment overlay.
        var handleBlacklistChange = function(e, method_name, blacklist_all,
                                             comment, target) {
            e.preventDefault();
            this.blacklist_submit_handler(
                method_name, blacklist_all, comment, target);
         };
        this.on("blacklist_changed", handleBlacklistChange,
            this);
    },

    /**
     * Pop up an overlay to let the user enter an optional comment.
     *
     * @param target {Node}
     *     The target input node that was clicked.
     * @returns {Y.lp.ui.FormOverlay}
     *     The overlay that was just created.
     */
    show_comment_overlay: function(target) {
        var comment_form = Y.Node.create("<form />")
            .appendChild(Y.Node.create("<textarea />")
                .set("name", "comment")
                .set("rows", "3")
                .set("cols", "60"));
        /* Buttons */
        var submit_button = Y.Node.create(
            '<button type="submit"/>')
                .set("text", "OK");
        var cancel_button = Y.Node.create(
            '<button type="button"/>')
                .set("text", "Cancel");

        var self = this;
        var submit_callback = function(data) {
            overlay.hide();
            // Get the comment string.
            var comment = "";
            if (data.comment !== undefined) {
                comment = data.comment[0];
            }
            // Figure out the new 'ignored' status.
            var value = target.get('value');
            var method_name = (value === 'NONE') ?
                'unblacklist' : 'blacklist';
            var blacklist_all = (
                target.get('value') === 'BLACKLISTED_ALWAYS');
            self.fire(
                'blacklist_changed', method_name, blacklist_all, comment,
                target);
        };
        var overlay = new Y.lp.ui.FormOverlay({
            align: {
                /* Align the centre of the overlay with the centre of the
                node containing the blacklist options. */
                node: this.get('srcNode'),
                points: [
                    Y.WidgetPositionAlign.CC,
                    Y.WidgetPositionAlign.CC]
            },
            headerContent: "<h2>Add an optional comment</h2>",
            form_content: comment_form,
            form_submit_button: submit_button,
            form_cancel_button: cancel_button,
            form_submit_callback: submit_callback,
            visible: true,
            destroy_on_hide: true
        });
        overlay.render();
        return overlay;
    },

    /**
     * 'Lock' the widget by disabling the input and displaying a spinner.
     *
     */
    lock: function() {
        // Disable all the inputs.
        this.get('srcNode').all('input').set('disabled', 'disabled');
        // Add the spinner.
        this.get('srcNode').prepend('<img src="/@@/spinner" />');
    },

    /**
     * 'Unlock' the widget by (re)enabling the input and removing the spinner.
     *
     */
    unlock: function() {
        var img = this.get('srcNode').one('img');
        if (img !== null) {
            img.remove();
        }
        this.get('srcNode').all('input').set('disabled', false);
    },

    // Duration of the animation fired after each blacklist status change.
    ANIM_DURATION: 1,

    /**
     * Submit the blacklist or unblacklist action. Updates the comment
     * list if successful.
     *
     * @param method_name {String}
     *     'blacklist' or 'unblacklist'.
     * @param blacklist_all {Boolean}
     *     Is this a blacklist all versions or blacklist current (only
     *     relevant if method_name is 'blacklist').
     * @param comment {String}
     *     The comment string.
     * @param target {Node}
     *     The target input node that was clicked.
     */
     blacklist_submit_handler: function(method_name, blacklist_all, comment,
                                        target) {
        var self = this;
        this.lock();
        var diff_rows = this.relatedRows;

        var config = {
            on: {
                success: function(updated_entry, args) {
                    self.unlock();
                    // Let the user know this item is now blacklisted.
                    target.set('checked', true);
                    Y.each(diff_rows, function(diff_row) {
                        var fade_to_gray = new Y.Anim({
                            node: diff_row,
                            from: { backgroundColor: '#FFFFFF'},
                            to: { backgroundColor: '#EEEEEE'},
                            duration: self.ANIM_DURATION,
                            reverse: (method_name === 'unblacklist')
                        });
                        fade_to_gray.on('end', function() {
                            self.fire('blacklisting_animation_ended');
                        });
                        fade_to_gray.run();
                    });
                    if (self.commentWidget !== null) {
                        self.commentWidget.display_new_comment(updated_entry);
                    }
                },
                failure: function(id, response) {
                    self.unlock();
                }
            },
            parameters: {
                all: blacklist_all,
                comment: comment
            }
        };
        namespace.lp_client.named_post(this.dsdLink, method_name, config);
    }
});

namespace.BlacklistWidget = BlacklistWidget;

/**
 * Update the latest comment on the difference row.
 *
 * @param comment_entry {lp.client.Entry} An object representing
 *     a DistroSeriesDifferenceComment.
 * @param placeholder {Node}
 *     The node in which to put the latest comment HTML fragment. The
 *     contents of this node will be replaced.
 */
namespace.update_latest_comment = function(comment_entry, placeholder) {
    var comment_latest_fragment_url =
        comment_entry.get('web_link') + "/+latest-comment-fragment";
    var config = {
        on: {
            success: function(comment_latest_fragment_html) {
                placeholder.set(
                    "innerHTML", comment_latest_fragment_html);
                Y.lp.anim.green_flash({node: placeholder}).run();
            },
            failure: function(id, response) {
                Y.lp.anim.red_flash({node: placeholder}).run();
            }
        },
        accept: Y.lp.client.XHTML
    };
    namespace.lp_client.get(comment_latest_fragment_url, config);
};

/**
 * AddCommentWidget: the widget used to display a small form to enter
 * a comment attached to a DSD.
 */
function AddCommentWidget(config) {
    AddCommentWidget.superclass.constructor.apply(this, arguments);
}

AddCommentWidget.NAME = "addCommentWidget";

AddCommentWidget.ATTRS = {
    /**
     * The content of the textarea used to add a new comment.
     * @type String
     */
    comment_text: {
        getter: function() {
            return this.addForm.one('textarea').get('value');
        },
        setter: function(comment_text) {
            this.addForm.one('textarea').set('value', comment_text);
        }
    }
};

Y.extend(AddCommentWidget, Y.Widget, {
    initializer: function(cfg) {
        this.latestCommentContainer = cfg.latestCommentContainer;
        this.addCommentPlaceholder = cfg.addCommentPlaceholder;
        this.apiUri = cfg.apiUri;

        this.addCommentLink = Y.Node.create([
            '<a class="widget-hd js-action sprite add" href="">',
            '  Add comment</a>'
            ].join(''));
        this.addForm = Y.Node.create([
            '<div class="widget-bd lazr-closed" ',
            '     style="height:0;overflow:hidden">',
            '  <textarea></textarea><button>Save comment</button>',
            '</div>'
            ].join(''));
    },

    renderUI: function() {
        this.get("contentBox")
            .append(this.addCommentLink)
            .append(this.addForm);
    },

    _fire_anim_end: function(anim, event_name) {
        var self = this;
        anim.on("end", function() {
            self.fire(event_name);
        });
    },

    slide_in: function() {
        var anim = Y.lp.ui.effects.slide_in(this.addForm);
        this._fire_anim_end(anim, 'slid_in');
        anim.run();
    },

    slide_out: function() {
        var anim = Y.lp.ui.effects.slide_out(this.addForm);
        this._fire_anim_end(anim, 'slid_out');
        anim.run();
    },

    bindUI: function() {
        this.addCommentLink.on("click", function(e) {
            e.preventDefault();
            this.slide_out();
        }, this);

        this.on("comment_added", function(e) {
            e.preventDefault();
            var comment_entry = e.details[0];
            this.display_new_comment(comment_entry);
        }, this);

        Y.on("click", function(e, comment_entry) {
            e.preventDefault();
            this.add_comment_handler();
        }, this.addForm.one('button'), this);
    },

    lock: function() {
        // Show a spinner.
        this.addForm.append('<img src="/@@/spinner" />');
        // Disable the textarea and button.
        this.addForm.all('textarea,button')
            .setAttribute('disabled', 'disabled');
    },

    unlock: function() {
        // Remove the spinner.
        this.addForm.all('img').remove();
        // Enable the form and the button.
        this.addForm.all('textarea,button')
            .removeAttribute('disabled');
    },

    clean: function() {
        this.set('comment_text', '');
    },

    /**
     * This method displays a new comment in the UI. It appends a comment
     * to the list of comments and updates the latest comments slot.
     *
     * @param comment_entry {Comment} A comment as returns by the api.
     */
    display_new_comment: function(comment_entry) {
        // Grab the XHTML representation of the comment,
        // prepend it to the list of comments and update the
        // 'latest comment' slot.
        var self = this;
        var config = {
            on: {
                success: function(comment_html) {
                    var comment_node = Y.Node.create(comment_html);
                    self.addCommentPlaceholder.insert(comment_node, 'before');
                    var reveal = Y.lp.ui.effects.slide_out(comment_node);
                    reveal.on("end", function() {
                        Y.lp.anim.green_flash(
                            {node: comment_node}).run();
                    });
                    reveal.run();
                    namespace.update_latest_comment(
                        comment_entry, self.latestCommentContainer);
                },
                failure: function() {
                    Y.lp.anim.red_flash(
                        {node: self.addForm.all('textarea')}).run();
                }
            },
            accept: Y.lp.client.XHTML
        };
        namespace.lp_client.get(comment_entry.get('self_link'), config);
    },

    /**
     * Handle the add comment event triggered by the 'add comment' form.
     *
     * This method adds the content of the comment form as a comment via
     * the API.
     *
     */
    add_comment_handler: function() {
        var comment_text = this.get('comment_text');

        // Treat empty comments as mistakes.
        if (Y.Lang.trim(comment_text).length === 0) {
            Y.lp.anim.red_flash({
                node: this.addForm.one('textarea')
                }).run();
            return;
        }

        var self = this;
        var success_handler = function(comment_entry) {
            self.clean();
            self.slide_in();
            self.fire('comment_added', comment_entry);
        };
        var failure_handler = function(id, response) {
            // Re-enable field with red flash.
            var node = self.addForm.one('textarea');
            Y.lp.anim.red_flash({node: node}).run();
        };

        var config = {
            on: {
                success: success_handler,
                failure: failure_handler,
                start: Y.bind(self.lock, self),
                end: Y.bind(self.unlock, self)
            },
            parameters: {
                comment: comment_text
            }
        };
        namespace.lp_client.named_post(this.apiUri, 'addComment', config);
    }

});

namespace.AddCommentWidget = AddCommentWidget;

namespace.setup = function() {
    Y.all('table.listing a.toggle-extra').each(function(toggle){
        var row = new namespace.ExpandableRowWidget({toggle: toggle});
    });
};

var set_package_diff_status = function(container, new_status, note_msg) {
    container.removeClass('request-derived-diff');
    container.removeClass('PENDING');
    note = container.all('.note').remove();
    container.addClass(new_status);
    if (note_msg !== undefined) {
        container.append([
            '<span class="note greyed-out">(',
            note_msg,
            ')</span>'].join(''));
    }
};

/*
* Helper function to extract the selected state from a jsonified
* Vocabulary.
*
* @param json_voc {object} A jsonified Vocabulary
*
*/
namespace.get_selected = function(json_voc) {
    var i;
    for (i = 0; i < json_voc.length; i++) {
        var obj = json_voc[i];
        if (obj.selected === true) {
            return obj;
        }
    }
    return undefined;
};

namespace.add_link_to_package_diff = function(container, url_uri) {
    var y_config = {
        headers: {'Accept': 'application/json;'},
        on: {
            success: function(url) {
                container.all('.update-failure-message').remove();
                container
                    .wrap('<a />')
                    .ancestor()
                        .set("href", url);
            },
            failure: function(url) {
                container.all('.update-failure-message').remove();

                var retry_handler = function(e) {
                    e.preventDefault();
                    namespace.add_link_to_package_diff(container, url_uri);
                };
                var failure_message = Y.lp.soyuz.base.makeFailureNode(
                    'Failed to fetch package diff url.', retry_handler);
                container.insert(failure_message);
            }
        }
    };
    namespace.lp_client.named_get(url_uri , null, y_config);
};

/**
* Polling intervall for checking package diff's status.
*/
namespace.poll_interval = 30000;

/**
* Attach package diff status poller.
*
* This method attachs a poller to the container to check
* the package diff object's status.
*
* @param container {Node} The container node displaying this package
*     diff information.
* @param dsd_link {string} The uri for the distroseriesdifference object.
*/
namespace.setup_pending_package_diff = function(container, dsd_link) {
    var parent = container.hasClass('parent');
    var package_diff_uri = [
        dsd_link,
        parent ? 'parent_package_diff_status' : 'package_diff_status'
        ].join('/');
    var build_package_diff_update_config = {
        uri: package_diff_uri,
        lp_client: namespace.lp_client,
        parent: parent,
        /**
        * This function knows how to update a package diff status.
        *
        * @config domUpdateFunction
        */
        domUpdateFunction: function(container, data_object) {
            var state_and_name = namespace.get_selected(data_object);
            var state = state_and_name.token;
            var name = state_and_name.title;
            if (state === 'FAILED') {
                set_package_diff_status(container, 'FAILED', name);
                Y.lp.anim.red_flash({node: container}).run();
             }
            else if (state === 'COMPLETED') {
                set_package_diff_status(container, 'COMPLETED');
                url_uri = [
                    dsd_link,
                    parent ? 'parent_package_diff_url' : 'package_diff_url'
                    ].join('/');
                namespace.add_link_to_package_diff(container, url_uri);
                Y.lp.anim.green_flash({node: container}).run();
             }
        },

        interval: namespace.poll_interval,

        /**
        * This function knows whether the package diff status
        * should stop being updated. It checks whether the state
        * is COMPLETED or FAILED.
        *
        * @config stopUpdatesCheckFunction
        */
        stopUpdatesCheckFunction: function(container){
            if (container.hasClass("COMPLETED")) {
                return true;
            }
            else if (container.hasClass("FAILED")) {
                return true;
            }
            else {
                return false;
            }
        }
    };
    container.plug(Y.lp.soyuz.dynamic_dom_updater.DynamicDomUpdater,
        build_package_diff_update_config);
};

/**
* Add a button to start package diff computation.
*
* @param row {Node} The container node for this package extra infos.
* @param dsd_link {string} The uri for the distroseriesdifference object.
*/
namespace.setup_request_derived_diff = function(container, dsd_link) {
    // Setup handler for diff requests. There should either zero or
    // one clickable node.
    container.all('.package-diff-compute-request').on('click', function(e) {
        e.preventDefault();
        namespace.compute_package_diff(container, dsd_link);
    });
};

/**
* - Add a button to start package diff computation (if needed).
* - Start pollers for pending packages diffs.
*
* @param row {Node} The container node for this package extra infos.
* @param dsd_link {string} The uri for the distroseriesdifference object.
*/
namespace.setup_packages_diff_states = function(container, dsd_link) {
    // Attach pollers for pending packages diffs.
    container.all('.PENDING').each(function(sub_container){
        namespace.setup_pending_package_diff(sub_container, dsd_link);
    });
    // Set-up the means to request a diff.
    namespace.setup_request_derived_diff(container, dsd_link);
};

/**
* Helper method to add a message node inside the placeholder.
*
* @param container {Node} The container in which to look for the
*     placeholder.
* @param msg_node {Node} The message node to add.
*/
namespace.add_msg_node = function(container, msg_node) {
    container.one('.package-diff-placeholder')
        .empty()
        .appendChild(msg_node);
};

/**
* Start package diff computation. Update package diff status to PENDING.
*
* @param row {Node} The container node for this package diff.
* @param dsd_link {string} The uri for the distroseriesdifference object.
*/
namespace.compute_package_diff = function(container, dsd_link) {
    var in_progress_message = Y.lp.soyuz.base.makeInProgressNode(
        'Computing package diff...');
    namespace.add_msg_node(container, in_progress_message);
    var success_cb = function(transaction_id, response, args) {
        container.one('p.update-in-progress-message').remove();
        container.one('.package-diff-placeholder').set(
            'text',
            'Differences from last common version:');
        container.all('.request-derived-diff').each(function(sub_container) {
            set_package_diff_status(sub_container, 'PENDING', 'Pending');
            // Setup polling
            namespace.setup_pending_package_diff(sub_container, dsd_link);
            var anim = Y.lp.anim.green_flash({
                node: sub_container
            });
            anim.run();
        });
    };
    var failure_cb = function(transaction_id, response, args) {
        container.one('p.update-in-progress-message').remove();
        var recompute = function(e) {
            e.preventDefault();
            namespace.compute_package_diff(container, dsd_link);
        };

        var msg = response.responseText;

        // If the error is not of the type raised by an error properly
        // raised by python then set a standard error message.
        if (response.status !== 400) {
            msg = 'Failed to compute package diff.';
        }
        var failure_msg = Y.lp.soyuz.base.makeFailureNode(msg, recompute);
        namespace.add_msg_node(container, failure_msg);
    };
    var config = {
        on: {
            'success': success_cb,
            'failure': failure_cb
        },
        "arguments": {
            'container': container,
            'dsd_link': dsd_link
        }
    };
    namespace.lp_client.named_post(dsd_link, 'requestPackageDiffs', config);
};

/**
* Get the number of packages to be synced.
*
*/
namespace.get_number_of_packages = function() {
    return Y.all(
        'input[name="field.selected_differences"]').filter(':checked').size();
};

/**
* Get a Node to display in the header of the overlay confirmation overlay.
* (e.g. "<h2>You're about to sync 1 package. Continue?</h2>",
*       "<h2>You're about to sync 20 packages. Continue?</h2>")
*/
namespace.get_confirmation_header_number_of_packages = function() {
    var nb_selected_packages = namespace.get_number_of_packages();
    var unit = (nb_selected_packages === 1) ? 'package' : 'packages';
    return Y.Node.create('<h2></h2>')
        .set('text', Y.Lang.sub(
            "You're about to sync {nr} {unit}. Continue?",
            {nr: nb_selected_packages, unit: unit}));
};

// Max number of packages to display in the summary.
namespace.MAX_PACKAGES = 15;

/**
* Get a summary for the packages to be synced.
*
* The summary will be display, for each package to be synced,
* the name of the package, the version in the parent and the version
* in the child. If more than MAX_PACKAGES are to be synced, the list
* will be limited to keep the display small.
*
* e.g.
* package1: version1, version2
* package2: version1, version2
* ... and 4 more packages.
*
*/
namespace.get_packages_summary = function() {
    var all_inputs = Y.all(
        'input[name="field.selected_differences"]').filter(':checked');
    var nb_inputs = all_inputs.size();
    var summary = Y.Node.create('<div><ul></ul></div>'),
        summary_ul = summary.one('ul');
    for (i=0; i < Math.min(namespace.MAX_PACKAGES, nb_inputs) ; i++) {
        var input = all_inputs.shift();
        var tr = input.ancestor('tr');
        var derived_node = tr.one('.derived-version');
        var has_derived_node = (derived_node !== null);
        var package_line = Y.Node.create('<li></li>');
        summary_ul.append(package_line);
        package_line.append(Y.Node.create('<b></b>')
            .set('text', tr.one('a.toggle-extra').get('text')));
        var version_content = ': ' +
            tr.one('.parent-version').get('text').trim();
        if (has_derived_node) {
            version_content = version_content +
                ' &rarr; ' + derived_node.get('text').trim();
        }
        package_line.append(Y.Node.create(version_content));
    }
    if (nb_inputs > namespace.MAX_PACKAGES) {
        summary.append(Y.Node.create(
            Y.Lang.sub(
                '... and {nr} more packages.',
                {nr: nb_inputs - namespace.MAX_PACKAGES})));
    }
    return summary;
};

}, "0.1", {"requires": ["io-base", "widget", "event", "overlay", "lang",
                        "lp.soyuz.base", "lp.client",
                        "lp.anim", "lp.ui.formoverlay", "lp.ui.effects",
                        "lp.soyuz.dynamic_dom_updater"]});
