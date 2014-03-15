/* Copyright 2009 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * @module Languages
 * @requires oop, event, node
 */

YUI.add('lp.languages', function(Y) {

var languages = Y.namespace('lp.languages');

/* Prefilled in initialize_language_page. */
var all_languages;

var hide_and_show = function(searchstring) {
    searchstring = searchstring.toLowerCase();
    var count_matches = 0;
    all_languages.each(function(element, index, list) {
        var href = element.get('href');
        var code = href.substr(href.lastIndexOf("/")+1);
        var english_name = element.get('text').toLowerCase();
        var comment_start = english_name.indexOf(' (');
        if(comment_start != -1) {
            english_name = english_name.substring(0, comment_start);
        }
        if(code.indexOf(searchstring) == -1 &&
           english_name.indexOf(searchstring) == -1) {
            element.ancestor('li').addClass('hidden');
        }
        else {
            count_matches = count_matches +1;
            element.ancestor('li').removeClass('hidden');
        }
    });
    var no_filter_matches = Y.one('#no_filter_matches');
    if(count_matches == 0) {
        no_filter_matches.removeClass('hidden');
    }
    else {
        no_filter_matches.addClass('hidden');
    }
};

var init_filter_form = function() {
    var heading = Y.one('.searchform h2');
    heading.setContent('Filter languages in Launchpad');
    var button = Y.one('.searchform input.submit');
    var inputfind = Y.one('.searchform input.textType');
    button.set('value', 'Filter languages');
    all_languages = Y.all('#all-languages li a');
    button.on('click', function(e){
        e.preventDefault();
        hide_and_show(inputfind.get('value'));
    });
};


languages.initialize_languages_page = function(Y) {
    init_filter_form();
};


// "oop" and "event" are required to fix known bugs in YUI, which
// are apparently fixed in a later version.
}, "0.1", {"requires": ["oop", "event", "node"]});
