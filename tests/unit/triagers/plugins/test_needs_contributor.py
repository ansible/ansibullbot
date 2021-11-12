from ansibullbot.plugins.needs_contributor import get_needs_contributor_facts


def test_needs_contributor_command():
    events = [
        {'event': 'labeled', 'label': 'needs_info', 'actor': 'mkrizek'},
        {'event': 'commented', 'body': 'Something something needs_contributor something something\n', 'actor': 'mkrizek'},
    ]

    facts = get_needs_contributor_facts(events, ['ansibot'])
    assert facts['is_needs_contributor']


def test_not_needs_contributor_command():
    events = [
        {'event': 'commented', 'body': 'Something something !needs_contributor something something\n','actor': 'mkrizek'},
    ]

    facts = get_needs_contributor_facts(events, ['ansibot'])
    assert not facts['is_needs_contributor']


def test_waiting_on_contributor_label():
    events = [
        {'event': 'labeled', 'label': 'waiting_on_contributor', 'actor': 'mkrizek'},
    ]

    facts = get_needs_contributor_facts(events, ['ansibot'])
    assert facts['is_needs_contributor']
