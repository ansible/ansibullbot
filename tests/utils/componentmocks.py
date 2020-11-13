#!/usr/bin/env python

import six
six.add_move(six.MovedModule('mock', 'mock', 'unittest.mock'))
from six.moves import mock

from backports import tempfile

import datetime
import json
import os
import shutil
import subprocess
import uuid

import pytz

try:
    #py3
    from urllib.parse import urlparse
except ImportError:
    #py2
    from urllib import unquote as urlparse

# reaction
#   * content '+1'
#   * id
#   * node_id
#   * user
#       * url
#       * login

# timeline
#   commented
#       * actor
#       * author_association
#       * body
#       * created_at
#       * event
#       * html_url
#       * id
#       * issue_url
#       * node_id
#       * updated_at
#       * url
#       * user
#   committed
#       * author
#       * comitter
#       * event
#       * html_url
#       * message
#       * node_id
#       * parents
#       * sha
#       * tree
#       * url
#       * verification
#   cross-referenced
#       * source
#           issue
#               raw_data
#           type: issue|?
#       * created_at
#       * updated_at
#       * actor
#       * event
#   head_ref_force_pushed
#       * actor
#       * commit_id
#       * commit_url
#       * created_at
#       * event
#       * id
#       * node_id
#       * url
#   labeled
#       * actor
#       * commit_id
#       * commit_url
#       * created_at
#       * event
#       * id
#       * label
#       * node_id
#       * url
#   mentioned
#       * actor
#       * commit_id
#       * commit_url
#       * created_at
#       * event
#       * id
#       * label
#       * node_id
#       * url
#   reviewed
#       * _links
#       * author_association
#       * body
#       * commit_id
#       * event
#       * html_url
#       * id
#       * node_id
#       * pull_request_url
#       * state
#       * submitted_at
#       * user
#   subscribed
#       * commit_id
#       * commit_url
#       * url
#       * created_at
#       * actor
#       * id
#       * node_id
#       * event
#   unlabeled
#       * actor
#       * commit_id
#       * commit_url
#       * created_at
#       * event
#       * id
#       * label
#       * node_id
#       * url


def get_timestamp():
    ts = datetime.datetime.utcnow()
    ats = pytz.utc.localize(ts)
    rts = ats.isoformat().split('.')[0] + 'Z'
    return rts


def get_custom_timestamp(months=-1, days=-1):
    today = datetime.datetime.today()
    td = (months * 30) + (days)
    newts = today - datetime.timedelta(days=(-1 * td))
    rts = newts.isoformat().split('.')[0] + 'Z'
    return rts


def unquote(string):

    # 'support%3Acore' -> support:core

    if '%3A' not in string:
        return string

    res = urlparse(string)

    if hasattr(res, 'path'):
        res = res.path

    return res


class IssueDatabase:

    eventids = set()
    issues = []

    teams = {
        'ansible-commit': ['jack', 'jill'],
        'ansible-community': ['bob', 'billy'],
    }

    def __init__(self, cachedir):
        self.cachedir = cachedir
        if not os.path.exists(self.cachedir):
            os.makedirs(self.cachedir)
        self.debug = False
        self.eventids = set()
        self.issues = []

        self.load_cache()

    def load_cache(self):
        cachefile = os.path.join(self.cachedir, 'issuedb.json')
        if not os.path.exists(cachefile):
            return

        with open(cachefile, 'r') as f:
            cachedata = json.loads(f.read())

        self.issues = cachedata['issues'][:]
        self.eventids = set(cachedata['eventids'][:])

        print('### ISSUEDB CACHE LOADED %s' % cachefile)

    def save_cache(self):
        cachefile = os.path.join(self.cachedir, 'issuedb.json')
        with open(cachefile, 'w') as f:
            f.write(json.dumps({
                'issues': self.issues[:],
                'eventids': list(self.eventids)
            }))

        print('### ISSUEDB CACHE SAVED %s' % cachefile)


    def get_url(self, url, method=None, headers=None, data=None):

        # workaround for changing object refs
        self.load_cache()

        if self.debug:
            print('#########################################')
            print('# issuedb %s' % id(self))
            print('# %s' % method or 'GET')
            print('# %s' % url)
            print('# %s' % headers)
            print('# %s' % data)
            print('#########################################')
        else:
            print('# %s %s' % (method or 'GET', url))

        rheaders = {
            'Date': datetime.datetime.now().isoformat(),
            'ETag': str(uuid.uuid4()),
            'Last-Modified': datetime.datetime.now().isoformat()
        }
        rdata = None

        parts = url.split('/')

        if method == 'PUT':

            if parts[-1] == 'merge':
                org = parts[4]
                repo = parts[5]
                number = int(parts[7])
                rdata = self.merge_pull(org=org, repo=repo, number=number, data=data)
            else:
                import epdb; epdb.st()

        elif method == 'POST':
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
            elif url.endswith('repos/ansible/ansible-azp'):
                rdata = self._get_repo('ansible/ansible-azp')
            elif url.endswith('repos/ansible/ansible/labels'):
                rdata = []

            elif parts[-2] == 'issues':
                org = parts[-4]
                repo = parts[-3]
                number = int(parts[-1])
                issue = self.get_issue(org=org, repo=repo, number=number)
                rdata = self.get_raw_data(issue)

            elif parts[-2] == 'pulls':
                org = parts[-4]
                repo = parts[-3]
                number = int(parts[-1])
                issue = self.get_issue(org=org, repo=repo, number=number)
                rdata = self.get_raw_data(issue, schema='pull')
                #import epdb; epdb.st()

            elif parts[-2] == 'comments':
                org = parts[-4]
                repo = parts[-3]
                commentid = int(parts[-1])
                rdata = self.get_comment(org=org, repo=repo, commentid=commentid)

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
                org = parts[4]
                repo = parts[5]
                number = int(parts[-2])
                issue = self.get_issue(org=org, repo=repo, number=number)
                events = issue.get('timeline', [])[:]
                rdata = []
                for event in events:
                    data = event.copy()
                    #data['updated_at'] = data['created_at']
                    rdata.append(data)

                #import epdb; epdb.st()
                #rdata = []

            elif parts[-1] in ['reactions']:
                org = parts[4]
                repo = parts[5]
                number = int(parts[-2])
                rdata = self.get_issue_property('reactions', org=org, repo=repo, number=number)

            elif parts[-1] == 'assignees':
                rdata = []

            elif parts[-1] == 'members':
                rdata = []
                rdata = self._get_members()

            elif parts[-1] == 'teams':
                rdata = self._get_teams()

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
                    'updated_at': get_timestamp(),
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

            elif parts[-1] == 'reviews':
                rdata = []

            elif parts[-1] == 'commits':
                org = parts[4]
                repo = parts[5]
                number = int(parts[-2])
                rdata = self.get_commits(org=org, repo=repo, number=number)

            elif parts[-2] == 'commits':
                org = parts[4]
                repo = parts[5]
                chash = parts[-1]

                # ansible/ansible/commits/xxxx
                # ansible/ansible/git/commits/xxxx

                if parts[-3] != 'git':
                    rdata = self.get_commit(org=org, repo=repo, chash=chash)
                else:
                    rdata = self.get_git_commit(org=org, repo=repo, chash=chash)
                    #import epdb; epdb.st()

            elif parts[-1] == 'files':
                org = parts[4]
                repo = parts[5]
                number = int(parts[-2])
                rdata = self.get_files(org=org, repo=repo, number=number)

            elif parts[6] == 'contents':
                # https://api.github.com:443/repos/profleonard/ansible/contents/shippable.yml
                org = parts[4]
                repo = parts[5]
                filename = '/'.join(parts[7:])
                rdata = self.get_file_conent(org=org, repo=repo, filename=filename)

            elif parts[-2] == 'statuses':
                # https://api.github.com/repos/ansible/ansible/statuses/1f45467df45e7d7a874073f0f4ae21f9c27bebd9
                org = parts[4]
                repo = parts[5]
                sid = parts[-1]
                rdata = self.get_pull_statuses(org, repo, sid)

            elif parts[-1] == 'file_map':
                rdata = {}

            elif parts[-2] == 'collections' and parts[-1] == 'list':
                rdata = {}

        # pause if we don't know how to handle this url+method yet
        if rdata is None:
            import epdb; epdb.st()
            return None

        #if 'labels' in parts and not rdata:
        #    import epdb; epdb.st()

        if self.debug:
            print('# %s' % rdata)

        return rheaders,rdata

    def merge_pull(self, org=None, repo=None, number=None, data=None, login=None):
        ix = self._get_issue_index(org=org, repo=repo, number=number, itype='pull')

        ts = get_timestamp()
        self.issues[ix]['updated_at'] = ts
        self.issues[ix]['merged_at'] = ts
        self.issues[ix]['closed_at'] = ts
        self.issues[ix]['state'] = 'closed'
        self.issues[ix]['merged'] = True

        user = {
            'login': (login or 'ansibot'),
            'url': 'https://api.github.com/users/%s' % (login or 'ansibot')
        }
        self.issues[ix]['closed_by'] = user.copy()
        self.issues[ix]['merged_by'] = user.copy()

        eid = self._get_new_event_id()
        event = {
            'event': 'closed',
            'actor': user.copy(),
            'id': eid, 
            'url': 'https://api.github.com/repos/%s/%s/issues/events/%s' % (org, repo, eid),
            'commit_id': None,
            'commit_url': None,
            'created_at': ts
        }
        self.issues[ix]['events'].append(event)

        # if resp[0] != 200 or u'successfully merged' not in resp[2]
        return [None, 'successfully merged']

    def get_pull_statuses(self, org, repo, sid):
        statuses = []
        sdata = {
            'url': 'https://api.github.com/repos/ansible/ansible/statuses/JSTATUS_1',
            'id': 'JSTATUS_1',
            'node_id': 'NODEJSTATUS1',
            'state': 'success',
            'description': 'Run 1 status is SUCCESS. ',
            'target_url': 'https://app.shippable.com/github/ansible/ansible/runs/1/summary',
            'context': 'Shippable',
            'created_at': get_timestamp(),
            'updated_at': get_timestamp(),
            'creator': {
                'login': 'ansibot'
            }
        }
        statuses.append(sdata)
        #import epdb; epdb.st()
        return statuses

    def shippable_response(self, url):
        # https://api.shippable.com/runs?projectIds=573f79d02a8192902e20e34b&isPullRequest=True --> []
        if 'api.shippable.com/runs' in url:
            return []

        return {}

    def graphql_response(self, data):

        # id, url, number, state, createdAt, updatedAt, repository, nameWithOwner

        # query, repository, owner, ansible, issues, states, OPEN, first 100
        #   id, url, number, state, createdAt, updatedAt, repository/nameWithOwner

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

        if 'issue' in words or 'pullRequest' in words:
            resp = {
                'data': {
                    'repository': {
                    }
                }
            }

            known_pulls = [x['number'] for x in self.issues if x['itype'] == 'pull']

            # if querying PRs and the number is not a PR, return None
            okey = 'issue'
            if rq.get('pullRequest') and rq['number'] not in known_pulls:
                okey = 'pullRequest'
                resp['data']['repository'][okey] = None 
                return resp

            resp['data']['repository'][okey] = {
                'id': 'xxxxxx',
                'state': 'open',
                'number': rq['number'],
                'createdAt': get_timestamp(), 
                'updatedAt': get_timestamp(),
                'repository': {'nameWithOwner': rq['owner'] + '/' + rq['name']},
                'url': 'https://github.com/%s/%s/%s/%s' % (rq['owner'], rq['name'], okey, rq['number'])
            }

        elif 'pullRequest' in words:
            resp = None

        elif 'issues' in words or 'pullRequests' in words:

            if 'issues' in words:
                tkey = 'issues'
            else:
                tkey = 'pullRequests'

            resp = {
                'data': {
                    'repository': {
                        tkey: {
                            'edges': [],
                            'pageInfo': {
                                'endCursor': 'abc1234',
                                'startCursor': 'abc1234',
                                'hasNextPage': False,
                                'hasPreviousPage': False
                            }
                        }
                    }
                }
            }

            edges = []
            for idx,x in enumerate(self.issues):
                if tkey == 'pullRequests' and not x['itype'] == 'pull':
                    continue
                edge = {
                    'node': {
                        'createdAt': x['created_at'],
                        'updatedAt': x['updated_at'],
                        'id': idx,
                        'number': x['number'],
                        'state': x['state'].upper(),
                        'url': x['html_url']
                    }
                }
                edges.append(edge)

            resp['data']['repository'][tkey]['edges'] = edges

        else:
            print(words)
            import epdb; epdb.st()

        return resp

    def _get_members(self):
        data = []
        members = set()
        for k,v in self.teams.items():
            for member in v:
                members.add(member)

        members = sorted(list(members))

        for idm,member in enumerate(members):
            data.append({
                'avatar_url': '',
                'bio': '',
                'blog': '',
                'company': '',
                'created_at': get_timestamp(),
                'updated_at': get_timestamp(),
                'email': 'foo@bar.com',
                'events_url': 'https://api.github.com/users/%s/events{/privacy}' % member,
                'followers': 0,
                'followers_url': 'https://api.github.com/users/%s/followers' % member,
                'following_url': 'https://api.github.com/users/%s/following{/other_user}' % member,
                'gists_url': 'https://api.github.com/users/%s/gists{/gist_id}' % member,
                'gravator"id': '',
                'hireable': None,
                'html_url': 'https://github.com/%s' % member,
                'id': idm,
                'location': '',
                'login': member,
                'name': member,
                'node_id': 'NODEM%s' % idm,
                'organizations_url': 'https://api.github.com/users/%s/orgs' % member,
                'public_gists': 0,
                'public_repos': 0,
                'received_events_url': 'https://api.github.com/users/%s/received_events' % member,
                'repos_url': 'https://api.github.com/users/%s/repos' % member,
                'site_admin': False,
                'starred_url': 'https://api.github.com/users/%s{/owner}{/repo}' % member,
                'subscriptions_url': 'https://api.github.com/users/%s/subscription' % member,
                'type': 'User',
                'url': 'https://api.github.com/users/%s' % member
            })

        return data

    def _get_teams(self):
        rdata = []
        keys = sorted(list(self.teams.keys()))
        for idk,k in enumerate(keys):
            v = self.teams[k]
            team = {
                'created_at': get_timestamp(),
                'updated_at': get_timestamp(),
                'description': '',
                'id': idk,
                'members_count': len(v),
                'members_url': 'https://api.github.com/teams/%s/members{/member}' % idk,
                'name': k,
                'node_id': 'NODET%s' % idk,
                'organization': {},
                'permission': 'pull',
                'privacy': 'secret',
                'repos_count': 1,
                'repositories_url': 'https://api.github.com/teams/%s/repos' % idk,
                'slug': '',
                'url': 'https://api.github.com/teams/%s' % idk
            }
            rdata.append(team)
        return rdata

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
            'created_at': get_timestamp(),
            'updated_at': get_timestamp(),
        }
        return ds

    def _get_new_issue_id(self):
        if len(self.issues) == 0:
            thisid = 1
        else:
            thisid = len(list(self.issues)) + 1
        return thisid

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

    def get_raw_data(self, issue, schema='issue'):
        org = issue['url'].split('/')[4]
        repo = issue['url'].split('/')[5]

        if issue['itype'].startswith('pull'):
            html_url = 'https://github.com/%s/%s/pull/%s' % (org, repo, issue['number'])
        else:
            html_url = 'https://github.com/%s/%s/issues/%s' % (org, repo, issue['number'])

        rdata = {
            'id': issue.get('id'),
            'node_id': issue.get('node_id') or 'NODEI%s' % issue.get('id'),
            'repository_url': 'https://api.github.com/repos/%s/%s' % (org, repo),
            'labels_url': 'https://api.github.com/repos/%s/%s/issues/%s/labels{/name}' % (org, repo, issue['number']),
            'comments_url': 'https://api.github.com/repos/%s/%s/issues/%s/events' % (org, repo, issue['number']),
            'events_url': 'https://api.github.com/repos/%s/%s/issues/%s/events' % (org, repo, issue['number']),
            'assignee': None,
            'assignees': [],
            'state': issue['state'],
            'title': issue['title'],
            'body': issue['body'],
            'comments': len(issue['comments']),
            'locked': False,
            'number': issue['number'],
            'url': issue['url'],
            'html_url': html_url,
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

        if schema.lower() in ['pull', 'pullrequest']:

            rdata['url'] = rdata['url'].replace('issues', 'pull')
            rdata['statuses_url'] = 'https://api.github.com/repos/%s/%s/statuses/PSTATUS_%s' % (issue['org'], issue['repo'], rdata['id'])
            rdata['commits_url'] = rdata['url'] + '/commits'
            rdata['comments_url'] = rdata['url'] + '/comments'
            rdata['review_comments_url'] = rdata['url'] + '/comments'
            rdata['review_comment_url'] = rdata['url'] + '/comments{/number}'
            rdata['diff_url'] = rdata['url'] + '.diff'
            rdata['merged_at'] = None
            rdata['merge_commit_sha'] = None
            rdata['merged'] = False
            rdata['merged_by'] = None
            rdata['mergeable'] = True
            rdata['mergeable_state'] = "clean"
            rdata['rebaseable'] = None
            rdata['requested_reviewers'] = []
            rdata['requested_teams'] = []
            rdata['review_comments'] = 0
            rdata['milestone'] = None
            rdata['head'] = {}
            rdata['base'] = {}
            rdata['_links'] = {}
            rdata['maintainer_can_modify'] = False
            rdata['commits'] = len(issue['commits'])
            rdata['additions'] = 1
            rdata['deletions'] = 1
            rdata['changed_files'] = 1

            rdata['head'] = {
                'label': None,
                'ref': None,
                'sha': 'sha1234567890',
                'user': rdata['user'].copy(),
                'repo': {
                    'id': None,
                    'node_id': 'NODER%s' % (rdata['user']['login'] + repo),
                    'name': repo,
                    'full_name': rdata['user']['login'] + '/' + repo,
                    'url': 'https://api.github.com/repos/%s/%s' % (rdata['user']['login'], repo),
                    'html_url': 'https://github.com/%s/%s' % (rdata['user']['login'], repo)
                }
            }

            rdata['base'] = {
                'label': '%s:devel' % repo,
                'ref': 'devel',
                'sha': 'sha1234567890',
                'user': rdata['user'].copy(),
                'repo': {
                    'id': None,
                    'node_id': 'NODER%s' % (org + repo),
                    'full_name': org + '/' + repo,
                    'url': 'https://api.github.com/repos/%s/%s' % (org, repo),
                }
            }

        return rdata

    def get_comment(self, org=None, repo=None, commentid=None):
        for issue in self.issues:
            if org and issue['org'] != org:
                continue
            if repo and issue['repo'] != repo:
                continue

            for comment in issue['comments']:
                if comment['id'] == commentid:
                    return comment.copy()

    def get_commits(self, org=None, repo=None, number=None):
        ix = self._get_issue_index(org=org, repo=repo, number=number)
        issue = self.issues[ix]
        return issue.get('commits', [])

    def get_commit(self, org=None, repo=None, chash=None):
        for issue in self.issues:
            if org and issue['org'] != org:
                continue
            if repo and issue['repo'] != repo:
                continue

            if 'commits' not in issue:
                continue

            for commit in issue['commits']:
                if commit['sha'] == chash:
                    return commit.copy()

        #import epdb; epdb.st()
        return None

    def get_git_commit(self, org=None, repo=None, chash=None):

        # git commits have a slightly different schema from other commits
        # https://api.github.com/repos/ansible/ansible/git/commits/7e22c7482e85cc98e14c4cdbc8b8ffb543917425

        thiscommit = self.get_commit(org=org, repo=repo, chash=chash)
        if thiscommit is None:
            return None

        for k,v in thiscommit['commit'].items():
            if isinstance(v, dict):
                thiscommit[k] = v.copy()
            else:
                thiscommit[k] = v
        thiscommit.pop('commit', None)
        thiscommit.pop('comments_url', None)

        return thiscommit

    def get_files(self, org=None, repo=None, number=None):
        ix = self._get_issue_index(org=org, repo=repo, number=number)
        issue = self.issues[ix]
        return issue.get('files', [])

    def get_file_conent(self, org=None, repo=None, filename=None):
        if filename != 'travis.yml':
            fdata = {
                'name': os.path.basename(filename), 
                'path': filename,
                'sha': 'sha0003030303',
                'url': 'https://api.github.com/repos/%s/%s/contents/%s?ref=devel' % (org, repo, filename),
                'type': 'file',
                'content': '',
                'encoding': 'base64',
            }
        else:
            fdata = {
                'message': 'Not Found',
                'documentation_url': 'https://developer.github.com/v3/repos/contents/#get-contents'
            }
        return fdata


    def set_issue_body(self, body, org=None, repo=None, number=None):
        ix = self._get_issue_index(org=org, repo=repo, nunmber=number)
        self.issues[ix]['body'] = body
        self.save_cache()

    def set_issue_title(self, title, org=None, repo=None, number=None):
        ix = self._get_issue_index(org=org, repo=repo, number=number)
        self.issues[ix]['title'] = title
        self.save_cache()

    def add_reaction(self, reaction, login=None, created_at=None, org=None, repo=None, number=None):
        reaction = unquote(reaction)
        ix = self._get_issue_index(org=org, repo=repo, number=number)
        event = {
            'content': reaction,
            'created_at': created_at or get_timestamp(),
            'id': self._get_new_event_id(),
            'user': {
                'login': login or 'ansibot',
                'url': 'https://api.github.com/users/%s' % login or 'ansibot'
            }
        }
        event['node_id'] = 'NODER%s' % event['id']
        self.issues[ix]['reactions'].append(event)
        self.issues[ix]['updated_at'] = event['created_at']

    def add_issue_label(self, label, login=None, created_at=None, org=None, repo=None, number=None):
        label = unquote(label)
        ix = self._get_issue_index(org=org, repo=repo, number=number)
        if label not in [x['name'] for x in self.issues[ix]['labels']]:

            ldata = {
                'name': label,
                'url': 'https://api.github.com/repos/%s/%s/labels/%s' % (org, repo, label)
            }

            self.issues[ix]['labels'].append(ldata)
            print('# added %s label to %s' % (label, self.issues[ix]['number']))

            event = {}
            event['id'] = self._get_new_event_id()
            event['node_id'] = 'NODE' + str(event['id'])
            event['url'] = 'https://api.github.com/repos/%s/%s/issues/events/%s' % (org, repo, event['id'])
            event['event'] = 'labeled'
            event['label'] = ldata
            event['actor'] = {
                'url': 'https://api.github.com/users/%s' % login or 'ansibot',
                'html_url': 'https://github.com/%s' % login or 'ansibot',
                'login': login or 'ansibot'
            }
            event['created_at'] = created_at or get_timestamp()
            self.issues[ix]['events'].append(event)
            self.issues[ix]['timeline'].append(event)
            self.issues[ix]['updated_at'] = event['created_at']

        self.save_cache()

    def add_issue_comment(self, comment, login=None, created_at=None, org=None, repo=None, number=None):

        # comments do not get added to events!!!

        if login is None:
            login = 'ansibot'

        ix = self._get_issue_index(org=org, repo=repo, number=number)
        thiscomment = {
            'id': self._get_new_event_id(),
            'body': comment,
            'user': {
                'url': 'https://api.github.com/users/%s' % login,
                'html_url': 'https://github.com/%s' % login,
                'login': login or 'ansibot'
            },
            'created_at': created_at or get_timestamp()
        }
        thiscomment['node_id'] = 'NODE' + str(thiscomment['id'])
        thiscomment['url'] = 'https://api.github.com/repos/%s/%s/issues/comments/%s' % (org, repo, thiscomment['id'])
        self.issues[ix]['comments'].append(thiscomment)
        self.issues[ix]['updated_at'] = thiscomment['created_at']


        tl = {
            'author_association': 'MEMBER',
            'actor': thiscomment['user'].copy(),
            'user': thiscomment['user'].copy(),
            'body': comment,
            'created_at': thiscomment['created_at'],
            'updated_at': thiscomment['created_at'],
            'url': thiscomment['url'],
            'id': thiscomment['id'],
            'node_id': thiscomment['node_id'],
            'issue_url': self.issues[ix]['url'],
            'event': 'commented'
        }
        self.issues[ix]['timeline'].append(tl)

        if self.debug:
            print('comment added to issue %s' % self.issues[ix]['number'])

        self.save_cache()


    def remove_issue_label(self, label, login=None, created_at=None, org=None, repo=None, number=None):
        label = unquote(label)
        ix = self._get_issue_index(org=org, repo=repo, number=number)
        if label in [x['name'] for x in self.issues[ix]['labels']]:

            ldata = {
                'name': label,
                'url': 'https://api.github.com/repos/%s/%s/labels/%s' % (org, repo, label)
            }

            self.issues[ix]['labels'].remove(ldata)
            print('# added %s label to %s' % (label, self.issues[ix]['number']))

            event = {}
            event['id'] = self._get_new_event_id()
            event['node_id'] = 'NODE' + str(event['id'])
            event['url'] = 'https://api.github.com/repos/%s/%s/issues/events/%s' % (org, repo, event['id'])
            event['event'] = 'unlabeled'
            event['label'] = ldata
            event['actor'] = {'login': login or 'ansibot'}
            event['created_at'] = created_at or get_timestamp()
            self.issues[ix]['events'].append(event)
            self.issues[ix]['timeline'].append(event)
            self.issues[ix]['updated_at'] = event['created_at']

            if self.debug:
                print('removed %s label from issue %s' % (label, self.issues[ix]['number']))

        self.save_cache()

    def add_cross_reference(self, login=None, created_at=None, org=None, repo=None, number=None, reference=None):
        assert isinstance(number, int)
        assert isinstance(reference, int)
        src_ix = self._get_issue_index(org=org, repo=repo, number=number)
        dst_ix = self._get_issue_index(org=org, repo=repo, number=reference)

        #src_issue = self.issues[src_ix]
        dst_issue = self.issues[dst_ix]

        #src_raw = self.get_raw_data(src_issue)
        dst_raw = self.get_raw_data(dst_issue)

        cr_event = {
            'actor': dst_raw['user'],
            'event': 'cross-referenced',
            'created_at': get_timestamp(),
            'updated_at': get_timestamp(),
            'source': {
                'type': 'issue',
                'issue': dst_raw
            }
        }

        #dst_issue
        #import epdb; epdb.st()
        self.issues[src_ix]['timeline'].append(cr_event)

        self.save_cache()

    def add_issue_file(
                self,
                filename,
                org=None,
                repo=None,
                number=None,
                patch='',
                commit_hash=None,
                additions=0,
                changes=0,
                deletions=0,
                sha=None,
                status=None,
                created_at=None
            ):

        ix = self._get_issue_index(org=org, repo=repo, number=number)
        if ix is None:
            import epdb; epdb.st()
        issue = self.issues[ix]

        if commit_hash is None:
            commit_hash = 'cHASH0001'
        if sha is None:
            sha = 'cSHA0001'
        fdata = {
            'additions': additions,
            'deletions': deletions,
            'changes': changes,
            'filename': filename,
            'patch': patch,
            'status': status,
            'sha': sha,
            'blob_url': 'https://github.com/%s/%s/blob/%s/%s' % (issue['org'], issue['repo'], commit_hash, filename),
            'raw_url': 'https://github.com/%s/%s/blob/%s/%s' % (issue['org'], issue['repo'], commit_hash, filename),
            'contents_url': 'https://github.com/%s/%s/contents/%s?ref=%s' % (issue['org'], issue['repo'], filename, commit_hash),
        }

        self.issues[ix]['files'].append(fdata)

    def _get_empty_stub(self):
        stub = {
            'itype': 'issue',
            'node_id': None,
            'id': None,
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
                assignees=None,
                commits=None,
                files=None
            ):

        thisissue = self._get_empty_stub()
        thisissue['id'] = self._get_new_issue_id()

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

        if number is not None:
            thisissue['number'] = number
        else:
            if len(self.issues) == 0:
                thisissue['number'] = 1
            else:
                thisissue['number'] = [x for x in self.issues if x['org'] == thisissue['org'] and x['repo'] == thisissue['repo']][-1]['number'] + 1

        thisissue['created_at'] = created_at or get_timestamp()
        thisissue['updated_at'] = updated_at or get_timestamp()

        if login:
            thisissue['user']['login'] = login
            thisissue['user']['url'] = 'https://api.github.com/users/%s' % login
            thisissue['created_by']['login'] = login
        else:
            thisissue['user']['login'] = 'jimbob'
            thisissue['user']['url'] = 'https://api.github.com/users/jimbob'
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

        thisissue['html_url'] = url.replace('api.github.com/repos', 'github.com')

        if commits:
            thisissue['commits'] = commits
        elif itype and itype.startswith('pull'):
            thisissue['commits'] = [
                {
                    'sha': 'd7e6a2eae2633a353e16f951a2c6a78c09db6953',
                    'node_id': None,
                    'commit': {
                        'author': {
                            'name': thisissue['user']['login'],
                            'email': '%s@noreply.github.com' % thisissue['user']['login'],
                            'date': thisissue['created_at'],
                        },
                        'committer': {
                            'name': thisissue['user']['login'],
                            'email': '%s@noreply.github.com' % thisissue['user']['login'],
                            'date': thisissue['created_at'],
                        },
                        'message': 'test commit',
                        'tree': {
                            'sha': '25d360965b12b923aa7cc23c5db202ca25b17d9f',
                            'url': 'https://api.github.com/repos/%s/%s/git/trees/25d360965b12b923aa7cc23c5db202ca25b17d9f' % (org, repo),
                        },
                        'url': 'https://api.github.com/repos/%s/%s/git/commits/d7e6a2eae2633a353e16f951a2c6a78c09db6953' % (org, repo),
                        'comment_count': 0,
                    },
                    'url': 'https://api.github.com/repos/%s/%s/commits/d7e6a2eae2633a353e16f951a2c6a78c09db6953' % (org, repo),
                    'html_url': 'https://github.com/%s/%s/commit/d7e6a2eae2633a353e16f951a2c6a78c09db6953' % (org, repo),
                    'comments_url': 'https://api.github.com/repos/%s/%s/commits/d7e6a2eae2633a353e16f951a2c6a78c09db6953/comments' % (org, repo),
                    'verification': {
                        'verified': False,
                        'reason': 'unsigned',
                        'signature': None,
                        'payload': None,
                    },
                    'author': thisissue['user'].copy(),
                    'committer': thisissue['user'].copy(),
                    'parents': [
                        {
                            'sha': '7e22c7482e85cc98e14c4cdbc8b8ffb543917425',
                            'url': 'https://api.github.com/repos/%s/%s/commits/7e22c7482e85cc98e14c4cdbc8b8ffb543917425' % (org, repo),
                            'html_url': 'https://github.com/%s/%s/commit/7e22c7482e85cc98e14c4cdbc8b8ffb543917425' % (org, repo),
                        }
                    ]
                }
            ]

        if files:
            thisissue['files'] = files
        elif itype and itype.startswith('pull'):
            thisissue['files'] = [
                {
                    'sha': '45b134231ef0f9c2a37c7896ea6f439d15982469',
                    'filename': 'lib/ansible/modules/foo/bar.py',
                    'status': 'added',
                    'additions': 317,
                    'deletions': 0,
                    'changes': 317,
                    'blob_url': 'https://github.com/%s/%s/blob/d7e6a2eae2633a353e16f951a2c6a78c09db6953/lib/ansible/modules/foo/bar.py' % (org, repo),
                    'raw_url': 'https://github.com/%s/%s/blob/d7e6a2eae2633a353e16f951a2c6a78c09db6953/lib/ansible/modules/foo/bar.py' % (org, repo),
                    'contents_url': 'https://api.github.com/repos/%s/%s/contents/lib/ansible/modules/foo/bar.py?ref=d7e6a2eae2633a353e16f951a2c6a78c09db6953' % (org, repo),
                    'patch': ''
                }
            ]

        self.issues.append(thisissue)

        self.save_cache()


class MockRequests:

    def __init__(self, issuedb):
        self.issuedb = issuedb

    def get(self, url, headers=None, data=None):
        return MockRequestsResponse(url, inheaders=headers, indata=data, method='GET', issuedb=self.issuedb)

    def post(self, url, headers=None, data=None):
        return MockRequestsResponse(url, inheaders=headers, indata=data, method='POST', issuedb=self.issuedb)

    def Session(self):
        return MockRequestsSession(self.issuedb)



class MockRequestsSession:
    def __init__(self, issuedb):
        self.issuedb = issuedb

    def get(self, url, allow_redirects=False, data=None, headers=None, timeout=None, verify=True):
        return MockRequestsResponse(url, inheaders=headers, indata=data, session=self, issuedb=self.issuedb)

    def post(self, url, allow_redirects=False, data=None, headers=None, timeout=None, verify=True):
        return MockRequestsResponse(url, inheaders=headers, indata=data, method='POST', issuedb=self.issuedb)

    def delete(self, url, allow_redirects=False, data=None, headers=None, timeout=None, verify=True):
        return MockRequestsResponse(url, inheaders=headers, indata=data, method='DELETE', issuedb=self.issuedb)

    def put(self, url, allow_redirects=False, data=None, headers=None, timeout=None, verify=True):
        # data: {"merge_method": "squash"}
        return MockRequestsResponse(url, inheaders=headers, indata=data, method='PUT', issuedb=self.issuedb)


class MockRequestsResponse:

    def __init__(self, url, inheaders=None, indata=None, method='GET', issuedb=None, session=None):
        self.issuedb = issuedb
        self.session = session
        self.method = method
        self.url = url
        self.inheaders = inheaders
        self.indata = indata
        self.rheaders, self.rdata = \
            self.issuedb.get_url(
                self.url,
                headers=self.inheaders,
                data=indata,
                method=method
            )

    @property
    def ok(self):
        return True

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
        print('WARNING %s' % message)

    @staticmethod
    def warning(message):
        print('WARNING %s' % message)

    @staticmethod
    def error(message):
        print('ERROR %s ' % message)

    @staticmethod
    def Formatter(format_string):
        return None

    @staticmethod
    def getLogger(*args, **kwargs):
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


class BotMockManager:

    mocks = []
    issuedb = None
    cachedir = None
    mr = None
    mrs = None
    ml = None

    def __init__(self):
        #self.mocks = []
        print('### STARTING MOCK MANAGER!!!')
        self.issuedb = None
        self.cachedir = None

    def __enter__(self):

        # make a cachedir
        self.cachedir = tempfile.mkdtemp(prefix='ansibot.test.idem.')

        # create the issuedb
        self.issuedb = IssueDatabase(self.cachedir)

        # force sqlite to use the cachedir
        unc = 'sqlite:///' + self.cachedir + '/test.db'
        unc_mock = mock.patch('ansibullbot.utils.sqlite_utils.C.DEFAULT_DATABASE_UNC', unc)
        self.mocks.append(unc_mock)

        # pre-create
        if not os.path.exists(self.cachedir):
            os.makedirs(self.cachedir)

        # cache a copy of ansible for all tests to use
        if not os.path.exists('/tmp/ansible.checkout'):
            p = subprocess.Popen('git clone https://github.com/ansible/ansible /tmp/ansible.checkout', shell=True)
            p.communicate()

        # copy the cached checkout to the cachedir for the bot to use
        if os.path.exists('/tmp/ansible.checkout'):
            p = subprocess.Popen(
                'cp -Rp /tmp/ansible.checkout %s' % os.path.join(self.cachedir, 'ansible.checkout'),
                shell=True
            )
            p.communicate()

        # MOCK ALL THE THINGS!
        self.mr = MockRequests(self.issuedb)
        self.mrs = MockRequestsSession(self.issuedb)
        self.ml = MockLogger

        self.mocks.append(mock.patch('ansibullbot.decorators.github.C.DEFAULT_RATELIMIT', False))
        self.mocks.append(mock.patch('ansibullbot.decorators.github.C.DEFAULT_BREAKPOINTS', True))
        self.mocks.append(mock.patch('ansibullbot.decorators.github.C.DEFAULT_GITHUB_USERNAME', 'ansibot'))
        self.mocks.append(mock.patch('ansibullbot.decorators.github.C.DEFAULT_GITHUB_TOKEN', 'abc1234'))
        self.mocks.append(mock.patch('github.Requester.requests', self.mr))
        self.mocks.append(mock.patch('ansibullbot.decorators.github.requests', self.mr))
        self.mocks.append(mock.patch('ansibullbot.parsers.botmetadata.logging', MockLogger))
        self.mocks.append(mock.patch('ansibullbot.triagers.ansible.logging', MockLogger))
        self.mocks.append(mock.patch('ansibullbot.triagers.ansible.requests', self.mr))
        self.mocks.append(mock.patch('ansibullbot.triagers.plugins.contributors.logging', MockLogger))
        self.mocks.append(mock.patch('ansibullbot.triagers.plugins.needs_revision.logging', MockLogger))
        self.mocks.append(mock.patch('ansibullbot.triagers.plugins.shipit.logging', MockLogger))
        self.mocks.append(mock.patch('ansibullbot.triagers.defaulttriager.logging', MockLogger))
        self.mocks.append(mock.patch('ansibullbot.utils.component_tools.logging', MockLogger))
        #self.mocks.append(mock.patch('ansibullbot.utils.component_tools.requests', self.mr))
        self.mocks.append(mock.patch('ansibullbot.utils.extractors.logging', MockLogger))
        self.mocks.append(mock.patch('ansibullbot.utils.gh_gql_client.logging', MockLogger))
        self.mocks.append(mock.patch('ansibullbot.utils.git_tools.logging', MockLogger))
        self.mocks.append(mock.patch('ansibullbot.utils.moduletools.logging', MockLogger))
        self.mocks.append(mock.patch('ansibullbot.utils.net_tools.logging', MockLogger))
        self.mocks.append(mock.patch('ansibullbot.utils.shippable_api.logging', MockLogger))
        self.mocks.append(mock.patch('ansibullbot.utils.sqlite_utils.logging', MockLogger))
        self.mocks.append(mock.patch('ansibullbot.utils.timetools.logging', MockLogger))
        self.mocks.append(mock.patch('ansibullbot.utils.version_tools.logging', MockLogger))
        self.mocks.append(mock.patch('ansibullbot.wrappers.defaultwrapper.logging', MockLogger))
        self.mocks.append(mock.patch('ansibullbot.wrappers.historywrapper.logging', MockLogger))
        self.mocks.append(mock.patch('ansibullbot.wrappers.ghapiwrapper.logging', MockLogger))
        self.mocks.append(mock.patch('ansibullbot.utils.gh_gql_client.requests', self.mr))
        self.mocks.append(mock.patch('ansibullbot.utils.shippable_api.requests', self.mr))
        self.mocks.append(mock.patch('ansibullbot.wrappers.ghapiwrapper.requests', self.mr))

        for _m in self.mocks:
            _m.start()

        return self

    def __exit__(self, type, value, traceback):

        for _m in self.mocks:
            _m.stop()

        if self.cachedir and os.path.exists(self.cachedir):
            shutil.rmtree(self.cachedir)
