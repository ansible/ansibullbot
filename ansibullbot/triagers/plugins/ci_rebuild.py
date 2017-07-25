#!/usr/bin/env python

'''
if self.meta['shipit_actors'] and self.meta['ci_stale']:
    ci_states = [x for x in iw.pullrequest_status if x['target_url'].startswith('https://app.shippable.com/')]
    ci_states = sorted(ci_states, key=itemgetter('created_at'))

    if ci_states and ci_states[-1]['state'] == 'success':
        target_url =  ci_states[-1]['target_url']
        match = re.match('https://app.shippable.com/github/ansible/ansible/runs/([\d]+)/summary', target_url)
        if match:
            # Trigger a new Shippable run if the PR is stalled, last run was a success and someone approved the PR
            self.SR.rebuild(match.group(1))
'''

def status_to_date_and_runid(status):
    """convert pr status to a tuple of date and runid"""

    created_at = status.get('created_at')
    target = status.get('target_url')
    if target.endswith('/summary'):
        target = target.split('/')[-2]
    else:
        target = target.split('/')[-1]
    target = int(target)
    return (created_at, target)


def get_rebuild_facts(iw, meta, shippable):

    rbmeta = {
        'needs_rebuild': False,
        'rebuild_run_number': None,
        'rebuild_run_id': None
    }

    if not meta['is_pullrequest']:
        return rbmeta

    if not meta['ci_stale']:
        return rbmeta

    if meta['is_needs_revision']:
        return rbmeta

    if meta['is_needs_rebase']:
        return rbmeta

    if meta['has_travis']:
        return rbmeta

    if not meta['has_shippable']:
        return rbmeta

    if meta['has_travis']:
        return rbmeta

    if not meta['shipit']:
        return rbmeta

    pr_status = [x for x in iw.pullrequest_status]
    ci_run_ids = [status_to_date_and_runid(x) for x in pr_status]
    ci_run_ids.sort(key=lambda x: x[0])
    last_run = ci_run_ids[-1][1]
    rbmeta['rebuild_run_number'] = last_run
    rbmeta['needs_rebuild'] = True

    return rbmeta
