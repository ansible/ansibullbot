#!/usr/bin/env python


def get_backport_facts(issuewrapper, meta):
    # https://github.com/ansible/ansibullbot/issues/367

    iw = issuewrapper

    bfacts = {
        'is_backport': False
    }

    if not iw.is_pullrequest():
        return bfacts

    if iw.pullrequest.base.ref != 'devel':
        bfacts['is_backport'] = True
        bfacts['base_ref'] = iw.pullrequest.base.ref

    return bfacts
