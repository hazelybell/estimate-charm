/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Client-side rendering of the tag list portlet.
 *
 * @module bugs
 * @submodule bugtask
 */

YUI.add('lp.bugs.bugtask.taglist', function(Y) {

var namespace = Y.namespace('lp.bugs.bugtask.taglist');
var spinner;

/**
 * Setup and start the AJAX request.
 */
namespace.setup_taglist = function(config) {
    spinner = Y.one('#tags-portlet-spinner');
    var io_config = {on: {start: namespace.show_spinner,
                          success: namespace.on_success,
                          end: namespace.hide_spinner}};
    var url = Y.one('#tags-content-link').getAttribute('href').replace(
        'bugs.', '');
    var io_provider = Y.lp.client.get_configured_io_provider(config);
    io_provider.io(url, io_config);
};

/**
 * Show the loading spinner.
 */
namespace.show_spinner = function() {
    spinner.removeClass('hidden');
};

/**
 * Hide the loading spinner.
 */
namespace.hide_spinner = function() {
    spinner.addClass('hidden');
};

/**
 * Display the tag list and set up events for showing more/fewer tags.
 */
namespace.on_success = function(transactionid, response, arguments) {
    var portlet = Y.one('#portlet-tags');
    if (Y.Lang.trim(response.responseText).length === 0) {
        portlet.addClass('hidden');
    }
    else {
        portlet.prepend(response.responseText);
        var show_more_link = Y.one('#show-more-tags-link');
        var show_fewer_link = Y.one('#show-fewer-tags-link');
        var tag_list = portlet.all('.data-list li');
        if (tag_list.size() > 20) {
            var extra_tags = tag_list.slice(20);
            extra_tags.addClass('hidden');
            show_more_link.removeClass('hidden');
            show_more_link.on('click', function(e) {
                e.halt();
                extra_tags.removeClass('hidden');
                show_more_link.addClass('hidden');
                show_fewer_link.removeClass('hidden');
            });
            show_fewer_link.on('click', function(e) {
                e.halt();
                extra_tags.addClass('hidden');
                show_more_link.removeClass('hidden');
                show_fewer_link.addClass('hidden');
            });
        }
    }
};

}, "0.1", {"requires": ["node", 'io-base', 'lp.client']});
