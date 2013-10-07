/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Expandable branch revisions.
 *
 * @module lp.code.branch.revisionexpander
 * @requires node, lp.client.plugins
 */

YUI.add('lp.code.branch.revisionexpander', function(Y) {

var namespace = Y.namespace('lp.code.branch.revisionexpander');

/*
 * Take a single revno, or a pair of revnos specifying a revision range, and
 * construct a URL to get the diff of those revnos using
 * LP.cache.branch_diff_link.
 */
function bmp_get_diff_url(start_revno, end_revno) {
    var diff_url;
    if (Y.Lang.isUndefined(end_revno)) {
        /* No end_revno passed, so only after a single revision diff. */
        return LP.cache.branch_diff_link + start_revno;
    }
    diff_url = LP.cache.branch_diff_link + end_revno;
    if (start_revno !== 0) {
       diff_url += '/' + start_revno;
    } else if (start_revno === 0 && end_revno !== 1) {
       diff_url += '/null:';
    }
    return diff_url;
}

function difftext_to_node(difftext) {
    var node = Y.Node.create('<table class="diff"></table>');
    var difflines = difftext.split('\n');
    var i;
    /* Remove the empty final row caused by a trailing newline
     * (if it is empty) */
    if (difflines.length > 0 && difflines[difflines.length-1] === '') {
        difflines.pop();
    }

    for (i=0; i < difflines.length; i++) {
        var line = difflines[i];
        var line_node = Y.Node.create('<td/>');
        line_node.set('text', line + '\n');
        /* Colour the unified diff */
        var header_pat = /^(===|---|\+\+\+) /;
        var chunk_pat = /^@@ /;
        if (line.match(header_pat)) {
            line_node.addClass('diff-header');
        } else if (line.match(chunk_pat)) {
            line_node.addClass('diff-chunk');
        } else {
            switch (line[0]) {
                case '+':
                    line_node.addClass('diff-added');
                    break;
                case '-':
                    line_node.addClass('diff-removed');
                    break;
            }
        }
        line_node.addClass('text');
        var row = Y.Node.create('<tr></tr>');
        row.appendChild(line_node);
        node.appendChild(row);
    }
    return node;
}

function revision_expander_config(expander){
   return {
        on: {
            success: function nodify_result(diff) {
                expander.receive(difftext_to_node(diff));
            },
            failure: function(trid, response, args) {
                expander.receive(Y.Node.create('<pre><i>Error</i></pre>'));
            }
        }
   };
}

function bmp_diff_loader(expander, lp_client) {
    if (lp_client === undefined) {
        lp_client = new Y.lp.client.Launchpad();
    }
    var rev_no_range = expander.icon_node.get(
        'id').replace('expandable-', '').split('-');
    var start_revno = rev_no_range[0]-1;
    var end_revno = rev_no_range[1];

    lp_client.get(bmp_get_diff_url(start_revno, end_revno),
        revision_expander_config(expander));
}

namespace.bmp_diff_loader = bmp_diff_loader;
namespace.difftext_to_node = difftext_to_node;
namespace.bmp_get_diff_url = bmp_get_diff_url;

}, "0.1", {"requires": ["node", "lp.app.widgets.expander"]});
