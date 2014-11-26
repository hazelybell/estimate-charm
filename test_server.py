#!/usr/bin/env python

import commands
import json
import os
import server
import shutil
import unittest


UC_HOME = os.path.expanduser('~/.unnaturalCode')
UC_HOME_BACKUP = os.path.expanduser('~/.unnaturalCode.bak')

def fromUCHome(*args):
    "Returns a path with UnnaturalCode home as the prefix."
    return os.path.join(UC_HOME, *args)

TEST_LOCK_FILE = fromUCHome('--test--')

def estimate_ngram_pids():
    """
    Returns a set of all estimate-ngram pids belonging to this process.
    """
    pid = os.getpid()
    print("process leader", pid)

    #pid = 1 # init -- we may not be the parent on estimate-ngram
    output = commands.getoutput('pgrep -P %d lt-estimate-ngr' % pid)
    return set(int(pid) for pid in output.split())

class UnnaturalHTTPTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Do back-up the existing corpus...
        assert not os.path.exists(TEST_LOCK_FILE)
        shutil.move(UC_HOME, UC_HOME_BACKUP)

        # Recreate the test directory.
        os.mkdir(UC_HOME)
        # Touch the lock file.
        with open(TEST_LOCK_FILE, 'a'):
            os.utime(TEST_LOCK_FILE, None)

    def setUp(self):
        server.app.config['TESTING'] = True
        self.app = server.app.test_client()

    def test_delete(self):
        assert len(estimate_ngram_pids()) in (0, 1)

        rv = self.app.delete('/py/')
        assert rv.status_code == 204

        assert not os.path.exists(fromUCHome('pyCorpus'))
        # It stopped running.
        assert not estimate_ngram_pids()

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

    @classmethod
    def tearDownClass(cls):
        # Delete the test corpus...
        assert os.path.exists(UC_HOME_BACKUP)
        assert os.path.exists(TEST_LOCK_FILE)
        shutil.rmtree(UC_HOME)
        # Restore the original corpus...
        shutil.move(UC_HOME_BACKUP, UC_HOME)


if __name__ == '__main__':
    unittest.main()
