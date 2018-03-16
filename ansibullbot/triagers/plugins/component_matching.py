#!/usr/bin/env python

#import copy
import logging
#import os
import re


def get_component_match_facts(issuewrapper, meta, component_matcher, file_indexer, module_indexer, valid_labels):
    '''High level abstraction for matching components to repo files'''

    # These should never return a match
    BLACKLIST_COMPONENTS = [
        'core', 'ansible'
    ]

    iw = issuewrapper

    cmeta = {}
    #cmeta['is_bad_pr'] = False
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
    #cmeta['is_migrated'] = False

    cmeta['component'] = None
    cmeta['component_name'] = []
    cmeta['component_match_strategy'] = None
    cmeta['component_matches'] = []
    cmeta['component_filenames'] = []
    cmeta['component_labels'] = []
    cmeta['component_maintainers'] = []
    cmeta['component_namespace_maintainers'] = []
    cmeta['component_notifiers'] = []
    cmeta['component_support'] = []

    cmeta['needs_component_message'] = False

    if iw.is_issue():
        t_component = iw.template_data.get('component name')
        cmeta['component_name'] = t_component

        if not t_component or t_component.lower() in BLACKLIST_COMPONENTS:
            if t_component is None:
                logging.debug('component is None')
            elif t_component.lower() in BLACKLIST_COMPONENTS:
                logging.debug('{} is a blacklisted component'.format(t_component))
            return cmeta

    # Check if this PR is screwed up in some way
    cmeta.update(get_pr_quality_facts(iw))
    if cmeta['is_bad_pr']:
        return cmeta

    # Try to match against something known ...
    CM_MATCHES = component_matcher.match(iw)
    cmeta['component_match_strategy'] = component_matcher.strategies

    # Reconcile with component commands ...
    if iw.is_issue():
        _CM_MATCHES = CM_MATCHES[:]
        CM_MATCHES = reconcile_component_commands(iw, component_matcher, CM_MATCHES)
        if _CM_MATCHES != CM_MATCHES:
            cmeta['component_match_strategy'] = ['component_command']

    # sort so that the filenames show up in the alphabetical/consisten order
    CM_MATCHES = sorted(CM_MATCHES, key=lambda k: k['repo_filename'])

    cmeta['component_matches'] = CM_MATCHES[:]
    cmeta['component_filenames'] = [x['repo_filename'] for x in CM_MATCHES]

    # Reduce the set of labels
    for x in CM_MATCHES:
        for y in x['labels']:
            if y in valid_labels and y not in cmeta['component_labels']:
                cmeta['component_labels'].append(y)

    # Need to reduce the set support field ...
    cmeta['component_support'] = sorted(set([x['support'] for x in CM_MATCHES]))
    if cmeta['component_support'] != ['community']:
        cmeta['is_core'] = True

    # Reduce the set of maintainers
    for x in CM_MATCHES:
        for y in x['maintainers']:
            if y not in cmeta['component_maintainers']:
                cmeta['component_maintainers'].append(y)

    # Reduce the set of namespace maintainers
    for x in CM_MATCHES:
        for y in x.get('namespace_maintainers', []):
            if y not in cmeta['component_namespace_maintainers']:
                cmeta['component_namespace_maintainers'].append(y)

    # Reduce the set of notifiers
    for x in CM_MATCHES:
        for y in x['notify']:
            if y not in cmeta['component_notifiers']:
                cmeta['component_notifiers'].append(y)

    # Get rid of those who wish to be ignored
    for x in CM_MATCHES:
        for y in x['ignore']:
            if y in cmeta['component_maintainers']:
                cmeta['component_maintainers'].remove(y)
            if y in cmeta['component_notifiers']:
                cmeta['component_notifiers'].remove(y)

    # is it a module ... or two?
    if [x for x in CM_MATCHES if 'lib/ansible/modules' in x['repo_filename']]:
        cmeta['is_module'] = True
        if len([x for x in CM_MATCHES if 'lib/ansible/modules' in x['repo_filename']]) > 1:
            cmeta['is_multi_module'] = True
        cmeta['is_plugin'] = True
        cmeta['module_match'] = [x for x in CM_MATCHES if 'lib/ansible/modules' in x['repo_filename']]

    # is it a plugin?
    if [x for x in CM_MATCHES if 'lib/ansible/plugins' in x['repo_filename']]:
        cmeta['is_plugin'] = True

    # is it a plugin?
    if [x for x in CM_MATCHES if 'lib/ansible/plugins/action' in x['repo_filename']]:
        cmeta['is_action_plugin'] = True

    # is it a module util?
    if [x for x in CM_MATCHES if 'lib/ansible/module_utils' in x['repo_filename']]:
        cmeta['is_module_util'] = True

    if iw.is_pullrequest():
        #cmeta['is_new_module'] = False
        #cmeta['is_new_directory'] = False
        #cmeta['is_new_plugin'] = False

        if iw.new_modules:
            cmeta['is_new_module'] = True
            cmeta['is_new_plugin'] = True

    # welcome message to indicate which files the bot matched
    if iw.is_issue():

        if len(iw.comments) == 0:
            cmeta['needs_component_message'] = True

        else:

            bpcs = iw.history.get_boilerplate_comments(dates=True, content=True, botnames=['ansibot', 'ansibotdev'])
            bpcs = [x for x in bpcs if x[1] == 'components_banner']

            if bpcs:
                # was the last list of files correct?
                lbpc = bpcs[-1]
                lbpc = lbpc[-1]
                _filenames = []
                for line in lbpc.split('\n'):
                    if line.startswith('*'):
                        parts = line.split()
                        fn = re.match('\[(\S+)\].*', parts[1]).group(1)
                        _filenames.append(fn)
                _filenames = sorted(set(_filenames))
                expected = sorted(set([x['repo_filename'] for x in CM_MATCHES]))
                if _filenames != expected:
                    cmeta['needs_component_message'] = True

    return cmeta


def reconcile_component_commands(iw, component_matcher, CM_MATCHES):
    """Allow components to be set by bot commands"""
    component_commands = iw.history.get_component_commands(botnames=[])
    component_filenames = [x['repo_filename'] for x in CM_MATCHES]

    for ccx in component_commands:

        if '\n' in ccx['body']:
            lines = ccx['body'].split('\n')
            lines = [x.strip() for x in lines if x.strip()]
        else:
            lines = [ccx['body'].strip()]

        # keep track if files are reset in the same comment
        cleared = False

        for line in lines:

            if not line.strip().startswith('!component'):
                continue

            # !component [action][filename]
            try:
                filen = line.split()[1]
            except IndexError:
                filen = line.replace('!component', '')

            # https://github.com/ansible/ansible/issues/37494#issuecomment-373548008
            if not filen:
                continue

            action = filen[0]
            filen = filen[1:]

            if action == '+' and filen not in component_filenames:
                component_filenames.append(filen)
            elif action == '-' and filen in component_filenames:
                component_filenames.remove(filen)
            elif action == '=':
                # possibly unintuitive but multiple ='s in the same comment
                # should initially clear the set and then become additive.
                if not cleared:
                    component_filenames = [filen]
                else:
                    component_filenames.append(filen)
                cleared = True

    CM_MATCHES = component_matcher.match_components('', '', '', files=component_filenames)

    return CM_MATCHES


def get_pr_quality_facts(issuewrapper):

    '''Use arbitrary counts to prevent notification+label storms'''

    iw = issuewrapper

    qmeta = {
        'is_bad_pr': False
    }

    if not iw.is_pullrequest():
        return qmeta

    for f in iw.files:
        if f.startswith('lib/ansible/modules/core') or \
                f.startswith('lib/ansible/modules/extras'):
            qmeta['is_bad_pr'] = True

    try:
        if len(iw.files) > 50:
            qmeta['is_bad_pr'] = True

        if len(iw.commits) > 50:
            qmeta['is_bad_pr'] = True
    except:
        # bypass exceptions for unit tests
        pass

    return qmeta
