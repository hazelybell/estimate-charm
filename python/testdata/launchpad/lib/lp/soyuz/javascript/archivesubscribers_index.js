/* Copyright 2009 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Enhancements for adding ppa subscribers.
 *
 * @module soyuz
 * @submodule archivesubscribers_index
 * @requires  event, node, oop
 */
YUI.add('lp.soyuz.archivesubscribers_index', function(Y) {

var namespace = Y.namespace('lp.soyuz.archivesubscribers_index');

/*
 * Setup the style and click handler for the add subscriber link.
 *
 * @method setup_archivesubscribers_index
 */
namespace.setup_archivesubscribers_index = function() {
    // If there are no errors then we hide the add-subscriber row and
    // potentially the whole table if there are no subscribers.
    if (Y.Lang.isNull(Y.one('p.error.message'))) {

        // Hide the add-subscriber row.
        var add_subscriber_row = Y.one(
            '#archive-subscribers .add-subscriber');
        add_subscriber_row.setStyle('display', 'none');

        // If there are no subscribers, then hide the complete section.
        var subscribers = Y.one('#subscribers');
        if (Y.Lang.isObject(Y.one('#no-subscribers'))) {
            subscribers.setStyle('display', 'none');
        }
    }

    // Add a link to open the add-subscriber row.
    var placeholder = Y.one('#add-subscriber-placeholder');
    placeholder.set(
        'innerHTML',
        '<a class="js-action sprite add" href="#">Add access</a>');

    // Unfortunately we can't use the lazr slider, as it uses display:block
    // which breaks table rows (they use display:table-row).
    function show_add_subscriber(e) {
        e.preventDefault();
        subscribers.setStyle('display', 'block');
        add_subscriber_row.setStyle('display', 'table-row');
    }

    Y.on('click', show_add_subscriber,
         '#add-subscriber-placeholder a');
};

}, "0.1", {"requires": ["oop", "node", "event"]});

