YUI.add('lp.app.errors', function(Y) {

var namespace = Y.namespace('lp.app.errors');

/*
 * Create a form button for canceling an error form
 * that won't reload the page on submit.
 *
 * @method cancel_form_button
 * @return button {Node} The form's cancel button.
*/
var cancel_form_button = function() {
    var button = Y.Node.create('<button>OK</button>');
    button.on('click', function(e) {
        e.preventDefault();
        error_overlay.hide();
    });
    return button;
};


var error_overlay;
/*
 * Create the form overlay to use when encountering errors.
 *
 * @method create_error_overlay
*/
var create_error_overlay = function() {
    // If the error_overlay has never been instantiated, or if it no longer
    // is in the DOM (probably because of a previous test cleanup)...
    if (error_overlay === undefined ||
        !Y.Lang.isValue(error_overlay.get('boundingBox').get('parentNode'))) {
        // ...make one and set it up.
        error_overlay = new Y.lp.ui.FormOverlay({
            headerContent: '<h2>Error</h2>',
            form_header:  '',
            form_content:  '',
            form_submit_button: Y.Node.create(
                '<button style="display:none"></button>'),
            form_cancel_button: cancel_form_button(),
            centered: true,
            visible: false
        });
        error_overlay.render();
    }
};

/**
 * Run a callback, optionally flashing a specified node red beforehand.
 *
 * If the supplied node evaluates false, the callback is invoked immediately.
 *
 * @method maybe_red_flash
 * @param flash_node The node to flash red, or null for no flash.
 * @param callback The callback to invoke.
 */
var maybe_red_flash = function(flash_node, callback)
{
    if (flash_node) {
        var anim = Y.lp.anim.red_flash({ node: flash_node });
        anim.on('end', callback);
        anim.run();
    } else {
        callback();
    }
};


/*
 * Take an error message and display in an overlay (creating it if necessary).
 *
 * @method display_error
 * @param flash_node {Node} The node to red flash.
 * @param msg {String} The message to display.
*/
namespace.display_error = function(flash_node, msg) {
    create_error_overlay();
    maybe_red_flash(flash_node, function(){
        error_overlay.showError(msg);
        error_overlay.show();
    });
};


var info_overlay;
/*
 * Display the form overlay for non-error informational messages.
 *
 * @method display_info
 * @param msg {String} The message to display.
*/
namespace.display_info = function(msg) {
    if (info_overlay === undefined) {
        info_overlay = new Y.lp.ui.PrettyOverlay({
            centered: true,
            visible: false
        });
        info_overlay.render();
    }
    var content = Y.Node.create(
      '<div style="background: url(/@@/info-large) no-repeat; ' +
      'min-height: 32px; padding-left: 40px; padding-top: 16px"/></div>');
    content.appendChild(Y.Node.create(msg));
    var button_div = Y.Node.create('<div style="text-align: right"></div>');
    var ok_button = Y.Node.create('<button>OK</button>');
    ok_button.on('click', function(e) {
        info_overlay.fire('cancel');
    });
    button_div.appendChild(ok_button);
    content.appendChild(button_div);
    info_overlay.set('bodyContent', content);
    info_overlay.show();
};

}, "0.1", {"requires":["lp.ui.formoverlay", "lp.ui.overlay", "lp.anim"]});
