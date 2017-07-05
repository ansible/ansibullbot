#!/usr/bin/env python


def automergeable(meta, issuewrapper):
    '''Can this be automerged?'''
    issue = issuewrapper

    # https://github.com/ansible/ansibullbot/issues/430
    if meta['is_backport']:
        return False

    if issue.wip:
        return False

    if meta['merge_commits']:
        return False

    if meta['has_commit_mention']:
        return False

    if meta['is_needs_revision']:
        return False

    if meta['is_needs_rebase']:
        return False

    if meta['is_needs_info']:
        return False

    if not meta['has_shippable']:
        return False

    if meta['has_travis']:
        return False

    if not meta['mergeable']:
        return False

    if len(issue.files) > 1:
        return False

    if meta['is_new_module']:
        return False

    if not meta['is_module']:
        return False

    if not meta['module_match']:
        return False

    metadata = meta['module_match']['metadata']
    supported_by = metadata.get('supported_by')
    if supported_by != 'community':
        return False

    return True


def needs_community_review(meta, issue):
    '''Notify community for more shipits?'''

    if not meta['is_new_module']:
        return False

    if meta['shipit']:
        return False

    if meta['is_needs_revision']:
        return False

    if meta['is_needs_rebase']:
        return False

    if meta['is_needs_info']:
        return False

    if meta['ci_state'] == 'pending':
        return False

    if not meta['has_shippable']:
        return False

    if meta['has_travis']:
        return False

    if not meta['mergeable']:
        return False

    mm = meta.get('module_match', {})
    if not mm:
        return False

    metadata = mm.get('metadata') or {}
    supported_by = metadata.get('supported_by')

    if supported_by != 'community':
        return False

    # expensive call done earlier in processing
    if not meta['notify_community_shipit']:
        return False

    return True
