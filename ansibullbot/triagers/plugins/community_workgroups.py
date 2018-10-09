#!/usr/bin/env python


def get_community_workgroup_facts(issuewrapper, meta):

    # https://github.com/ansible/ansibullbot/issues/820

    # https://github.com/ansible/community#groups-we-help
    WORKING_GROUPS = {
        u'cloud/amazon': u'aws',
        u'cloud/azure': u'azure',
        u'cloud/linode/': u'linode',
        u'cloud/vmware': u'vmware',
        u'network/': u'network',
        u'windows/': u'windows'

    }

    iw = issuewrapper
    facts = {
        u'workgroup': None,
        u'is_maintainer': False,
        u'has_notification': False,
        u'needs_notification': False
    }

    wgroups = set()
    for cm in meta.get(u'component_matches', []):
        ns = cm.get(u'namespace')
        if ns:
            for k,v in WORKING_GROUPS.items():
                if ns.startswith(k):
                    wgroups.add(v)
                    break
    wgroups = list(wgroups)
    if len(wgroups) == 1:
        facts[u'workgroup'] = wgroups[0]

    maintainer = iw.submitter in meta[u'component_maintainers']
    if maintainer:
        facts[u'is_maintainer'] = True

    bpc = iw.history.last_date_for_boilerplate(u'community_workgroups')
    if bpc:
        facts[u'has_notification'] = True

    if not bpc and len(wgroups) == 1 and not maintainer and len(iw.comments) == 0:
        facts[u'needs_notification'] = True

    return {u'wg': facts}
