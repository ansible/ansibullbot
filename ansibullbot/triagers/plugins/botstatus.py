def get_bot_status_facts(issuewrapper, module_indexer, core_team=[], bot_names=[]):
    iw = issuewrapper
    bs = False
    for ev in iw.history.history:
        if ev['event'] != 'commented':
            continue
        if 'bot_status' in ev['body']:
            if ev['actor'] not in bot_names:
                if ev['actor'] in core_team or \
                        ev['actor'] == iw.submitter or \
                        ev['actor'] in module_indexer.all_maintainers:
                    bs = True
                    continue
        # <!--- boilerplate: bot_status --->
        if bs:
            if ev['actor'] in bot_names:
                if 'boilerplate: bot_status' in ev['body']:
                    bs = False
                    continue
    return {'needs_bot_status': bs}
