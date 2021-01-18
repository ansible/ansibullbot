import gzip
import json
import os
import shutil

from ansibullbot._text_compat import to_bytes


def compress_gzip_file(path_in, path_out):
    with open(path_in) as f_in, gzip.open(path_out, 'w') as f_out:
        shutil.copyfileobj(f_in, f_out)
    os.remove(path_in)


def read_gzip_json_file(path):
    with gzip.open(path, 'r') as f:
        return json.loads(f.read())


def write_gzip_json_file(path, data):
    with gzip.open(path, 'w') as f:
        f.write(to_bytes(json.dumps(data)))
