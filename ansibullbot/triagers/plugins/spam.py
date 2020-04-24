#!/usr/bin/env python


def get_spam_facts(issuewrapper, meta):

    iw = issuewrapper

    sfacts = {
        u'spam_comment_ids': set()
    }

    whitelist = [
        'boilerplate: components_banner',
        'boilerplate: notify'
    ]

    #comments = iw.load_update_fetch('comments')
    comments = iw.comments[:]
    comments = [x for x in comments if x.user.login == 'ansibot']

    cdates = {}
    cmap = {}
    for comment in comments:
        cdates[comment.id] = comment.created_at
        if comment.body not in cmap:
            cmap[comment.body] = set()
        cmap[comment.body].add(comment.id)

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
            sfacts[u'spam_comment_ids'].add(cid)

    sfacts[u'spam_comment_ids'] = list(sfacts[u'spam_comment_ids'])

    return sfacts
