/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Code for updating the diff when a new version is available.
 *
 * @module lp.code.branchmergeproposal.updater
 * @requires node, lp.client
 */

YUI.add('lp.code.branchmergeproposal.updater', function(Y) {

var namespace = Y.namespace('lp.code.branchmergeproposal.updater');

function UpdaterWidget(config) {
    UpdaterWidget.superclass.constructor.apply(this, arguments);
}

Y.mix(UpdaterWidget, {

    NAME: 'updaterWidget',

    ATTRS: {

        /**
         * The LP client to use. If none is provided, one will be
         * created during initialization.
         *
         * @attribute lp_client
         */
        lp_client: {
            value: null
        },

        /**
         * The summary node.
         *
         * @attribute summary_node
         */
        summary_node: {
            value: null,
            writeOnce: "initOnly"
        },

        /**
         * Whether or not this MP is still 'pending'.
         *
         * @attribute pending
         * @readOnly
         */
        pending: {
            readOnly: true,
            getter: function() {
                return !Y.Lang.isValue(
                    this.get('srcNode').one('.diff-content'));
            }
        },

        /**
         * The HTML code for the stats diff.
         *
         * @attribute diff_stats
         */
        diff_stats: {
            getter: function() {
                var summary_node = this.get('summary_node');
                if (!Y.Lang.isValue(summary_node) ||
                    !Y.Lang.isValue(summary_node.one(
                         '#summary-row-b-diff'))) {
                    return null;
                }
                return summary_node.one(
                    '#summary-row-b-diff').one('td').get('innerHTML');
            },
            setter: function(value) {
               this._setup_diff_stats_container();
               var container = this.get(
                   'summary_node').one('#summary-row-b-diff').one('td');
               container.set('innerHTML', value);
            }
        },

        /**
         * The HTML code for the diff.
         *
         * @attribute diff
         */
        diff: {
            getter: function() {
                if (this.get('pending')) {
                    return '';
                }
                else {
                    return this.get(
                        'srcNode').one('.diff-content').get('innerHTML');
                }
            },
            setter: function(value) {
               this._setup_diff_container();
               this.get(
                   'srcNode').one('.diff-content').set('innerHTML', value);
            }
        }
    }

});

Y.extend(UpdaterWidget, Y.Widget, {

    /*
     * The initializer method that is called from the base Plugin class.
     *
     * @method initializer
     * @protected
     */
    initializer: function(cfg){
        // If we have not been provided with a Launchpad Client, then
        // create one now:
        if (null === this.get("lp_client")){
            // Create our own instance of the LP client.
            this.set("lp_client", new Y.lp.client.Launchpad());
        }
        this.set('summary_node', cfg.summary_node);
    },

    /*
     * Set the proper icon to indicate the diff is updating.
     *
     * @method set_status_updating
     */
    set_status_updating: function() {
       this.cleanup_status();
       this._set_status('spinner', 'Update in progress.');
    },

    /*
     * Set the proper icon to indicate the diff will be updated when the
     * new version is available.
     *
     * @method set_status_longpolling
     */
    set_status_longpolling: function() {
       this.cleanup_status();
       this._set_status(
           'longpoll_loading',
           'The diff will be updated as soon as a new version is available.');
    },

    /*
     * Set the proper icon to indicate that the diff update is broken.
     *
     * @method set_status_longpollerror
     */
    set_status_longpollerror: function() {
       this.cleanup_status();
       this._set_status(
           'longpoll_error',
           'Diff update error, please reload to see the changes.');
    },

    /*
     * Add a status image to the diff title.
     *
     * @method _set_status
     */
    _set_status: function(image_name, title) {
       var image = Y.Node.create('<img />')
           .set('src', '/@@/' + image_name)
           .set('title', title);
       this.get('srcNode').one('h2').append(image);
    },

    /*
     * Remove the status image to the diff title.
     *
     * @method cleanup_status
     */
    cleanup_status: function() {
        this._setup_diff_container();
        this.get('srcNode').all('h2 img').remove();
    },

    /*
     * Add a row in the page summary table to display the diff stats
     * if needed.
     *
     * @method _setup_diff_stats_container
     */
     _setup_diff_stats_container: function() {
        if (!Y.Lang.isValue(this.get('diff_stats'))) {
            var summary_node = this.get('summary_node');
            var diff_stats = Y.Node.create('<tr />')
                .set('id', 'summary-row-b-diff')
                .append(Y.Node.create('<th />')
                    .set("text", "Diff against target:"))
                .append(Y.Node.create('<td />'));
            summary_node.one(
                '#summary-row-9-target-branch').insert(diff_stats, 'after');
        }
     },

    /*
     * Populate the widget with the required nodes to display the diff
     * if needed.
     *
     * @method _setup_diff_container
     */
    _setup_diff_container: function() {
        if (this.get('pending')) {
            // Cleanup.get('srcNode').
            this.get('srcNode').empty();
            // Create the diff container.
            var review_diff = Y.Node.create('<div />')
                .set('id', 'review-diff')
                .append(Y.Node.create('<h2 />')
                    .set("text", "Preview Diff "))
                .append(Y.Node.create('<div />')
                    .addClass("diff-content"));
            this.get('srcNode').append(review_diff);
        }
    },

    /*
     * Update the page with the last version of the diff and update the
     * stats.
     *
     * @method update
     */
    update: function() {
        this.update_stats();
        this.update_diff();
    },

    /*
     * Update the diff stats with the last version.
     *
     * @method update_stats
     */
    update_stats: function() {
        var self = this;
        var config = {
            on: {
                success: function(diff_stats) {
                    self.set('diff_stats', diff_stats);
                    // (re)connect the js scroller link.
                    Y.lp.code.branchmergeproposal.reviewcomment.link_scroller(
                        '#proposal-summary a.diff-link', '#review-diff');
                    var node = self.get('summary_node');
                    Y.lp.anim.green_flash({node: node}).run();
                },
                failure: function() {
                    var node = self.get('summary_node');
                    Y.lp.anim.red_flash({node: node}).run();
                }
            }
        };
        var mp_uri = LP.cache.context.web_link;
        this.get('lp_client').get(mp_uri + "/++diff-stats", config);
     },


    /*
     * Update the diff content with the last version.
     *
     * @method update_diff
     */
    update_diff: function() {
        var self = this;
        var config = {
            on: {
                success: function(diff) {
                    self.set('diff', diff);
                    var node = self.get('srcNode').one('.diff-content');
                    Y.lp.anim.green_flash({node: node}).run();
                    self.fire(self.NAME + '.updated');
                },
                failure: function() {
                    var node = self.get('srcNode').one('.diff-content');
                    Y.lp.anim.red_flash({node: node}).run();
                },
                start: function() {
                    self.set_status_updating();
                },
                end: function() {
                    self.cleanup_status();
                }
            }
        };
        var mp_uri = LP.cache.context.web_link;
        this.get('lp_client').get(mp_uri + "/++diff", config);
    }

});

/*
 * Export UpdaterWidget.
 */
namespace.UpdaterWidget = UpdaterWidget;

/*
 * Returns true if the event fired means that the preview_diff field of the
 * MP has been updated.
 *
 */
namespace.is_mp_diff_updated = function(event_data) {
    return (event_data.what === "modified" &&
        event_data.edited_fields.indexOf("preview_diff") >= 0);
};

}, '0.1', {requires: ['node', 'lp.client', 'lp.anim',
                      'lp.code.branchmergeproposal.reviewcomment']});
