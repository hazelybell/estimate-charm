/* Copyright 2009 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Handling of form overlay widgets for bug pages.
 *
 * @module bugs
 * @submodule filebug_dupefinder
 */
YUI.add('lp.bugs.filebug_dupefinder', function(Y) {

var BLOCK = 'block',
    DISPLAY = 'display',
    EXPANDER_COLLAPSED = '/@@/treeCollapsed',
    EXPANDER_EXPANDED = '/@@/treeExpanded',
    INNER_HTML = 'innerHTML',
    NONE = 'none',
    SRC = 'src',
    HIDDEN = 'hidden';

var namespace = Y.namespace('lp.bugs.filebug_dupefinder');

/*
 * The IO provider to use. A stub may be used for testing.
 */
var YIO = Y;
/*
 * The NodeList of possible duplicates.
 */
var bug_already_reported_expanders;
/*
 * The search field on the +filebug form
 */
var search_field;
/*
 * The search button on the +filebug form
 */
var search_button;
/**
 * The base URL for similar bug searches.
 */
var search_url_base;
/**
 * The base URL for all inline +filebug work.
 */
var filebug_base_url;


/*
 * The boilerplate elements for the do-you-want-to-subscribe
 * FormOverlay.
 */
var submit_button_html =
    '<button type="submit" name="field.actions.this_is_my_bug" ' +
    'value="Yes, this is the bug I\'m trying to report">Affects Me</button>';
var cancel_button_html =
    '<button type="button" name="field.actions.cancel">Choose Again</button>';

/**
 * Return the relevant duplicate-details div for a bug-already-reported
 * expander.
 * @param expander The expander for which to return the relevant div.
 */
function get_details_div(expander) {
    var details_div = expander.get(
        'parentNode').get('parentNode').one('.duplicate-details');

    // Check that the details_div actually exists and raise an error if
    // we can't find it.
    if (!Y.Lang.isValue(details_div)) {
        Y.fail(
            "Unable to find details div for expander " + expander.get('id'));
    } else {
        return details_div;
    }
}

/**
 * Show the bug reporting form and collapse all bug details forms.
 */
function show_bug_reporting_form() {
    // If the bug reporting form is in a hidden container, as it is on
    // the AJAX dupe search, show it.
    var filebug_form_container = Y.one('#filebug-form-container');
    if (Y.Lang.isValue(filebug_form_container)) {
        filebug_form_container.setStyles({
                    'opacity': '1.0',
                    'display': 'block'
        });
    }

    // Show the bug reporting form.
    var bug_reporting_form = Y.one('#bug-reporting-form');
    bug_reporting_form.setStyle(DISPLAY, BLOCK);

    var submit_button = Y.one(Y.DOM.byId('field.actions.submit_bug'));
    submit_button.focus();
    submit_button.removeAttribute('disabled');

    // Focus the relevant elements of the form based on
    // whether the package drop-down is displayed.
    var bugtarget_package_btn = Y.one(
        Y.DOM.byId('field.bugtarget.option.package'));
    if (Y.Lang.isValue(bugtarget_package_btn)) {
        Y.one(Y.DOM.byId('field.bugtarget.package')).focus();
    } else {
        Y.one(Y.DOM.byId('field.comment')).focus();
    }
}

/**
 * Fade the bug reporting form and optionally hide it also. Only fade the
 * form if it is already visible.
 */
function fade_bug_reporting_form(hide_after_fade) {
    Y.one(Y.DOM.byId(
        'field.actions.submit_bug')).setAttribute('disabled', 'true');
    var filebug_form_container = Y.one('#filebug-form-container');
    var maybe_hide_form = function() {
        if (hide_after_fade) {
            filebug_form_container.setStyle(DISPLAY, NONE);
        }
    };

    var form_display = filebug_form_container.getStyle(DISPLAY);
    if (form_display !== NONE) {
        var form_fade_out = new Y.Anim({
            node: filebug_form_container,
            to: {opacity: 0.2},
            duration: 0.5
        });
        form_fade_out.on('end', maybe_hide_form);
        form_fade_out.run();
    } else {
        maybe_hide_form();
    }
}

/**
 * Search for bugs that may match the text that the user has entered and
 * display them in-line.
 */
function search_for_and_display_dupes() {
    function show_failure_message(transaction_id, response, args) {
        // If the request failed due to a timeout, display a message
        // explaining how the user may be able to work around it.
        var error_message = '';
        if (response.status === 503) {
            // We treat 503 (service unavailable) as a timeout because
            // that's what timeouts in LP return.
            error_message =
                "Searching for your bug in Launchpad took too long. " +
                "Try reducing the number of words in the summary " +
                "field and click \"Check again\" to retry your search. " +
                "Alternatively, you can enter the details of your bug " +
                "below.";
        } else {
            // Any other error code gets a generic message.
            error_message =
                "An error occured whilst trying to find bugs matching " +
                "the summary you entered. Click \"Check again\" to retry " +
                "your search. Alternatively, you can enter the " +
                "details of your bug below.";
        }

        var error_node = Y.Node.create('<p></p>');
        error_node.set('text', error_message);
        Y.one('#possible-duplicates').appendChild(error_node);

        Y.one('#spinner').addClass(HIDDEN);
        show_bug_reporting_form();

        Y.one(Y.DOM.byId('field.title')).set(
            'value', search_field.get('value'));
        search_button.set('value', 'Check again');
        search_button.removeClass(HIDDEN);
    }

    var on_success = function(transaction_id, response, args) {
        // Hide the spinner and show the duplicates.
        Y.one('#spinner').addClass(HIDDEN);

        var duplicate_div = Y.one('#possible-duplicates');
        duplicate_div.set(INNER_HTML, response.responseText);

        bug_already_reported_expanders = Y.all(
            'td.bug-already-reported-expander');
        if (bug_already_reported_expanders.size() > 0) {
            // If there are duplicates shown, set up the JavaScript of
            // the duplicates that have been returned.
            Y.lp.bugs.filebug_dupefinder.setup_dupes();
            // And fade out and hide the bug reporting form.
            fade_bug_reporting_form(true);
        } else {
            // Otherwise, show the bug reporting form.
            show_bug_reporting_form();
        }

        // Now we need to wire up the text expander after we load our textarea
        // onto the page, but only if we find one on the page. In testing we
        // don't have one. We want to just fail silently.
        var textarea = Y.one("#bug-reporting-form textarea");
        if (textarea) {
            textarea.plug(
                Y.lp.app.formwidgets.ResizingTextarea, {
                min_height: 300
            });
        }

        // Copy the value from the search field into the title field
        // on the filebug form.
        Y.one('#bug-reporting-form input[name="field.title"]').set(
            'value', search_field.get('value'));

        // Finally, change the label on the search button and show it again.
        search_button.set('value', 'Check again');
        search_button.removeClass(HIDDEN);
    };

    var search_term = encodeURI(search_field.get('value'));
    var search_url = search_url_base + '?title=' + search_term;

    // Hide the button and +filebug form, show the spinner and clear the
    // contents of the possible duplicates div.
    search_button.addClass(HIDDEN);
    Y.one('#spinner').removeClass(HIDDEN);
    Y.one('#possible-duplicates').set(INNER_HTML, '');

    var filebug_form_container = Y.one('#filebug-form-container');
    var form_fade_out = new Y.Anim({
        node: filebug_form_container,
        to: {opacity: 0.2},
        duration: 0.2
    });
    form_fade_out.on('end', function() {
        var config = {on: {success: on_success,
                       failure: show_failure_message}};
        YIO.io(search_url, config);
    });
    form_fade_out.run();
}

/*
 * Create the overlay for a user to optionally subscribe to a bug that
 * affects them.
 * @param form The form to which the FormOverlay is going to be
 *             attached.
 */
function create_subscribe_overlay(form) {
    // Grab the bug id and title from the "Yes, this is my bug" form.
    var bug_id = form.one(
        'input.bug-already-reported-as').get('value');
    var bug_title = Y.one('#bug-' + bug_id + '-title').get(INNER_HTML);

    if (bug_title.length > 35) {
        // Truncate the bug title if it's more than 35 characters long.
        bug_title = bug_title.substring(0, 35) + '...';
    }

    // Construct the form. This is a bit hackish but it saves us from
    // having to try to get information from TAL into JavaScript and all
    // the horror that entails.
    var subscribe_form_body =
        '<div style="width: 320px">' +
        '    <p style="width: 100%; font-size: 12px;">#'+
                bug_id + ' "' + bug_title + '"' +
        '    <br /><br /></p>' +
        '    <p style="font-weight: bold;">' +
        '       <input type="hidden" name="field.bug_already_reported_as" ' +
        '           value="' + bug_id + '" /> ' +
        '       <input type="radio" name="field.subscribe_to_existing_bug" ' +
        '           id="dont-subscribe-to-bug-' + bug_id + '" value="no" ' +
        '           class="subscribe-option" checked="true" /> ' +
        '       <label for="dont-subscribe-to-bug-' + bug_id + '"> ' +
        '         Just mark the bug as affecting me' +
        '       </label>' +
        '    </p>' +
        '    <p>' +
        '       <input type="radio" name="field.subscribe_to_existing_bug" ' +
        '           id="subscribe-to-bug-' + bug_id + '" value="yes" ' +
        '           class="subscribe-option" />' +
        '       <label for="subscribe-to-bug-' + bug_id + '"> ' +
        '         Subscribe me as well' +
        '       </label>' +
        '    </p>' +
        '</div>';

    // Create the do-you-want-to-subscribe FormOverlay.
    var subscribe_form_overlay = new Y.lp.ui.FormOverlay({
        headerContent: '<h2>Affected by this bug?</h2>',
        form_content: subscribe_form_body,
        form_submit_button: Y.Node.create(submit_button_html),
        form_cancel_button: Y.Node.create(cancel_button_html),
        centered: true,
        visible: false
    });
    subscribe_form_overlay.render('#duplicate-overlay-bug-' + bug_id);

    // Alter the overlay's properties to make sure it submits correctly
    // and to the right place.
    var form_node = subscribe_form_overlay.form_node;
    form_node.set('action', form.get('action'));
    form_node.set('method', 'post');

    // Add an on-click handler to the radio buttons to ensure that their
    // labels' styles are set correctly when they're selected.
    var radio_buttons = form.all('input.subscribe-option');
    Y.each(radio_buttons, function(radio_button) {
        var weight = radio_button.get('checked') ? 'bold' : 'normal';
        radio_button.get('parentNode').setStyle('fontWeight', weight);
    });

    return subscribe_form_overlay;
}

/**
 * Set up the dupe finder, overriding the default behaviour of the
 * +filebug search form.
 */
function set_up_dupe_finder(transaction_id, response, args) {
    // Grab the inline filebug base url and store it.
    filebug_base_url = Y.one('#filebug-base-url').getAttribute('href');
    search_url_base = Y.one('#duplicate-search-url').getAttribute('href');

    search_button = Y.one(Y.DOM.byId('field.actions.search'));
    search_field = Y.one(Y.DOM.byId('field.title'));

    if (Y.Lang.isValue(search_button)) {
        // Update the label on the search button so that it no longer
        // says "Continue".
        search_button.set('value', 'Next');

        // Change the name and id of the search field so that it doesn't
        // confuse the view when we submit a bug report.
        search_field.set('name', 'field.search');
        search_field.set('id', 'field.search');

        // Set up the handler for the search form.
        var search_form = Y.one('#filebug-search-form');
        search_form.on('submit', function(e) {
            // Prevent the event from propagating; we don't want to reload
            // the page.
            e.halt();
            search_for_and_display_dupes();
        });
    }
}

namespace.setup_dupes = function() {
    bug_already_reported_expanders = Y.all(
        'td.bug-already-reported-expander');
    var bug_reporting_form = Y.one('#bug-reporting-form');

    if (bug_already_reported_expanders.size() > 0) {
        // Set up the onclick handlers for the expanders.
        Y.each(Y.all('.similar-bug'), function(row) {
            var bug_expander = row.one('span.expander');
            var bug_details_div = row.one('div.duplicate-details');
            var bug_title_link = row.one('.duplicate-bug-link');
            bug_title_link.addClass('js-action');
            var view_bug_link = row.one('.view-bug-link');
            var expander = new Y.lp.app.widgets.expander.Expander(
                bug_expander, bug_details_div);
            expander.setUp();

            // Entire row, when clicked, expands/folds bug details.
            row.on('click', function(e) {
                e.halt();
                expander.render(!expander.isExpanded());
            });

            // The "view this bug" link shouldn't trigger the
            // collapsible, so we stop the event from propagating.
            view_bug_link.on('click', function(e) {
                e.stopPropagation();
            });

            // The same is true for the collapsible section. People
            // may want to copy and paste this, which involves
            // clicking, so we stop the onclick event from
            // propagating here, too.
            bug_details_div.on('click', function(e) {
                e.stopPropagation();
            });

            // Preventing default behaviour stops the browser from
            // emitting the focus event here as well.
            bug_title_link.on('click', function(e) {
                // Stop the click event from being emitted down
                // to the container node.
                if (this.focused_expansion === true &&
                    expander._animation.get('running')) {
                    e.stopPropagation();
                }
                this.focused_expansion = false;
                e.preventDefault();
            });

            // Set up the on focus handler for the link so that
            // tabbing will expand the different bugs.
            bug_title_link.on('focus', function(e) {
                if (!expander.isExpanded()) {
                    this.focused_expansion = true;
                    expander.render(true);

                    // If the bug reporting form is shown, hide it.
                    if (bug_reporting_form.getStyle(DISPLAY) === BLOCK) {
                        bug_reporting_form.addClass(HIDDEN);
                    }
                }
            });
        });

        // Hide the bug reporting form.
        bug_reporting_form.addClass(HIDDEN);
    }

    var bug_not_reported_button = Y.one('#bug-not-already-reported');
    if (Y.Lang.isValue(bug_not_reported_button)) {
        // The bug_not_reported_button won't show up if there aren't any
        // possible duplicates.
        bug_not_reported_button.on('click', show_bug_reporting_form);
    }

    // Attach the form overlay to the "Yes, this is my bug" forms.
    var this_is_my_bug_forms = Y.all('form.this-is-my-bug-form');
    Y.each(this_is_my_bug_forms, function(form) {
        var subscribe_form_overlay = create_subscribe_overlay(form);

        form.on('submit', function(e) {
            // We don't care about the original event, so stop it
            // and show the form overlay that we just created.
            e.halt();
            subscribe_form_overlay.show();
        });
    });
};

namespace.setup_dupe_finder = function() {
    var config = {on: {success: set_up_dupe_finder,
                   failure: function() {}}};
    // Load the filebug form asynchronously. If this fails we
    // degrade to the standard mode for bug filing, clicking through
    // to the second part of the bug filing form.
    var filebug_form_url_element = Y.one('#filebug-form-url');
    if (Y.Lang.isValue(filebug_form_url_element)) {
        var filebug_form_url = filebug_form_url_element.getAttribute('href');
        YIO.io(filebug_form_url, config);
    }
};

/**
 * Set up and configure the module.
 */
 namespace.setup_config = function(config) {
    if (config.yio !== undefined) {
        //We can be given an alternative IO provider for use in tests.
        YIO = config.yio;
    }
};

}, "0.1", {"requires": [
    "base", "io", "oop", "node", "event", "json", "lp.ui.formoverlay",
    "lp.ui.effects", "lp.app.widgets.expander",
    "lp.app.formwidgets.resizing_textarea", "plugin"]});
