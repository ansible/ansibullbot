def get_performance_facts(issuewrapper):
    iw = issuewrapper

    pfacts = {
        'is_performance': False
    }

    body = ''
    try:
        body = iw.body.lower()
    except AttributeError:
        pass

    title = ''
    try:
        title = iw.title.lower()
    except AttributeError:
        pass

    # TODO search in comments too?
    for data in (body, title):
        if 'performance' in data:
            pfacts['is_performance'] = True
            break

    return pfacts
