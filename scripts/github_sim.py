#!/usr/bin/env python

import six
import time

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


def get_issue(org, repo, number):

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

    return {
        'assignees': [],
        'created_at': '2018-09-12T21:14:02Z',
        'updated_at': '2018-09-12T21:24:05Z',
        'url': url,
        'events_url': e_url,
        'html_url': h_url,
        'number': int(number),
        'labels': [],
        'user': {
            'login': 'foouser'
        },
        'title': 'this thing is broken',
        'body': '',
        'state': 'open'
    }


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
    elif len(path_parts) == 2 and path_parts[-1] == 'teams':
        return jsonify([])


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
        print('sending repo labels')
        return jsonify([])

    elif path_parts[-1] == 'comments':
        if request.method == 'POST':
            print('adding comment(s)')
            print(request.headers)
            print(request.data)
            '''
            {"body": "blah blah blah"}
            '''
            import epdb; epdb.st()
            return jsonify({})
        else:
            return jsonify([])

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
