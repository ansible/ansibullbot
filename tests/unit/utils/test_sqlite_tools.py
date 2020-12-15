import os
import tempfile

from unittest import mock

from ansibullbot.utils.sqlite_utils import AnsibullbotDatabase


def test_db_file_endswith_version():

    with tempfile.TemporaryDirectory() as cachedir:
        unc = 'sqlite:///' + cachedir + '/test.db'

        with mock.patch('ansibullbot.utils.sqlite_utils.C.DEFAULT_DATABASE_UNC', unc):

            ADB = AnsibullbotDatabase(cachedir=cachedir)

            print(ADB.unc)
            assert ADB.unc.endswith('_' + ADB.VERSION)


def test_db_file_corrupted():

    with tempfile.TemporaryDirectory() as cachedir:
        unc = 'sqlite:///' + cachedir + '/test.db'

        with mock.patch('ansibullbot.utils.sqlite_utils.C.DEFAULT_DATABASE_UNC', unc):

            # create the initial file
            ADB1 = AnsibullbotDatabase(cachedir=cachedir)
            unc_file = ADB1.unc
            unc_file = unc_file.replace('sqlite:///', '')
            with open(unc_file, 'w') as f:
                f.write('NULLNULLNULLNULL')

            # now try to init again
            ADB2 = AnsibullbotDatabase(cachedir=cachedir)

            assert os.path.exists(ADB2.dbfile)


def test_set_and_get_rate_limit():

    with tempfile.TemporaryDirectory() as cachedir:
        unc = 'sqlite:///' + cachedir + '/test.db'

        with mock.patch('ansibullbot.utils.sqlite_utils.C.DEFAULT_DATABASE_UNC', unc):

            ADB = AnsibullbotDatabase(cachedir=cachedir)

            rl = {
                'resources': {
                    'core': {
                        'limit': 5000,
                        'remaining': 5000
                    }
                }
            }

            ADB.set_rate_limit(username='bob', token='abcd1234', rawjson=rl)
            remaining = ADB.get_rate_limit_remaining(username='bob', token='abcd1234')
            rl2 = ADB.get_rate_limit_rawjson(username='bob', token='abcd1234')
            counter = ADB.get_rate_limit_query_counter(username='bob', token='abcd1234')

            assert remaining == 5000
            assert rl == rl2
            assert counter == 2
