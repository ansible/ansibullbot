import logging

import requests

import ansibullbot.constants as C


def post_to_receiver(path, params, data):
    if not data:
        return

    if not C.DEFAULT_RECEIVER_HOST or 'none' in C.DEFAULT_RECEIVER_HOST.lower():
        return

    rr = None
    if C.DEFAULT_RECEIVER_HOST and data:
        receiverurl = 'http://'
        receiverurl += C.DEFAULT_RECEIVER_HOST
        receiverurl += ':'
        receiverurl += str(C.DEFAULT_RECEIVER_PORT)
        receiverurl += '/'
        receiverurl += path
        logging.info('RECEIVER: POST to %s' % receiverurl)
        try:
            rr = requests.post(receiverurl, params=params, json=data)
        except Exception as e:
            logging.warning(e)

    try:
        if rr is not None:
            for k, v in rr.json().items():
                logging.info('RECEIVER: %s %s' % (v, k))
    except ValueError as e:
        logging.debug('RECEIVER: status_code = %s' % rr.status_code)
        logging.warning(e)


def get_receiver_summaries(username, reponame, state=None, number=None):
    '''
    @app.route('/summaries', methods=['GET', 'POST'])
    def summaries():
        username = request.args.get('user')
        reponame = request.args.get('repo')
        number = request.args.get('number')
    '''

    if not username or not reponame:
        return

    if not C.DEFAULT_RECEIVER_HOST or 'none' in C.DEFAULT_RECEIVER_HOST.lower():
        return

    if C.DEFAULT_RECEIVER_HOST:
        receiverurl = 'http://'
        receiverurl += C.DEFAULT_RECEIVER_HOST
        receiverurl += ':'
        receiverurl += str(C.DEFAULT_RECEIVER_PORT)
        receiverurl += '/'
        receiverurl += 'summaries'
        logging.info('RECEIVER: GET %s' % receiverurl)

        params = {'user': username, 'repo': reponame}
        if state:
            params['state'] = state

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
        username = request.args.get('user')
        reponame = request.args.get('repo')
        number = request.args.get('number')
    '''

    if not username or not reponame:
        return

    if not C.DEFAULT_RECEIVER_HOST or 'none' in C.DEFAULT_RECEIVER_HOST.lower():
        return

    if C.DEFAULT_RECEIVER_HOST:
        receiverurl = 'http://'
        receiverurl += C.DEFAULT_RECEIVER_HOST
        receiverurl += ':'
        receiverurl += str(C.DEFAULT_RECEIVER_PORT)
        receiverurl += '/'
        receiverurl += 'metadata'
        logging.info('RECEIVER: GET %s' % receiverurl)

        params = {'user': username, 'repo': reponame}
        if number:
            params['number'] = number
        if keys:
            params['key'] = keys

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
