#!/usr/bin/env python

import datetime
import hashlib
import json
import os
import pickle
import random
import six
import time

from pprint import pprint
from flask import Flask
from flask import jsonify
from flask import request


app = Flask(__name__)


BASEURL = 'http://localhost:5000'
ERROR_TIMER = 0

TOKENS = {
    'AAA': 'ansibot'
}


########################################################
#   MOCK 
########################################################

class GithubMock(object):

    ifile = '/tmp/fakeup/issues.p'
    efile = '/tmp/fakeup/events.p'
    ISSUES = {'github': {}}
    EVENTS = {}
    STATUS_HASHES = {}

    def __init__(self):
        pass

    def get_issue_status_uuid(self, org, repo, number):
        # .../repos/ansible/ansibullbot/statuses/882849ea5f96f757eae148ebe59f504a40fca2ce
        key = (org, repo, int(number))
        if key not in self.STATUS_HASHES:
            hash_object = hashlib.sha256(str(key))
            self.STATUS_HASHES[key] = hash_object.hexdigest()
        return self.STATUS_HASHES[key]

    def get_status(self, hex_digest):
        key = None
        for k,v in self.STATUS_HASHES.items():
            if v == hex_digest:
                key = k 
                break
        status = {}
        return status

    def get_issue(self, org, repo, number, itype='issue'):

        def get_labels(org, repo, number):
            labels = []
            events = self.EVENTS.get((org, repo, number), [])
            for event in events:
                if event['event'] == 'labeled':
                    labels.append(event['label'])
                elif event['event'] == ['unlabeled']:
                    labels = [x for x in labels if x['name'] != event['label']['name']]
            return labels

        key = (org, repo, int(number))
        if key in self.ISSUES['github']:
            return self.ISSUES['github'][key]

        print('# creating %s %s' % (number, itype))

        url = BASEURL
        url += '/'
        url += 'repos'
        url += '/'
        url += org
        url += '/'
        url += repo
        url += '/'
        '''
        if itype.lower() in ['pull', 'pullrequest']:
            url += 'pulls'
        else:
            url += 'issues'
        '''
        url += 'issues'
        url += '/'
        url += str(number)

        h_url = BASEURL
        h_url += '/'
        h_url += org
        h_url += '/'
        h_url += repo
        h_url += '/'
        if itype.lower() in ['pull', 'pullrequest']:
            h_url += 'pull'
        else:
            h_url += 'issues'
        #h_url += 'issues'
        #h_url += 'issue'
        h_url += '/'
        h_url += str(number)

        e_url = BASEURL
        e_url += '/'
        e_url += org
        e_url += '/'
        e_url += repo
        e_url += '/'
        e_url += 'issues'
        e_url += '/'
        e_url += str(number)
        e_url += '/'
        e_url += 'events'

        payload = {
            'id': 1000 + int(number),
            'assignees': [],
            'created_at': get_timestamp(), 
            'updated_at': get_timestamp(),
            'url': url,
            'events_url': e_url,
            'html_url': h_url,
            'number': int(number),
            'labels': get_labels(org, repo, int(number)),
            'user': {
                'login': 'foouser'
            },
            'title': 'this thing is broken',
            'body': '',
            'state': 'open'
        }

        if itype.lower() in ['pull', 'pullrequest']:
            pull_url = url.replace('issues', 'pulls')
            diff_url = pull_url + '.diff'
            patch_url = pull_url + '.patch'
            pull_h_url = h_url.replace('issues', 'pull')
            payload['pull_request'] = {
                "url": pull_url,
                "html_url": pull_h_url,
                "diff_url": diff_url,
                "patch_url": patch_url
            }

        self.ISSUES['github'][key] = payload.copy()
        self.save_data()

        #import epdb; epdb.st()
        pprint(payload)
        return payload

    def get_pullrequest(self, org, repo, number):
        issue = GM.get_issue(org, repo, number, itype='pull')
        issue['url'] = issue['url'].replace('issues', 'pulls')
        issue['requested_reviewers'] = []
        issue['requested_teams'] = []
        issue['commits_url'] = issue['url'] + '/commits'
        issue['review_comments_url'] = issue['url'] + '/comments'
        issue['review_comment_url'] = issue['url'] + '/comments{/number}'
        issue['head'] = {
            'repo': {
                'name': repo,
                'full_name': issue['user']['login'] + '/' + repo,
                'url': BASEURL + '/repos/' + issue['user']['login'] + '/' + repo
            },
            'sha': '882849ea5f96f757eae148ebe59f504a40fca2ce'
        }
        issue['base'] = {}
        issue['_links'] = {}
        issue['merged'] = False
        issue['mergeable'] = True
        issue['rebaseable'] = True
        issue['mergeable_state'] = 'unstable'
        issue['merged_by'] = None
        issue['review_comments'] = 0
        issue['commits'] = 1
        issue['additions'] = 10
        issue['deletions'] = 2
        issue['changed_files'] = 1
        issue['author_association'] = 'CONTRIBUTOR'

        status_hash = self.get_issue_status_uuid(org, repo, number)
        issue['statuses_url'] = BASEURL + '/repos/' + org + '/' + repo + '/statuses/' + status_hash
        return issue

    def save_data(self):

        with open(self.ifile, 'w') as f:
            #f.write(json.dumps(ISSUES))
            pickle.dump(self.ISSUES, f)

        with open(self.efile, 'w') as f:
            #f.write(json.dumps(EVENTS))
            pickle.dump(self.EVENTS, f)

    def load_data(self):

        if os.path.exists(self.ifile):
            with open(self.ifile, 'r') as f:
                #ISSUES = json.loads(f.read()) 
                self.ISSUES = pickle.load(f)

        if os.path.exists(self.efile):
            with open(self.efile, 'r') as f:
                #EVENTS = json.loads(f.read()) 
                self.EVENTS = pickle.load(f)

    def get_issue_event(self, org, repo, eid):
        event = None
        for k,events in GM.EVENTS.items():
            for ev in events:
                if ev['id'] == eid:
                    event = ev.copy()
                    break
        return event

    def get_issue_events(self, org, repo, number):
        key = (org, repo, int(number))
        events = self.EVENTS.get(key, [])
        # do not return comments as events!
        events = [x for x in events if x['event'] != 'commented']
        return events

    def add_issue_event(self, org, repo, number, event):

        key = (org, repo, int(number))
        if key not in self.ISSUES:
            self.get_issue(org, repo, int(number))
        if key not in self.EVENTS:
            self.EVENTS[key] = []
        eid = 0
        for k,v in self.EVENTS.items():
            for ev in v:
                eid+=1
        eid += 1
        event['id'] = eid

        if event['event'] == 'commented':
            #https://api.github.com/repos/ansible/ansible/issues/comments/428709071
            event['url'] = '%s/repos/%s/%s/issues/comments/%s' % (BASEURL, org, repo, eid)
        else:
            event['url'] = '%s/repos/%s/%s/issues/events/%s' % (BASEURL, org, repo, eid)

        self.EVENTS[key].append(event)
        self.ISSUES['github'][key]['updated_at'] = event['updated_at']
        self.save_data()

    def add_issue_label(self, org, repo, number, label, username):
        event = {
            'event': 'labeled',
            'created_at': get_timestamp(),
            'updated_at': get_timestamp(),
            'label': {'name': label},
            'user': {
                'login': username
            },
            'actor': {
                'login': username
            }
        }
        self.add_issue_event(org, repo, number, event)

    def remove_issue_label(self, org, repo, number, label, username):
        event = {
            'event': 'unlabeled',
            'created_at': get_timestamp(),
            'updated_at': get_timestamp(),
            'label': {'name': label},
            'user': {
                'login': username
            },
            'actor': {
                'login': username
            }
        }
        self.add_issue_event(org, repo, number, event)

    def add_issue_comment(self, org, repo, number, body, username):
        event = {
            'event': 'commented',
            'created_at': get_timestamp(),
            'updated_at': get_timestamp(),
            'user': {
                'login': username
            },
            'actor': {
                'login': username
            },
            'body': request.json['body']
        }
        self.add_issue_event(org, repo, number, event)

    def get_issue_comments(self, org, repo, number):
        events = self.EVENTS.get((org, repo, number), [])
        comments = [x for x in events if x['event'] == 'commented']
        return comments


GM = GithubMock()


def get_timestamp():
    # 2018-10-15T21:21:48.150184
    # 2018-10-10T18:25:49Z
    ts = datetime.datetime.now().isoformat()
    ts = ts.split('.')[0]
    ts += 'Z'
    return ts


########################################################
#   ROUTES
########################################################

def error_time():
    global ERROR_TIMER
    print('ERROR_TIMER: %s' % ERROR_TIMER)
    ERROR_TIMER += 1
    if ERROR_TIMER >= 10000:
        ERROR_TIMER = 0
        return True
    else:
        return False


class InternalServerError(Exception):
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        #return rv
        return None


@app.errorhandler(InternalServerError)
def throw_ise(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response


@app.before_first_request
def prep_server():
    #import epdb; epdb.st()
    #GM.load_data()
    if not GM.ISSUES['github']:
        for i in range(1, 11):
            ispr = bool(random.getrandbits(1))
            if ispr or i == 1:
                GM.get_issue('ansible', 'ansible', i, itype='pull')
            else:
                GM.get_issue('ansible', 'ansible', i, itype='issue')

    #issue = GM.get_issue('ansible', 'ansible', 1)
    #import epdb; epdb.st()

@app.route('/')
def root():
    return jsonify({})


@app.route('/rate_limit')
def rate_limit():
    reset = int(time.time()) + 10
    rl = {
        'resources': {
            'core': {
                'limit': 5000,
                'remaining': 5000,
                'reset': reset
            }
        },
        'rate': {
            'limit': 5000,
            'remaining': 5000,
            'reset': reset
        }
    }
    return jsonify(rl)


@app.route('/orgs/<path:path>')
def orgs(path):
    path_parts = path.split('/')
    print(six.text_type((len(path_parts),path_parts)))

    if error_time():
        raise InternalServerError(None, status_code=500)

    if len(path_parts) == 1:
        return jsonify({
            'assignees': [],
            'url': 'http://localhost:5000/orgs/' + path_parts[-1],
            'name': path_parts[-1],
            'id': 1,
            'created_at': '2018-01-08T20:25:21Z',
            'updated_at': '2018-01-08T20:25:21Z'
        })
    elif len(path_parts) == 2 and path_parts[-1] == 'members':
        return jsonify([])
    elif len(path_parts) == 2 and path_parts[-1] == 'teams':
        return jsonify([])


def dict_xpath_set(ddict, path, key, value):

    obj = ddict
    for ix in path:
        if ix not in obj:
            obj[ix] = {} 
        obj = obj[ix]

    if 'kwargs' not in obj:
        obj['kwargs'] = {}
    if 'nodes' not in obj:
        obj['nodes'] = []
    obj['kwargs'][key] = value

    #pprint(ddict)
    #import epdb; epdb.st()
    return ddict


def dict_xpath_add(ddict, path, value):
    obj = ddict
    for ix in path:
        if ix not in obj:
            obj[ix] = {} 
        obj = obj[ix]

    if 'kwargs' not in obj:
        obj['kwargs'] = {}
    if 'nodes' not in obj:
        obj['nodes'] = []
    obj['nodes'].append(value)
    return ddict


@app.route('/graphql', methods=['GET', 'POST'])
def graphql():
    # 127.0.0.1 - - [14/Oct/2018 23:03:10] "POST /graphql HTTP/1.1" 404 -

    headers = dict(request.headers)
    print(request.data)
    #payload = request.data
    print(request.json)
    payload = request.json
    print(payload)

    try:
        jdata = json.loads(request.data)
        print(jdata)
        print(jdata.keys())
        print(jdata['query'])
    except Exception as e:
        print('ERROR: %s' % e)


    qinfo = {}
    qpath = []
    qlines = jdata['query'].split('\n')
    for idl,ql in enumerate(qlines):
        # normalize
        ql = ql.replace('){', ') {')

        print('%s:: %s' % (idl,ql))

        # 1::     repository(owner:"ansible", name:"ansible") {
        if ql.rstrip().endswith('{'):
            if '(' in ql and ')' in ql:

                # repository
                qlkey = ql.lstrip().split('(')[0]
                if not qlkey:
                    continue
                qpath.append(qlkey)
                print('branch?: %s' % qlkey)

                #qinfo[qlkey] = {}
                ql = ql.strip()
                ql = ql.replace('repository(', '')
                ql = ql.replace('pullRequest(', '')
                ql = ql.replace(') {', '')

                # owner/name/etc
                parts = ql.split(',')            
                for part in parts:
                    key = part.split(':')[0].strip()
                    val = part.split(':')[-1].strip()
                    #qinfo[qlkey][key] = val

                    '''
                    print('# sending in ...')
                    print('\tpath: ' + str(qpath))
                    print('\tkey: ' + key)
                    print('\tval: ' + val)

                    print('# result ...')
                    '''
                    qinfo = dict_xpath_set(qinfo, qpath, key, val)
                    #pprint(qinfo)
                    #import epdb; epdb.st()
            elif ql.rstrip().endswith('{'):
                # new branch
                qlkey = ql.lstrip().split('{')[0]
                if not qlkey:
                    continue
                print('branch?: %s' % qlkey)
                qpath.append(qlkey)

        elif ql.rstrip().endswith('}'):
            qpath = qpath[:-1]

        elif '{' not in ql and '}' not in ql and ql.strip():
            # nodes
            node = ql.strip()
            print('node?: ' + ql)
            qinfo = dict_xpath_add(qinfo, qpath, node)


    print('# QINFO ...')
    pprint(qinfo)

    data = {}
    if 'repository' in qinfo:
        data['repository'] = {}
        if 'pullRequest' in qinfo['repository']:
            data['repository']['pullRequest'] = {}
            nodes = qinfo['repository']['pullRequest']['nodes'][:]
            if 'number' in qinfo['repository']['pullRequest']['kwargs']:
                issue = GM.get_issue(
                    'ansible',
                    'ansible',
                    qinfo['repository']['pullRequest']['kwargs']['number']
                )
                pprint(issue)
                for node in nodes:
                    node = node.replace('At', '_at')
                    data['repository']['pullRequest'][node] = issue[node.lower()]

        elif 'issues' in qinfo['repository'] or 'pullRequests' in qinfo['repository']:

            ikey = 'issues'
            if 'pullRequests' in qinfo['repository']:
                ikey = 'pullRequests'
            data['repository'][ikey] = {'edges': [] }

            issues_keys = []
            for k,v in GM.ISSUES['github'].items():
                #print(k)
                #pprint(v)
                if 'pullRequests' in qinfo['repository']:
                    if v.get('pull_request'):
                        issues_keys.append(k)
                elif not v.get('pull_request'):
                    issues_keys.append(k)

            print('# total keys: %s' % len(issues_keys))
            issues_keys = sorted(issues_keys)
            issues = []
            for ik in issues_keys:
                issue = GM.ISSUES['github'][ik]
                node = {}
                node['id'] = issue['id']
                node['url'] = issue['url']
                node['number'] = issue['number']
                node['state'] = issue['state']
                node['createdAt'] = issue['created_at']
                node['updatedAt'] = issue['updated_at']
                node['repository'] = {
                    'nameWithOwner': None
                }
                data['repository'][ikey]['edges'].append({'node': node.copy()})

        else:
            print('# UNHANDLED GRAPH ENDPOINT')

    print('# RESULT ...')
    pprint(data)
    return jsonify({'data': data})


@app.route('/repos/<path:path>', methods=['GET', 'POST'])
def repos(path):
    # http://localhost/repos/ansible/ansible/labels
    # http://localhost/repos/ansible/ansible/issues/1/comments

    path_parts = path.split('/')
    print(six.text_type((len(path_parts),path_parts)))
    print(request.path)

    if error_time():
        raise InternalServerError(None, status_code=500)

    if len(path_parts) == 2:
        print('sending repo')
        payload = {
            'name': path_parts[-1],
            'url': BASEURL + '/repos/' + path_parts[-2] + '/' + path_parts[-1],
            'full_name': '/'.join([path_parts[-2],path_parts[-1]]),
            'created_at': '2012-03-06T14:58:02Z',
            'updated_at': get_timestamp()
        }
        pprint(payload)
        return jsonify(payload)

    auth = dict(request.headers)['Authorization']
    token = auth.split()[-1]
    username = TOKENS.get(token)
    org = path_parts[0]
    repo = path_parts[1]

    if len(path_parts) == 3 and path_parts[-1] == 'assignees':
        print('sending repo assignees')
        return jsonify([])

    if len(path_parts) == 3 and path_parts[-1] == 'labels':
        print('path: %s %s' % (path_parts, len(path_parts)))
        print('sending repo labels')
        return jsonify([])

    if len(path_parts) == 5 and path_parts[-1] == 'labels':
        # [u'ansible', u'ansible', u'issues', u'1', u'labels']
        if request.method in ['POST', 'PUT', 'DELETE']:
            number = int(path_parts[3])
            labels = request.json

            print('adding label(s) %s to %s by %s' % (labels, number, username))
            for label in labels:
                if request.method == 'POST':
                    GM.add_issue_label(org, repo, number, label, username)
                elif request.method == 'DELETE':
                    GM.remove_issue_label(org, repo, number, label, username)

            return jsonify({})

    elif len(path_parts) == 5 and path_parts[-1] == 'comments':
        number = int(path_parts[3])

        if request.method == 'POST':
            print('adding comment(s) by %s' % username)
            GM.add_issue_comment(org, repo, number, request.json['body'], username)
            return jsonify({})
        else:
            comments = GM.get_issue_comments(org, repo, number)
            print('return %s comments for %s' % (len(comments), number))
            return jsonify(comments)

    elif len(path_parts) == 4 and path_parts[-2] == 'issues':
        print('sending issue')
        # [u'ansible', u'ansible', u'issues', u'1issues']
        if not path_parts[-1].isdigit():
            raise InternalServerError(None, status_code=500)
        #return jsonify(GM.get_issue(path_parts[0], path_parts[1], path_parts[-1]))
	issue = GM.get_issue(path_parts[0], path_parts[1], path_parts[-1])
        pprint(issue)
	resp = jsonify(issue)
	resp.headers['ETag'] = 'a00049ba79152d03380c34652f2cb612'
	return resp

    elif len(path_parts) == 5 and path_parts[-2] == 'comments':
        # (5, [u'ansible', u'ansible', u'issues', u'comments', u'2'])
        cid = int(path_parts[-1])
        comment = None
        for k,ev in GM.EVENTS:
            if ev['id'] == cid:
                comment = ev.copy()
                break
        print('sending comment: %s' % comment)
        return jsonify(comment)

    elif len(path_parts) == 5 and path_parts[-1] == 'events':
        number = int(path_parts[3])
        events = GM.get_issue_events(org, repo, number)
        print('sending %s events %s/%s/%s' % (len(events), org, repo, number))
        return jsonify(events)

    elif len(path_parts) == 5 and path_parts[-2] == 'events':
        # (5, [u'ansible', u'ansible', u'issues', u'events', u'3'])
        eid = int(path_parts[-1])
        event = GM.get_issue_event(org, repo, eid)
        print('# found event ...')
        pprint(event)
        return jsonify(event)

    elif len(path_parts) == 5 and path_parts[-1] == 'reactions':
        number = int(path_parts[3])
        key = (org, repo, int(number))
        events = GM.EVENTS.get(key, [])
        events = [x for x in events if x['event'] == 'reacted']
        print('sending %s reactions %s/%s/%s' % (len(events), org, repo, number))
        return jsonify(events)

    elif len(path_parts) == 2:
        return jsonify({})

    elif len(path_parts) == 4 and path_parts[-2] == 'pulls':
        # (4, [u'ansible', u'ansible', u'pulls', u'1'])
        issue = GM.get_pullrequest(path_parts[0], path_parts[1], path_parts[-1])
	resp = jsonify(issue)
	resp.headers['ETag'] = 'a00049ba79152d03380c34652f2cb612'
	return resp

    elif len(path_parts) == 4 and path_parts[-2] == 'statuses':
        status = GM.get_status(path_parts[-1])        
        return jsonify(status)

    elif len(path_parts) == 5 and path_parts[-1] == 'commits':
        return jsonify([])

    elif len(path_parts) == 5 and path_parts[-1] == 'files':
        return jsonify([])

    elif len(path_parts) == 5 and path_parts[-1] == 'reviews':
        return jsonify([])

    elif len(path_parts) == 4 and path_parts[2] == 'contents':
        return ''

    print('unhandled path for "repo" route ...')
    print(six.text_type((len(path_parts),path_parts)))


@app.route('/<path:path>', methods=['GET', 'POST'])
def abstract_path(path):
    # /ansible/ansible/issues/1

    print('# ABSTRACT PATH! - %s' % path)
    path_parts = path.split('/')
    print(six.text_type((len(path_parts),path_parts)))
    print(request.path)



if __name__ == "__main__":
    app.run(debug=True)
