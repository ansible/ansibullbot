# COLLECTIONS

## What is this all about?

Here are some links to read through and familiarize yourself with ...

* [Blog post about collections](https://www.ansible.com/blog/getting-started-with-ansible-collections)
* [Docs on using collections](https://docs.ansible.com/ansible/devel/user_guide/collections_using.html)
* [Docs on developing collections](https://docs.ansible.com/ansible/devel/dev_guide/developing_collections.html)
* [Docs on contributing to collections](https://docs.ansible.com/ansible/devel/community/contributing_maintained_collections.html)
* [Main ansible-collections org README](https://github.com/ansible-collections/overview/blob/master/README.rst)

## Why is ansibot directing me here?

A. You made a change or filed an issue for a plugin|module file that no longer exists in github.com:ansible/ansible.

or

B. You created a new module.

## What if ansibot made a mistake in deciding my issue or PR was for a file in a collection?

Comment "!needs_collection_redirect" in the issue and the bot will override the redirect.

## How to manually find out which collection something was moved to?

The main reference is the YAML file [lib/ansible/config/ansible_builtin_runtime.yml](https://github.com/ansible/ansible/blob/devel/lib/ansible/config/ansible_builtin_runtime.yml) - it is ansible-base's internal reference and used for backwards compatibility.

If you want to manually find out where some content was moved, simply search that file for the name of the module, plugin, or module_utils (without the file extension). For example, search for `openssl_certificate` if you want to know where `lib/ansible/modules/crypto/openssl_certificate.py` was moved to. You should find an entry looking like this:
```.yaml

    openssl_certificate:
      redirect: community.crypto.x509_certificate
```
This means that the `openssl_certificate` module is now in the `community.crypto` collection, and is called `x509_certificate` in it.

To find where the collection is hosted, you can find it on [Ansible Galaxy](https://galaxy.ansible.com/). The easiest way is to go to `https://galaxy.ansible.com/community/crypto`, with `community` and `crypto` replaced by the namespace and name of the collection, respectively. The collections should have a "Repo" and/or "Issue Tracker" link, which should guide you to the home of the collection.

## What should I do now?

1. Determine which collection+repo the file should live in now.
2. Migrate your PR or issue to the new repo

## How do I migrate my issue to another repo?

Github only allows issue migration between repos in the same organization. Most collections are in the ansible-collections org so we are unable
to migrate them automatically from ansible/ansible. The simplest approach is to just open a new issue in the new repo.

## How do I migrate my PR to another repo?

A tool exists to assist with migrating ansible/ansible PRs, but is waiting on the community team to deploy. In the meantime, you
can either recreate your PR in the new repo, or try to setup the tool on your own.

https://github.com/ansible/prmove

### Moving PRs manually

When moving PRs, you need to know that some things changed. This affects paths where content has to be placed, and Python imports that have to be changed.

The following list mentions the most important path changes, in the format "ansible/ansible path -> collection repo path". It assumes that a collection is in the root of its repository; if that's not the case (i.e. there is no directory `plugins`), you need to add more directories.

- `lib/ansible/module_utils/` → `plugins/module_utils/`
- `lib/ansible/modules/` → `plugins/modules/`
- `lib/ansible/plugins/` → `plugins/`
- `test/units/module_utils/` → `tests/unit/plugins/module_utils/`
- `test/units/modules/` → `tests/unit/plugins/modules/`
- `test/units/plugins/` → `tests/unit/plugins/`
- `test/integration/targets/` → `tests/integration/targets/`
- `test/sanity/ignore.txt` → `tests/sanity/ignore-2.*.txt`

The next list contains a mapping of Python imports. It assumes that the collection from what something is imported is called `foo.bar`.

- `import ansible.module_utils.` → `import ansible_collections.foo.bar.plugins.module_utils.`
- `import ansible.modules.` → `import ansible_collections.foo.bar.plugins.modules.` (should only happen in unit tests)
- `import ansible.plugins.` → `import ansible_collections.foo.bar.plugins.` (should only happen in unit tests)

Imports of content not moved from ansible/ansible have to stay as before. Only content moved to collections needs to be imported this way.

Finally, if your PR does deprecate an option, a feature, a module, or a plugin, there have been slight changes (in that you need to specify the collection name in some cases) as well. The syntax for all kind of deprecations is mentioned [here](https://github.com/ansible-collections/overview/issues/45#issuecomment-645619042). For modules, and in-code deprecations, `ansible-test sanity` will also tell you if you missed something.

## Why did the bot close my issue or PR?

For the reasons stated above, we will not be auto-migrating all the issues and PRs and need to take action to make sure they are being
filed in the appropriate repositories.

Pull requests do not need to be open when migrating, and there is no other reason to keep them open in the ansible/ansible repo.

## What if none of this makes sense to me?

Please reach out via the typical communication channels: https://docs.ansible.com/ansible/latest/community/communication.html
