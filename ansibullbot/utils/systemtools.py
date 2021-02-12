import copy
import os
import subprocess


def run_command(cmd, cwd=None, env=None):
    if env:
        _env = copy.deepcopy(dict(os.environ))
        _env.update(env)
        env = copy.deepcopy(_env)
        for k, v in env.items():
            env[k] = str(v)
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=env)
    (so, se) = p.communicate()
    return p.returncode, so, se
