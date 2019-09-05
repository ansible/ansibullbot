#!/usr/bin/env python

import pytest

from ansibullbot.utils.extractors import extract_pr_number_from_comment


@pytest.mark.parametrize('test_input,expected', [
    ('resolved_by_pr 5136', 5136),
    ('resolved_by_pr: 5136', 5136),
    ('resolved_by_pr #5136', 5136),
    ('resolved_by_pr: #5136', 5136),
    ('resolved_by_pr https://github.com/ansible/ansible/issues/5136', 5136),
    ('resolved_by_pr: https://github.com/ansible/ansible/issues/5136', 5136)
])
#@pytest.mark.parametrize('resolved_by_pr: 5136', [5136])
#@pytest.mark.parametrize('resolved_by_pr #5136', [5136])
#@pytest.mark.parametrize('resolved_by_pr: #5136', [5136])
#@pytest.mark.parametrize('resolved_by_pr https://github.com/ansible/ansible/issues/5136', [5136])
#@pytest.mark.parametrize('resolved_by_pr: https://github.com/ansible/ansible/issues/5136', [5136])
def test_extract_pr_number_from_comment(test_input, expected):
    assert extract_pr_number_from_comment(test_input) == expected
    
