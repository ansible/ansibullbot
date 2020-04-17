#!/usr/bin/env python

import copy
import json
import os


def get_collection_facts(iw, component_matcher, meta):

    if isinstance(meta.get('is_backport'), bool):
        is_backport = meta['is_backport']
    else:
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
        'collection_filemap_full': {},
        'collection_file_matches': {},
        'collection_fqcn_label_remove': set(),
    }

    cmap = {}
    for cm in meta.get(u'component_matches', []):
        if cm.get('repo_filename'):
            cmap[cm['repo_filename']] = None

    fqcns = set()
    for key in cmap.keys():
        if key in iw.renamed_files.values():
            continue
        if key in iw.renamed_files:
            continue
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
        if v is None:
            continue
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

    # loose matching for misc files ...
    if not is_backport and fqcns and 'changelog' in ''.join(cmap.keys()):
        missing = set()
        for k,v in cmap.items():
            if not k.startswith('changelogs/') and not k.startswith('test/units/') and not v:
                missing.add(k)
        if not missing:
            cfacts['needs_collection_redirect'] = True
            cfacts['component_support'] = ['community']

            if not iw.history.last_date_for_boilerplate('collection_migration'):
                cfacts['needs_collection_boilerplate'] = True

    # allow users to override the redirect
    cstatus = iw.history.command_status('needs_collection_redirect')
    if cstatus is False:
        cfacts['needs_collection_redirect'] = False
        cfacts['needs_collection_boilerplate'] = False

    # clean up incorrect labels ...
    for label in iw.labels:
        if label.startswith('collection:'):
            fqcn = label.split(':')[1]
            if fqcn not in fqcns:
                cfacts['collection_fqcn_label_remove'].add(fqcn)

    cfacts['collection_fqcn_label_remove'] = list(cfacts['collection_fqcn_label_remove'])

    return cfacts
