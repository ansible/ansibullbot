#!/usr/bin/env python


def get_label_command_facts(issuewrapper, meta, module_indexer, core_team=[], valid_labels=[]):

    iw = issuewrapper
    add_labels = []
    del_labels = []

    namespace_labels = [
        u'aci',
        u'avi',
        u'aws',
        u'azure',
        u'cloud',
        u'cloudstack',
        u'digital_ocean',
        u'docker',
        u'f5',
        u'gce',
        u'infoblox',
        u'jboss',
        u'meraki',
        u'netapp',
        u'networking',
        u'nxos',
        u'openstack',
        u'ovirt',
        u'ucs',
        u'vmware',
        u'windows',
    ]

    whitelist = [
        u'docksite_pr',
        u'easyfix',
        u'module',
        u'needs_triage',
        u'needs_verified',
        u'test',
    ]

    whitelist += namespace_labels
    whitelist += [x for x in valid_labels if x.startswith(u'affects_')]
    whitelist += [x for x in valid_labels if x.startswith(u'c:')]
    whitelist += [x for x in valid_labels if x.startswith(u'm:')]

    iw = issuewrapper
    maintainers = [x for x in core_team]
    maintainers += module_indexer.all_maintainers
    maintainers = sorted(set(maintainers))

    for ev in iw.history.history:
        if ev[u'actor'] in maintainers and ev[u'event'] == u'commented':
            if u'+label' in ev[u'body'] or u'-label' in ev[u'body']:
                for line in ev[u'body'].split(u'\n'):
                    if u'label' not in line:
                        continue
                    words = line.split()

                    label = words[1]
                    if label not in whitelist:
                        continue
                    action = words[0]
                    if action == u'+label':
                        add_labels.append(label)
                        if label in del_labels:
                            del_labels.remove(label)
                    elif action == u'-label':
                        del_labels.append(label)
                        if label in add_labels:
                            add_labels.remove(label)

    # prevent waffling on label actions
    #   https://github.com/ansible/ansibullbot/issues/672
    managed = sorted(set(add_labels + del_labels))
    for ml in managed:
        if iw.history.label_is_waffling(ml, limit=5):
            if ml in add_labels:
                add_labels.remove(ml)
            if ml in del_labels:
                del_labels.remove(ml)

    fact = {
        u'label_cmds': {
            u'add': add_labels,
            u'del': del_labels
        }
    }

    return fact


def get_waffling_overrides(issuewrapper, meta, module_indexer, core_team=[], valid_labels=[]):

    iw = issuewrapper
    overrides = []

    iw = issuewrapper
    maintainers = [x for x in core_team]
    maintainers += module_indexer.all_maintainers
    maintainers = sorted(set(maintainers))

    for ev in iw.history.history:
        if ev[u'actor'] in maintainers and ev[u'event'] == u'commented':
            if u'!waffling' in ev.get(u'body', u''):
                lines = ev[u'body'].split(u'\n')
                for line in lines:
                    if line.strip().startswith(u'!waffling'):
                        line = line.strip()
                        parts = line.strip().split()
                        thislabel = parts[1].strip()
                        if thislabel not in overrides:
                            overrides.append(thislabel)

    fact = {
        u'label_waffling_overrides': overrides
    }

    return fact
