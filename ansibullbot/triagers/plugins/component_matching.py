#!/usr/bin/env python

import copy
import logging
import os


def find_module_match(issuewrapper, module_indexer):

    iw = issuewrapper

    match = None

    cname = iw.template_data.get('component name')
    craw = iw.template_data.get('component_raw')

    if module_indexer.find_match(cname, exact=True):
        match = module_indexer.find_match(cname, exact=True)
    elif iw.template_data.get('component_raw') \
            and ('module' in iw.title or
                 'module' in craw or
                 'action' in craw):
        # FUZZY MATCH?
        logging.info('fuzzy match module component')
        fm = module_indexer.fuzzy_match(
            title=iw.title,
            component=craw
        )
        if fm:
            match = module_indexer.find_match(fm)
    else:
        pass

    return match


def get_component_match_facts(issuewrapper, meta, file_indexer, module_indexer, valid_labels):

    iw = issuewrapper

    cmeta = {}
    cmeta['is_bad_pr'] = False
    cmeta['is_module'] = False
    cmeta['is_action_plugin'] = False
    cmeta['is_new_module'] = False
    cmeta['is_new_directory'] = False
    cmeta['is_module_util'] = False
    cmeta['is_plugin'] = False
    cmeta['is_new_plugin'] = False
    cmeta['is_core'] = False
    cmeta['is_multi_module'] = False
    cmeta['module_match'] = None
    cmeta['component'] = None
    cmeta['is_migrated'] = False
    cmeta['component_matches'] = []

    # https://github.com/ansible/ansibullbot/issues/562
    filenames = []
    if iw.is_pullrequest():
        filenames = iw.files
        checked = []
        to_add = []
        for fn in filenames:
            if fn.startswith('test/integration/targets/'):
                bn = fn.split('/')[3]
                if bn in checked:
                    continue
                else:
                    checked.append(bn)
                mmatch = module_indexer.find_match(bn)
                if mmatch:
                    to_add.append(mmatch['repo_filename'])

                '''
                # FIXME - enumerate aliases file for additional modules
                td = '/'.join(fn.split('/')[0:4])
                aliases_file = os.path.join(td, 'aliases')
                aliases = file_indexer.get_file_content(aliases_file)
                if aliases:
                    import epdb; epdb.st()
                '''

        if to_add:
            filenames = sorted(set(filenames + to_add))

    if iw.is_pullrequest():
        cmeta['component_matches'] = file_indexer.find_component_matches_by_file(filenames)
    else:
        ckeys = file_indexer.find_component_match(iw.title, iw.body, iw.template_data)
        if ckeys:
            cmeta['component_matches'] = file_indexer.find_component_matches_by_file(ckeys)

    if iw.is_issue():
        if iw.template_data.get('component name'):

            match = find_module_match(iw, module_indexer)
            if match:
                cmeta['is_module'] = True
                cmeta['is_plugin'] = True
                cmeta['module_match'] = copy.deepcopy(match)
                cmeta['component'] = match['name']

    elif len(iw.files) > 100:
        # das merge?
        cmeta['bad_pr'] = True
        cmeta['component_matches'] = []

    else:
        # assume pullrequest
        for f in iw.files:

            # creating a new dir?
            if file_indexer.isnewdir(os.path.dirname(f)):
                cmeta['is_new_directory'] = True

            if f.startswith('lib/ansible/modules/core') or \
                    f.startswith('lib/ansible/modules/extras'):
                cmeta['is_bad_pr'] = True
                continue

            if f.startswith('lib/ansible/module_utils'):
                cmeta['is_module_util'] = True
                continue

            if f.startswith('lib/ansible/plugins/action'):
                cmeta['is_action_plugin'] = True

            if f.startswith('lib/ansible') \
                    and not f.startswith('lib/ansible/modules'):
                cmeta['is_core'] = True

            if not f.startswith('lib/ansible/modules') and \
                    not f.startswith('lib/ansible/plugins/actions'):
                continue

            # duplicates?
            if cmeta['module_match']:
                # same maintainer?
                nm = module_indexer.find_match(f)
                if nm:
                    cmeta['is_multi_module'] = True
                    if nm['maintainers'] == \
                            cmeta['module_match']['maintainers']:
                        continue
                    else:
                        # >1 set of maintainers
                        logging.info('multiple modules referenced')
                        pass

            if module_indexer.find_match(f):
                match = module_indexer.find_match(f)
                cmeta['is_module'] = True
                cmeta['is_plugin'] = True
                cmeta['module_match'] = copy.deepcopy(match)
                cmeta['component'] = match['name']

            elif f.startswith('lib/ansible/modules') \
                    and (f.endswith('.py') or f.endswith('.ps1')):
                cmeta['is_new_module'] = True
                cmeta['is_module'] = True
                cmeta['is_plugin'] = True
                match = copy.deepcopy(module_indexer.EMPTY_MODULE)
                match['name'] = os.path.basename(f).replace('.py', '')
                match['filepath'] = f
                match.update(
                    module_indexer.split_topics_from_path(f)
                )

                # keep track of namespace maintainers for new mods too
                ns = match['namespace']
                match['namespace_maintainers'] = \
                    module_indexer.get_maintainers_for_namespace(ns)

                # these are "community" supported from the beginning?
                match['metadata']['supported_by'] = 'community'

                cmeta['module_match'] = copy.deepcopy(match)
                cmeta['component'] = match['name']

            elif f.endswith('.md'):
                # network/avi/README.md
                continue
            else:
                # FIXME - what do with these files?
                logging.warning('unhandled filepath for matching: %s' % f)

    # get labels for files ...
    if not iw.is_pullrequest():
        cmeta['is_issue'] = True
        cmeta['is_pullrequest'] = False
        cmeta['component_labels'] = []

        if not cmeta['is_module']:
            components = file_indexer.find_component_match(
                iw.title,
                iw.body,
                iw.template_data
            )
            cmeta['guessed_components'] = components
            if components:
                comp_labels = file_indexer.get_component_labels(
                    valid_labels,
                    components
                )
                cmeta['component_labels'] = comp_labels
            else:
                cmeta['component_labels'] = []

    else:
        cmeta['is_issue'] = False
        cmeta['is_pullrequest'] = True
        cmeta['component_labels'] = \
            file_indexer.get_component_labels(
                filenames,
                valid_labels=valid_labels
            )

    # who owns this? FIXME - is this even used?
    cmeta['owner'] = ['ansible']
    if cmeta['module_match']:
        print(cmeta['module_match'])
        maintainers = cmeta['module_match']['maintainers']
        if maintainers:
            cmeta['owner'] = maintainers
        elif cmeta['is_new_module']:
            cmeta['owner'] = ['ansible']
        else:
            logging.error('NO MAINTAINER LISTED FOR %s'
                          % cmeta['module_match']['name'])

    elif cmeta['is_pullrequest'] and cmeta['component_matches']:
        cmeta['owner'] = []
        for cmatch in cmeta['component_matches']:
            for user in cmatch['owners']:
                if user not in cmeta['owner']:
                    cmeta['owner'].append(user)
            for user in cmatch['notify']:
                if user not in cmeta['owner']:
                    cmeta['owner'].append(user)

    # if any component is core, then the whole thing is core
    if cmeta['component_matches']:
        core = False
        for cmatch in cmeta['component_matches']:
            if cmatch.get('supported_by') in ['networking', 'core']:
                core = True
                break
        cmeta['is_core'] = core

    elif not cmeta['is_module']:
        # everything else is "core"
        cmeta['is_core'] = True

    return cmeta
