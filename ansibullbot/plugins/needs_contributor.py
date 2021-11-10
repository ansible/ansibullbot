def get_needs_contributor_facts(issuewrapper, botnames=None):
    if botnames is None:
        botnames = []
    needs_contributor = False

    for event in issuewrapper.history.history:
        if event['actor'] in botnames:
            continue

        if event['event'] == 'labeled':
            if event['label'] in ['needs_contributor', 'waiting_on_contributor']:
                needs_contributor = True
                continue

        if event['event'] == 'unlabeled':
            if event['label'] == ['needs_contributor', 'waiting_on_contributor']:
                needs_contributor = False
                continue

        if event['event'] == 'commented':
            if '!needs_contributor' in event['body']:
                needs_contributor = False
                continue

            if 'needs_contributor' in event['body'] and '!needs_contributor' not in event['body']:
                needs_contributor = True
                continue

    return {'is_needs_contributor': needs_contributor}
