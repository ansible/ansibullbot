# -*- coding: utf-8 -*-
import io
import json

from ansibullbot._json_compat import json_dump, json_dumps


TEST_DATA = {u'їдло': u'jídlo'}
STRING_DATA = u'''
{
  "їдло": "jídlo"
}
'''.strip()


def test_json_dump_to_file(tmpdir):
    p = str(tmpdir.join('test_food_dump.json'))

    with open(p, 'w') as jf:
        json_dump(TEST_DATA, jf)

    with open(p) as jf:
        stored_data = json.load(jf)

    assert stored_data == TEST_DATA


def test_json_dump_to_stringio():
    inmemory_buffer = io.StringIO()

    json_dump(TEST_DATA, inmemory_buffer)

    inmemory_buffer.seek(0)
    stored_data = json.load(inmemory_buffer)

    inmemory_buffer.close()

    assert stored_data == TEST_DATA


def test_json_dumps(tmpdir):
    dumped_data = json_dumps(TEST_DATA)
    assert dumped_data == STRING_DATA
