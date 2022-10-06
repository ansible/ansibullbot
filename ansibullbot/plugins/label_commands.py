def get_label_command_facts(iw, all_maintainers, maintainer_team=None, valid_labels=None):
    if valid_labels is None:
        valid_labels = []
    if maintainer_team is None:
        maintainer_team = []

    whitelist = [
        'docsite_pr',
        'easyfix',
        'module',
        'needs_triage',
        'needs_verified',
        'test',
        'networking',
        'windows',
    ]
    whitelist.extend([x for x in valid_labels if x.startswith(('affects_', 'c:', 'm:'))])

    maintainers = set(maintainer_team).union(all_maintainers)

    add_labels = []
    del_labels = []
    # iterate through the description and comments and look for label commands
    for ev in iw.history.history:
        if ev['actor'] in maintainers and ev['event'] == 'commented':
            if '+label' in ev['body'] or '-label' in ev['body']:
                for line in ev['body'].split('\n'):
                    if 'label' not in line:
                        continue
                    words = line.split()

                    # https://github.com/ansible/ansibullbot/issues/1284
                    if len(words) < 2:
                        continue

                    label = words[1]
                    if label not in whitelist:
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
    for ml in sorted(set(add_labels + del_labels)):
        if iw.history.label_is_waffling(ml, limit=5):
            if ml in add_labels:
                add_labels.remove(ml)
            if ml in del_labels:
                del_labels.remove(ml)

    return {
        'label_cmds': {
            'add': add_labels,
            'del': del_labels
        }
    }


def get_waffling_overrides(iw, all_maintainers, maintainer_team=None):
    if maintainer_team is None:
        maintainer_team = []

    maintainers = set(maintainer_team).union(all_maintainers)
    overrides = []
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

    return {
        'label_waffling_overrides': overrides
    }
