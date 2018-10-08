#!/usr/bin/env python

import logging
import re


def get_component_match_facts(iw, component_matcher, valid_labels):
    '''High level abstraction for matching components to repo files'''

    # These should never return a match
    BLACKLIST_COMPONENTS = [
        u'core', u'ansible'
    ]

    cmeta = {
        u'is_module': False,
        u'is_action_plugin': False,
        u'is_new_module': False,
        u'is_new_directory': False,
        u'is_module_util': False,
        u'is_plugin': False,
        u'is_new_plugin': False,
        u'is_core': False,
        u'is_multi_module': False,
        u'module_match': None,
        u'component': None,
        u'component_name': [],
        u'component_match_strategy': None,
        u'component_matches': [],
        u'component_filenames': [],
        u'component_labels': [],
        u'component_maintainers': [],
        u'component_namespace_maintainers': [],
        u'component_notifiers': [],
        u'component_support': [],
        u'needs_component_message': False,
    }

    if iw.is_issue():
        t_component = iw.template_data.get(u'component name')
        cmeta[u'component_name'] = t_component

        if not t_component or t_component.lower() in BLACKLIST_COMPONENTS:
            if t_component is None:
                logging.debug(u'component is None')
            elif t_component.lower() in BLACKLIST_COMPONENTS:
                logging.debug(u'{} is a blacklisted component'.format(t_component))
            return cmeta

    # Check if this PR is screwed up in some way
    cmeta.update(get_pr_quality_facts(iw))
    if cmeta[u'is_bad_pr']:
        return cmeta

    # Try to match against something known ...
    CM_MATCHES = component_matcher.match(iw)
    cmeta[u'component_match_strategy'] = component_matcher.strategies

    # Reconcile with component commands ...
    if iw.is_issue():
        _CM_MATCHES = CM_MATCHES[:]
        CM_MATCHES = reconcile_component_commands(iw, component_matcher, CM_MATCHES)
        if _CM_MATCHES != CM_MATCHES:
            cmeta[u'component_match_strategy'] = [u'component_command']

    # sort so that the filenames show up in the alphabetical/consisten order
    CM_MATCHES = sorted(CM_MATCHES, key=lambda k: k[u'repo_filename'])

    cmeta[u'component_matches'] = CM_MATCHES[:]
    cmeta[u'component_filenames'] = [x[u'repo_filename'] for x in CM_MATCHES]

    # Reduce the set of labels
    for x in CM_MATCHES:
        for y in x[u'labels']:
            if y in valid_labels and y not in cmeta[u'component_labels']:
                cmeta[u'component_labels'].append(y)

    # Need to reduce the set support field ...
    cmeta[u'component_support'] = sorted(set([x[u'support'] for x in CM_MATCHES]))
    if cmeta[u'component_support'] != [u'community']:
        cmeta[u'is_core'] = True

    # Reduce the set of maintainers
    for x in CM_MATCHES:
        for y in x[u'maintainers']:
            if y not in cmeta[u'component_maintainers']:
                cmeta[u'component_maintainers'].append(y)

    # Reduce the set of namespace maintainers
    for x in CM_MATCHES:
        for y in x.get(u'namespace_maintainers', []):
            if y not in cmeta[u'component_namespace_maintainers']:
                cmeta[u'component_namespace_maintainers'].append(y)

    # Reduce the set of notifiers
    for x in CM_MATCHES:
        for y in x[u'notify']:
            if y not in cmeta[u'component_notifiers']:
                cmeta[u'component_notifiers'].append(y)

    # Get rid of those who wish to be ignored
    for x in CM_MATCHES:
        for y in x[u'ignore']:
            if y in cmeta[u'component_maintainers']:
                cmeta[u'component_maintainers'].remove(y)
            if y in cmeta[u'component_notifiers']:
                cmeta[u'component_notifiers'].remove(y)

    # is it a module ... or two?
    if [x for x in CM_MATCHES if u'lib/ansible/modules' in x[u'repo_filename']]:
        cmeta[u'is_module'] = True
        if len([x for x in CM_MATCHES if u'lib/ansible/modules' in x[u'repo_filename']]) > 1:
            cmeta[u'is_multi_module'] = True
        cmeta[u'is_plugin'] = True
        cmeta[u'module_match'] = [x for x in CM_MATCHES if u'lib/ansible/modules' in x[u'repo_filename']]

    # is it a plugin?
    if [x for x in CM_MATCHES if u'lib/ansible/plugins' in x[u'repo_filename']]:
        cmeta[u'is_plugin'] = True

    # is it a plugin?
    if [x for x in CM_MATCHES if u'lib/ansible/plugins/action' in x[u'repo_filename']]:
        cmeta[u'is_action_plugin'] = True

    # is it a module util?
    if [x for x in CM_MATCHES if u'lib/ansible/module_utils' in x[u'repo_filename']]:
        cmeta[u'is_module_util'] = True

    if iw.is_pullrequest():
        if iw.new_modules:
            cmeta[u'is_new_module'] = True
            cmeta[u'is_new_plugin'] = True

        # https://github.com/ansible/ansibullbot/issues/684
        if iw.new_files:
            for x in iw.new_files:
                if u'/plugins/' in x:
                    cmeta[u'is_new_plugin'] = True

    # welcome message to indicate which files the bot matched
    if iw.is_issue():

        if len(iw.comments) == 0:
            cmeta[u'needs_component_message'] = True

        else:

            bpcs = iw.history.get_boilerplate_comments(dates=True, content=True, botnames=[u'ansibot', u'ansibotdev'])
            bpcs = [x for x in bpcs if x[1] == u'components_banner']

            if bpcs:
                # was the last list of files correct?
                lbpc = bpcs[-1]
                lbpc = lbpc[-1]
                _filenames = []
                for line in lbpc.split(u'\n'):
                    if line.startswith(u'*'):
                        parts = line.split()
                        m = re.match(u'\[(\S+)\].*', parts[1])
                        if m:
                            _filenames.append(m.group(1))
                _filenames = sorted(set(_filenames))
                expected = sorted(set([x[u'repo_filename'] for x in CM_MATCHES]))
                if _filenames != expected:
                    cmeta[u'needs_component_message'] = True

    return cmeta


def reconcile_component_commands(iw, component_matcher, CM_MATCHES):
    """Allow components to be set by bot commands"""
    component_commands = iw.history.get_component_commands(botnames=[])
    component_filenames = [x[u'repo_filename'] for x in CM_MATCHES]

    for ccx in component_commands:

        if u'\n' in ccx[u'body']:
            lines = ccx[u'body'].split(u'\n')
            lines = [x.strip() for x in lines if x.strip()]
        else:
            lines = [ccx[u'body'].strip()]

        # keep track if files are reset in the same comment
        cleared = False

        for line in lines:

            if not line.strip().startswith(u'!component'):
                continue

            # !component [action][filename]
            try:
                filen = line.split()[1]
            except IndexError:
                filen = line.replace(u'!component', u'')

            # https://github.com/ansible/ansible/issues/37494#issuecomment-373548008
            if not filen:
                continue

            action = filen[0]
            filen = filen[1:]

            if action == u'+' and filen not in component_filenames:
                component_filenames.append(filen)
            elif action == u'-' and filen in component_filenames:
                component_filenames.remove(filen)
            elif action == u'=':
                # possibly unintuitive but multiple ='s in the same comment
                # should initially clear the set and then become additive.
                if not cleared:
                    component_filenames = [filen]
                else:
                    component_filenames.append(filen)
                cleared = True

    CM_MATCHES = component_matcher.match_components(u'', u'', u'', files=component_filenames)

    return CM_MATCHES


def get_pr_quality_facts(issuewrapper):

    '''Use arbitrary counts to prevent notification+label storms'''

    iw = issuewrapper

    qmeta = {
        u'is_bad_pr': False,
        u'is_bad_pr_reason': list(),
        u'is_empty_pr': False
    }

    if not iw.is_pullrequest():
        return qmeta

    for f in iw.files:
        if f.startswith(u'lib/ansible/modules/core') or \
                f.startswith(u'lib/ansible/modules/extras'):
            qmeta[u'is_bad_pr'] = True

    # https://github.com/ansible/ansibullbot/issues/534
    try:
        if len(iw.files) == 0:
            qmeta[u'is_bad_pr'] = True
            qmeta[u'is_empty_pr'] = True
    except:
        pass

    try:
        if len(iw.files) > 50:
            qmeta[u'is_bad_pr'] = True
            qmeta[u'is_bad_pr_reason'].append(u'More than 50 changed files.')

        if len(iw.commits) > 50:
            qmeta[u'is_bad_pr'] = True
            qmeta[u'is_bad_pr_reason'].append(u'More than 50 commits.')
    except:
        # bypass exceptions for unit tests
        pass

    return qmeta
