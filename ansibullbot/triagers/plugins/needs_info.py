#!/usr/bin/env python

import datetime
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
    #import epdb; epdb.st()

    maintainers = sorted(
        set(
            [x for x in maintainers
                if x != 'DEPRECATED' and
                x != issue.submitter and
                x not in triager.BOTNAMES]
        )
    )

    for event in issue.history.history:

        if needs_info and \
                event['actor'] == issue.submitter and \
                event['event'] == 'commented':

            #print('%s set false' % event['actor'])
            needs_info = False
            continue

        #if event['actor'] in triager.BOTNAMES or \
        #        event['actor'] not in maintainers:
        #    continue

        # allow anyone to trigger needs_info
        if event['actor'] in triager.BOTNAMES:
            continue

        if event['event'] == 'labeled':
            if event['label'] == 'needs_info':
                #print('%s set true' % event['actor'])
                needs_info = True
                continue
        if event['event'] == 'unlabeled':
            if event['label'] == 'needs_info':
                #print('%s set false' % event['actor'])
                needs_info = False
                continue
        if event['event'] == 'commented':
            if '!needs_info' in event['body']:
                #print('%s set false' % event['actor'])
                needs_info = False
                continue
            elif 'needs_info' in event['body']:
                #print('%s set true' % event['actor'])
                needs_info = True
                continue

    #import epdb; epdb.st()
    return needs_info


def needs_info_template_facts(iw, meta):

    nifacts = {
        'template_missing': False,
        'template_missing_sections': [],
        'template_warning_required': False,
        'is_needs_info': meta.get('is_needs_info')
    }

    if not iw.template_data:
        nifacts['template_missing'] = True

    itype = iw.template_data.get('issue type')
    missing = []

    # theoretically we only need to know the issue type for a PR
    if iw.is_pullrequest():
        expected = ['issue type']
    else:
        expected = ['issue type', 'ansible version', 'component name']

    for exp in expected:
        if exp not in iw.template_data:
            if itype == 'feature idea' and exp == 'ansible version':
                pass
            else:
                missing.append(exp)
    if missing:
        nifacts['template_missing_sections'] = missing

    if nifacts['template_missing'] or nifacts['template_missing_sections']:

        # force needs_info
        if iw.is_issue:
            nifacts['is_needs_info'] = True

        # trigger the warning comment
        bpcs = iw.history.get_boilerplate_comments()
        bpcs = [x[0] for x in bpcs]
        if 'issue_missing_data' not in bpcs:
            nifacts['template_warning_required'] = True

    return nifacts


def needs_info_timeout_facts(iw, meta):

    # warn at 30 days
    NI_WARN = int(C.DEFAULT_NEEDS_INFO_WARN)
    # close at 60 days
    NI_EXPIRE = int(C.DEFAULT_NEEDS_INFO_EXPIRE)

    nif = {
        'needs_info_action': None
    }

    if not meta['is_needs_info']:
        return nif

    if 'needs_info' not in iw.labels:
        return nif

    la = iw.history.label_last_applied('needs_info')
    ni_bpd = iw.history.last_date_for_boilerplate('needs_info_base')
    md_bpd = iw.history.last_date_for_boilerplate('issue_missing_data')
    if not ni_bpd and not md_bpd:
        return nif

    now = pytz.utc.localize(datetime.datetime.now())

    # use the most recent date among the two templates
    if not ni_bpd and md_bpd:
        bpd = md_bpd
    elif ni_bpd and not md_bpd:
        bpd = ni_bpd
    elif ni_bpd and md_bpd:
        if ni_bpd > md_bpd:
            bpd = ni_bpd
        else:
            bpd = md_bpd

    if bpd:
        delta = (now - bpd).days
    else:
        delta = (now - la).days

    if delta > NI_EXPIRE:
        nif['needs_info_action'] = 'close'
    elif delta > NI_WARN:
        nif['needs_info_action'] = 'warn'

    return nif
