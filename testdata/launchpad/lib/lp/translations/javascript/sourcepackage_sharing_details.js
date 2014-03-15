/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 */

YUI.add('lp.translations.sourcepackage_sharing_details', function(Y) {
var namespace = Y.namespace('lp.translations.sourcepackage_sharing_details');

/**
 * This class represents the state of a checklist item.
 */
function CheckItem(config){
    CheckItem.superclass.constructor.apply(this, arguments);
}
CheckItem.ATTRS = {
    complete: {value: false},
    // Optional reference to an item that must be completed before setting
    // this.
    dependency: {value: null},
    // True if this item is enabled.
    enabled: {
        getter: function(){
            if (!this.get('user_authorized')){
                return false;
            }
            if (Y.Lang.isNull(this.get('dependency'))){
                return true;
            }
            return this.get('dependency').get('complete');
        }
    },
    user_authorized: {value: false},
    // The HTML identifier of the item.
    identifier: null,
    pending: {value: false}
};
Y.extend(CheckItem, Y.Base, {
});

namespace.CheckItem = CheckItem;

/**
 * This class reflects the state of a Checklist item that holds a link.
 */
function LinkCheckItem(){
    LinkCheckItem.superclass.constructor.apply(this, arguments);
}
LinkCheckItem.ATTRS = {
    // This item is complete if _text is set.
    complete: {getter:
        function() {
            return !Y.Lang.isNull(this.get('_text'));
        }
    },
    // _text is unset by default.
    _text: {value: null},
    // text is read-only.
    text: {getter:
        function(){
            return this.get('_text');
        }
    },
    // _url is unset by default.
    _url: {value: null},
    // text is read-only.
    url: { getter:
        function(){
            return this.get('_url');
        }
    }
};
Y.extend(LinkCheckItem, CheckItem, {
    /**
     * Set the text and URL of the link for this LinkCheckItem.
     */
    set_link: function(text, url){
        this.set('_text', text);
        this.set('_url', url);
    },
    clear_link: function() {
        this.set('_text', null);
        this.set('_url', null);
    }
});

namespace.LinkCheckItem = LinkCheckItem;


namespace.autoimport_modes = {
    no_import: 'None',
    import_templates: 'Import template files',
    import_translations: 'Import template and translation files'
};


namespace.usage = {
    unknown: 'Unknown',
    launchpad: 'Launchpad',
    external: 'External',
    no_applicable: 'Not Applicable'
};

/**
 * This class represents the state of the translation sharing config
 * checklist.
 */
function TranslationSharingConfig (config){
    TranslationSharingConfig.superclass.constructor.apply(this, arguments);
}
Y.extend(TranslationSharingConfig, Y.Base, {
    initializer: function(){
        var product_series = new LinkCheckItem(
            {identifier: 'packaging'});
        this.set('product_series', product_series);
        var usage = new CheckItem(
            {identifier: 'translation', dependency: product_series});
        this.set('translations_usage', usage);
        var branch = new LinkCheckItem(
            {identifier: 'branch', dependency: this.get('product_series')});
        this.set('branch', branch);
        var autoimport = new CheckItem(
            {identifier: 'upstream-sync', dependency: branch});
        this.set('autoimport', autoimport);
        var configuration = new CheckItem(
            {identifier: 'configuration', user_authorized: true});
        this.set('configuration', configuration);
        this.set(
            'all_items', [product_series, usage, branch, autoimport]);
    }
});
namespace.TranslationSharingConfig = TranslationSharingConfig;


/**
 * Create a form overlay for a submittable form.
 */
function create_form_overlay(title_html, submit_callback){
    var submit_button = Y.Node.create(
        '<button type="submit" name="field.actions.create" ' +
        'value="Save Changes">Save</button>'
        );
    var cancel_button = Y.Node.create(
        '<button type="button" name="field.actions.cancel" ' +
        '>Cancel</button>'
        );
    function hide_and_callback(){
        form_overlay.hide();
        submit_callback.apply(this, arguments);
    }
    var form_overlay = new Y.lp.ui.FormOverlay({
        centered: true,
        headerContent: title_html,
        form_cancel_button: cancel_button,
        form_submit_button: submit_button,
        form_submit_callback: hide_and_callback,
        visible: false
    });
    return form_overlay;
}


function update_form(overlay, entry, view_name) {
    var url = Y.lp.client.get_form_url(entry, view_name);
    overlay.loadFormContentAndRender(url);
    overlay.render();
}


function update_unlink_form(overlay, productseries) {
    overlay.get('form_content')
        .one('a')
        .set('href', Y.lp.get_url_path(productseries.get('web_link')))
        .set('text', productseries.get('title'));
    overlay.render();
}


function submit_form(config, form_data, entry, view_name, action) {
    var form_data_entries = [];
    var key;
    for (key in form_data){
        if (form_data.hasOwnProperty(key)){
            encoded_key = encodeURIComponent(key);
            values = form_data[key];
            for (i=0; i < values.length; i++){
                form_entry = (
                    encoded_key + '=' + encodeURIComponent(values[i]));
                form_data_entries.push(form_entry);
            }
        }
    }
    form_data_entries.push('field.actions.' + action + '=ignored');
    var data = form_data_entries.join('&');
    var url = Y.lp.client.get_form_url(entry, view_name);
    config.method = 'POST';
    config.data = data;
    Y.io(url, config);
}


function add_activator(picker, selector) {
    var element = Y.one(selector);
    element.on('click', function(e) {
        e.halt();
        this.show();
    }, picker);
    element.addClass(picker.get('picker_activator_css_class'));
}


function enum_title(form_data, name, map) {
    var key = form_data[name][0];
    Y.log(key);
    var title = map[key.toLowerCase()];
    Y.log(title);
    return title;
}


function IOHandler(controller, check, error_handler) {
    that = this;
    this.check = check;
    this.controller = controller;
    if (!Y.Lang.isValue(error_handler)){
        this.error_handler = new Y.lp.client.ErrorHandler();
    }
    else {
        this.error_handler = error_handler;
    }
    this.error_handler.showError = function(error_msg) {
        check.set('pending', false);
        controller.update_check(check);
        var flash_target = Y.one(controller.visible_check_selector(check));
        Y.lp.app.errors.display_error(Y.one(flash_target), error_msg);
    };
}

IOHandler.prototype.show_success = function(){
    this.check.set('pending', false);
    this.controller.update();
    this.controller.flash_check_green(this.check);
};

IOHandler.prototype.refresh_from_model = function(model){
    this.controller.update_from_model(model);
    this.show_success();
};

IOHandler.prototype.refresh_config = function(){
    return this.chain_config(
        Y.bind("load_model", this.controller),
        Y.bind('refresh_from_model', this));
};


/**
 * Return an LP client config using error_handler.
 *
 * @param next {Object} A callback to call on success.
 */
IOHandler.prototype.get_config = function(next) {
    var config = {
        on:{
            success: next,
            failure: this.error_handler.getFailureHandler()
        }
    };
    return config;
};


/**
 * Return an LP client config that will call the specified callbacks
 * in sequence, using error_handler.
 *
 * @param next {Object} A callback to call on success.
 */
IOHandler.prototype.chain_config = function() {
    var last_config;
    var i;
    // Each callback is bound to the next, so we use reverse order.
    for(i = arguments.length-1; i >= 0; i--){
        if (i === arguments.length - 1) {
            callback = arguments[i];
        }
        else {
            callback = Y.bind(arguments[i], this, last_config);
        }
        last_config = this.get_config(callback);
    }
    return last_config;
};


namespace.IOHandler = IOHandler;


/**
 * This class is the controller for updating the TranslationSharingConfig.
 * It handles updating the HTML and the DB model.
 */
function TranslationSharingController (config){
    TranslationSharingController.superclass.constructor.apply(
        this, arguments);
}
Y.extend(TranslationSharingController, Y.Base, {
    initializer: function(source_package){
        this.set('tsconfig', new TranslationSharingConfig());
        this.set('productseries', null);
        this.set('product', null);
        this.set('branch', null);
        this.set('source_package', null);
        this.set('branch_picker_config', null);
    },
    /*
     * Select the specified branch as the translation branch.
     *
     * @param branch_summary {Object} An object containing api_url, css,
     * description, value, title
     */
    configure: function(model, branch_picker_config, unlink_overlay,
                        import_overlay, usage_overlay) {
        this.set('branch_picker_config', branch_picker_config);
        this.set('unlink_overlay', unlink_overlay);
        this.set('import_overlay', import_overlay);
        this.set('usage_overlay', usage_overlay);
        this.update_from_model(model);
    },
    update_from_model: function(model) {
        this.set('source_package', model.context);
        this.replace_productseries(model.productseries);
        this.replace_product(model.product);
        this.set_branch(model.upstream_branch);
        this.set_permissions(model);
    },
    load_model: function(config){
        var source_package = this.get('source_package');
        Y.lp.client.load_model(source_package, '+sharing-details', config);
    },
    set_permissions: function(permissions){
        var usage = this.get('tsconfig').get('translations_usage');
        usage.set(
            'user_authorized', permissions.user_can_change_translation_usage);
        var branch = this.get('tsconfig').get('branch');
        branch.set('user_authorized', permissions.user_can_change_branch);
        var autoimport = this.get('tsconfig').get('autoimport');
        autoimport.set(
            'user_authorized',
            permissions.user_can_change_translations_autoimport_mode);
        var product_series = this.get('tsconfig').get('product_series');
        if (permissions.user_can_change_product_series !== undefined){
            product_series.set(
                'user_authorized',
                permissions.user_can_change_product_series);
        }
    },
    set_productseries: function(productseries) {
        var check = this.get('tsconfig').get('product_series');
        if (Y.Lang.isValue(productseries)){
            this.set('productseries', productseries);
            check.set_link(
                productseries.get('title'), productseries.get('web_link'));
        }
        else {
            check.clear_link();
        }
    },
    replace_productseries: function(productseries) {
        this.set_productseries(productseries);
        var autoimport_mode = namespace.autoimport_modes.no_import;
        if (!Y.Lang.isNull(productseries)){
            var unlink_overlay = this.get('unlink_overlay');
            update_unlink_form(unlink_overlay, productseries);

            autoimport_mode = productseries.get(
                'translations_autoimport_mode');
            var import_overlay = this.get('import_overlay');
            update_form(
                import_overlay, productseries, '+translations-settings');
        }
        this.set_autoimport_mode(autoimport_mode);
    },
    set_product: function(product) {
        this.set('product', product);
        this.get('branch_picker_config').context = product;
    },
    replace_product: function(product) {
        this.set_product(product);
        var translations_usage = namespace.usage.unknown;
        if (!Y.Lang.isNull(product)){
            translations_usage = product.get('translations_usage');
            var usage_overlay = this.get('usage_overlay');
            update_form(
                usage_overlay, product, '+configure-translations');
        }
        this.set_translations_usage(translations_usage);
    },
    set_branch: function(branch) {
        this.set('branch', branch);
        var check = this.get('tsconfig').get('branch');
        if (Y.Lang.isValue(branch)){
            check.set_link(
                'lp:' + branch.get('unique_name'), branch.get('web_link'));
        }
        else {
            check.clear_link();
        }
    },
    set_autoimport_mode: function(mode) {
        var complete = (
            mode === namespace.autoimport_modes.import_translations);
        this.get('tsconfig').get('autoimport').set('complete', complete);
    },
    set_translations_usage: function(usage) {
        complete = (
            usage === namespace.usage.launchpad ||
            usage === namespace.usage.external);
        var usage_check = this.get('tsconfig').get('translations_usage');
        usage_check.set('complete', complete);
    },
    select_productseries: function(productseries_summary) {
        var that = this;
        var productseries_check = that.get('tsconfig').get('product_series');
        var lp_client = new Y.lp.client.Launchpad();
        function save_productseries(config) {
            productseries_check.set('pending', true);
            that.update_check(productseries_check);
            var source_package = that.get('source_package');
            config.parameters = {
                productseries: productseries_summary.api_uri};
            source_package.named_post('setPackaging', config);
        }
        var io_handler = new IOHandler(this, productseries_check);
        save_productseries(io_handler.refresh_config());
    },
    remove_productseries: function(productseries_summary) {
        var that = this;
        var productseries_check = that.get('tsconfig').get('product_series');
        var lp_client = new Y.lp.client.Launchpad();
        function delete_packaging(config) {
            productseries_check.set('pending', true);
            var source_package = that.get('source_package');
            source_package.named_post('deletePackaging', config);
        }
        function set_checks() {
            that.replace_productseries(null);
            that.replace_product(null);
            that.set_branch(null);
            io_handler.show_success();
        }
        var io_handler = new IOHandler(this, productseries_check);
        delete_packaging(io_handler.get_config(set_checks));
    },
    select_branch: function(branch_summary) {
        var that = this;
        var lp_client = new Y.lp.client.Launchpad();
        var branch_check = that.get('tsconfig').get('branch');
        var productseries = that.get('productseries');

        function save_branch(config) {
            branch_check.set('pending', true);
            that.update_check(branch_check);
            productseries.set('branch_link', branch_summary.api_uri);
            productseries.lp_save(config);
        }
        var io_handler = new IOHandler(this, branch_check);
        save_branch(io_handler.refresh_config());
    },
    /**
     * Update the display of all checklist items.
     */
    update: function(){
        var all_items = this.get('tsconfig').get('all_items');
        var overall = this.get('tsconfig').get('configuration');
        var i;
        overall.set('complete', true);
        for (i = 0; i < all_items.length; i++){
            this.update_check(all_items[i]);
            if (!all_items[i].get('complete')){
                overall.set('complete', false);
            }
        }
        this.update_check(overall);
    },
    check_selector: function(check, complete) {
        var completion = complete ? '-complete' : '-incomplete';
        return '#' + check.get('identifier') + completion;
    },
    visible_check_selector: function(check) {
        return this.check_selector(check, check.get('complete'));
    },
    spinner_selector: function(check) {
        return this.visible_check_selector(check) + '-spinner';
    },
    picker_selector: function(check, complete) {
        return this.check_selector(check, complete) + '-picker a';
    },
    set_check_picker: function(check, picker) {
        add_activator(picker, this.picker_selector(check, true));
        add_activator(picker, this.picker_selector(check, false));
    },
    /**
     * Update the display of a single checklist item.
     */
    update_check: function(check){
        var complete = Y.one(this.check_selector(check, true));
        var hide_picker = !check.get('enabled') || check.get('pending');
        var link = complete.one('.link a');
        if (link !== null){
            link.set('href', check.get('url'));
            link.set('text', check.get('text'));
        }
        complete.toggleClass('hidden', !check.get('complete'));
        complete.toggleClass('lowlight', !check.get('enabled'));
        var complete_picker = Y.one(this.picker_selector(check, true));
        if (complete_picker !== null) {
            complete_picker.toggleClass('hidden', hide_picker);
        }
        var incomplete = Y.one(this.check_selector(check, false));
        incomplete.toggleClass('hidden', check.get('complete'));
        incomplete.toggleClass('lowlight', !check.get('enabled'));
        var incomplete_picker = Y.one(this.picker_selector(check, false));
        if (incomplete_picker !== null) {
            incomplete_picker.toggleClass('hidden', hide_picker);
        }
        var spinner = Y.one(this.spinner_selector(check));
        if (Y.Lang.isValue(spinner)){
            spinner.toggleClass('hidden', !check.get('pending'));
        }
    },
    flash_check_green: function(check) {
        var element = Y.one(this.visible_check_selector(check));
        var anim = Y.lp.anim.green_flash({node: element});
        anim.run();
    }
});
namespace.TranslationSharingController = TranslationSharingController;


/**
 * Method to prepare the AJAX translation sharing config functionality.
 */
namespace.prepare = function(cache) {
    var sharing_controller = new namespace.TranslationSharingController();
    var lp_client = new Y.lp.client.Launchpad();
    cache = lp_client.wrap_resource(null, cache);
    var branch_picker_config = {
        picker_activator: '#branch-incomplete-picker a',
        header : 'Select translation branch',
        step_title: 'Search',
        save: Y.bind('select_branch', sharing_controller),
        context: cache.product
    };
    var picker = Y.lp.app.picker.create(
        'BranchRestrictedOnProduct', branch_picker_config);
    /* Picker can't normally be activated by two different elements. */
    add_activator(picker, '#branch-complete-picker a');
    var productseries_picker_config = {
        picker_activator: '#packaging-complete-picker a',
        header : 'Select project series',
        step_title: 'Search',
        save: Y.bind('select_productseries', sharing_controller),
        context: cache.product
    };
    var productseries_picker = Y.lp.app.picker.create(
        'ProductSeries', productseries_picker_config);
    /* Picker can't normally be activated by two different elements. */
    add_activator(productseries_picker, '#packaging-incomplete-picker a');
    var unlink_overlay = create_form_overlay(
            '<h2>Unlink an upstream project<h2>', function(form_data) {
            Y.log('Unlinking.');
            sharing_controller.remove_productseries();
        });
    unlink_overlay.set(
            'form_content', Y.Node.create(
                '<p>This will remove the upstream link to '+
                '<a href="">foo</a>.</p>'));
    Y.one('#remove-packaging').on('click', function(e) {
        e.preventDefault();
        this.show();
        }, unlink_overlay);
    var import_overlay = create_form_overlay(
        '<h2>Import settings<h2>', function(form_data) {
        Y.log(form_data['field.translations_autoimport_mode']);
        mode = enum_title(
            form_data, 'field.translations_autoimport_mode',
            namespace.autoimport_modes);
        var product_series = sharing_controller.get('productseries');
        product_series.set('translations_autoimport_mode', mode);
        var autoimport_check = sharing_controller.get(
            'tsconfig').get('autoimport');
        handler = new IOHandler(sharing_controller, autoimport_check);
        function update_controller() {
            sharing_controller.set_autoimport_mode(mode);
            handler.show_success();
        }
        autoimport_check.set('pending', true);
        sharing_controller.update_check(autoimport_check);
        /* XXX: AaronBentley 2011-04-04 bug=369293: Avoid 412 on repeated
         * changes.  This does not increase the risk of changing from a
         * stale value, because the staleness check is not reasonable.
         * The user is changing from the default shown in the form, not
         * the value stored in productseries.
         */
        product_series.removeAttr('http_etag');
        product_series.lp_save(handler.get_config(update_controller));
    });
    var autoimport = sharing_controller.get('tsconfig').get('autoimport');
    sharing_controller.set_check_picker(autoimport, import_overlay);
    var usage = sharing_controller.get('tsconfig').get('translations_usage');
    var usage_overlay = create_form_overlay(
        '<h2>Configure translations<h2>', function(form_data) {
        var product = sharing_controller.get('product');
        var io_handler = new IOHandler(
            sharing_controller, usage, new Y.lp.client.FormErrorHandler());
        usage.set('pending', true);
        sharing_controller.update_check(usage);
        var config = io_handler.refresh_config();
        submit_form(
            config, form_data, product, '+configure-translations', 'change');
    });
    sharing_controller.set_check_picker(usage, usage_overlay);
    sharing_controller.configure(
        cache, branch_picker_config,
        unlink_overlay, import_overlay, usage_overlay);
    sharing_controller.update();
};
}, "0.1", {"requires": [
    'lp', 'lp.app.errors', 'lp.app.picker', 'oop', 'lp.client',
    'lp.anim']});
