#!/usr/bin/env python

import copy
import logging
import re

from pprint import pprint


def get_collection_facts(iw, component_matcher, meta):

    if iw.is_issue():
        is_backport = False
    else:
        is_backport = iw.pullrequest.base.ref != u'devel'

    cfacts = {
        'is_collection': False,
        # notification about collections and closure ...
        'needs_collection_boilerplate': False,
        # close it ...
        'needs_collection_redirect': False,
        'collection_redirects': [],
        'collection_filemap': {},
        'collection_file_matches': {}
    }

    cmap = {}
    for cm in meta.get(u'component_matches', []):
        if cm.get('repo_filename'):
            cmap[cm['repo_filename']] = None

    fqcns = set()
    for key in cmap.keys():
        cmap[key] = component_matcher.search_ecosystem(key)
        if cmap[key]:
            for match in cmap[key]:
                if match.startswith('collection:'):
                    fqcns.add(match.split(':')[1])

    cfacts['collection_filemap'] = copy.deepcopy(cmap)

    cfacts['collection_redirects'] = list(fqcns)
    cfacts['collection_fqcns'] = list(fqcns)
    if fqcns:
        cfacts['is_collection'] = True

    # make urls for the bot comment
    for k,v in cmap.items():
        for idi,item in enumerate(v):
            parts = item.split(':')
            cmap[k][idi] = k + ' -> ' + 'https://galaxy.ansible.com/' + parts[1].replace('.', '/')

    cfacts['collection_file_matches'] = copy.deepcopy(cmap)

    # should this be forwarded off to a collection repo?
    if list([x for x in cmap.values() if x]) and not is_backport:
        cfacts['needs_collection_redirect'] = True
        cfacts['component_support'] = ['community']

        if not iw.history.last_date_for_boilerplate('collection_migration'):
            cfacts['needs_collection_boilerplate'] = True

    pprint(cfacts)

    import epdb; epdb.st()
    return cfacts
