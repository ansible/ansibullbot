#!/usr/bin/env python

import logging
import ansibullbot.constants as C
from ansibullbot._text_compat import to_text

import requests


def post_to_receiver(path, params, data):

    if not data:
        return

    if not C.DEFAULT_RECEIVER_HOST or u'none' in C.DEFAULT_RECEIVER_HOST.lower():
        return

    rr = None
    if C.DEFAULT_RECEIVER_HOST and data:
        receiverurl = u'http://'
        receiverurl += C.DEFAULT_RECEIVER_HOST
        receiverurl += u':'
        receiverurl += to_text(C.DEFAULT_RECEIVER_PORT)
        receiverurl += u'/'
        receiverurl += path
        logging.info(u'RECEIVER: POST to %s' % receiverurl)
        try:
            rr = requests.post(receiverurl, params=params, json=data)
        except Exception as e:
            logging.warning(e)

    try:
        if rr is not None:
            for k, v in rr.json().items():
                logging.info(u'RECEIVER: %s %s' % (v, k))
    except ValueError as e:
        logging.debug(u'RECEIVER: status_code = %s' % rr.status_code)
        logging.warning(e)


def get_receiver_summaries(username, reponame, state=None, number=None):
    '''
    @app.route('/summaries', methods=['GET', 'POST'])
    def summaries():
        print('summaries!')
        print(request)

        username = request.args.get('user')
        reponame = request.args.get('repo')
        number = request.args.get('number')
    '''

    if not username or not reponame:
        return

    if not C.DEFAULT_RECEIVER_HOST or u'none' in C.DEFAULT_RECEIVER_HOST.lower():
        return

    if C.DEFAULT_RECEIVER_HOST:
        receiverurl = u'http://'
        receiverurl += C.DEFAULT_RECEIVER_HOST
        receiverurl += u':'
        receiverurl += to_text(C.DEFAULT_RECEIVER_PORT)
        receiverurl += u'/'
        receiverurl += u'summaries'
        logging.info(u'RECEIVER: GET %s' % receiverurl)

        params = {u'user': username, u'repo': reponame}
        if state:
            params[u'state'] = state

        rr = None
        try:
            rr = requests.get(
                receiverurl,
                params=params
            )
        except Exception as e:
            logging.warning(e)

        if rr:
            return rr.json()

    return None


def get_receiver_metadata(username, reponame, number=None, keys=None):
    '''
    @app.route('/metadata', methods=['GET', 'POST'])
    def metadata():
        print('metadata!')
        print(request)
        username = request.args.get('user')
        reponame = request.args.get('repo')
        number = request.args.get('number')
    '''

    if not username or not reponame:
        return

    if not C.DEFAULT_RECEIVER_HOST or u'none' in C.DEFAULT_RECEIVER_HOST.lower():
        return

    if C.DEFAULT_RECEIVER_HOST:
        receiverurl = u'http://'
        receiverurl += C.DEFAULT_RECEIVER_HOST
        receiverurl += u':'
        receiverurl += to_text(C.DEFAULT_RECEIVER_PORT)
        receiverurl += u'/'
        receiverurl += u'metadata'
        logging.info(u'RECEIVER: GET %s' % receiverurl)

        params = {u'user': username, u'repo': reponame}
        if number:
            params[u'number'] = number
        if keys:
            params[u'key'] = keys

        rr = None
        try:
            rr = requests.get(
                receiverurl,
                params=params
            )
        except Exception as e:
            logging.warning(e)

        if rr:
            return rr.json()

    return None
