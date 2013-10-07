/* Copyright 2009 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Auxiliary functions used in Soyuz pages
 *
 * @module soyuz
 * @submodule base
 * @namespace soyuz
 * @requires yahoo, node
 */

YUI.add('lp.soyuz.base', function(Y) {

var namespace = Y.namespace('lp.soyuz.base');


/*
 * Return a node containing a standard failure message to be used
 * in XHR-based page updates.
 */
namespace.makeFailureNode = function (text, handler) {
    var failure_message = Y.Node.create('<p><span></span><a>Retry</a></p>');
    failure_message.addClass('update-failure-message');
    failure_message.one('span').set('text', text);

    var retry_link = failure_message.one('a')
        .addClass('update-retry')
        .set('href', '')
        .on('click', handler);

    return failure_message;
};


/*
 * Return a node containing a standard in-progress message to be used
 * in XHR-based page updates.
 */
namespace.makeInProgressNode = function (text) {
    var in_progress_message = Y.Node.create('<p><span></span></p>');
    in_progress_message.addClass('update-in-progress-message');
    in_progress_message.one('span').set('text', text);

    return in_progress_message;
};

}, "0.1", {"requires":["node"]});
