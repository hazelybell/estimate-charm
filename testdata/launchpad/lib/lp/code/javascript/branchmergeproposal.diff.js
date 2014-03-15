/* Copyright 2009 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Code for handling the popup diffs in the pretty overlays.
 *
 * @module lp.code.branchmergeproposal.diff
 * @requires node
 */

YUI.add('lp.code.branchmergeproposal.diff', function(Y) {

// Grab the namespace in order to be able to expose the connect method.
var namespace = Y.namespace('lp.code.branchmergeproposal.diff');

/*
 * The DiffOverlay object inherits from the lazr-js PerttyOverlay.
 *
 * By sub-classing the DiffOverlay gets its own CSS class that is applied to
 * the various HTML objects that are created.  This allows styling of the
 * overlay in a different way to any other PrettyOverlays.
 */
var DiffOverlay;
DiffOverlay = function() {
    DiffOverlay.superclass.constructor.apply(this, arguments);
    Y.after(this._setupDismissDiff, this, 'syncUI');
};

Y.extend(DiffOverlay, Y.lp.ui.PrettyOverlay, {
        bindUI: function() {
            // call PrettyOverlay's bindUI
            this.constructor.superclass.bindUI.call(this);
        },

        /*
         * Override widget's hide/show methods, since DiffOverlay
         * doesn't provide CSS to handle .visible objects.
         */
        hide: function() {
            this.constructor.superclass.hide.call(this);
            this.get('boundingBox').setStyle('display', 'none');
        },

        show: function() {
            this.constructor.superclass.show.call(this);
            this.get('boundingBox').setStyle('display', 'block');
        }
    });

// The NAME gets appended to 'yui-' to give the class name 'yui-diff-overlay'.
DiffOverlay.NAME = 'diff-overlay';

// A local page cache of the diff overlays that have been rendered.
// This makes subsequent views of an already loaded diff instantaneous.
var rendered_overlays = {};

/*
 * Display the diff for the specified api_url.
 *
 * If the specified api_url has already been rendered in an overlay, show it
 * again.  If it hasn't been loaded, show the spinner, and load the diff using
 * the LP API.
 *
 * If the diff fails to load, the user is taken to the librarian url just as
 * if Javascript was not enabled.
 */
function display_diff(node, api_url, librarian_url, lp_client) {

    // Look to see if we have rendered one already.
    if (rendered_overlays[api_url] !== undefined) {
        rendered_overlays[api_url].show();
        return;
    }

    // Show a spinner.
    var html = [
        '<img src="/@@/spinner" alt="loading..." ',
        '     style="padding-left: 0.5em"/>'].join('');
    var spinner = Y.Node.create(html);
    node.appendChild(spinner);

    // Load the diff.
    var config = {
        on: {
            success: function(formatted_diff) {
                node.removeChild(spinner);
                var diff_overlay = new DiffOverlay({
                        headerContent: "<h2>Branch Diff</h2>",
                        bodyContent: Y.Node.create(formatted_diff),
                        align: {
                            node: node,
                            points: [Y.WidgetPositionAlign.TL,
                                     Y.WidgetPositionAlign.TL]
                        },
                        progressbar: false
                    });
                rendered_overlays[api_url] = diff_overlay;
                diff_overlay.render();
            },
            failure: function() {
                node.removeChild(spinner);
                // Fail over to loading the librarian link.
                document.location = librarian_url;
            }
        },
        accept: Y.lp.client.XHTML
    };
    lp_client.get(api_url, config);
}

/*
 * Export rendered widgets.
 */
namespace.rendered_overlays = rendered_overlays;

/*
 * Link up the onclick handler for the a.diff-link in the node to the function
 * that will popup the diff in the pretty overlay.
 */
namespace.link_popup_diff_onclick = function(node, lp_client) {
    if (lp_client === undefined) {
        lp_client = new Y.lp.client.Launchpad();
    }
    var a = node.one('a.diff-link');
    if (Y.Lang.isValue(a)) {
        a.addClass('js-action');
        var librarian_url = a.getAttribute('href');
        var api_url = node.one('a.api-ref').getAttribute('href');
        a.on('click', function(e) {
                e.preventDefault();
                display_diff(a, api_url, librarian_url, lp_client);
            });
    }
};

/*
 * Connect the diff links to their pretty overlay function.
 */
namespace.connect_diff_links = function() {
    // Setup the LP client.
    var lp_client = new Y.lp.client.Launchpad();

    // Listen for the branch-linked custom event.
    Y.on('lp:branch-linked', namespace.link_popup_diff_onclick);
    // var status_content = Y.one('#branch-details-status-value');
    var nl = Y.all('.popup-diff');
    if (nl) {
        nl.each(function(node, key, node_list) {
            namespace.link_popup_diff_onclick(node, lp_client);
        });
    }
};

  }, '0.1', {requires: ['event', 'io', 'node', 'lp.ui.overlay', 'lp.client']});
