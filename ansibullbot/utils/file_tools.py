import gzip
import json

from ansibullbot._text_compat import to_bytes


def read_gzip_json_file(path):
    with gzip.open(path, 'r') as f:
        return json.loads(f.read())


def write_gzip_json_file(path, data):
    with gzip.open(path, 'w') as f:
        f.write(to_bytes(json.dumps(data)))
