/* Copyright 2010 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * @module lp.translations.importqueueentry
 * @requires node, lp.anim
 */

YUI.add('lp.translations.importqueueentry', function(Y) {

var namespace = Y.namespace('lp.translations.importqueueentry');


/**
 * Groups of form fields to be visible per file type.
 * @private
 */
var field_groups = {
    'POT': ['potemplate', 'name', 'translation_domain', 'languagepack'],
    'PO': ['potemplate', 'potemplate_name', 'language'],
    'UNSPEC': []
};


var last_file_type = 'UNSPEC';

var hidden_field_class = 'hidden';

/* Last selected template name and translation domain that are not among
 * the options in the templates dropdown.
 */
var custom_template_name, custom_translation_domain;


/**
 * Find a page element by HTML id.
 *
 * Works around a YUI bug.
 *
 * @private
 * @param elem_id The HTML id of an element on the current page.
 * @return The DOM Node with that id, or None.
 */
function getElemById(elem_id) {
    /* XXX HenningEggers 2009-03-24: 'elem_id' is a Zope form field, and
     * triggers YUI bug #2423101.  We'll work around it.
     */
    return Y.one(Y.DOM.byId(elem_id));
}


/**
 * Find the DOM input element for a given zope field.
 * @private
 * @param field_name Name of a zope form field.
 * @return DOM input field corresponding to the zope form field.
 */
function getFormField(field_name) {
    return getElemById('field.' + field_name);
}


/**
 * Retrieve current value of a form field, or null if it does not exist.
 * @private
 * @param field_name Zope form field name.
 */
function getFormFieldValue(field_name) {
    var field = getFormField(field_name);
    return (field === null) ? null : field.get('value');
}


/**
 * Find the table row that contains the given form field.
 * @private
 * @param field_name Name of a zope form field.
 * @return DOM entry containing the entire zope form field including
 *  markup.
 */
function getFormEntry(field_name) {
    /* We're interested in the tr tag surrounding the input element that
     * Zope generated for the field.  The input element's id consists of
     * the string "field" and the field's name, joined by a dot.
     */
    var field = getFormField(field_name);
    return (field === null) ? null : field.ancestor('tr');
}


/**
 * Is the form field of the given name currently visible?
 * @private
 * @param field_name Zope form field name.
 */
function isFieldVisible(field_name) {
    var entry = getFormEntry(field_name);
    return (entry === null) ? false : !entry.hasClass(hidden_field_class);
}


/**
 * If field is shown, update its value.
 * @private
 * @param field_name Zope form field name to update.
 * @param value New value for input field.
 */
function updateFieldInputIfShown(field_name, value) {
    if (isFieldVisible(field_name)) {
        getFormField(field_name).set('value', value);
    }
}


/**
 * Apply function `alteration` to the form fields for a given file type.
 * @private
 * @param file_type Apply to fields associated with this file type.
 * @param alteration Function to run for each field; takes the field's
 *  DOM element as an argument.
 */
function alterFields(file_type, alteration) {
    var field_names = field_groups[file_type];
    if (field_names !== null) {
        Y.Array.each(field_names, function (field_name) {
            var tr = getFormEntry(field_name);
            if (tr !== null) {
                alteration(tr);
            }
        });
    }
}


/**
 * Change selected file type.
 * @private
 * @param file_type The newly selected file type.
 * @param interactively Animate the appareance of previously hidden fields.
 */
function updateCurrentFileType(file_type, interactively) {
    // Hide irrelevant fields.
    var hideElement = function (element) {
        element.addClass(hidden_field_class);
    };
    for (var group in field_groups) {
        if (group !== file_type) {
            alterFields(group, hideElement);
        }
    }

    // Reveal relevant fields.
    var showElement = function (element) {
        element.removeClass(hidden_field_class);
    };
    alterFields(file_type, showElement);

    if (interactively) {
        // Animate revealed fields.
        var animateElement = function (element) {
            Y.lp.anim.green_flash({node: element}).run();
        };
        alterFields(file_type, animateElement);
    }

    last_file_type = file_type;
}


/**
 * Update the state of the templates dropdown to reflect the current
 * contents of the name and translation_domain fields.
 */
function updateTemplatesDropdown() {
    var name = getFormFieldValue('name');
    var domain = getFormFieldValue('translation_domain');
    var potemplate_dropdown = getFormField('potemplate');
    var options = potemplate_dropdown.get('options');
    var num_options = options.size();

    for (var option_index = 0; option_index < num_options; option_index++) {
        var option = options.item(option_index);
        var known_name = option.get('textContent');
        if (known_name == name && template_domains[known_name] == domain) {
            // The current template name/domain are in the dropdown's
            // options.  Select that option.
            potemplate_dropdown.set('selectedIndex', option_index);
            return;
        }
    }

    // No match.  Select no template.
    potemplate_dropdown.set('selectedIndex', 0);
    custom_template_name = name;
    custom_translation_domain = domain;
}


/**
 * Handle a change to the templates dropdown.
 */
function handleTemplateChoice(e) {
    var dropdown = e.target;
    var option_index = dropdown.get('selectedIndex');
    var name, domain;
    if (option_index > 0) {
        // Template selected.  Use its name and translation domain.
        name = dropdown.get('options').item(option_index).get('text');
        domain = template_domains[name];
    } else {
        // No template selected.  Pick whatever we had for this case.
        name = custom_template_name;
        domain = custom_translation_domain;
    }
    updateFieldInputIfShown('name', name);
    updateFieldInputIfShown('translation_domain', domain);
}


/**
 * Set up the templates dropdown and related event handlers.
 */
function setUpTemplatesChoice() {
    custom_template_name = getFormFieldValue('name');
    custom_translation_domain = getFormFieldValue('translation_domain');
    updateTemplatesDropdown();

    getFormField('potemplate').on('change', handleTemplateChoice);

    getFormField('name').on('change', updateTemplatesDropdown);
    getFormField('translation_domain').on('change', updateTemplatesDropdown);
}


/**
 * Handle change event for current file type.
 * @private
 */
function handleFileTypeChange() {
    var file_type = this.get('value');
    if (file_type != last_file_type) {
        updateCurrentFileType(file_type, true);
    }
}


/**
 * Set up the import-queue-entry page.
 */
namespace.setup_page = function () {
    var file_type_field = getFormField('file_type');
    var preselected_file_type = file_type_field.get('value');
    updateCurrentFileType(preselected_file_type, false);
    setUpTemplatesChoice();
    file_type_field.on('change', handleFileTypeChange);
};

}, "0.1", {"requires": ['node', 'lp.anim']});
