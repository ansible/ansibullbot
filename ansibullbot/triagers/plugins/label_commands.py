#!/usr/bin/env python


def get_label_command_facts(issuewrapper, meta, module_indexer, core_team=[], valid_labels=[]):

    iw = issuewrapper
    add_labels = []
    del_labels = []

    wl = [
        'needs_triage',
        'test',
        'module',
        'cloud',
        'aws',
        'azure',
        'digital_ocean',
        'docker',
        'gce',
        'openstack',
        'vmware',
        'networking',
        'windows',
        'easyfix'
    ]
    wl += [x for x in valid_labels if x.startswith('affects_')]
    wl += [x for x in valid_labels if x.startswith('c:')]

    iw = issuewrapper
    maintainers = [x for x in core_team]
    maintainers += module_indexer.all_maintainers
    maintainers = sorted(set(maintainers))

    for ev in iw.history.history:
        if ev['actor'] in maintainers and ev['event'] == 'commented':
            if '+label' in ev['body'] or '-label' in ev['body']:
                for line in ev['body'].split('\n'):
                    if 'label' not in line:
                        continue
                    words = line.split()

                    label = words[1]
                    if label not in wl:
                        continue
                    action = words[0]
                    if action == '+label':
                        add_labels.append(label)
                        if label in del_labels:
                            del_labels.remove(label)
                    elif action == '-label':
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
        'label_cmds': {
            'add': add_labels,
            'del': del_labels
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
        if ev['actor'] in maintainers and ev['event'] == 'commented':
            if '!waffling' in ev.get('body', ''):
                lines = ev['body'].split('\n')
                for line in lines:
                    if line.strip().startswith('!waffling'):
                        line = line.strip()
                        parts = line.strip().split()
                        thislabel = parts[1].strip()
                        if thislabel not in overrides:
                            overrides.append(thislabel)

    fact = {
        'label_waffling_overrides': overrides
    }

    return fact
