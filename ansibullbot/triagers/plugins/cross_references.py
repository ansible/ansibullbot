def get_cross_reference_facts(issuewrapper, meta):

    iw = issuewrapper

    crfacts = {
        'has_pr': False,
        'has_issue': False,
        'needs_has_pr': False,
        'needs_has_issue': False,
    }

    cross_refs = [x for x in iw.events if x['event'] == 'cross-referenced']

    urls = set()
    for cr in cross_refs:
        urls.add(cr['source']['issue']['html_url'])

    pulls = [x for x in urls if '/pull/' in x]
    issues = [x for x in urls if '/pull/' not in x]

    if iw.is_issue() and pulls:
        crfacts['has_pr'] = True
    elif iw.is_pullrequest() and issues:
        crfacts['has_issue'] = True

    if crfacts['has_pr']:
        if not iw.history.was_unlabeled('has_pr'):
            crfacts['needs_has_pr'] = True

    if crfacts['has_issue']:
        if not iw.history.was_unlabeled('has_issue'):
            crfacts['needs_has_issue'] = True

    return crfacts
