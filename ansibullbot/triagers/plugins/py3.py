#!/usr/bin/env python

import logging

import six


def get_python3_facts(issuewrapper):
    '''Is the issue related to python3?'''
    iw = issuewrapper
    ispy3 = False
    py3strings = [u'python 3', u'python3', u'py3', u'py 3']

    for py3str in py3strings:

        if py3str in iw.title.lower():
            ispy3 = True
            break

        for k, v in six.iteritems(iw.template_data):
            if not v:
                continue
            if py3str in v.lower():
                ispy3 = True
                break

        if ispy3:
            break

    if ispy3:
        for comment in iw.comments:
            if u'!python3' in comment[u'body']:
                logging.info(u'!python3 override in comments')
                ispy3 = False
                break

    py3facts = {
        u'is_py3': ispy3
    }

    return py3facts
