#!/usr/bin/env python


def get_contributor_facts(issuewrapper, meta, module_indexer, file_indexer, core_team=None, bot_names=None):
    cfacts = {
        'new_contributor': False
    }

    iw = issuewrapper

    if iw.is_issue():
        return cfacts

    # no bots
    if bot_names and iw.submitter in bot_names:
        return cfacts

    # ignore ansible team
    if core_team and iw.submitter in core_team:
        return cfacts

    # check commit log for user's email address(es)
    emails = sorted(set(iw.committer_emails))
    commits = file_indexer.commits_by_email(emails)
    if commits:
        return cfacts

    # check sqlite
    emails = module_indexer.get_emails_by_login(iw.submitter)
    if emails:
        return cfacts

    # module docstrings
    if iw.submitter in module_indexer.all_authors:
        return cfacts

    # botmeta
    if iw.submitter in module_indexer.all_maintainers:
        return cfacts

    # blame data
    ec = {v: k for k, v in module_indexer.emails_cache.iteritems()}
    if iw.submitter in ec:
        return cfacts

    cfacts['new_contributor'] = True

    return cfacts
