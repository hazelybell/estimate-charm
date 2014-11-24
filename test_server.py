#!/usr/bin/env python

import os
import server
import unittest
import json

# TODO: test CORSness of this...

class UnnaturalHTTPTestCase(unittest.TestCase):
    def setUp(self):
        server.app.config['TESTING'] = True
        self.app = server.app.test_client()

    def test_info(self):
        rv = self.app.get('/py')
        # It should redirect...
        assert 300 <= rv.status_code < 400
        assert rv.headers['Location'].endswith('/py/')

        rv = self.app.get('/py/')
        assert rv.status_code == 200
        assert rv.headers['Content-Type'] == 'application/json'

        # Now parse the JSON, making sure there are a few critical fields.
        resp = json.loads(rv.data)
        assert resp['language'].lower() == 'python'
        assert type(resp['order']) is int
        assert resp['order'] > 1
        # There are less important, but they should at least be there...
        assert all(prop in resp for prop in ['name', 'description', 'smoothing'])

    def test_train(self):
        # TODO: Fake a corpus up in here!
        rv = self.app.post('/py/', data=dict(s='print "Hello, World!"\n'))

        # TODO: THIS IS A TERRIBLE TEST AND YOU SHOULD FEEL BAD

        assert rv.status_code == 202
        assert rv.headers['Content-Type'] == 'application/json'

        resp = json.loads(rv.data)
        assert resp['tokens'] == 3

    def test_predict_from_url(self):
        # NOTE: THIS IS RELYING ON A CORPUS ALREADY EXISTING AT
        # ~/.unnaturalcode/pyCorpus!
        rv = self.app.get('/py/predict/from/api_utils/import')

        assert rv.status_code == 200 
        assert rv.headers['Content-Type'] == 'application/json'
        resp = json.loads(rv.data)

        assert len(resp['suggestions']) > 0
        # Despite sending three tokens, the minimum tokens used for prediction
        # MUST be four!
        assert len(resp['tokens']) == 4
        assert resp['tokens'][0][4] == '<unk>'

    def test_predict_from_post(self):
        # NOTE: THIS IS RELYING ON A CORPUS ALREADY EXISTING AT
        # ~/.unnaturalcode/pyCorpus!
        self.app.post()

        # TODO: THIS TEST!
        pass

    def test_accepting_cross_origin_requests(self):
        rv = self.app.options('/py/predict/')
        assert rv.status_code == 200
        assert rv.headers.get('Access-Control-Allow-Origin') == '*'

        # Could use a for-loop, but the test errors become more vague. 
        rv = self.app.options('/py/xentropy')
        assert rv.status_code == 200
        assert rv.headers.get('Access-Control-Allow-Origin') == '*'

    def test_cross_entropy(self):
        # NOTE: THIS IS RELYING ON A CORPUS ALREADY EXISTING AT
        # ~/.unnaturalcode/pyCorpus!
        pass


if __name__ == '__main__':
    unittest.main()
