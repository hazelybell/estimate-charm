/*
 * Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 */
YUI.add('lp.translations.sourcepackage_sharing_details.test', function (Y) {

    var tests = Y.namespace(
        'lp.translations.sourcepackage_sharing_details.test');
    tests.suite = new Y.Test.Suite('source package sharing details Tests');

    var namespace = Y.lp.translations.sourcepackage_sharing_details;
    var IOHandler = namespace.IOHandler;
    var TranslationSharingConfig = namespace.TranslationSharingConfig;
    var TranslationSharingController = namespace.TranslationSharingController;
    var CheckItem = (
      Y.lp.translations.sourcepackage_sharing_details.CheckItem);
    var LinkCheckItem = (
      Y.lp.translations.sourcepackage_sharing_details.LinkCheckItem);
    var test_ns = Y.lp.translations.sourcepackage_sharing_details;

    tests.suite.add(new Y.Test.Case({
        // Test the setup method.
        name: 'setup',

        test_translations_usage_enabled: function() {
            var sharing_config = new TranslationSharingConfig();
            var usage = sharing_config.get('translations_usage');
            usage.set('user_authorized', true);
            Y.Assert.isFalse(usage.get('enabled'));
            sharing_config.get('product_series').set_link('ps', 'http://');
            Y.Assert.isTrue(usage.get('enabled'));
        },
        test_branch: function() {
            var sharing_config = new TranslationSharingConfig();
            var product_series = sharing_config.get('product_series');
            Y.Assert.isFalse(product_series.get('complete'));
            var branch = sharing_config.get('branch');
            branch.set('user_authorized', true);
            Y.Assert.isFalse(branch.get('enabled'));
            product_series.set_link('ps', 'http://');
            Y.Assert.isTrue(branch.get('enabled'));
        },
        test_set_branch: function() {
            var lp_client = new Y.lp.client.Launchpad();
            var branch = lp_client.wrap_resource('http://example.com', {
                unique_name: 'unique',
                web_link: 'http://example.com',
                resource_type_link: 'http://foo_type'
            });
            var sharing_controller = new TranslationSharingController();
            sharing_controller.set_branch(branch);
            var check = sharing_controller.get('tsconfig').get('branch');
            Y.Assert.areEqual('lp:unique', check.get('text'));
        },
        test_autoimport: function() {
            var sharing_config = new TranslationSharingConfig();
            var autoimport = sharing_config.get('autoimport');
            autoimport.set('user_authorized', true);
            Y.Assert.isFalse(autoimport.get('enabled'));
            sharing_config.get('branch').set_link('br', 'http://foo');
            Y.Assert.isTrue(sharing_config.get('autoimport').get('enabled'));
        },
        test_LinkCheckItem_contents: function() {
            var lci = new LinkCheckItem();
            Y.Assert.isNull(lci.get('text'));
            Y.Assert.isNull(lci.get('url'));
            lci.set_link('mytext', 'http://example.com');
            Y.Assert.areEqual('mytext', lci.get('text'));
            Y.Assert.areEqual('http://example.com', lci.get('url'));
        },
        test_LinkCheckItem_clear: function() {
            var lci = new LinkCheckItem();
            lci.set_link('mytext', 'http://example.com');
            lci.clear_link();
            Y.Assert.isNull(lci.get('text'));
            Y.Assert.isNull(lci.get('url'));
        },
        test_LinkCheckItem_complete: function() {
            var lci = new LinkCheckItem();
            Y.Assert.isFalse(lci.get('complete'));
            lci.set_link('text', 'http://example.com');
            Y.Assert.isTrue(lci.get('complete'));
        },
        test_CheckItem_enabled: function() {
            var ci = new CheckItem({user_authorized: true});
            Y.Assert.isTrue(ci.get('enabled'));
        },
        test_CheckItem_enabled_dependency: function(){
            var lci = new LinkCheckItem();
            var ci = new CheckItem({dependency: lci, user_authorized: true});
            Y.Assert.isFalse(ci.get('enabled'));
            lci.set_link('text', 'http://example.com');
            Y.Assert.isTrue(ci.get('enabled'));
        },
        test_CheckItem_identifier: function(){
            var ci = new CheckItem({identifier: 'id1'});
            Y.Assert.areEqual('id1', ci.get('identifier'));
        },
        test_CheckItem_user_authorized: function() {
            var ci = new CheckItem({user_authorized: true});
            Y.Assert.isTrue(ci.get('enabled'));
            ci.set('user_authorized', false);
            Y.Assert.isFalse(ci.get('enabled'));
        },
        test_configure_empty: function() {
            var ctrl = new TranslationSharingController();
            var model = {
                productseries: null,
                product: null,
                upstream_branch: null
            };
            ctrl.configure(model, {});
        },
        test_configure: function() {
            var cache = {
                product: {
                    translations_usage: test_ns.usage.launchpad,
                    resource_type_link: 'http://product'
                },
                productseries: {
                    title: 'title1',
                    web_link: 'http://web1',
                    translations_autoimport_mode: (
                        test_ns.autoimport_modes.import_translations),
                    resource_type_link: 'productseries'
                },
                upstream_branch: {
                    unique_name: 'title2',
                    web_link: 'http://web2',
                    resource_type_link: 'branch'
                },
                context: {
                    resource_type_link: 'http://sourcepackage'
                },
                user_can_change_branch: true
            };
            var ctrl = new TranslationSharingController();
            var lp_client = new Y.lp.client.Launchpad();
            var model = lp_client.wrap_resource(null, cache);
            var import_overlay = {
                loadFormContentAndRender: function() {},
                render: function() {},
                get: function(ignore) {
                    return Y.Node.create(
                        '<p><a href="http://fake">fake</a></p>');
                    }
            };
            unlink_overlay = import_overlay;
            usage_overlay = import_overlay;
            ctrl.configure(
                model, {}, unlink_overlay, import_overlay, usage_overlay);
            var tsconfig = ctrl.get('tsconfig');
            Y.Assert.areEqual(
                tsconfig.get('product_series').get('text'), 'title1');
            Y.Assert.areEqual(
                tsconfig.get('product_series').get('url'), 'http://web1');
            Y.Assert.areEqual(
                tsconfig.get('branch').get('text'), 'lp:title2');
            Y.Assert.isTrue(tsconfig.get('branch').get('user_authorized'));
            Y.Assert.isTrue(tsconfig.get('autoimport').get('complete'));
            Y.Assert.isTrue(
                tsconfig.get('translations_usage').get('complete'));
            Y.Assert.areSame(ctrl.get('source_package'), model.context);
        },
        test_update_from_model: function() {
            var null_model = {
                productseries: null,
                product: null,
                upstream_branch: null
            };

            var cache = {
                product: {
                    translations_usage: test_ns.usage.launchpad,
                    resource_type_link: 'http://product'
                },
                productseries: {
                    title: 'title1',
                    web_link: 'http://web1',
                    translations_autoimport_mode: (
                        test_ns.autoimport_modes.import_translations),
                    resource_type_link: 'productseries'
                },
                upstream_branch: {
                    unique_name: 'title2',
                    web_link: 'http://web2',
                    resource_type_link: 'branch'
                },
                context: {
                    resource_type_link: 'http://sourcepackage'
                },
                user_can_change_branch: true
            };
            var ctrl = new TranslationSharingController();
            var lp_client = new Y.lp.client.Launchpad();
            var model = lp_client.wrap_resource(null, cache);
            var import_overlay = {
                loadFormContentAndRender: function() {},
                render: function() {},
                get: function(ignore) {
                    return Y.Node.create(
                        '<p><a href="http://fake">fake</a></p>');
                    }
            };
            unlink_overlay = import_overlay;
            usage_overlay = import_overlay;
            ctrl.configure(
                null_model, {}, unlink_overlay, import_overlay,
                usage_overlay);
            ctrl.update_from_model(model);
            var tsconfig = ctrl.get('tsconfig');
            Y.Assert.areEqual(
                tsconfig.get('product_series').get('text'), 'title1');
            Y.Assert.areEqual(
                tsconfig.get('product_series').get('url'), 'http://web1');
            Y.Assert.areEqual(
                tsconfig.get('branch').get('text'), 'lp:title2');
            Y.Assert.isTrue(tsconfig.get('branch').get('user_authorized'));
            Y.Assert.isTrue(tsconfig.get('autoimport').get('complete'));
            Y.Assert.isTrue(
                tsconfig.get('translations_usage').get('complete'));
            Y.Assert.areSame(ctrl.get('source_package'), model.context);
        },
        test_set_permissions: function(){
            var ctrl = new TranslationSharingController();
            var config = ctrl.get('tsconfig');
            var overall = config.get('configuration');
            Y.Assert.isTrue(overall.get('user_authorized'));
            ctrl.set_permissions({
                user_can_change_translation_usage: true,
                user_can_change_branch: true,
                user_can_change_translations_autoimport_mode: true,
                user_can_change_product_series: true
            });
            var usage = config.get('translations_usage');
            Y.Assert.isTrue(usage.get('user_authorized'));
            ctrl.set_permissions({
                user_can_change_translation_usage: false,
                user_can_change_branch: true,
                user_can_change_translations_autoimport_mode: true,
                user_can_change_product_series: true
            });
            Y.Assert.isFalse(usage.get('user_authorized'));
            var branch = config.get('branch');
            Y.Assert.isTrue(branch.get('user_authorized'));
            ctrl.set_permissions({
                user_can_change_translation_usage: false,
                user_can_change_branch: false,
                user_can_change_translations_autoimport_mode: true,
                user_can_change_product_series: true
            });
            Y.Assert.isFalse(branch.get('user_authorized'));
            var autoimport = config.get('autoimport');
            Y.Assert.isTrue(autoimport.get('user_authorized'));
            ctrl.set_permissions({
                user_can_change_translation_usage: false,
                user_can_change_branch: false,
                user_can_change_translations_autoimport_mode: false,
                user_can_change_product_series: true
            });
            Y.Assert.isFalse(autoimport.get('user_authorized'));
            var product_series = config.get('product_series');
            Y.Assert.isTrue(product_series.get('user_authorized'));
            ctrl.set_permissions({
                user_can_change_translation_usage: false,
                user_can_change_branch: false,
                user_can_change_translations_autoimport_mode: false,
                user_can_change_product_series: false
            });
            Y.Assert.isFalse(product_series.get('user_authorized'));
            ctrl.set_permissions({
                user_can_change_translation_usage: false,
                user_can_change_branch: false,
                user_can_change_translations_autoimport_mode: false
            });
            Y.Assert.isFalse(product_series.get('user_authorized'));
        },
        test_update_branch: function(){
            var complete = Y.one('#branch-complete');
            var incomplete = Y.one('#branch-incomplete');
            var link = Y.one('#branch-complete a');
            Y.Assert.areEqual('', link.get('text'));
            Y.Assert.areNotEqual('lp:///', link.get('href'));
            Y.Assert.isFalse(complete.hasClass('hidden'));
            Y.Assert.isFalse(incomplete.hasClass('hidden'));
            var ctrl = new TranslationSharingController();
            ctrl.update();
            Y.Assert.isTrue(complete.hasClass('hidden'));
            Y.Assert.isFalse(incomplete.hasClass('hidden'));
            ctrl.get('tsconfig').get('branch').set_link('a', 'lp:///');
            ctrl.update();
            Y.Assert.isFalse(complete.hasClass('hidden'));
            Y.Assert.isTrue(incomplete.hasClass('hidden'));
            link = Y.one('#branch-complete a');
            Y.Assert.areEqual('a', link.get('text'));
            Y.Assert.areEqual('lp:///', link.get('href'));
        },
        test_update_all: function() {
            var ctrl = new TranslationSharingController();
            var config = ctrl.get('tsconfig');
            ctrl.update();
            var config_incomplete = Y.one('#configuration-incomplete');
            Y.Assert.isFalse(config_incomplete.hasClass('hidden'));
            var pack_incomplete = Y.one('#packaging-incomplete');
            Y.Assert.isFalse(pack_incomplete.hasClass('hidden'));
            var usage_incomplete = Y.one('#translation-incomplete');
            Y.Assert.isFalse(usage_incomplete.hasClass('hidden'));
            var sync_incomplete = Y.one('#upstream-sync-incomplete');
            Y.Assert.isFalse(sync_incomplete.hasClass('hidden'));
            config.get('configuration').set('complete', true);
            config.get('product_series').set_link('a', 'http:///');
            config.get('branch').set_link('a', 'http:///');
            config.get('translations_usage').set('complete', true);
            config.get('autoimport').set('complete', true);
            ctrl.update();
            Y.Assert.isTrue(config_incomplete.hasClass('hidden'));
            Y.Assert.isTrue(pack_incomplete.hasClass('hidden'));
            Y.Assert.isTrue(usage_incomplete.hasClass('hidden'));
            Y.Assert.isTrue(sync_incomplete.hasClass('hidden'));
        },
        test_update_check_disabled: function() {
            var incomplete = Y.one('#branch-incomplete');
            var ctrl = new TranslationSharingController();
            var branch = ctrl.get('tsconfig').get('branch');
            branch.set('user_authorized', true);
            ctrl.update_check(branch);
            Y.Assert.isTrue(incomplete.hasClass('lowlight'));
            var product_series = ctrl.get('tsconfig').get('product_series');
            product_series.set_link('a', 'http://');
            ctrl.update_check(branch);
            Y.Assert.isFalse(incomplete.hasClass('lowlight'));
        },
        test_update_check_pending: function(){
            var incomplete_spinner = Y.one(
                '#upstream-sync-incomplete-spinner');
            var ctrl = new TranslationSharingController();
            var autoimport = ctrl.get('tsconfig').get('autoimport');
            autoimport.set('user_authorized', true);
            var branch = ctrl.get('tsconfig').get('branch');
            branch.set_link('a', 'b');
            var incomplete_picker = Y.one(
                ctrl.picker_selector(autoimport, false));
            ctrl.update_check(autoimport);
            Y.Assert.isTrue(
                incomplete_spinner.hasClass('hidden'), 'spinner hidden');
            Y.Assert.isFalse(
                incomplete_picker.hasClass('hidden'), 'picker seen');
            autoimport.set('pending', true);
            ctrl.update_check(autoimport);
            Y.Assert.isFalse(
                incomplete_spinner.hasClass('hidden'), 'spinner seen');
            Y.Assert.isTrue(
                incomplete_picker.hasClass('hidden'), 'picker hidden');
            autoimport.set('complete', true);
            var complete_spinner = Y.one(
                '#upstream-sync-complete-spinner');
            var complete_picker = Y.one(
                ctrl.picker_selector(autoimport, true));
            ctrl.update_check(autoimport);
            Y.Assert.isFalse(complete_spinner.hasClass('hidden'));
            Y.Assert.isTrue(complete_picker.hasClass('hidden'));
            autoimport.set('pending', false);
            ctrl.update_check(autoimport);
            Y.Assert.isTrue(complete_spinner.hasClass('hidden'));
            Y.Assert.isFalse(complete_picker.hasClass('hidden'));
        },
        test_set_autoimport_mode: function() {
            var ctrl = new TranslationSharingController();
            var check = ctrl.get('tsconfig').get('autoimport');
            Y.Assert.isFalse(check.get('complete'));
            ctrl.set_autoimport_mode('Import template and translation files');
            Y.Assert.isTrue(check.get('complete'));
            ctrl.set_autoimport_mode('Import template files');
            Y.Assert.isFalse(check.get('complete'));
        },
        test_set_translations_usage: function() {
            var ctrl = new TranslationSharingController();
            var check = ctrl.get('tsconfig').get('translations_usage');
            ctrl.set_translations_usage('Unknown');
            Y.Assert.isFalse(check.get('complete'));
            ctrl.set_translations_usage('Launchpad');
            Y.Assert.isTrue(check.get('complete'));
            ctrl.set_translations_usage('Not Applicable');
            Y.Assert.isFalse(check.get('complete'));
            ctrl.set_translations_usage('External');
            Y.Assert.isTrue(check.get('complete'));
        }
    }));

    tests.suite.add(new Y.Test.Case({
        name: 'setup',
        test_show_success: function(){
            var controller = new TranslationSharingController();
            var check = controller.get('tsconfig').get('branch');
            check.set('pending', true);
            controller.update_check(check);
            spinner = Y.one(controller.spinner_selector(check));
            Y.Assert.isFalse(spinner.hasClass('hidden'));
            io_handler = new IOHandler(controller, check);
            io_handler.show_success();
            Y.Assert.isFalse(check.get('pending'));
            Y.Assert.isTrue(spinner.hasClass('hidden'));
        }
    }));

}, '0.1', {
    requires: ['lp.testing.runner', 'test', 'test-console',
               'lp.translations.sourcepackage_sharing_details']
});
