#!/usr/bin/env python

import six
six.add_move(six.MovedModule('mock', 'mock', 'unittest.mock'))
from six.moves import mock

from backports import tempfile

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import time
import urllib

import github
import pytz

from ansibullbot.triagers.ansible import AnsibleTriage



def unquote(string):
    if hasattr(urllib, 'parse'):
        res = urllib.parse(string)
    else:
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
            #elif url.endswith('/graphql'):
            #    rdata = self.graphql_response(data)
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
                    #data['created_at'] = data['created_at'].isoformat().split('.')[0] + 'Z' 
                    data['updated_at'] = data['created_at']
                    rdata.append(data)
                    #import epdb; epdb.st()

            elif parts[-1] in ['events']:
                org = parts[4]
                repo = parts[5]
                number = int(parts[-2])
                issue = self.get_issue(org=org, repo=repo, number=number)
                events = issue.get('events', [])[:]
                rdata = []
                for event in events:
                    data = event.copy()
                    #data['created_at'] = data['created_at'].isoformat().split('.')[0] + 'Z' 
                    data['updated_at'] = data['created_at']
                    rdata.append(data)
                    #import epdb; epdb.st()

                #if rdata:
                #    import epdb; epdb.st()

            elif parts[-1] in ['timeline']:
                rdata = []

            elif parts[-1] in ['reactions']:
                rdata = []
                #import epdb; epdb.st()

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
        # 'created_at': datetime.datetime.now().isoformat().split('.')[0] + 'Z',
        ts = datetime.datetime.utcnow()
        ats = pytz.utc.localize(ts)
        #import epdb; epdb.st()
        rts = ats.isoformat().split('.')[0] + 'Z'
        #import epdb; epdb.st()
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
        #import epdb; epdb.st()
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

        #print('1) %s/%s/%s/%s not found' % (org, repo, itype, number))
        return None


    def get_issue(self, org=None, repo=None, number=None, itype=None):
        ix = self._get_issue_index(org=org, repo=repo, number=number, itype=itype)
        if ix is None:
            #print('2) %s/%s/%s/%s not found' % (org, repo, itype, number))
            return None

        return self.issues[ix].copy()

    def get_issue_property(self, property_name, org=None, repo=None, number=None, itype=None):

        #print('##############################')
        #print('# MOCKID: %s' % id(self))
        #print('##############################')

        ix = self._get_issue_index(org=org, repo=repo, number=number, itype=itype)
        data = self.issues[ix].get(property_name)
        '''
        if isinstance(data, set):
            data = list(data)[:]
        if isinstance(data, list):
            for idx,x in enumerate(data):
                if not isinstance(x, dict):
                    continue
                if not isinstance(x['created_at'], datetime.datetime):
                    # 2019-08-12T10:14:17Z
                    try:
                        data[idx]['created_at'] = datetime.datetime.strptime(x['created_at'], '%Y-%m-%dT%H:%M:%SZ')
                    except Exception as e:
                        print(e)
                        import epdb; epdb.st()
        elif property_name.endswith('_at') and not isinstance(data, datetime.datetime):
            import epdb; epdb.st()
        '''

        #print('KEY: %s' % property_name)
        #print('DATA: %s' % data)

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
        #import epdb; epdb.st()
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
            #import epdb; epdb.st()

    def add_issue_comment(self, comment, login=None, created_at=None, org=None, repo=None, number=None):
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

        '''
        thisevent = thiscomment.copy()
        thisevent['url'] = 'https://api.github.com/repos/%s/%s/issues/events/%s' % (org, repo, thiscomment['id'])
        thisevent['event'] = 'commented'
        thisevent['actor'] = thisevent['user'].copy()
        #thisevent.pop('user', None)
        self.issues[ix]['events'].append(thisevent)
        self.issues[ix]['updated_at'] = thisevent['created_at']
        '''

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

            #self.issues[ix]['labels'].remove(label)
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

        '''
        url = 'https://api.github.com/repos/%s/%s' % (org, repo)
        if itype and itype.startswith('pull'):
            url += '/pulls/'
        else:
            url += '/issues/'
        url += str(number)
        thisissue['url'] = url

        thisissue['html_url'] = url.replace('api.github.com/repos', '')
        #import epdb; epdb.st()
        '''

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


class MockGithub:
    def __init__(self, base_url=None, login_or_token=None):
        self.base_url = base_url
        self.login_or_token = login_or_token

    def get_organization(self, orgname):
        return MockGithubOrg(self, orgname)

    def get_repo(self, repo_path):
        return MockGithubRepo(self, repo_path)


class MockGithubOrg:
    def __init__(self, github, orgname):
        self.github = github
        self.orgname = orgname

    @property
    def updated_at(self):
        return datetime.datetime.now()

    def get_members(self):
        return []

    def get_teams(self):
        return []


class MockGithubRepo:
    def __init__(self, github, repo_path):
        self.github = github
        self.repo_path = repo_path
        self._org = self.repo_path.split('/')[0]
        self._repo = self.repo_path.split('/')[1]
        self._assignees = []

    def update(self):
        pass

    @property
    def updated_at(self):
        return datetime.datetime.now()

    def get_assignees(self):
        return []

    def get_labels(self):
        return []

    def get_issue(self, number):

        if ID.get_issue(org=self._org, repo=self._repo, number=number):
            return MockGithubIssue(self, number)

        return None

    def get_pull(self, number):

        if ID.get_issue(org=self._org, repo=self._repo, number=number, itype='pull'):
            return MockGithubPull(self, number)

        return None

    def has_in_assignees(self, user):
        if user in self._assignees:
            return True
        return False


class MockGithubUser:
    def __init__(self, login):
        self._login = login

    @property
    def login(self):
        return self._login


class MockGithubIssue:
    def __init__(self, repo, number):
        self._ID = ID
        self.repo = repo
        self.number = number
    
        #self.state = 'open'
        #self.url = 'https://api.github.com/repos/%s/issues/%s' % (self.repo.repo_path, self.number)
        #self.html_url = 'https://github.com/%s/issues/%s' % (self.repo.repo_path, self.number)

        #self.created_at = datetime.datetime.now()
        #self.updated_at = datetime.datetime.now()
        #self._user_login = 'phantom_phreak'

    def update(self):
        pass

    def _requester(*args, **kwargs):
        import epdb; epdb.st()

    def add_to_labels(self, label, login=None, created_at=None):
        ID.add_issue_label(label, login=login, created_at=created_at, org=self._org, repo=self._repo, number=self.number)

    def remove_from_labels(self, label, login=None, created_at=None):
        ID.remove_issue_label(label, login=login, created_at=created_at, org=self._org, repo=self._repo, number=self.number)

    def create_comment(self, comment, login=None, created_at=None):
        ID.add_issue_comment(comment, login=login, created_at=created_at, org=self._org, repo=self._repo, number=self.number)

    @property
    def _org(self):
        return self.repo._org

    @property
    def _repo(self):
        return self.repo._repo

    @property
    def created_at(self):
        return ID.get_issue_property('created_at', org=self._org, repo=self._repo, number=self.number)

    @property
    def updated_at(self):
        return ID.get_issue_property('updated_at', org=self._org, repo=self._repo, number=self.number)

    @property
    def url(self):
        return 'https://api.github.com/repos/%s/issues/%s' % (self.repo.repo_path, self.number)

    @property
    def html_url(self):
        return 'https://github.com/%s/issues/%s' % (self.repo.repo_path, self.number)

    @property
    def state(self):
        return ID.get_issue_property('state', org=self._org, repo=self._repo, number=self.number)

    @property
    def assignees(self):
        assignee_logins = ID.get_issue_property('assignees', org=self._org, repo=self._repo, number=self.number)
        assignees = [MockGithubUser(x) for x in assignee_logins]
        return assignees

    def get_raw_data(self):
        
        rdata = {
            'events_url': 'https://api.github.com/repos/%s/%s/issues/%s/events' % (1,3,4),
            'assignees': [],
            'state': self.state,
            'title': self.title,
            'body': self.body,
            'comments': len(self.comments),
            'number': self.number,
            'url': self.url,
            'html_url': self.html_url,
            'user': {
                'login': self.user.login
            },
            'labels': [{'name': x.name} for x in self.labels],
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
        return rdata

    def get_comments(self):
        #return self.comments
        _comments = ID.get_issue_property('comments', org=self._org, repo=self._repo, number=self.number)
        comments = [MockComment(x) for x in _comments]
        #if [x.created_at for x in comments if not isinstance(x.created_at, datetime.datetime)]:
        #    import epdb; epdb.st()
        return comments

    def get_events(self):
        return self.events

    @property
    def user(self):
        login = 'phantomPhreak'
        return MockGithubUser(login)

    @property
    def body(self):
        return ID.get_issue_property('body', org=self._org, repo=self._repo, number=self.number)

    @property
    def title(self):
        return ID.get_issue_property('title', org=self._org, repo=self._repo, number=self.number)

    @property
    def comments(self):
        '''
        _comments = ID.get_issue_property('comments', org=self._org, repo=self._repo, number=self.number)
        comments = [MockComment(x) for x in _comments]
        if [x.created_at for x in comments if not isinstance(x.created_at, datetime.datetime)]:
            import epdb; epdb.st()
        return comments
        '''
        return len(self.get_comments())

    @property
    def events(self):
        events_raw = ID.get_issue_property('events', org=self._org, repo=self._repo, number=self.number)
        events = [MockEvent(x) for x in events_raw]
        #if [x.created_at for x in events if not isinstance(x.created_at, datetime.datetime)]:
        #    import epdb; epdb.st()
        return events

    @property
    def labels(self):
        label_names = ID.get_issue_property('labels', org=self._org, repo=self._repo, number=self.number)
        labels = [MockLabel(x) for x in label_names]
        return labels


class MockGithubPull(MockGithubIssue):
    def __init__(self, repo, number):

        #super(MockGithubPull, self).__init__(repo, number)
        self.repo = repo
        self.number = number
        self.state = 'open'

        self.url = 'https://api.github.com/repos/%s/pulls/%s' % (self.repo.repo_path, self.number)
        self.html_url = 'https://github.com/%s/pulls/%s' % (self.repo.repo_path, self.number)
        
        self.created_at = datetime.datetime.now()
        self.updated_at = datetime.datetime.now()

class MockEvent:
    def __init__(self, data):
        self.data = data

    def __repr__(self):
        return '(%s) %s' % (self.data['id'], self.data['event'])

    @property
    def event(self):
        return self.data.get('event')
    @property
    def created_at(self):
        return self.data.get('created_at')
    @property
    def actor(self):
        return MockGithubUser(self.data['actor']['login'])


class MockComment:
    def __init__(self, data):
        self.data = data

    def __repr__(self):
        return '(comment) [%s] %s' % (self.user.login, self.body)

    @property
    def body(self):
        return self.data['body']

    @property
    def id(self):
        return self.data['id']

    @property
    def created_at(self):
        return self.data['created_at']

    @property
    def user(self):
        return MockGithubUser(self.data['user']['login'])


class MockLabel:
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return '(label: %s)' % self.name

'''
class MockRequester:
    def requestJson(*args, **kwargs):
        import epdb; epdb.st()
'''

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

    '''
    def graphql_response(self):

        # id, url, number, state, createdAt, updatedAt, repository, nameWithOwner

        indata = self.indata
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
            'createdAt': datetime.datetime.now().isoformat(), 
            'updatedAt': datetime.datetime.now().isoformat(),
            'repository': {'nameWithOwner': rq['owner'] + '/' + rq['name']},
            'url': 'https://github.com/%s/%s/%s/%s' % (rq['owner'], rq['name'], okey, rq['number'])
        }

        return resp
    '''

    def json(self):
        return self.rdata


    '''
    def _json(self):
        if self.url == u'https://api.github.com/graphql':
            return self.graphql_response()

        if self.url in RESPONSES:
            return RESPONSES.get(self.url, {})

        # https://api.github.com/repos/ansible/ansible/issues/1/comments
        # https://api.github.com/repos/ansible/ansible/issues/1/events
        # https://api.github.com/repos/ansible/ansible/issues/1/timeline
        url = self.url.replace('https://api.github.com/repos/', '')       
        parts = url.split('/')


        if len(parts) == 5:
            # org/repo/type/number/property
            data = ID.get_issue_property(parts[-1], org=parts[0], repo=parts[1], number=int(parts[3]))
            if isinstance(data, list):
                for idx,x in enumerate(data):
                    if isinstance(x, dict):
                        for k,v in x.items():
                            if isinstance(v, datetime.datetime):
                                data[idx][k] = isoformat_to_zulu_time(v.isoformat())
            return data

        elif len(parts) == 4:
            # org/repo/type/number/property
            data = ID.get_issue(parts[-1], org=parts[0], repo=parts[1], number=int(parts[3]))
            for k,v in data.items():
                if isinstance(v, datetime.datetime):
                    data[k] = isoformat_to_zulu_time(v.isoformat())
            return data

        import epdb; epdb.st()
    '''


def mock_pickle_dump(*args, **kwargs):
    '''Can't pickle magicmocks'''
    fn = args[1].name
    ID.pickles[fn] = args[0]
    with open(fn, 'w') as f:
        f.write('<pickledata>')


def mock_pickle_load(*args, **kwargs):
    '''Can't pickle magicmocks'''
    fn = args[0].name
    #import epdb; epdb.st()
    return ID.pickles[fn]


def isoformat_to_zulu_time(isoformat):
    # 2019-08-08T14:21:48.909199 -> 2019-08-08T14:21:48Z
    newts = isoformat.split('.')[0] + 'Z'
    return newts


class TestIdempotence:

    cachedir = None

    def setUp(self):
        print('setup called!')

    def teardown(self):
        print('teardown called!')

    @mock.patch('ansibullbot.decorators.github.C.DEFAULT_RATELIMIT', False)
    @mock.patch('ansibullbot.decorators.github.C.DEFAULT_BREAKPOINTS', True)
    @mock.patch('ansibullbot.decorators.github.C.DEFAULT_GITHUB_TOKEN', 'ansibot')
    @mock.patch('ansibullbot.decorators.github.C.DEFAULT_GITHUB_TOKEN', 'abc1234')
    #@mock.patch('ansibullbot.utils.moduletools.pickle_dump', mock_pickle_dump)
    #@mock.patch('ansibullbot.utils.moduletools.pickle_load', mock_pickle_load)
    #@mock.patch('ansibullbot.wrappers.defaultwrapper.pickle_dump', mock_pickle_dump)
    #@mock.patch('ansibullbot.wrappers.defaultwrapper.pickle_load', mock_pickle_load)
    #@mock.patch('ansibullbot.wrappers.ghapiwrapper.pickle_dump', mock_pickle_dump)
    #@mock.patch('ansibullbot.wrappers.ghapiwrapper.pickle_load', mock_pickle_load)
    #@mock.patch('ansibullbot.wrappers.historywrapper.pickle_dump', mock_pickle_dump)
    #@mock.patch('ansibullbot.wrappers.historywrapper.pickle_load', mock_pickle_load)
    #@mock.patch('ansibullbot.triagers.ansible.C')
    #@mock.patch('ansibullbot.triagers.defaulttriager.Github', MockGithub)
    @mock.patch('github.Requester.requests', MockRequests)
    @mock.patch('ansibullbot.decorators.github.requests', MockRequests)
    @mock.patch('ansibullbot.triagers.ansible.requests', MockRequests)
    @mock.patch('ansibullbot.utils.gh_gql_client.requests', MockRequests)
    @mock.patch('ansibullbot.utils.shippable_api.requests', MockRequests)
    @mock.patch('ansibullbot.wrappers.ghapiwrapper.requests', MockRequests)
    #def test_noop(self, mock_C, mock_github, mock_requests1, mock_requests2, mock_requests2, ):
    def test_noop(self, *args, **kwargs):

        #mock_C = args[0]

        with tempfile.TemporaryDirectory(prefix='ansibot.test.') as cachedir:

            if not os.path.exists(cachedir):
                os.makedirs(cachedir)

            if not os.path.exists('/tmp/ansible.checkout'):
                p = subprocess.Popen('git clone https://github.com/ansible/ansible /tmp/ansible.checkout', shell=True)
                p.communicate()

            #shutil.copytree('/tmp/ansible.checkout', os.path.join(cachedir, 'ansible.checkout'))
            p = subprocess.Popen(
                'cp -Rp /tmp/ansible.checkout %s' % os.path.join(cachedir, 'ansible.checkout'),
                shell=True
            )
            p.communicate()

            unc = 'sqlite:///' + cachedir + '/test.db'

            with mock.patch('ansibullbot.utils.sqlite_utils.C.DEFAULT_DATABASE_UNC', unc):

                mock_github = MockGithub

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

                #mock_C.DEFAULT_GITHUB_URL = 'http://localhost:5000'
                #mock_C.DEFAULT_GITHUB_USERNAME = 'ansibot'
                #mock_C.DEFAULT_GITHUB_TOKEN = 'abc123'

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

                gh = MockGithub(login_or_token='abc123')
                repo = gh.get_repo('ansible/ansible')
                issue1 = repo.get_issue(1)
                #time.sleep(1)
                issue1.add_to_labels('needs_triage', login='ansibot')
                #time.sleep(1)
                issue1.add_to_labels('needs_info', login='ansibot')
                #time.sleep(1)
                issue1.add_to_labels('needs_template', login='ansibot')
                #time.sleep(1)
                issue1.add_to_labels('support:core', login='ansibot')
                #time.sleep(1)
                issue1.add_to_labels('affects_2.9', login='ansibot')
                #time.sleep(1)
                issue1.add_to_labels('bug', login='ansibot')
                #time.sleep(1)
                issue1.add_to_labels('module', login='ansibot')
                #time.sleep(1)
                issue1.add_to_labels('support:community', login='ansibot')
                #time.sleep(1)
                issue1.remove_from_labels('needs_triage', login='ansibot')
                #time.sleep(1)

                #print(issue1.events)
                #import epdb; epdb.st()
                #return

                comment = [
                    'Files identified in the description:',
                    '* [`lib/ansible/modules/cloud/vmware/vmware_guest.py`](https://github.com/ansible/ansible/blob/devel/lib/ansible/modules/cloud/vmware/vmware_guest.py)',
                    '',
                    'If these files are inaccurate, please update the `component name` section of the description or use the `!component` bot command.',
                    '[click here for bot help](https://github.com/ansible/ansibullbot/blob/master/ISSUE_HELP.md)',
                    '',
                    '<!--- boilerplate: components_banner --->'
                ]

                issue1.create_comment('\n'.join(comment), login='ansibot')

                issue1.create_comment('FOO BAR BAZ!!!')
                if len(issue1.get_comments()) != len(ID.issues[0]['comments']):
                    import epdb; epdb.st()

                if len(issue1.get_comments()) != len(ID.get_issue_property('comments')):
                    import epdb; epdb.st()

                _gh = github.Github(login_or_token='abc123')
                _repo = _gh.get_repo('ansible/ansible')
                _issue1 = _repo.get_issue(1)
                #print([x for x in _issue1.get_events()])
                #import epdb; epdb.st()

                AT = AnsibleTriage(args=bot_args)
                for x in range(0, 3):
                    AT.run()
                    #time.sleep(10)
                    #import epdb; epdb.st()

                #import epdb; epdb.st()
                print('DONE')
