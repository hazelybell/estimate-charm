/* Copyright 2010 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * @module lp.translations.languages
 * @requires node
 */

YUI.add('lp.translations.languages', function(Y) {

var namespace = Y.namespace('lp.translations.languages');

var toggle_node_visibility = function(node, index, list) {
  node.toggleClass('hidden');
  node.toggleClass('seen');
};

/**
 * Set up the initial visibility for languages in a serieslanguages table.
 */
namespace.initialize_languages_table = function(Y) {
    Y.all('.not-preferred-language').each(function(node, index, list) {
        node.addClass('hidden');
    });
    Y.all('.preferred-language').each(function(node, index, list) {
        node.addClass('seen');
    });
};


/**
 * Toggle visibility for languages in a serieslanguages table.
 */
namespace.toggle_languages_visibility = function(e) {
    e.preventDefault();
    Y.all('.not-preferred-language').each(toggle_node_visibility);
    var toggle_button = e.currentTarget;
    if (toggle_button.hasClass('all-languages-visible')) {
      toggle_button.setContent('View all languages');
      toggle_button.removeClass('all-languages-visible');
    } else {
      toggle_button.setContent('View only preferred languages');
      toggle_button.addClass('all-languages-visible');
    }
};


}, "0.1", {"requires": ["node"]});

