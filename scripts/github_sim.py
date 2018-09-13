#!/usr/bin/env python

from flask import Flask
from flask import jsonify
from flask import request

app = Flask(__name__)


ERROR_TIMER = 0


def error_time():
    global ERROR_TIMER
    print('ERROR_TIMER: %s' % ERROR_TIMER)
    ERROR_TIMER += 1
    if ERROR_TIMER >= 10:
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
    rl = {
        'resources': {
            'core': {
                'limit': 5000,
                'remaining': 5000,
                'reset': 1536808348
            }
        },
        'rate': {
            'limit': 5000,
            'remaining': 5000,
            'reset': 1536808348
        }
    }
    return jsonify(rl)


@app.route('/orgs/<path:path>')
def orgs(path):
    path_parts = path.split('/')
    print(str((len(path_parts),path_parts)))

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


@app.route('/repos/<path:path>')
def repos(path):
    # http://localhost/repos/ansible/ansible/labels
    path_parts = path.split('/')
    print(str((len(path_parts),path_parts)))

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

    elif len(path_parts) == 4 and path_parts[-2] == 'issues':

        url = 'http://localhost:5000'
        url += '/'
        url += 'repos'
        url += '/'
        url += path_parts[0]
        url += '/'
        url += path_parts[1]
        url += '/'
        url += 'issues'
        url += '/'
        url += path_parts[-1]

        h_url = 'http://localhost:5000'
        h_url += '/'
        h_url += path_parts[0]
        h_url += '/'
        h_url += path_parts[1]
        h_url += '/'
        h_url += 'issues'
        h_url += '/'
        h_url += path_parts[-1]

        e_url = 'http://localhost:5000'
        e_url += '/'
        e_url += path_parts[0]
        e_url += '/'
        e_url += path_parts[1]
        e_url += '/'
        e_url += 'issues'
        e_url += '/'
        e_url += path_parts[-1]
        e_url += '/'
        e_url += 'events'
        #import epdb; epdb.st()

        print('sending issue')
        return jsonify({
            'assignees': [],
            'created_at': '2018-09-12T21:14:02Z',
            'updated_at': '2018-09-12T21:24:05Z',
            'url': url,
            'events_url': e_url,
            'html_url': h_url,
            'number': int(path_parts[-1]),
            'labels': [],
            'user': {
                'login': 'foouser'
            },
            'title': 'this thing is broken',
            'body': '',
            'state': 'open'
        })
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

    print(str((len(path_parts),path_parts)))



if __name__ == "__main__":
    app.run(debug=True)
