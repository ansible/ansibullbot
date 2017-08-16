#!/usr/bin/env python

import logging


def get_python3_facts(issuewrapper):
    '''Is the issue related to python3?'''
    iw = issuewrapper
    ispy3 = False
    py3strings = ['python 3', 'python3', 'py3', 'py 3']

    for py3str in py3strings:

        if py3str in iw.title.lower():
            ispy3 = True
            break

        for k,v in iw.template_data.iteritems():
            if not v:
                continue
            if py3str in v.lower():
                ispy3 = True
                break

        if ispy3:
            break

    if ispy3:
        for comment in iw.comments:
            if '!python3' in comment.body:
                logging.info('!python3 override in comments')
                ispy3 = False
                break

    py3facts = {
        'is_py3': ispy3
    }

    return py3facts
