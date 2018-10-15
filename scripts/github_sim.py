#!/usr/bin/env python

import json
import six
import time

from pprint import pprint
from flask import Flask
from flask import jsonify
from flask import request


app = Flask(__name__)


ERROR_TIMER = 0

TOKENS = {
    'AAA': 'abot'
}

ISSUES = {
    'github': {}
}

EVENTS = {}


def get_issue(org, repo, number):

    def get_labels(org, repo, number):
        labels = []
        events = EVENTS.get((org, repo, number), [])
        for event in events:
            if event['event'] == 'labeled':
                labels.append(event['label'])
            elif event['event'] == ['unlabeled']:
                labels = [x for x in labels if x['name'] != event['label']['name']]
        return labels

    key = (org, repo, number)
    if key in ISSUES:
        return ISSUES[key]

    url = 'http://localhost:5000'
    url += '/'
    url += 'repos'
    url += '/'
    url += org
    url += '/'
    url += repo
    url += '/'
    url += 'issues'
    url += '/'
    url += str(number)

    h_url = 'http://localhost:5000'
    h_url += '/'
    h_url += org
    h_url += '/'
    h_url += repo
    h_url += '/'
    h_url += 'issues'
    h_url += '/'
    h_url += str(number)

    e_url = 'http://localhost:5000'
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
        'created_at': '2018-09-12T21:14:02Z',
        'updated_at': '2018-09-12T21:24:05Z',
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

    ISSUES[key] = payload.copy()

    return payload


def add_issue_event(org, repo, number, event):
    key = (org, repo, int(number))
    if key not in ISSUES:
        get_issue(org, repo, int(number))
    if key not in EVENTS:
        EVENTS[key] = []
    EVENTS[key].append(event)


def error_time():
    global ERROR_TIMER
    print('ERROR_TIMER: %s' % ERROR_TIMER)
    ERROR_TIMER += 1
    if ERROR_TIMER >= 100:
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
    for i in range(0, 100):
        get_issue('ansbile', 'ansible', i)


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


    pprint(qinfo)

    data = {}
    if 'repository' in qinfo:
        data['repository'] = {}
        if 'pullRequest' in qinfo['repository']:
            data['repository']['pullRequest'] = {}
            nodes = qinfo['repository']['pullRequest']['nodes'][:]
            if 'number' in qinfo['repository']['pullRequest']['kwargs']:
                issue = get_issue(
                    'ansible',
                    'ansible',
                    qinfo['repository']['pullRequest']['kwargs']['number']
                )
                pprint(issue)
                for node in nodes:
                    node = node.replace('At', '_at')
                    data['repository']['pullRequest'][node] = issue[node.lower()]


    pprint(data)
    return jsonify({'data': data})


@app.route('/repos/<path:path>', methods=['GET', 'POST'])
def repos(path):
    # http://localhost/repos/ansible/ansible/labels
    # http://localhost/repos/ansible/ansible/issues/1/comments

    path_parts = path.split('/')
    print(six.text_type((len(path_parts),path_parts)))

    if error_time():
        raise InternalServerError(None, status_code=500)

    if len(path_parts) == 2:
        print('sending repo')
        return jsonify({
            'name': path_parts[-1],
            'full_name': '/'.join([path_parts[-2],path_parts[-1]]),
            'created_at': '2012-03-06T14:58:02Z',
            'updated_at': '2018-09-13T03:17:56Z'
        })

    if len(path_parts) == 3 and path_parts[-1] == 'assignees':
        print('sending repo assignees')
        return jsonify([])

    if path_parts[-1] == 'labels':
        if len(path_parts) == 5:
            # [u'ansible', u'ansible', u'issues', u'1', u'labels']
            auth = dict(request.headers)['Authorization']
            token = auth.split()[-1]
            username = TOKENS.get(token)
            org = path_parts[0]
            repo = path_parts[1]
            number = int(path_parts[3])

            labels = request.json

            print('adding label(s) %s by %s' % (labels, username))
            for label in labels:
                event = {
                    'event': 'labeled',
                    'created_at': None,
                    'updated_at': None,
                    'label': {'name': label}
                }
                if request.method != 'POST':
                    event['event'] = 'unlabeled'
                add_issue_event(org, repo, number, event)
            return jsonify({})

        else:
            print('path: %s %s' % (path_parts, len(path_parts)))
            print('sending repo labels')
            return jsonify([])

    elif path_parts[-1] == 'comments':

        auth = dict(request.headers)['Authorization']
        token = auth.split()[-1]
        username = TOKENS.get(token)
        org = path_parts[0]
        repo = path_parts[1]
        number = int(path_parts[3])

        if request.method == 'POST':
            print('adding comment(s) by %s' % username)
            event = {
                'event': 'commented',
                'created_at': None,
                'updated_at': None,
                'body': request.json['body']
            }
            add_issue_event(org, repo, number, event)
            return jsonify({})
        else:
            events = EVENTS.get((org, repo, number), [])
            comments = [x for x in events if x['event'] == 'commented']
            return jsonify(comments)

    elif len(path_parts) == 4 and path_parts[-2] == 'issues':
        print('sending issue')
        return jsonify(get_issue(path_parts[0], path_parts[1], path_parts[-1]))

    elif len(path_parts) == 5 and path_parts[-1] == 'comments':
        print('sending comments')

        return jsonify([])
    elif len(path_parts) == 5 and path_parts[-1] == 'events':
        print('sending events')
        return jsonify([])
    elif len(path_parts) == 5 and path_parts[-1] == 'reactions':
        print('sending reactions')
        return jsonify([])
    elif len(path_parts) == 2:
        return jsonify({})

    print('unhandled path ...')
    print(six.text_type((len(path_parts),path_parts)))



if __name__ == "__main__":
    app.run(debug=True)
