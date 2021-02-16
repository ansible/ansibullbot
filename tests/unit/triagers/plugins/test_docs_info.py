import pytest

from ansibullbot.triagers.plugins.docs_info import get_docs_facts
from tests.utils.issue_mock import IssueMock

datafiles = (
    {
        'id': 'docs/docsite/ changes',
        'path': 'tests/fixtures/docs_info/0_issue.yml',
        'expected_result': True
    },
    {
        'id': '.py changes: DOCUMENTATION',
        'path': 'tests/fixtures/docs_info/1_issue.yml',
        'expected_result': True
    },
    {
        'id': '.py changes: EXAMPLES',
        'path': 'tests/fixtures/docs_info/4_issue.yml',
        'expected_result': True
    },
    {
        'id': 'multiple changes: DOCUMENTATION & docs/docsite',
        'path': 'tests/fixtures/docs_info/5_issue.yml',
        'expected_result': True
    },
    {
        'id': '.py changes: non-doc/examples',
        'path': 'tests/fixtures/docs_info/2_issue.yml',
        'expected_result': False
    },
    {
        'id': 'non-doc non-.py changes',
        'path': 'tests/fixtures/docs_info/3_issue.yml',
        'expected_result': False
    },
)

def datafile_id(datafile):
    return datafile['id']

@pytest.fixture(params=datafiles, ids=datafile_id)
def iw_fixture(request):
    iw_param = {
        'issue': IssueMock(request.param['path']),
        'expects': request.param['expected_result']
    }
    return iw_param

def test_docs_facts(iw_fixture):
    iw = iw_fixture['issue']
    expects = iw_fixture['expects']

    facts = get_docs_facts(iw)
    assert facts['is_docs_only'] == expects
