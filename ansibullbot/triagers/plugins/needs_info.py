#!/usr/bin/env python

import datetime
import logging
import pytz
import ansibullbot.constants as C


def is_needsinfo(triager, issue):

    needs_info = False

    maintainers = [x for x in triager.ansible_members]
    maintainers += [x for x in triager.ansible_core_team]

    '''
    if triager.meta.get('module_match'):
        maintainers += triager.meta['module_match'].get('maintainers', [])
        ns = triager.meta['module_match'].get('namespace')
        if ns:
            maintainers += \
                triager.module_indexer.get_maintainers_for_namespace(ns)
        if triager.meta['module_match']['authors']:
            maintainers += triager.meta['module_match']['authors']

        rfn = triager.meta['module_match']['repo_filename']
        if triager.module_indexer.committers.get(rfn):
            maintainers += triager.module_indexer.committers.get(rfn).keys()
    '''

    maintainers = sorted(
        set(
            [x for x in maintainers
                if x != u'DEPRECATED' and
                x != issue.submitter and
                x not in triager.BOTNAMES]
        )
    )

    for event in issue.history.history:

        if needs_info and \
                event[u'actor'] == issue.submitter and \
                event[u'event'] == u'commented':

            #print('%s set false' % event['actor'])
            needs_info = False
            continue

        #if event['actor'] in triager.BOTNAMES or \
        #        event['actor'] not in maintainers:
        #    continue

        # allow anyone to trigger needs_info
        if event[u'actor'] in triager.BOTNAMES:
            continue

        if event[u'event'] == u'labeled':
            if event[u'label'] == u'needs_info':
                #print('%s set true' % event['actor'])
                needs_info = True
                continue
        if event[u'event'] == u'unlabeled':
            if event[u'label'] == u'needs_info':
                #print('%s set false' % event['actor'])
                needs_info = False
                continue
        if event[u'event'] == u'commented':
            if u'!needs_info' in event[u'body']:
                #print('%s set false' % event['actor'])
                needs_info = False
                continue
            elif u'needs_info' in event[u'body']:
                #print('%s set true' % event['actor'])
                needs_info = True
                continue

    return needs_info


def needs_info_template_facts(iw, meta):

    nifacts = {
        u'template_missing': False,
        u'template_missing_sections': [],
        u'template_warning_required': False,
        u'is_needs_info': meta.get(u'is_needs_info')
    }

    if not iw.template_data:
        nifacts[u'template_missing'] = True

    itype = iw.template_data.get(u'issue type')
    missing = []

    # theoretically we only need to know the issue type for a PR
    if iw.is_pullrequest():
        expected = [u'issue type']
    else:
        expected = [u'issue type', u'ansible version', u'component name']

    for exp in expected:
        if exp not in iw.template_data:
            if itype == u'feature idea' and exp == u'ansible version':
                pass
            else:
                missing.append(exp)

    if missing:
        nifacts[u'template_missing_sections'] = missing

    if nifacts[u'template_missing'] or nifacts[u'template_missing_sections']:

        # force needs_info
        if iw.is_issue:
            nifacts[u'is_needs_info'] = True

        # trigger the warning comment
        bpcs = iw.history.get_boilerplate_comments()
        bpcs = [x[0] for x in bpcs]
        if u'issue_missing_data' not in bpcs:
            nifacts[u'template_warning_required'] = True

    return nifacts


def needs_info_timeout_facts(iw, meta):

    # warn at 30 days
    NI_WARN = int(C.DEFAULT_NEEDS_INFO_WARN)
    # close at 60 days
    NI_EXPIRE = int(C.DEFAULT_NEEDS_INFO_EXPIRE - C.DEFAULT_NEEDS_INFO_WARN)

    nif = {
        u'needs_info_action': None
    }

    if not meta[u'is_needs_info']:
        return nif

    if u'needs_info' not in iw.labels:
        return nif

    la = iw.history.label_last_applied(u'needs_info')

    # https://github.com/ansible/ansibullbot/issues/1254
    if la is None:
        # iterate and log event event in history so we can debug this problem
        for ide,event in enumerate(iw.history.history):
            logging.debug('history (%s): %s' % (ide,  event))

    lr = iw.history.label_last_removed(u'needs_info')
    ni_bpd = iw.history.last_date_for_boilerplate(u'needs_info_base')
    md_bpd = iw.history.last_date_for_boilerplate(u'issue_missing_data')

    now = pytz.utc.localize(datetime.datetime.now())

    # use the most recent date among the two templates
    bpd = None
    if not ni_bpd and md_bpd:
        bpd = md_bpd
    elif ni_bpd and not md_bpd:
        bpd = ni_bpd
    elif ni_bpd and md_bpd:
        if ni_bpd > md_bpd:
            bpd = ni_bpd
        else:
            bpd = md_bpd

    # last boilerplate was sent and after that needs_info was unlabeled, starting over...
    if lr and bpd and bpd < lr:
        bpd = None

    if bpd:
        # fix multiple warnings
        bp_comments = iw.history.get_boilerplate_comments()
        bp_comments_found = [c for c in bp_comments if c[0] == u'needs_info_base']

        try:
            delta = (now - bpd).days
        except TypeError as e:
            logging.error(e)
            import epdb; epdb.st()

        if delta >= NI_EXPIRE:
            if len(bp_comments_found) >= 1:
                nif[u'needs_info_action'] = u'close'
    else:
        delta = (now - la).days
        if delta > NI_WARN:
            nif[u'needs_info_action'] = u'warn'

    return nif
