import datetime
import logging

import ansibullbot.constants as C


def is_needsinfo(iw, botnames=None):
    if botnames is None:
        botnames = []
    needs_info = False

    for event in iw.history.history:
        if needs_info and \
                event['actor'] == iw.submitter and \
                event['event'] == 'commented':

            needs_info = False
            continue

        # allow anyone to trigger needs_info
        if event['actor'] in botnames:
            continue

        if event['event'] == 'labeled':
            if event['label'] == 'needs_info':
                needs_info = True
                continue
        if event['event'] == 'unlabeled':
            if event['label'] == 'needs_info':
                needs_info = False
                continue
        if event['event'] == 'commented':
            if '!needs_info' in event['body']:
                needs_info = False
                continue
            if 'needs_info' in event['body']:
                needs_info = True
                continue

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

    itype = iw.template_data.get('issue type', '')
    missing = []

    # theoretically we only need to know the issue type for a PR
    expected = ['issue type']
    if not iw.is_pullrequest():
        expected.append('component name')
        if itype.lower() not in ('feature idea', 'documentation report'):
            expected.append('ansible version')

    component_match_strategy = meta.get('component_match_strategy', []) or []
    for exp in expected:
        if exp not in iw.template_data or not iw.template_data[exp]:
            if exp == 'component name' and 'component_command' in component_match_strategy:
                continue
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
    NI_EXPIRE = int(C.DEFAULT_NEEDS_INFO_EXPIRE - C.DEFAULT_NEEDS_INFO_WARN)

    nif = {
        'needs_info_action': None
    }

    if not meta['is_needs_info']:
        return nif

    if 'needs_info' not in iw.labels:
        return nif

    la = iw.history.label_last_applied('needs_info')

    # https://github.com/ansible/ansibullbot/issues/1254
    if la is None:
        # iterate and log event event in history so we can debug this problem
        for ide,event in enumerate(iw.history.history):
            logging.debug('history (%s): %s' % (ide,  event))

    lr = iw.history.label_last_removed('needs_info')
    ni_bpd = iw.history.last_date_for_boilerplate('needs_info_base')
    md_bpd = iw.history.last_date_for_boilerplate('issue_missing_data')

    now = datetime.datetime.now(datetime.timezone.utc)

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
        bp_comments_found = [c for c in bp_comments if c[0] == 'needs_info_base']

        delta = (now - bpd).days

        if delta >= NI_EXPIRE:
            if len(bp_comments_found) >= 1:
                nif['needs_info_action'] = 'close'
            else:
                # NOTE even though NI_EXPIRE time passed, we should not close
                # because no warning has been posted so just warn.
                # This is to remedy https://github.com/ansible/ansibullbot/issues/1329.
                nif['needs_info_action'] = 'warn'
        elif delta > NI_WARN:
            if len(bp_comments_found) == 0:
                nif['needs_info_action'] = 'warn'
    else:
        delta = (now - la).days
        if delta > NI_WARN:
            nif['needs_info_action'] = 'warn'

    return nif
