/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Code for handling the update of the branch merge proposals.
 *
 * @module lp.code.branchmergeproposal.nominate
 */

YUI.add('lp.code.branchmergeproposal.nominate', function(Y) {

var namespace = Y.namespace('lp.code.branchmergeproposal.nominate');

var lp_client;

/**
 * Helper method to make the confirmation prompt for branch visibility.
 * @param branches_to_check
 * @param branch_info
 */
var _make_confirm_propmpt = function(branches_to_check, branch_info) {
    var visible_branches = branch_info.visible_branches;
    var invisible_branches = Y.Array.filter(branches_to_check, function(i) {
        return Y.Array.indexOf(visible_branches, i) < 0;
    });
    return Y.lp.mustache.to_html([
    "<p class='block-sprite large-warning'>",
    "{{person_name}} does not currently have permission to ",
    "view branches:</p>",
    "<ul style='margin-left: 50px'>",
    "    {{#invisible_branches}}",
    "        <li>{{.}}</li>",
    "    {{/invisible_branches}}",
    "</ul>",
    "<p>If you proceed, {{person_name}} will be subscribed to the " +
    "branches.</p>",
    "<p>Do you really want to nominate this reviewer?</p>"
    ].join(''), {
        invisible_branches: invisible_branches,
        person_name: branch_info.person_name
    });
};

/**
 * Picker validation callback which confirms that the nominated reviewer can
 * be given visibility to the specified branches.
 * @param branches_to_check
 * @param branch_info
 * @param picker
 * @param save_fn
 * @param cancel_fn
 */
var confirm_reviewer = function(branches_to_check, branch_info, picker,
                                save_fn, cancel_fn) {
    var visible_branches = branch_info.visible_branches;
    if (Y.Lang.isArray(visible_branches)
            && visible_branches.length !== branches_to_check.length) {
        var yn_content = _make_confirm_propmpt(
            branches_to_check, branch_info);
        Y.lp.app.picker.yesno_save_confirmation(
                picker, yn_content, "Nominate", "Choose Again",
                save_fn, cancel_fn);
    } else {
        if (Y.Lang.isFunction(save_fn)) {
            save_fn();
        }
    }
};

    /**
     * The validation plugin for the reviewer picker.
     * @param picker
     * @param value
     * @param save_fn
     * @param cancel_fn
     */
var check_reviewer_can_see_branches = function(picker, value, save_fn,
                                               cancel_fn) {
    if (value === null || !Y.Lang.isValue(value.api_uri)) {
        if (Y.Lang.isFunction(save_fn)) {
            save_fn();
            return;
        }
    }

    var reviewer_uri = Y.lp.client.normalize_uri(value.api_uri);
    reviewer_uri = Y.lp.client.get_absolute_uri(reviewer_uri);
    var error_handler = new Y.lp.client.ErrorHandler();
    error_handler.showError = function(error_msg) {
        picker.set('error', error_msg);
    };

    var branches_to_check = [LP.cache.context.unique_name];
    var target_name = Y.DOM.byId('field.target_branch.target_branch').value;
    if (Y.Lang.trim(target_name) !== '') {
        branches_to_check.push(target_name);
    }
    var confirm = function(branch_info) {
        namespace.confirm_reviewer(
            branches_to_check, branch_info, picker, save_fn, cancel_fn);
    };
    var y_config =  {
        on: {
            success: confirm,
            failure: error_handler.getFailureHandler()
        },
        parameters: {
            person: reviewer_uri,
            branch_names: branches_to_check
        }
    };
    lp_client.named_get("/branches", "getBranchVisibilityInfo", y_config);
};

/**
 * Display a confirmation prompt asking the user if the really want to grant
 * visibility to the source and/or target branches for the nominated reviewer.
 * If the user answers 'yes', we cause a form submission as for a regular
 * merge proposal registration.
 * @param branch_info the result of making the getBranchVisibilityInfo call.
 */
var confirm_reviewer_nomination = function(branch_info) {
    var branches_to_check = branch_info.branches_to_check;
    var yn_content = _make_confirm_propmpt(branches_to_check, branch_info);
    var co = new Y.lp.app.confirmationoverlay.ConfirmationOverlay({
        submit_fn: function() {
            var form = Y.one("[name='launchpadform']");
            var dispatcher = Y.Node.create('<input>')
                .set('type', 'hidden')
                .addClass('hidden-input')
                .set('name', 'field.actions.register')
                .set('value', 'Propose Merge');
            form.append(dispatcher);
            form.submit();
        },
        form_content: yn_content,
        headerContent: '<h2>Confirm reviewer nomination</h2>',
        submit_text: 'Confirm'
    });
    co.show();
};

/**
 * Show the submit spinner.
 *
 * @method _showSubmitSpinner
 */
var _showSubmitSpinner = function(submit_link) {
    var spinner_node = Y.Node.create(
    '<img class="spinner" src="/@@/spinner" alt="Submitting..." />');
    submit_link.insert(spinner_node, 'after');
    submit_link.set('disabled', true);
};

/**
 * Hide the submit spinner.
 *
 * @method _hideSubmitSpinner
 */
var _hideSubmitSpinner = function(submit_link) {
    var spinner = submit_link.get('parentNode').one('.spinner');
    if (spinner !== null) {
        spinner.remove(true);
    }
    submit_link.set('disabled', false);
};

/**
 * Redirect to a new URL. We need to break this out to allow testing.
 *
 * @method _redirect
 * @param url
 */
var _redirect = function(url) {
    window.location.replace(url);
};

/**
 * Wire up the register mp submit button.
 * @param io_provider
 */
var setup_nominate_submit = function(io_provider) {
    Y.lp.client.remove_notifications();
    var form = Y.one("[name='launchpadform']");
    var error_handler = new Y.lp.client.FormErrorHandler({
        form: form
    });
    var submit_link = Y.one("[name='field.actions.register']");
    error_handler.showError = Y.bind(function (error_msg) {
        _hideSubmitSpinner(submit_link);
        Y.lp.app.errors.display_error(undefined, error_msg);
    }, this);
    error_handler.handleError = Y.bind(function(id, response) {
        if( response.status === 400
                && response.statusText === 'Branch Visibility') {
            var response_info = Y.JSON.parse(response.responseText);
            namespace.confirm_reviewer_nomination(response_info);
            return true;
        }
        return error_handler.constructor.prototype.handleError.call(
            error_handler, id, response);
    }, this);

    var base_url = LP.cache.context.web_link;
    var submit_url = base_url + "/+register-merge";
    form.on('submit', function(e) {
        e.halt();
        var y_config = {
            method: "POST",
            headers: {'Accept': 'application/json;'},
            on: {
                start: Y.bind(function() {
                    error_handler.clearFormErrors();
                    _showSubmitSpinner(submit_link);
                }),
                end:
                    Y.bind(_hideSubmitSpinner, namespace, submit_link),
                failure: error_handler.getFailureHandler(),
                success:
                    function(id, response) {
                        if (response.status === 201) {
                            namespace._redirect(
                                response.getResponseHeader("Location"));
                        }
                    }
            }
        };
        var form_data = {};
        form.all("[name^='field.']").each(function(field) {
            form_data[field.get('name')] = field.get('value');
        });
        form_data.id = form;
        y_config.form = form_data;
        io_provider.io(submit_url, y_config);
    });
};

var setup_reviewer_confirmation = function() {
    var validation_namespace = Y.namespace('lp.app.picker.validation');
    var widget_id = 'show-widget-field-reviewer';
    validation_namespace[widget_id]= check_reviewer_can_see_branches;
};

// XXX wallyworld 2012-02-03 bug=925818
// We should construct YUI objects and widgets as required and not just
// attach stuff to the namespace.
// For testing
namespace.setup_reviewer_confirmation = setup_reviewer_confirmation;
namespace.check_reviewer_can_see_branches = check_reviewer_can_see_branches;
namespace.confirm_reviewer = confirm_reviewer;
namespace.confirm_reviewer_nomination = confirm_reviewer_nomination;
namespace.setup_nominate_submit = setup_nominate_submit;
namespace._redirect = _redirect;

// We want to disable the review_type field if no reviewer is
// specified. In such cases, the reviewer will be set by the back end
// to be the default for the target branch and the review type will be None.
var reviewer_changed = function(value) {
    var reviewer = Y.Lang.trim(value);
    var review_type = Y.DOM.byId('field.review_type');
    review_type.disabled = (reviewer === '');
};

namespace.setup = function(conf) {
    lp_client = new Y.lp.client.Launchpad(conf);
    var io_provider = Y.lp.client.get_configured_io_provider(conf);
    Y.on('blur',
      function(e) {
        reviewer_changed(e.target.get('value'));
      },
      Y.DOM.byId('field.reviewer'));
    var f = Y.DOM.byId('field.reviewer');
    reviewer_changed(f.value);

    setup_reviewer_confirmation();
    setup_nominate_submit(io_provider);
};

}, "0.1", {"requires": ["array-extras", "io", "substitute", "dom", "node",
   "json",   "event", "lp.client", "lp.mustache", "lp.app.picker",
   "lp.app.confirmationoverlay"]});
