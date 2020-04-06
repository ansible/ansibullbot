#!/usr/bin/env python

import copy
import logging
import re


def get_collection_facts(iw, component_matcher, meta):

    if iw.is_issue():
        is_backport = False
    else:
        is_backport = iw.pullrequest.base.ref != u'devel'

    cfacts = {
        'is_collection': False,
        'needs_collection_redirect': False,
        'collection_redirects': [],
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

    cfacts['collection_redirects'] = list(fqcns)
    cfacts['collection_fqcns'] = list(fqcns)
    if fqcns:
        cfacts['is_collection'] = True
    cfacts['collection_file_matches'] = copy.deepcopy(cmap)

    # should this be forwarded off to a collection repo?
    if list([x for x in cmap.values() if x]) and not is_backport:
        cfacts['needs_collection_redirect'] = True
        cfacts['component_support'] = ['community']

    if cfacts['is_collection']:
        import epdb; epdb.st()

    return cfacts
