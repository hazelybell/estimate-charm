/* Copyright 2009 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * @module lp.translations.pofile
 * @requires anim, cookie, event-key, event, node
 */

YUI.add('lp.translations.pofile', function(Y) {

var namespace = Y.namespace('lp.translations.pofile');

var KEY_CODE_TAB = 9;
var KEY_CODE_ENTER = 13;
var KEY_CODE_LEFT = 37;
var KEY_CODE_UP = 38;
var KEY_CODE_RIGHT = 39;
var KEY_CODE_DOWN = 40;
var KEY_CODE_0 = 48;
var KEY_CODE_A = 65;
var KEY_CODE_B = 66;
var KEY_CODE_C = 67;
var KEY_CODE_D = 68;
var KEY_CODE_F = 70;
var KEY_CODE_J = 74;
var KEY_CODE_K = 75;
var KEY_CODE_L = 76;
var KEY_CODE_N = 78;
var KEY_CODE_P = 80;
var KEY_CODE_R = 82;
var KEY_CODE_S = 83;

/**
 * Function to disable/enable all suggestions as they are marked/unmarked
 * for dismission.
 */
var setupSuggestionDismissal = function(e) {
    all_dismiss_boxes = Y.all('.dismiss_action');
    if (all_dismiss_boxes !== null) {
        all_dismiss_boxes.each(function(checkbox) {
            var classbase = checkbox.get('id');
            var diverge_id = classbase.replace(/dismiss/, 'diverge');
            var current_class = classbase.replace(/dismiss/, 'current');
            var current_radios = Y.all('.' + current_class);
            var dismissables = Y.all('.' + classbase+'able');
            // The button and textarea cannot be fetched beforehand
            // because they are or may be created dynamically.
            var dismissable_inputs_class = [
                '.', classbase, 'able_button input, ',
                '.', classbase, 'able_button button, ',
                '.', classbase, 'able_button textarea'].join("");
            checkbox.on('click', function(e) {
                if (checkbox.get('checked')) {
                    dismissables.addClass('dismissed');
                    Y.all(dismissable_inputs_class).set('checked', false);
                    Y.all(dismissable_inputs_class).set('disabled', true);
                    Y.all('#' + diverge_id).set('disabled', false);
                    current_radios.set('checked', true);
                } else {
                    dismissables.removeClass('dismissed');
                    Y.all(dismissable_inputs_class).set('disabled', false);
                }
            });
        });
    }
};


var hide_notification = function(node) {
  var hide_anim = new Y.Anim({
      node: node,
      to: { height: 0,
            marginTop: 0, marginBottom: 0,
            paddingTop: 0, paddingBottom: 0 }
  });
  node.setStyle('border', 'none');
  hide_anim.set('duration', 0.4);
  hide_anim.on('end', function(e) {
      node.setStyle('display', 'none');
  });
  hide_anim.run();
};


var updateNotificationBox = function(e) {
  var notice = Y.one('.important-notice-container');
  if (notice === null) {
    // We have no notice container on this page, this is why there is
    // nothing more to be done by this function.
    return;
  }
  var balloon = notice.one('.important-notice-balloon');
  var dismiss_notice_cookie = ('translation-docs-for-' +
                               documentation_cookie);

  // Check the cookie to see if the user has already dismissed
  // the notification box for this session.
  var already_seen = Y.Cookie.get(dismiss_notice_cookie, Boolean);
  if (already_seen !== null) {
     notice.setStyle('display', 'none');
  }

  var cancel_button = notice.one(
      '.important-notice-cancel-button');
  // Cancel button starts out hidden.  If user has JavaScript,
  // then we want to show it.
  if (cancel_button === null) {
    // No cancel button was found to attach the action.
    return;
  }
  cancel_button.setStyle('visibility', 'visible');
  cancel_button.on('click', function(e) {
      e.halt();
      hide_notification(balloon);
      Y.Cookie.set(dismiss_notice_cookie, true);
  });
};

var WORKING_MODE_SWITCH_ID = "#translation-switch-working-mode";
var WORKING_MODE_CONTAINER_ID = "#translation-switch-working-mode-container";
var WORKING_MODE_COOKIE = "translation-working-mode";
var WORKING_MODE_REVIEWER = "reviewer";
var WORKING_MODE_TRANSLATOR = "translator";

/*
 * This function is sanitizing the WORKING_MODE_COOKIE and in case it contains
 * unknow values, we play it safe by returning WORKING_MODE_REVIEWER, which
 * is the default mode.
 */
var getWorkingMode = function () {
    var current_mode = Y.Cookie.get(WORKING_MODE_COOKIE);
    if (current_mode === WORKING_MODE_TRANSLATOR) {
        return WORKING_MODE_TRANSLATOR;
    } else {
        return WORKING_MODE_REVIEWER;
    }
};

var setWorkingMode = function (mode) {
    if(mode === WORKING_MODE_TRANSLATOR) {
        text = 'Translator&nbsp;mode';
    } else {
        text = 'Reviewer&nbsp;mode';
    }
    Y.one(WORKING_MODE_SWITCH_ID).set('innerHTML', text);
    Y.Cookie.set(WORKING_MODE_COOKIE, mode, {path: "/"});
};

var switchWorkingMode = function () {
    if (getWorkingMode() === WORKING_MODE_TRANSLATOR) {
        setWorkingMode(WORKING_MODE_REVIEWER);
    } else {
        setWorkingMode(WORKING_MODE_TRANSLATOR);
    }
};


/**
 * Initialize the current working mode and attach the node event for
 * switching between modes.
 */
var initializeWorkingMode = function () {

    var working_mode = Y.one(WORKING_MODE_CONTAINER_ID);
    if (working_mode !== null) {
        working_mode.removeClass('hidden');
        setWorkingMode(getWorkingMode());
        Y.on("click", switchWorkingMode, WORKING_MODE_SWITCH_ID);
    }
};


var setFocus = function(field) {
    // if there is nofield, do nothing
    if (Y.one('#' + field) !== null) {
        Y.one('#' + field).focus();
    }
};


var setNextFocus = function(e, field) {
    setFocus(field);
    // stopPropagation() and preventDefault()
    e.halt();
};


var setPreviousFocus = function(e, field, original) {

    // Original singular test is focused first to make sure
    // it is visible when scrolling up
    setFocus(original);
    setFocus(field);
    // stopPropagation() and preventDefault()
    e.halt();
};


var copyOriginalTextOne = function(from_id, to_id, select_id) {
    var from = Y.one('#' + from_id);
    var to = Y.one('#' + to_id);
    if (from.hasClass('no-translation')) {
        to.set('value', '');
        return;
    }
    to.set('value', from.get('text'));
    selectWidgetByID(select_id);
};


var copyOriginalTextPlural = function(e, from_id, to_id_pattern, nplurals) {
    e.halt();
    // skip when x is 0, as that is the singular
    var x;
    for (x = 1; x < nplurals; x++) {
        var to_id = to_id_pattern + x + "_new";
        var to_select = to_id_pattern + x + "_new_select";
        copyOriginalTextOne(from_id, to_id, to_select);
    }
};


var copyOriginalTextAll = function(e, msgset_id, translation_stem) {

    // stopPropagation() and preventDefault()
    e.halt();

    var original_singular = msgset_id + '_singular';
    var original_plural = msgset_id + '_plural';
    var singular_select = translation_stem + '_translation_0_new_select';
    var translation_singular = translation_stem + '_translation_0_new';
    var translation_plural = translation_stem + '_translation_';
    // Copy singular text
    copyOriginalTextOne(
        original_singular, translation_singular, singular_select);

    // Copy plural text if needed
    if (Y.Lang.isValue(Y.one('#' + translation_plural + '1'))) {
        copyOriginalTextPlural(
            e, original_plural, translation_plural, plural_forms);
    }
};


var selectWidgetByID = function(widget) {
    var node = Y.one('#' + widget);
    if (node !== null) {
        node.set('checked', true);
    }
};


var toggleWidget = function(widget) {
    var node = Y.one('#' + widget);
    if (node !== null) {
        if (node.get('checked')) {
            node.set('checked', false);
        } else {
            node.set('checked', true);
        }
    }
};


var selectTranslation = function(e, field) {
    // Don't select when tabbing, navigating and simply pressing
    // enter to submit the form.
    // Also, don't select when using keyboard shortcuts (ie Alt+Shift+KEY)
    // Looks like this is not needed for Epiphany and Chromium
    if (e.keyCode === KEY_CODE_TAB || e.keyCode === KEY_CODE_ENTER ||
        e.keyCode === KEY_CODE_LEFT || e.keyCode === KEY_CODE_UP ||
        e.keyCode === KEY_CODE_RIGHT || e.keyCode === KEY_CODE_DOWN ||
        (e.shiftKey && e.altKey)) {
            return;
    }

    // translation_select_id has one of the following formats:
    //  * msgset_1_es_translation_0_new_select
    //  * msgset_2_pt_BR_translation_0_new_select
    var translation_select_id = field + '_select';
    selectWidgetByID(translation_select_id);

    var working_mode_switch = Y.one(WORKING_MODE_SWITCH_ID);
    // Autoselect the force suggestion checkbox only if working in translator
    // mode and the switch is on the page.
    if (working_mode_switch !== null &&
        getWorkingMode() === WORKING_MODE_TRANSLATOR) {
        var translation_field = Y.one('#' + field);
        if (translation_field !== null &&
            translation_field.get('value') === '') {
            var html_parts = field.split('_');
            var force_suggestion = (
                html_parts[0] + '_' + html_parts[1] +
                '_force_suggestion');
            selectWidgetByID(force_suggestion);
        }
    }

};


var initializeGlobalKeyBindings = function(fields) {

    Y.one('document').on("keyup", function(e) {
        var link;
        // Shift+Alt+S - Save form
        if (e.shiftKey && e.altKey && e.keyCode === KEY_CODE_S) {
            Y.one('#save_and_continue_button').invoke('click');
        }
        // Shift+Alt+F - Go to search field
        if (e.shiftKey && e.altKey && e.keyCode === KEY_CODE_F) {
            setFocus('search_box');
        }
        // Shift+Alt+B - Go to first translation field
        if (e.shiftKey && e.altKey && e.keyCode === KEY_CODE_B) {
            setFocus(fields[0]);
        }
        // Shift+Alt+N - Go to next page in batch
        if (e.shiftKey && e.altKey && e.keyCode === KEY_CODE_N) {
            link = Y.one('#batchnav_next');
            if (link !== null){
                window.location.assign(link.get('href'));
            }
        }
        // Shift+Alt+P - Go to previous page in batch
        if (e.shiftKey && e.altKey && e.keyCode === KEY_CODE_P) {
            link = Y.one('#batchnav_previous');
            if (link !== null){
                window.location.assign(link.get('href'));
            }
        }
        // Shift+Alt+A - Go to first page in batch
        if (e.shiftKey && e.altKey && e.keyCode === KEY_CODE_A) {
            link = Y.one('#batchnav_first');
            if (link !== null){
                window.location.assign(link.get('href'));
            }
        }
        // Shift+Alt+L - Go to last page in batch
        if (e.shiftKey && e.altKey && e.keyCode === KEY_CODE_L) {
            link = Y.one('#batchnav_last');
            if (link !== null){
                window.location.assign(link.get('href'));
            }
        }
    });
};

var copyTranslationClickHandler = function(
        node, allow_default_processing, to_field_id, from_field_id) {
    node.on(
        'click', function(e) {
            var select_node_id = to_field_id.replace(/_new/, "_new_select");
            if (!allow_default_processing) {
                e.halt();
            } else {
                select_node_id = null;
            }
            if (!Y.Lang.isValue(from_field_id)) {
                from_field_id = to_field_id.replace(/_new/, "");
            }
            copyOriginalTextOne(
                from_field_id,
                to_field_id, select_node_id);
        });
};


/**
 * Wire the click handler for the copy links and radio buttons.
 * @param fields
 */
var initializeFieldsClickHandlers = function(fields) {
    var radiobutton_click_handler = function(node) {
        var from_node_id = node.get('id').replace(/_radiobutton/, '');
        copyTranslationClickHandler(
            node, true, fields[key], from_node_id);
    };
    var link_click_handler = function(node) {
        var from_node_id =
            node.get('id').replace(/_singular_copy_text/, '');
        copyTranslationClickHandler(
            node, false, fields[key], from_node_id);
    };
    var key;
    for (key = 0; key < fields.length-1; key++) {
        var html_parts = fields[key].split('_');
        var msgset_id = html_parts[0] + '_' + html_parts[1];
        var translation_stem = fields[key].replace(
            /_translation_(\d)+_new/,"");

        var node = Y.one('#' + msgset_id + '_singular_copy_text');
        if (Y.Lang.isValue(node)) {
            node.on(
                'click', copyOriginalTextAll, Y, msgset_id,
                translation_stem);
        }
        node = Y.one('#' + msgset_id + '_plural_copy_text');
        if (Y.Lang.isValue(node)) {
            node.on(
                'click', copyOriginalTextPlural, Y, msgset_id + '_plural',
                translation_stem + '_translation_', plural_forms);
        }
        node = Y.one('#' + fields[key].replace(/_new/, "_radiobutton"));
        if (Y.Lang.isValue(node)) {
            copyTranslationClickHandler(node, true, fields[key]);
        }
        node = Y.one('#' + fields[key].replace(
            /_new/, "_singular_copy_text"));
        if (Y.Lang.isValue(node)) {
            copyTranslationClickHandler(node, false, fields[key]);
        }
        var rbs = Y.all('.' + fields[key].replace(/_new/,"") + ' input');
        rbs.each(radiobutton_click_handler);
        var links = Y.all('.' + fields[key].replace(/_new/,"") + ' a');
        links.each(link_click_handler);
    }
};

var initializeSuggestionsKeyBindings = function(stem) {

    var suggestions = Y.all('.' + stem.replace(/_new/,"") + ' input');
    suggestions.each(function(node) {
        // Only add keybinding for the first 9 suggestions
        var index = suggestions.indexOf(node);
        if (index < 10) {
            // Shift+Alt+NUMBER - Mark suggestion NUMBER
            Y.on('key', function(e, id) {
                    selectWidgetByID(id);
                },
                '#' + stem, 'down:' + Number(index+49) + '+shift+alt',
                Y, node.get('id'));
        }
    });
};


/*
 * Adapter for calling functions from Y.on().
 * It is used for ignoring the `event` parameter that is passed to all
 * functions called by Y.on().
 */
var on_event_adapter = function(event, method, argument) {
    method(argument);
};


/**
 * Set up the key bindings for a given field.
 * @param field_id
 */
var setupFieldKeyBindings = function(field_id, field_node) {
    // field_id has one of the following formats:
    //  * msgset_1_es_translation_0_new
    //  * msgset_2_pt_BR_translation_0_new
    // msgset_id is 'msgset_1' or 'msgset_2'
    // translation_stem has one of the following formats:
    //  * msgset_1_es
    //  * msgset_2_pt_BR
    var html_parts = field_id.split('_');
    var msgset_id = html_parts[0] + '_' + html_parts[1];
    var translation_stem = field_id.replace(
        /_translation_(\d)+_new/,"");

    if (!Y.Lang.isValue(field_node)) {
        field_node = Y.one('#' + field_id);
    }
    Y.on(
        'change', selectTranslation,
        field_node, Y, field_id);
    Y.on(
        'keypress', selectTranslation,
        field_node, Y, field_id);

    // Shift+Alt+C - Copy original text
    Y.on(
        'key', copyOriginalTextAll, field_node,
        'down:' + KEY_CODE_C + '+shift+alt',
        Y, msgset_id, translation_stem);

    // Shift+Alt+R - Toggle someone should review
    Y.on(
        'key', on_event_adapter,
        field_node, 'down:' + KEY_CODE_R + '+shift+alt', Y,
        toggleWidget, msgset_id + '_force_suggestion');

    // Shift+Alt+D - Toggle dismiss all translations
    Y.on(
        'key', on_event_adapter,
        field_node, 'down:' + KEY_CODE_D + '+shift+alt', Y,
        toggleWidget, msgset_id + '_dismiss');

    // Shift+Alt+0 - Mark current translation
    Y.on(
        'key', on_event_adapter,
        field_node, 'down:' + KEY_CODE_0 + '+shift+alt', Y,
        selectWidgetByID,
        field_id.replace(/_new/, "_radiobutton"));

    initializeSuggestionsKeyBindings(field_id);
};


var initializeFieldsKeyBindings = function (fields) {
    var key;
    for (key = 0; key < fields.length; key++) {
        var next = key + 1;
        var previous = key - 1;

        // Set next field and copy text for all but last field
        // (last is Save & Continue button)
        if (key < fields.length - 1) {
            // Shift+Alt+J - Go to next translation
            Y.on(
                'key', setNextFocus, '#' + fields[key],
                'down:' + KEY_CODE_J + '+shift+alt', Y, fields[next]);
            // Shift+Alt+KEY_DOWN - Go to next translation
            Y.on(
                'key', setNextFocus, '#' + fields[key],
                'down:' + KEY_CODE_DOWN + '+shift+alt', Y, fields[next]);

            setupFieldKeyBindings(fields[key]);
        }

        // Set previous field for all but first field
        if (key > 0) {
            var parts = fields[previous].split('_');
            var singular_copy_text = (
                parts[0] + '_' + parts[1] + '_singular_copy_text');
            // Shift+Alt+K - Go to previous translation
            Y.on(
                'key', setPreviousFocus, '#' + fields[key],
                'down:' + KEY_CODE_K + '+shift+alt', Y, fields[previous],
                singular_copy_text);
            // Shift+Alt+KEY_UP - Go to previous translation
            Y.on(
                'key', setPreviousFocus, '#' + fields[key],
                'down:' + KEY_CODE_UP + '+shift+alt', Y, fields[previous],
                singular_copy_text);
        }
    }
};


/**
 * Force suggestion and diverge translation checkboxes are mutually excluded.
 * Checking one of them will disable the other.
 * When the dismiss all suggestion checkbox is checked, uncheking the
 * diverte translation checkbox should keep the force suggestion disabled.
 */
var initializeReviewDivergeMutualExclusion = function (fields) {

    var suggestion_checkbox_click_handler = function(
            e, suggestion_checkbox, diverge_checkbox) {
        if (suggestion_checkbox.get('checked') === true) {
            diverge_checkbox.set('disabled', true);
        } else {
            diverge_checkbox.set('disabled', false);
        }
    };
    var diverge_checkbox_click_handler = function(
            e, suggestion_checkbox, diverge_checkbox, msgset_id) {
        if (diverge_checkbox.get('checked') === true) {
            suggestion_checkbox.set('disabled', true);
        } else {
            // Don't enable the force suggestion checkbox if dismiss
            // all suggestions is enabled.
            var dismiss_checkbox = Y.one(
                '#' + msgset_id + '_dismiss');
            if (dismiss_checkbox !== null &&
                dismiss_checkbox.get('checked') === true) {
                return;
            }
            suggestion_checkbox.set('disabled', false);
        }
    };

    // Diverge message field format is 'msgset_ID_diverge'
    // Force suggestion field format is 'msgset_ID_force_suggestion'
    var key;
    for (key = 0; key < fields.length; key++) {
        var html_parts = fields[key].split('_');
        var msgset_id = html_parts[0] + '_' + html_parts[1];
        var diverge_id = msgset_id + '_diverge';
        var suggestion_id = msgset_id + '_force_suggestion';
        var diverge_checkbox = Y.one('#' + diverge_id);
        var suggestion_checkbox = Y.one('#' + suggestion_id);

        if (diverge_checkbox === null || suggestion_checkbox === null) {
            break;
        }

        Y.on(
            'click', suggestion_checkbox_click_handler,
            Y, suggestion_checkbox, diverge_checkbox);

        Y.on(
            'click', diverge_checkbox_click_handler,
            Y, suggestion_checkbox, diverge_checkbox, msgset_id);
    }
};


/**
 * Initialize event-key bindings such as moving to the next or previous
 * field, or copying original text
 */
var initializeKeyBindings = function(e) {
    if (translations_order.length < 1) {
        // If no translations fiels are displayed on the page
        // don't initialize the translations order
        return;
    }

    var fields = translations_order.split(' ');
    // The last field is Save & Continue button
    fields.push('save_and_continue_button');

    initializeGlobalKeyBindings(fields);
    initializeFieldsKeyBindings(fields);
    initializeFieldsClickHandlers(fields);
};

/*
 * Controls the behavior for reseting current translations
 */
var resetTranslation = function (event, translation_id) {
    if (this === null) {
        // Don't do nothing if we don't have a context object.
        return;
    }
    if (this.get('checked') === true) {
        var new_translation_select = Y.one(
            '#' + translation_id + '_select');
        if (new_translation_select !== null) {
            new_translation_select.set('checked', true);
        }
    } else {
        var new_translation_field = Y.one('#' + translation_id);
        if (new_translation_field !== null &&
            new_translation_field.get('value') === '') {
           var current_select_id = translation_id.replace(
               /_new$/, '_radiobutton');
           var current_select = Y.one('#' + current_select_id);
           if (current_select !== null) {
               current_select.set('checked', true);
           }
        }
    }
};


/**
 * Translations can be reset by submitting an empty translations and ticking
 * the 'Someone should review this translation' checkbox.
 * Ticking the 'Someone should review this translation' will automatically
 * select the new empty translation.
 */
var initializeResetBehavior = function (fields) {
    var key;
    for (key = 0; key < fields.length; key++) {
        var html_parts = fields[key].split('_');
        var msgset_id = html_parts[0] + '_' + html_parts[1];
        var node = Y.one('#' + msgset_id + '_force_suggestion');
        if (node === null) {
            // If we don't have a force_suggestion checkbox associated with
            // this field, just continue to the next field.
            break;
        }
        Y.on('click', resetTranslation, node , node, fields[key]
        );
    }
};


/**
 * Initialize common Javascript code for POFile and TranslationMessage
 * +translate pages.
 *
 * This will add event-key bindings such as moving to the next or previous
 * field, or copying original text.
 * It will also initializing the reset checkbox behavior and will show the
 * error notifications.
 */
var initializeBaseTranslate = function () {
    try {
      setupSuggestionDismissal();
    } catch (setup_suggestion_dismissal_error) {
      Y.log(setup_suggestion_dismissal_error, "error");
    }

    try {
      initializeKeyBindings();
    } catch (initialize_key_bindings_error) {
      Y.log(initialize_key_bindings_error, "error");
    }

    try {
      var fields = translations_order.split(' ');
      initializeResetBehavior(fields);
    } catch (initialize_reset_behavior_error) {
      Y.log(initialize_reset_behavior_error, "error");
    }

    try {
    initializeWorkingMode();
    } catch (initialize_working_mode_errors) {
      Y.log(initialize_working_mode_errors, "error");
    }

    try {
      setFocus(autofocus_field);
    } catch (set_focus_error) {
      Y.log(set_focus_error, "error");
    }
};


var convertTextInputToTextArea = function(current_text_input, rows) {
    var new_text_area = Y.Node.create("<textarea></textarea>")
            .set('id', current_text_input.get('id'))
            .set('name', current_text_input.get('name'))
            .set('lang', current_text_input.get('lang'))
            .set('dir', current_text_input.get('dir'))
            .set('rows', rows);
    new_text_area.set('value', current_text_input.get('value'));
    current_text_input.replace(new_text_area);
    setupFieldKeyBindings(new_text_area.get('id'), new_text_area);
    return new_text_area;
};


var insertAllExpansionButtons = function() {
    Y.all('input.expandable').each(function(expandable_field) {
        var button = Y.Node.create('<button><img></img></button>')
                .set('title',
                     'Makes the field larger, so you can see more text.')
                .setStyles({
                    'padding': '0'});
        button.one('img')
                .set('alt',
                     'Enlarge Field')
                .set('src',
                     '/+icing/translations-add-more-lines.gif');
        button.on('click', function(e) {
            e.halt();
            var text_area = convertTextInputToTextArea(expandable_field, 6);
            text_area.focus();
            button.remove();
            return false;
        });
        expandable_field.get('parentNode').appendChild(button);
    });
};


/*
 * Initialize Javascript code for a POFile +translate page.
 */
namespace.initializePOFile = function(e) {
    try {
      updateNotificationBox();
    } catch (update_notification_box_error) {
      Y.log(update_notification_box_error, "error");
    }
    initializeBaseTranslate();
    insertAllExpansionButtons();
};


/*
 * Initialize Javascript code for a TranslationMessage +translate page.
 */
namespace.initializeTranslationMessage = function(e) {

    try {
        var fields = translations_order.split(' ');
        initializeReviewDivergeMutualExclusion(fields);
    } catch (initialize_review_diverge_mutual_exclusion_error) {
      Y.log(e, "error");
    }

    initializeBaseTranslate();
};

}, "0.1", {"requires": ["event", "event-key", "node", "cookie", "anim"]});
