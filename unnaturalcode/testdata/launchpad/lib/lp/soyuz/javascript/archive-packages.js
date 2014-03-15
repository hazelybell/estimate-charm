/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Code for handling the JavaScript side of archive-package.
 *
 * @module lp.soyuz.archive_packages
 * @requires node
 */

YUI.add('lp.soyuz.archive_packages', function(Y) {

// Grab the namespace in order to be able to expose the connect method.
var namespace = Y.namespace('lp.soyuz.archive_packages');

var PendingCopyJobWidget = function() {
    PendingCopyJobWidget.superclass.constructor.apply(this, arguments);
};

PendingCopyJobWidget.NAME = 'pending-copy-job-widget';

PendingCopyJobWidget.ATTRS = {
    /**
     * The id for this job.
     *
     * @attribute job_id
     * @type String
     * @default null
     */
    job_id: {
        value: null
    },
    /**
     * The uri for the context archive.
     *
     * @attribute archive_uri
     * @type String
     * @default null
     */
    archive_uri: {
        value: null
    }
};

PendingCopyJobWidget.HTML_PARSER = {
    job_id: function(srcNode) {
        return srcNode.getAttribute('job_id');
    }
};

Y.extend(PendingCopyJobWidget, Y.Widget, {
    initializer: function(cfg) {
        this.client = new Y.lp.client.Launchpad();
        this.set('archive_uri', cfg.archive_uri);
    },

    bindUI: function() {
        this.constructor.superclass.bindUI.call(this);
        // Wire up the cancel link.
        var cancel_link = this.get('srcNode').one('.remove-notification');
        if (Y.Lang.isValue(cancel_link)) {
            var self = this;
            cancel_link.on('click', function(e) {
                e.halt();
                self.cancel();
            });
        }
    },

    /**
     * Show the spinner.
     *
     * @method showSpinner
     */
    showSpinner: function() {
        var spinnerNode = Y.Node.create('<img />')
            .set('src', '/@@/spinner')
            .addClass('spinner');
        var cancel_link = this.get('srcNode').one('.remove-notification');
        cancel_link.insert(spinnerNode, 'after');
    },

    /**
     * Hide the spinner.
     *
     * @method hideSpinner
     */
    hideSpinner: function() {
        this.get('srcNode').all('.spinner').remove();
    },

    /**
     * Cancel this copy job: call the removeCopyNotification api method and
     * delete the node from the page.
     *
     * @method cancel
     */
    cancel: function() {
        var self = this;
        var config = {
            on: {
                start: function() {
                    self.showSpinner();
                },
                end: function() {
                    self.hideSpinner();
                },
                success: function() {
                    Y.lp.anim.green_flash({node: self.get('srcNode')}).run();
                    self.get('srcNode').remove();
                },
                failure: function() {
                    Y.lp.anim.red_flash({node: self.get('srcNode')}).run();
                }
            },
            parameters: {
                job_id: this.get('job_id')
            }
        };
        this.client.named_post(
            this.get('archive_uri'), 'removeCopyNotification', config);

        this.fire('cancel');
    }

});

namespace.PendingCopyJobWidget = PendingCopyJobWidget;

}, '0.1', {requires: ['event', 'io', 'node', 'widget', 'lp.client',
                      'lp.anim']});
