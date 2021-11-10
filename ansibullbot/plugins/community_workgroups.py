def get_community_workgroup_facts(issuewrapper, meta):
    # https://github.com/ansible/ansibullbot/issues/820
    # https://github.com/ansible/community#groups-we-help
    WORKING_GROUPS = {
        'cloud/amazon': 'aws',
        'cloud/azure': 'azure',
        'cloud/linode/': 'linode',
        'cloud/vmware': 'vmware',
        'network/': 'network',
        'windows/': 'windows'

    }

    iw = issuewrapper
    facts = {
        'workgroup': None,
        'is_maintainer': False,
        'has_notification': False,
        'needs_notification': False
    }

    wgroups = set()
    for cm in meta.get('component_matches', []):
        ns = cm.get('namespace')
        if ns:
            for k,v in WORKING_GROUPS.items():
                if ns.startswith(k):
                    wgroups.add(v)
                    break
    wgroups = list(wgroups)
    if len(wgroups) == 1:
        facts['workgroup'] = wgroups[0]

    maintainer = iw.submitter in meta['component_maintainers']
    if maintainer:
        facts['is_maintainer'] = True

    bpc = iw.history.last_date_for_boilerplate('community_workgroups')
    if bpc:
        facts['has_notification'] = True

    if not bpc and len(wgroups) == 1 and not maintainer and len(iw.comments) == 0:
        facts['needs_notification'] = True

    return {'wg': facts}
