#!/usr/bin/env python

import os


def get_deprecation_facts(issuewrapper, meta):
    # https://github.com/ansible/ansibullbot/issues/29

    deprecated = False

    # this only handles modules for now
    if meta['is_module']:
        mmatches = meta['module_match']
        if not isinstance(mmatches, list):
            mmatches = [mmatches]
        for mmatch in mmatches:
            if mmatch.get('deprecated'):
                deprecated = True
                break

            # modules with an _ prefix are deprecated
            bn = os.path.basename(mmatch['repo_filename'])
            if bn.startswith('_') and not bn.startswith('__'):
                deprecated = True
                break

    return {'deprecated': deprecated}
