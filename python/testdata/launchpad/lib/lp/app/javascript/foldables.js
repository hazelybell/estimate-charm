/**
 * Copyright 2011 Canonical Ltd. This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Making foldable sections of html
 *
 * Usage:
 *  lp.app.foldables.activate();
 *
 * @module lp.app.foldables
 */

YUI.add('lp.app.foldables', function(Y) {

    var module = Y.namespace('lp.app.foldables');
    var VOID_URL = '_:void(0);'.replace('_', 'javascript');

    var toggleFoldable = function(e) {
        var ELEMENT_NODE = 1;
        var node = e.currentTarget;
        while (node.get('nextSibling')) {
            node = node.get('nextSibling');
            if (node.get('nodeType') !== ELEMENT_NODE) {
                continue;
            }
            if (!node.hasClass('foldable') &&
                !node.hasClass('foldable-quoted')) {
                continue;
            }
            if (node.getStyle('display') === 'none') {
                node.setStyle('display', 'inline');
            } else {
                node.setStyle('display', 'none');
            }
        }
    };

    module.activate = function () {
        // Create links to toggle the display of foldable content.
        var included = Y.all('span.foldable');
        var quoted = Y.all('span.foldable-quoted');
        quoted.each(function (n) {
            included.push(n);
        });

        included.each(function (span, index, list) {
            if (span.hasClass('foldable-quoted')) {
                var quoted_lines = span.all('br');
                if (quoted_lines && quoted_lines.size() <= 11) {
                    // We do not hide short quoted passages (12 lines) by
                    // default.
                    return;
                }
            }

            var ellipsis = Y.Node.create('<a/>');
            ellipsis.setStyle('textDecoration', 'underline');
            ellipsis.set('href', VOID_URL);
            ellipsis.on('click', toggleFoldable);
            ellipsis.appendChild(Y.Node.create('[...]'));

            span.get('parentNode').insertBefore(ellipsis, span);
            span.insertBefore(Y.Node.create('<br/>'), span.get('firstChild'));
            span.setStyle('display', 'none');
            if (span.get('nextSibling')) {
                // Text lines follows this span.
                var br = Y.Node.create('<br/>');
                span.get('parentNode').insertBefore(
                    br,
                    span.get('nextSibling')
                );
            }
        });
    };

}, '0.1.0', {
    requires: ['base', 'node']
});
