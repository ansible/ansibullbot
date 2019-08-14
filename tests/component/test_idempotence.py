#!/usr/bin/env python

import six
six.add_move(six.MovedModule('mock', 'mock', 'unittest.mock'))
from six.moves import mock

from backports import tempfile

import argparse
import datetime
import json
import logging
import os
import re
import shutil
import subprocess
import time
import urllib

import github
import pytest
import pytz

from ansibullbot.triagers.ansible import AnsibleTriage


def unquote(string):
    '''py2+py3 compat unquoting'''
    if hasattr(urllib, 'parse'):
        # py3
        res = urllib.parse(string)
    else:
        # py2
        res = urllib.unquote(string)

    return res


class IssueDatabase:

    eventids = set()
    pickles = {}
    issues = []

    def __init__(self):
        self.debug = False
        eventids = set()
        self.issues = []
        self.pickles = {}

    def get_url(self, url, method=None, headers=None, data=None):
        if self.debug:
            print('#########################################')
            print('# %s' % method or 'GET')
            print('# %s' % url)
            print('# %s' % headers)
            print('#########################################')
        rheaders = {}
        rdata = None

        parts = url.split('/')

        if method == 'POST':
            if url.endswith('/graphql'):
                rdata = self.graphql_response(data)
            elif parts[-1] == 'comments':
                org = parts[4]
                repo = parts[5]
                number = int(parts[7])
                #import epdb; epdb.st()
                jdata = json.loads(data)
                self.add_issue_comment(jdata['body'], org=org, repo=repo, number=number)
                rdata = {}
            elif parts[-1] == 'labels':
                org = parts[4]
                repo = parts[5]
                number = int(parts[7])
                labels = json.loads(data)
                for label in labels:
                    self.add_issue_label(label, org=org, repo=repo, number=number)
                rdata = {}
            else:
                import epdb; epdb.st()

        elif method == 'DELETE':
            if parts[-2] == 'labels':
                org = parts[4]
                repo = parts[5]
                number = int(parts[7])
                lname = parts[-1]
                self.remove_issue_label(lname, org=org, repo=repo, number=number)
                rdata = {}
            else:
                import epdb; epdb.st()

        else:
            if 'api.shippable.com' in url:
                rdata = self.shippable_response(url)
            elif url.endswith('repos/ansible/ansible'):
                rdata = self._get_repo('ansible/ansible')
            elif url.endswith('repos/ansible/ansible/labels'):
                rdata = []
            elif parts[-2] == 'issues':
                org = parts[-4]
                repo = parts[-3]
                number = int(parts[-1])
                issue = self.get_issue(org=org, repo=repo, number=number)
                rdata = self.get_raw_data(issue)

            elif parts[-1] in ['comments']:
                org = parts[4]
                repo = parts[5]
                number = int(parts[-2])
                issue = self.get_issue(org=org, repo=repo, number=number)
                comments = issue.get('comments', [])[:]
                rdata = []
                for comment in comments:
                    data = comment.copy()
                    data['updated_at'] = data['created_at']
                    rdata.append(data)

            elif parts[-1] in ['events']:
                org = parts[4]
                repo = parts[5]
                number = int(parts[-2])
                issue = self.get_issue(org=org, repo=repo, number=number)
                events = issue.get('events', [])[:]
                rdata = []
                for event in events:
                    data = event.copy()
                    data['updated_at'] = data['created_at']
                    rdata.append(data)

            elif parts[-1] in ['timeline']:
                rdata = []

            elif parts[-1] in ['reactions']:
                rdata = []

            elif parts[-1] == 'assignees':
                rdata = []

            elif parts[-1] == 'members':
                rdata = []

            elif parts[-1] == 'teams':
                rdata = []

            elif parts[-2] == 'events':
                number = int(parts[-1])
                for issue in self.issues:
                    for event in issue['events']:
                        if event['id'] == number:
                            rdata = event.copy()
                            break
                if rdata:

                    for k,v in rdata.items():
                        if k.endswith('_at') and isinstance(v, datetime.datetime):
                            rdata[k] = v.isoformat().split('.')[0] + 'Z'

            elif parts[-2] == 'orgs':
                org = parts[-1]
                rdata = {
                    'id': 1000,
                    'node_id': 1000,
                    'updated_at': self._get_timestamp(),
                    'url': url.replace(':443', ''),
                    'name': org.title(),
                    'login': org,
                    'members_url': 'https://api.github.com/orgs/%s/members{/member}' % org
                }


            elif parts[-2] == 'assignees':
                login = parts[-1]
                rdata = {
                    'id': 1000,
                    'node_id': 1000,
                    'login': login,
                    'url': 'https://api.github.com/users/%s' % login,
                    'type': 'User',
                    'site_admin': False
                }


        # pause if we don't know how to handle this url+method yet
        if rdata is None:
            import epdb; epdb.st()

        if self.debug:
            print('# %s' % rdata)

        return rheaders,rdata

    def shippable_response(self, url):
        return {}

    def graphql_response(self, data):

        # id, url, number, state, createdAt, updatedAt, repository, nameWithOwner

        indata = data
        indata = indata.replace('\\n', ' ')
        indata = indata.replace('\\' , ' ')
        indata = indata.replace('(', ' ')
        indata = indata.replace(')', ' ')
        indata = indata.replace('{', ' ')
        indata = indata.replace('}', ' ')
        indata = indata.replace('"', ' ')
        indata = indata.replace(',', ' ')
        indata = indata.replace(':', ' ')
        words = [x.strip() for x in indata.split() if x.strip()]

        rq = {}
        for idw,word in enumerate(words):
            if word in ['owner', 'name', 'number']:
                if word not in rq:
                    rq[word] = words[idw+1]
                continue
            if word == 'pullRequest':
                rq['pullRequest'] = True

        resp = {
            'data': {
                'repository': {
                }
            }
        }

        # if querying PRs and the number is not a PR, return None
        okey = 'issue'
        if rq.get('pullRequest'):
            okey = 'pullRequest'
            resp['data']['repository'][okey] = None 
            return resp

        resp['data']['repository'][okey] = {
            'id': 'xxxxxx',
            'state': 'open',
            'number': rq['number'],
            'createdAt': self._get_timestamp(), 
            'updatedAt': self._get_timestamp(),
            'repository': {'nameWithOwner': rq['owner'] + '/' + rq['name']},
            'url': 'https://github.com/%s/%s/%s/%s' % (rq['owner'], rq['name'], okey, rq['number'])
        }

        return resp


    def _get_timestamp(self):
        ts = datetime.datetime.utcnow()
        ats = pytz.utc.localize(ts)
        rts = ats.isoformat().split('.')[0] + 'Z'
        return rts

    def _get_repo(self, repo):
        ds = {
            'id': 3638964,
            'node_id': 'MDEwOlJlcG9zaXRvcnkzNjM4OTY0',
            'name': 'ansible',
            'full_name': 'ansible/ansible',
            'owner': {
                'url': 'https://api.github.com/users/ansible',
                'login': 'ansible'
            },
            'organization': {
                'url': 'https://api.github.com/orgs/ansible',
                'login': 'ansible'
            },
            'description': '',
            'url': 'https://api.github.com/repos/ansible/ansible',
            'created_at': self._get_timestamp(),
            'updated_at': self._get_timestamp(),
        }
        return ds

    def _get_new_event_id(self):
        if len(self.eventids) == 0:
            thisid = 1
        else:
            thisid = list(self.eventids)[-1] + 1
        self.eventids.add(thisid)
        return thisid

    def _get_issue_index(self, org=None, repo=None, number=None, itype=None):
        for idx, x in enumerate(self.issues):
            if org and x['org'] != org:
                continue
            if repo and x['repo'] != repo:
                continue
            if number and x['number'] != number:
                continue
            if itype and x['itype'] != itype:
                continue

            return idx

        return None


    def get_issue(self, org=None, repo=None, number=None, itype=None):
        ix = self._get_issue_index(org=org, repo=repo, number=number, itype=itype)
        if ix is None:
            return None

        return self.issues[ix].copy()

    def get_issue_property(self, property_name, org=None, repo=None, number=None, itype=None):
        ix = self._get_issue_index(org=org, repo=repo, number=number, itype=itype)
        data = self.issues[ix].get(property_name)

        return data

    def get_raw_data(self, issue):
        org = issue['url'].split('/')[4]
        repo = issue['url'].split('/')[5]
        rdata = {
            'id': issue.get('id'),
            'node_d': issue.get('node_id'),
            'repository_url': 'https://api.github.com/repos/%s/%s' % (org, repo),
            'labels_url': 'https://api.github.com/repos/%s/%s/issues/%s/labels{/name}' % (org, repo, issue['number']),
            'comments_url': 'https://api.github.com/repos/%s/%s/issues/%s/events' % (org, repo, issue['number']),
            'events_url': 'https://api.github.com/repos/%s/%s/issues/%s/events' % (org, repo, issue['number']),
            'assignees': [],
            'state': issue['state'],
            'title': issue['title'],
            'body': issue['body'],
            'comments': len(issue['comments']),
            'number': issue['number'],
            'url': issue['url'],
            'html_url': 'https://github.com/%s/%s/issues/%s' % (org, repo, issue['number']),
            'user': {
                'url': 'https://api.github.com/users/%s' % issue['user']['login'],
                'login': issue['user']['login']
            },
            'labels': list(issue['labels']),
            'created_at': issue['created_at'],
            'updated_at': issue['updated_at'],
            'closed_at': None,
            'closed_by': None,
            'author_association': "NONE"
        }
        return rdata

    def set_issue_body(self, body, org=None, repo=None, number=None):
        ix = self._get_issue_index(org=org, repo=repo, nunmber=number, itype=itype)
        self.issues[ix]['body'] = body

    def set_issue_title(self, title, org=None, repo=None, number=None):
        ix = self._get_issue_index(org=org, repo=repo, number=number, itype=itype)
        self.issues[ix]['title'] = title

    def add_issue_label(self, label, login=None, created_at=None, org=None, repo=None, number=None):
        label = unquote(label)
        ix = self._get_issue_index(org=org, repo=repo, number=number)
        if label not in [x['name'] for x in self.issues[ix]['labels']]:

            ldata = {
                'name': label,
                'url': 'https://api.github.com/repos/%s/%s/labels/%s' % (org, repo, label)
            }

            self.issues[ix]['labels'].append(ldata)

            event = {}
            event['id'] = self._get_new_event_id()
            event['node_id'] = 'NODE' + str(event['id'])
            event['url'] = 'https://api.github.com/repos/%s/%s/issues/events/%s' % (org, repo, event['id'])
            event['event'] = 'labeled'
            event['label'] = ldata
            event['actor'] = {
                'url': 'https://api.github.com/users/%s' % login or ansibot,
                'html_url': 'https://github.com/%s' % login or ansibot,
                'login': login or 'ansibot'
            }
            event['created_at'] = created_at or self._get_timestamp()
            self.issues[ix]['events'].append(event)
            self.issues[ix]['updated_at'] = event['created_at']

    def add_issue_comment(self, comment, login=None, created_at=None, org=None, repo=None, number=None):

        # comments do not get added to events!!!

        ix = self._get_issue_index(org=org, repo=repo, number=number)
        thiscomment = {
            'id': self._get_new_event_id(),
            'body': comment,
            'user': {
                'url': 'https://api.github.com/users/%s' % login or 'ansibot',
                'html_url': 'https://github.com/%s' % login or 'ansibot',
                'login': login or 'ansibot'
            },
            'created_at': created_at or self._get_timestamp()
        }
        thiscomment['node_id'] = 'NODE' + str(thiscomment['id'])
        thiscomment['url'] = 'https://api.github.com/repos/%s/%s/issues/comments/%s' % (org, repo, thiscomment['id'])
        self.issues[ix]['comments'].append(thiscomment)
        self.issues[ix]['updated_at'] = thiscomment['created_at']

        if self.debug:
            print('comment added to issue %s' % self.issues[ix]['number'])


    def remove_issue_label(self, label, login=None, created_at=None, org=None, repo=None, number=None):
        label = unquote(label)
        ix = self._get_issue_index(org=org, repo=repo, number=number)
        if label in [x['name'] for x in self.issues[ix]['labels']]:

            ldata = {
                'name': label,
                'url': 'https://api.github.com/repos/%s/%s/labels/%s' % (org, repo, label)
            }

            self.issues[ix]['labels'].remove(ldata)

            event = {}
            event['id'] = self._get_new_event_id()
            event['node_id'] = 'NODE' + str(event['id'])
            event['url'] = 'https://api.github.com/repos/%s/%s/issues/events/%s' % (org, repo, event['id'])
            event['event'] = 'unlabeled'
            event['label'] = ldata
            event['actor'] = {'login': login or 'ansibot'}
            event['created_at'] = created_at or self._get_timestamp()
            self.issues[ix]['events'].append(event)
            self.issues[ix]['updated_at'] = event['created_at']

            if self.debug:
                print('removed %s label from issue %s' % (label, self.issues[ix]['number']))

    def _get_empty_stub(self):
        stub = {
            'itype': 'issue',
            'state': 'open',
            'number': None,
            'user': {'login': None},
            'created_by': {'login': None},
            'created_at': None,
            'updated_at': None,
            'body': '',
            'title': '',
            'labels': [],
            'assignees': [],
            'comments': [],
            'events': [],
            'timeline': [],
            'reactions': []
        }
        return stub.copy()

    def add_issue(
                self,
                itype=None,
                org='ansible',
                repo='ansible',
                number=None,
                login=None,
                title=None,
                body=None,
                created_at=None,
                updated_at=None,
                labels=None,
                assignees=None
            ):

        thisissue = self._get_empty_stub()

        if itype:
            thisissue['itype'] = itype

        if org:
            thisissue['org'] = org
        else:
            thisissue['org'] = 'ansible'

        if repo:
            thisissue['repo'] = repo
        else:
            thisissue['repo'] = 'ansible'

        if number is None:
            if len(self.issues) == 0:
                thisissue['number'] = 1
            else:
                thisissue['number'] = [x for x in self.issues if x['org'] == thisissue['org'] and x['repo'] == thisissue['repo']][-1]['number'] + 1

        if created_at:
            thisissue['created_at'] = created_at
        else:
            thisissue['created_at'] = self._get_timestamp()

        if updated_at:
            thisissue['updated_at'] = updated_at
        else:
            thisissue['updated_at'] = self._get_timestamp()

        if login:
            thisissue['user']['login'] = login
            thisissue['created_by']['login'] = login
        else:
            thisissue['user']['login'] = 'jimbob'
            thisissue['created_by']['login'] = 'jimbob'

        if assignees:
            thisissue['assignees'] = assignees

        if title:
            thisissue['title'] = title

        if body:
            thisissue['body'] = body

        if labels:
            thisissue['labels'] = labels

        if assignees:
            thisissue['assignees'] = assignees

        url = 'https://api.github.com/repos/%s/%s' % (org, repo)
        if itype and itype.startswith('pull'):
            url += '/pulls/'
        else:
            url += '/issues/'
        url += str(thisissue['number'])
        thisissue['url'] = url

        thisissue['html_url'] = url.replace('api.github.com/repos', '')
        #import epdb; epdb.st()

        self.issues.append(thisissue)


ID = IssueDatabase()


RESPONSES = {
    'https://api.shippable.com/runs?projectIds=573f79d02a8192902e20e34b&isPullRequest=True': {},
    #'https://api.github.com/repos/ansible/ansible/issues/1/comments': [],
    #'https://api.github.com/repos/ansible/ansible/issues/1/events': [],
    #'https://api.github.com/repos/ansible/ansible/issues/1/timeline': []
}




class MockRequests:

    @staticmethod
    def get(url, headers=None, data=None):
        return MockRequestsResponse(url, inheaders=headers, indata=data, method='GET')

    @staticmethod
    def post(url, headers=None, data=None):
        return MockRequestsResponse(url, inheaders=headers, indata=data, method='POST')

    @staticmethod
    def Session():
        return MockRequestsSession()


class MockRequestsSession:
    def __init__(self):
        pass

    def get(self, url, allow_redirects=False, data=None, headers=None, timeout=None, verify=True):
        #r_headers, r_data = ID.get_url(url, headers=headers, data=data)        
        #import epdb; epdb.st()
        return MockRequestsResponse(url, inheaders=headers, indata=data)

    def post(self, url, allow_redirects=False, data=None, headers=None, timeout=None, verify=True):
        return MockRequestsResponse(url, inheaders=headers, indata=data, method='POST')

    def delete(self, url, allow_redirects=False, data=None, headers=None, timeout=None, verify=True):
        return MockRequestsResponse(url, inheaders=headers, indata=data, method='DELETE')


class MockRequestsResponse:

    def __init__(self, url, inheaders=None, indata=None, method='GET'):
        self.method = method
        self.url = url
        self.inheaders = inheaders
        self.indata = indata
        #self.rheaders = None
        #self.rdata = None
        self.rheaders, self.rdata = ID.get_url(self.url, headers=self.inheaders, data=indata, method=method)

    @property
    def text(self):
        try:
            raw = json.dumps(self.json())
        except Exception as e:
            print(e)
            import epdb; epdb.st()
        return raw

    @property
    def headers(self):
        return self.rheaders

    @property
    def status_code(self):
        return 200

    def json(self):
        return self.rdata


class MockLogger:
    INFO = 'info'
    DEBUG = 'debug'

    @staticmethod
    def info(message):
        print('INFO %s' % message)

    @staticmethod
    def debug(message):
        print('DEBUG %s' % message)

    @staticmethod
    def warn(message):
        print('WARN %s' % message)

    @staticmethod
    def warn(message):
        print('ERROR %s ' % message)

    @staticmethod
    def Formatter(format_string):
        return None

    @staticmethod
    def getLogger():
        return MockLogger()

    def setLevel(self, level):
        self.level = level

    def addHandler(self, handler):
        pass

    @staticmethod
    def StreamHandler():
        return MockLogger()

    def setFormatter(self, formatter):
        pass


class TestIdempotence:

    cachedir = None

    def setUp(self):
        # cache a checkout to speed up successive tests
        if not os.path.exists('/tmp/ansible.checkout'):
            p = subprocess.Popen('git clone https://github.com/ansible/ansible /tmp/ansible.checkout', shell=True)
            p.communicate()

        logging.level = logging.DEBUG

    def teardown(self):
        logging.level = logging.INFO

    '''
    @pytest.fixture(autouse=True)
    def inject_fixtures(self, caplog):
        self._caplog = caplog
    '''

    @mock.patch('ansibullbot.decorators.github.C.DEFAULT_RATELIMIT', False)
    @mock.patch('ansibullbot.decorators.github.C.DEFAULT_BREAKPOINTS', True)
    @mock.patch('ansibullbot.decorators.github.C.DEFAULT_GITHUB_TOKEN', 'ansibot')
    @mock.patch('ansibullbot.decorators.github.C.DEFAULT_GITHUB_TOKEN', 'abc1234')
    @mock.patch('github.Requester.requests', MockRequests)
    @mock.patch('ansibullbot.decorators.github.requests', MockRequests)
    @mock.patch('ansibullbot.triagers.ansible.requests', MockRequests)
    #@mock.patch('ansibullbot.triagers.defaulttriager.DefaultTriager.set_logger')
    @mock.patch('ansibullbot.triagers.defaulttriager.logging', MockLogger)
    @mock.patch('ansibullbot.triagers.ansible.logging', MockLogger)
    @mock.patch('ansibullbot.utils.gh_gql_client.requests', MockRequests)
    @mock.patch('ansibullbot.utils.shippable_api.requests', MockRequests)
    @mock.patch('ansibullbot.wrappers.ghapiwrapper.requests', MockRequests)
    def test_noop(self, *args, **kwargs):

        with tempfile.TemporaryDirectory(prefix='ansibot.test.idem.') as cachedir:

            if not os.path.exists(cachedir):
                os.makedirs(cachedir)

            # copy the cached checkout
            if os.path.exists('/tmp/ansible.checkout'):
                p = subprocess.Popen(
                    'cp -Rp /tmp/ansible.checkout %s' % os.path.join(cachedir, 'ansible.checkout'),
                    shell=True
                )
                p.communicate()

            # make sure the database is put in the right place
            unc = 'sqlite:///' + cachedir + '/test.db'

            with mock.patch('ansibullbot.utils.sqlite_utils.C.DEFAULT_DATABASE_UNC', unc):

                print('')
                print('############################################################')
                print('#            TEMPDIR: %s ' % cachedir)
                print('############################################################')

                bot_args = [
                    '--debug',
                    '--verbose',
                    '--only_issues',
                    '--ignore_module_commits',
                    '--skip_module_repos',
                    '--cachedir=%s' % cachedir,
                    '--logfile=%s' % os.path.join(cachedir, 'bot.log'),
                    '--no_since',
                    '--id=1',
                    '--force'
                ]

                body = [
                    '#### ISSUE TYPE',
                    'bug report',
                    '#### SUMMARY',
                    'does not work.',
                    '#### COMPONENT NAME',
                    'vmware_guest',
                    '#### ANSIBLE VERSION',
                    '2.9.0'
                ]
                ID.add_issue(body='\n'.join(body))


                AT = AnsibleTriage(args=bot_args)
                for x in range(0, 2):
                    AT.run()

                # /tmp/ansibot.test.isxYlS/ansible/ansible/issues/1/meta.json                
                metafile = os.path.join(cachedir, 'ansible', 'ansible', 'issues', '1', 'meta.json')
                assert os.path.exists(metafile)

                with open(metafile, 'r') as f:
                    meta = json.loads(f.read())

                for k,v in meta['actions'].items():
                    assert not v
