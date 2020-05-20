def get_bot_status_facts(issuewrapper, all_maintainers, core_team=[], bot_names=[]):
    iw = issuewrapper
    bs = False
    for ev in iw.history.history:
        if ev[u'event'] != u'commented':
            continue
        if u'bot_status' in ev[u'body']:
            if ev[u'actor'] not in bot_names:
                if ev[u'actor'] in core_team or \
                        ev[u'actor'] == iw.submitter or \
                        ev[u'actor'] in all_maintainers:
                    bs = True
                    continue
        # <!--- boilerplate: bot_status --->
        if bs:
            if ev[u'actor'] in bot_names:
                if u'boilerplate: bot_status' in ev[u'body']:
                    bs = False
                    continue
    return {u'needs_bot_status': bs}
