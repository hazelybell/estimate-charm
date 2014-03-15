YUI.add('lp.translations.poexport', function(Y) {

var namespace = Y.namespace('lp.translations.poexport');

/*
 * Initialize Javascript code for a POT/<lang_code> +export page.
 */
namespace.initialize_pofile_export_page = function() {
    var pochanged_block = Y.one('#div_pochanged');
    if (Y.Lang.isNull(pochanged_block)) {
        return false;
    }

    var formatlist = Y.one('#div_format select');
    var checkbox = Y.one('#div_pochanged input');
    var changedtext = Y.one('#div_pochanged span');
    function toggle_pochanged() {
        if (formatlist.get('value') === 'PO') {
            changedtext.removeClass('disabledpochanged');
            checkbox.set('disabled', false);
        }
        else {
            changedtext.addClass('disabledpochanged');
            checkbox.set('disabled', true);
        }
    }
    formatlist.on('change', toggle_pochanged);
    // Initialize the state of the controls.
    toggle_pochanged();
    Y.one('#po-format-only').addClass('hidden');
    return true;
};

}, "0.1", {"requires": ["node"]});
