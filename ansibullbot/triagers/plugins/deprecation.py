#!/usr/bin/env python

import os


def get_deprecation_facts(issuewrapper, meta):
    # https://github.com/ansible/ansibullbot/issues/29

    deprecated = False

    # this only handles modules for now
    if meta[u'is_module']:
        mmatches = meta[u'module_match']
        if not isinstance(mmatches, list):
            mmatches = [mmatches]
        for mmatch in mmatches:
            if mmatch.get(u'deprecated'):
                deprecated = True
                break

            # modules with an _ prefix are deprecated
            bn = os.path.basename(mmatch[u'repo_filename'])
            if bn.startswith(u'_') and not bn.startswith(u'__'):
                deprecated = True
                break

    return {u'deprecated': deprecated}
