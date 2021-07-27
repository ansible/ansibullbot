# Contribution Tips

## Who is this document for?

Anyone who wants to write a patch for the bot

## Development Setup

### Config files

1. `~/.ansibullbot.cfg` The bot needs this file primarily to get it's gitub api tokens. An example is located in https://github.com/ansible/ansibullbot/blob/devel/examples/ansibullbot.cfg
2. `~/.ansibullbot` This directory is where the bot writes all the pickle and json and checkouts it uses.

### Caching and RateLimiting

A repo as large as https://github.com/ansible/ansible has so many tickets that it is literally impossible to simply fetch them all, compute a state and then apply changes. The remedy is to cache everything possible and use [conditional requests](https://developer.github.com/v3/#conditional-requests) wherever possible. Even with caching and conditional requests, you will still find undocument rate limits such as IP throttling and random 500 ISEs. To remedy that, we have a [RateLimited decorator](https://github.com/ansible/ansibullbot/blob/devel/ansibullbot/decorators/github.py#L109). The decorator is the result of years of trial and error and constant hacking around.

#### Test Proxy

A [proxy](https://github.com/jctanner/github-test-proxy) was created to assist with testing new ansibot changes across a large set of tickets. Typically, the way it's used is to invoke the bot with environment vars to override the github url used by all the underlying requestors...


```
# starting the proxy ...
git clone https://github.com/jctanner/github-test-proxy
cd github-test-proxy
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. bin/github-test-proxy --help
PYTHONPATH=. bin/github-test-proxy proxy --debug --token=<GITHUBAPITOKEN> --shippable_token=<SHIPPABLETOKEN> --fixtures=/tmp/gproxy/fixtures --deltas=/tmp/gproxy/deltas
```


```
# starting the bot ...
ANSIBULLBOT_GITHUB_URL=http://localhost:5000 \
ANSIBULLBOT_SHIPPABLE_URL=http://localhost:5000 \
./triage_ansible.py <args>`
```

With that setup, every request will cache to disk and subsequent runs will be much faster.


## Testing Philosophy

A lot of painstaking work has gone into the unit, component and integration tests in this project. We continue to strive for good test coverage. However, there are so many edgecases when dealing with the github api and the "fuzzy" nature of text analysis. To be absolutely sure your change has the desired effect, you should run the bot against LOTs of issues, if not ALL the issues. On top of that, you need to run it multiple times against some test issues to ensure the behavior is idempotent. A component test exists to check for idempotency, but it is fairly complex and can't be considered a gaurantee even if it passes.
