#!/usr/bin/env python

import logging
import lib.constants as C
import requests


def post_to_receiver(path, params, data):
    rr = None
    if C.DEFAULT_RECEIVER_HOST and data:
        receiverurl = 'http://'
        receiverurl += C.DEFAULT_RECEIVER_HOST
        receiverurl += ':'
        receiverurl += C.DEFAULT_RECEIVER_PORT
        receiverurl += '/'
        receiverurl += path
        logging.info('RECEIVER: POST to %s' % receiverurl)
        try:
            rr = requests.post(receiverurl, params=params, json=data)
        except Exception as e:
            logging.warning(e)

    if rr is not None:
        for k,v in rr.json().items():
            logging.info('RECEIVER: %s %s' % (v, k))


