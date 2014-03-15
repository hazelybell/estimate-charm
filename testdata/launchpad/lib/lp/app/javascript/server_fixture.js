/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Code to support full application server testing with YUI.
 *
 * @module Y.lp.testing.serverfixture
 */
YUI.add('lp.testing.serverfixture', function(Y) {

var module = Y.namespace('lp.testing.serverfixture');

/*
 * This function calls fixture on the appserver side.
 */
module.setup = function(testcase) {
    // self-post, get data, stash/merge on testcase
    var fixtures = Y.Array(arguments, 1);
    var data = Y.QueryString.stringify(
        {action: 'setup',
         fixtures: fixtures.join(',')
        });
    var config = {
        method: "POST",
        data: data,
        sync: true,
        headers: {Accept: 'application/json'}
        };
    var response = Y.io(window.location, config);
    if (response.status !== 200) {
        Y.error(response.responseText);
    }
    data = Y.JSON.parse(response.responseText);
    if (!Y.Lang.isValue(testcase._lp_fixture_setups)) {
        testcase._lp_fixture_setups = [];
    }
    testcase._lp_fixture_setups = testcase._lp_fixture_setups.concat(
        fixtures);
    if (!Y.Lang.isValue(testcase._lp_fixture_data)) {
        testcase._lp_fixture_data = {};
    }
    testcase._lp_fixture_data = Y.merge(testcase._lp_fixture_data, data);
    return data;
};

module.addCleanup = function(testcase, callable) {
  if (Y.Lang.isUndefined(testcase._lp_fixture_cleanups)) {
    testcase._lp_fixture_cleanups = [];
  }
  testcase._lp_fixture_cleanups.push(callable);
};

module.runWithIFrame = function(config, test) {
  // Note that the iframe url must be in the same domain as the test page.
  var iframe = Y.Node.create('<iframe/>').set('src', config.uri);
  Y.one('body').append(iframe);
  module.addCleanup(
    config.testcase,
    function() {
      iframe.remove();
    }
  );
  var timeout = config.timeout;
  if (!Y.Lang.isValue(timeout)) {
    timeout = 30000;
  }
  var iframe_is_ready = config.iframe_is_ready;
  if (!Y.Lang.isValue(iframe_is_ready)) {
    iframe_is_ready = function() {return true;};
  }
  var wait = config.wait;
  if (!Y.Lang.isValue(wait)) {
    wait = 100;
  }
  var start;
  var retry_function;
  retry_function = function() {
    var tested = false;
    var win = Y.Node.getDOMNode(iframe.get('contentWindow'));
    if (Y.Lang.isValue(win) && Y.Lang.isValue(win.document)) {
      var IYUI = YUI({
        base: '/+icing/yui/',
        filter: 'raw',
        combine: false,
        fetchCSS: false,
        win: win});
      if (iframe_is_ready(IYUI)) {
        test(IYUI);
        tested = true;
      }
    }
    if (!tested) {
      var now = new Date().getTime();
      if (now-start < timeout) {
        config.testcase.wait(retry_function, wait);
      } else {
        Y.Assert.fail('Timeout: Page did not load in iframe: ' + config.uri);
      }
    }
  };
  start = new Date().getTime();
  config.testcase.wait(retry_function, wait);
};

module.teardown = function(testcase) {
    var cleanups = testcase._lp_fixture_cleanups;
    var i;
    if (!Y.Lang.isUndefined(cleanups)) {
      for (i=cleanups.length-1; i>=0 ; i--) {
        cleanups[i]();
      }
    }
    var fixtures = testcase._lp_fixture_setups;
    if (Y.Lang.isUndefined(fixtures)) {
      // Nothing to be done.
      return;
    }
    var data = Y.QueryString.stringify(
        {action: 'teardown',
         fixtures: fixtures.join(','),
         data: Y.JSON.stringify(testcase._lp_fixture_data)
        });
    var config = {
        method: "POST",
        data: data,
        sync: true
        };
    var response = Y.io(window.location, config);
    if (response.status !== 200) {
        Y.error(response.responseText);
    }
    delete testcase._lp_fixture_setups;
    delete testcase._lp_fixture_data;
};

module.run = function(suite) {
  var handle_complete = function(data) {
    window.status = '::::' + Y.JSON.stringify(data);
  };
  Y.Test.Runner.on('complete', handle_complete);
  var handle_pass = function(data) {
    window.status = '>>>>' + Y.JSON.stringify(
      {testCase: data.testCase.name,
       testName: data.testName,
       type: data.type
      });
  };
  Y.Test.Runner.on('pass', handle_pass);
  var handle_fail = function(data) {
    window.status = '>>>>' + Y.JSON.stringify(
      {testCase: data.testCase.name,
       testName: data.testName,
       type: data.type,
       error: data.error.getMessage()
      });
  };
  Y.Test.Runner.on('fail', handle_fail);
  Y.Test.Runner.add(suite);

  var console = new Y.Console({newestOnTop: false});

  Y.on('domready', function() {
    console.render('#log');
    Y.Test.Runner.run();
  });
};

  },
 "0.1",
 {"requires": ["io", "json", "querystring", "test", "lp.client", "node"]});
