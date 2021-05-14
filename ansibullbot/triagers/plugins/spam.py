import ansibullbot.constants as C


def get_spam_facts(issuewrapper):

    iw = issuewrapper

    sfacts = {
        'spam_comment_ids': set()
    }

    whitelist = [
        'boilerplate: components_banner',
        'boilerplate: notify'
    ]

    comments = iw.comments[:]
    comments = [x for x in comments if x['actor'] in C.DEFAULT_BOT_NAMES]

    cdates = {}
    cmap = {}
    for comment in comments:
        cdates[comment['id']] = comment['created_at']
        if comment['body'] not in cmap:
            cmap[comment['body']] = set()
        cmap[comment['body']].add(comment['id'])

    spamkeys = set()
    for k,v in cmap.items():
        whitelisted = False
        for wl in whitelist:
            if wl in k:
                whitelisted = True
                break
        if whitelisted:
            if len(list(v)) > 1:
                spamkeys.add(k)

    for spamkey in spamkeys:
        commentids = list(cmap[spamkey])
        commentids = sorted(commentids, key=lambda x: cdates[x])
        for cid in commentids[:-1]:
            sfacts['spam_comment_ids'].add(cid)

    sfacts['spam_comment_ids'] = list(sfacts['spam_comment_ids'])

    return sfacts
