# Ansibot Help

Making progress in resolving issues for modules depends upon your interaction! Please be sure to respond to requests or additional information as needed. If at anytime you think this bot is misbehaving, please leave a comment containing the keyword [`bot_broken`](#cmd-bot_broken) and an Ansible staff member will intervene.

#### Table of contents

* [For issue submitters](#for-issue-submitters)
* [For pull request submitters](#for-pull-request-submitters)
  * [When will your pull request be merged?](#when-will-your-pull-request-be-merged)
    * [New Modules](#new-modules)
    * [Existing Modules](#existing-modules)
      * [unmaintained](#unmaintained)
      * [core](#core)
      * [curated](#curated)
      * [community](#community)
    * [Non-module changes](#non-module-changes)
* [For community maintainers](#for-community-maintainers)
* [For anyone else](#for-anyone-else)
* [Commands](#commands)
* [Labels](#labels)
  * [When to use label commands](#when-to-use-label-commands)
  * [How to use label commands](#how-to-use-label-commands)

## For issue submitters
Please note that if you have a question about how to use this feature or module with Ansible, that's probably something you should ask on the [ansible-project](https://groups.google.com/forum/#!forum/ansible-project) mailing list, rather than submitting a bug report. For more details, please see [I’ve Got A Question](http://docs.ansible.com/ansible/community.html#i-ve-got-a-question).

If the feature/module maintainer or ansibot needs further information, please respond to the request, so that you can help the devs to help you!

The bot requires a minimal subset of information from the issue template:
* issue type
* component name
* ansible version
* summary

If any of those items are missing or empty, ansibot will keep the issue in a `needs_info` state until the data is provided in the issue's description. The bot is expecting an issue description styled after the default issue template, so please use that whenever possible.

Expect the bot to do a few things:

1. Add common [labels](#labels) such as `needs_triage`, `bug_report`, `feature_idea`, etc.

   These labels are determined by templated data in the description. Please fill out the templates as accurately as possible so that the appropriate labels are used.

2. Notify and assign the maintainer(s) of the relevant file(s) or module(s).

   Notifications will happen via a comment with the `@NAME` syntax. If you know of other interested parties, feel free to ping them in a comment or in your issue description.

If you are not sure who the issue is waiting on, please use the [`bot_status`](#cmd-bot_status) command.

## For pull request submitters
Expect the bot to do a few things:

1. All of the items described in the for [issue submitters](#for-issue-submitters) section.

2. Add [labels](#labels) indicating the status of the pull request.

Please prefix your pull request's title with `WIP` if you are not yet finished making changes. This will tell the bot to ignore the [`needs_rebase`](#label-needs_rebase) and [`shipit`](#label-shipit) workflows until you remove it from the title.

If you are finished committing to your pull request or have made changes due to a request, please use the [`ready_for_review`](#cmd-ready_for_review) command.

If you are not sure who the pull request is waiting on, please use the [`bot_status`](#cmd-bot_status) command.

### When will your pull request be merged?

:information_source: `Approve` pull request status is ignored, [`shipit`](#cmd-shipit) command is used by maintainer to approve a pull request.

#### New Modules

New modules require two [`shipit`](#cmd-shipit) from module maintainers, maintainers of a module in the same namespace, or core team members before the bot will label it `shipit`. At that point, the module will be merged once a member of the Ansible organization has reviewed it and decided to include it.

:information_source: If you are a maintainer of a module in the same namespace, only one `shipit` is required.

#### Existing Modules

Module's have metadata with a [`supported_by`](http://docs.ansible.com/ansible/latest/dev_guide/developing_modules_documenting.html#ansible-metadata-block) field per the [metadata proposal](https://github.com/ansible/proposals/issues/30).

:information_source: If you have **changes to other files in the pull request**, the `supported_by` property is ignored because the Ansible core team **must** approve those changes. When other changes are line deletions in `ansible/test/*/*.txt` files, the `supported_by` property isn't ignored.

The possible values of `supported_by` are:

##### unmaintained

no community members are responsible for this module, so changes will have to be reviewed by the core team until someone volunteers to maintain it. See [core](#core).

##### core

Members of the Ansible organization typically do all the maintainence on this module, so only they can approve changes. Expect reviews to take longer than most other modules because of the volume the core team has on a daily basis.

##### curated

These modules are developed and maintained by the community, but the Ansible core team needs to approve changes. Once two or more module maintainers, maintainers of a module in the same namespace, or core team members give [`shipit`](#cmd-shipit), the core team will be alerted to review.

##### community

These modules are also developed, maintained and supported by the community. If you are a module maintainer, a maintainer of a module in the same namespace, or a core team member use the [`shipit`](#cmd-shipit) command to approve the pull request. The bot will wait for two shipits from module maintainers, maintainers of a module in the same namespace, or core team members, then automerge.

:information_source: If you are maintainer of the module or maintainer of a module in the same namespace, only one [`shipit`](#cmd-shipit) is required.

#### Non-module changes

The ansible core team approves these pull requests and it may take some time for them to get to your request.

## For community maintainers

:information_source: `Approve` pull request status is ignored, [`shipit`](#cmd-shipit) command must be used in order to approve a pull request.

Thanks in advance for taking a look at issues and pull requests and for your ongoing maintainince. If you are unable to troubleshoot or review this issue/pull request with the information provided, please ping the submitter of the issue in a comment to let them know.

## For anyone else
Reactions help us determine how many people are interested in a pull request or have run across a similar bug. Please leave a +1 [reaction](https://github.com/blog/2119-add-reactions-to-pull-requests-issues-and-comments) (:+1:) if that applies to you. Any additional details you can provide, such as your usecase, environment, steps to reproduce, or workarounds you have found, can help out with resolving issues or getting pull requests merged.

## Commands

To streamline the maintenance process, we've added some commands to the ansibot that you can use to help direct the work flow. Using the automation is simply a matter of adding one of the following commands in your comments:

Command | Scope | Allowed | Description
--- | --- | --- | ---
**<a name="cmd-bot_broken">bot_broken</a>** | issues pull requests | anyone | Use this command if you think the bot is misbehaving, and an Ansible staff member will investigate.
**<a name="cmd-bot_skip">bot_skip</a>** | issues pull requests | staff | Ansible staff members use this to have the bot skip triaging an issue.
**<a name="cmd-bot_status">bot_status</a>** | pull requests | submitters maintainers | Use this command if you would like the bot to comment with some helpful metadata about the issue.
**<a name="cmd-needs_info">needs_info</a>** | issues pull requests | maintainers past committers | Use this command if you need more information from the submitter. We will notify the submitter and apply the [`needs_info`](#label-needs_info) label.
**<a name="cmd-!needs_info">!needs_info</a>** | issues pull requests | maintainers past committers | If you do not need any more information and just need time to work the issue, leave a comment that contains the command `!needs_info` and the [`needs_info`](#label-needs_info) label will be replaced with [`waiting_on_maintainer`](#label-waiting_on_maintainer).
**<a name="cmd-needs_revision">needs_revision</a>** | pull requests | maintainers | Use this command if you would like the submitter to make changes.
**<a name="cmd-!needs_revision">!needs_revision</a>** | pull requests | maintainers | If you want to clear the [`needs_revision`](#label-needs_revision) label, use this command.
**<a name="cmd-needs_rebase">needs_rebase</a>** | pull requests | maintainers | Use this command if the submitters branch is out of date. The bot should automatically apply this label, so you may never need to use it.
**<a name="cmd-!needs_rebase">!needs_rebase</a>** | pull requests | maintainers | Clear the [`needs_rebase`](#label-needs_rebase) label.
**<a name="cmd-notabug">notabug</a>** | issues | maintainers | If you believe this is not a bug, please leave a comment stating `notabug`, along with any additional information as to why it is not, and we will close this issue.
**<a name="cmd-bug_resolved">bug_resolved</a>** | issues | maintainers | If you believe this issue is resolved, please leave a comment stating `bug_resolved`, and we will close this issue.
**<a name="cmd-resolved_by_pr">resolved_by_pr</a>** | issues | maintainers | If you believe this issue has been resolved by a pull request, please leave a comment stating `resolved_by_pr` followed by the pull request number.
**<a name="cmd-wontfix">wontfix</a>** | issues | maintainers | If this is a bug that you can't or won't fix, please leave a comment including the word `wontfix`, along with an explanation for why it won't be fixed.
**<a name="cmd-needs_contributor">needs_contributor</a>** | issues | maintainers | If this bug or feature request is something that you want implemented but do not have the time or expertise to do, comment with `needs_contributor`, and the issue will be put into a [`waiting_on_contributor`](#label-waiting_on_contributor) state.
**<a name="cmd-duplicate_of">duplicate_of</a>** | issues | maintainers | If this bug or feature request is a duplicate of another issue, comment with `duplicate_of` followed by the issue number that it duplicates, and the issue will be closed.
**<a name="cmd-close_me">close_me</a>** | issues | maintainers | If the issue can be closed for a reason you will specify in the comment, use this command.
**<a name="cmd-ready_for_review">ready_for_review</a>** | pull requests | submitters | If you are finished making commits to your pull request or have made changes due to a request, please use this command to trigger a review from the maintainer(s).
**<a name="cmd-shipit">shipit</a>** | pull requests | maintainers | If you approve of the code in this pull request, use this command to have it merged. Note that Github `Approve` pull request status is ignored, this command must be used in order to approve the pull request.
**<a name="cmd-add-label">+label</a>** | issues pull requests | staff maintainers | Add a whitelisted label. See [When to use label commands](#when-to-use-label-commands).
**<a name="cmd-remove-label">-label</a>** | issues pull requests | staff maintainers | Remove a whitelisted label. See [When to use label commands](#when-to-use-label-commands).

## Labels

The bot adds many labels on issues and pull requests.

Label | Scope | Prevent automerge | Description
--- | --- | --- | ---
**<a name="label-stale_ci">stale_ci</a>** | pull requests | yes | Added when the last CI result is older than one week.
**<a name="label-stale_review">stale_review</a>** | pull requests | no | Added when submitter made some updates after a reviewer requested some changes, if the submitter updates are older than seven days and the reviewer didn't update his review.
**<a name="label-core_review">core_review</a>** | pull requests | no | In order to be merged, these pull requests must follow the [core](#core) review workflow.
**<a name="label-community_review">community_review</a>** | pull requests no | In order to be merged, these pull requests must follow the [community](#community) review workflow.
**<a name="label-backport">backport</a>** | pull requests | no | Added to pull requests which don't target `devel` branch.
**<a name="label-c:_name_">c:_name_</a>** | issues pull requests | no | Categorize issues or pull requests by their relevant source code files.
**<a name="label-feature_pull_request">feature_pull_request</a>** | pull requests | no | Added to pull requests adding new features.
**<a name="label-bugfix_pull_request">bugfix_pull_request</a>** | pull requests | no | Added to pull requests fixing bugs.
**<a name="label-docs_pull_request">docs_pull_request</a>** | pull requests | no | Identify pull requests related to documentation.
**<a name="label-test_pull_request">test_pull_request</a>** | pull requests | no | Identify pull requests related to tests.
**<a name="label-easyfix">easyfix</a>** | issue or pull requests | no | Identify easy entrance point for people who are looking to start contributing.
**<a name="label-WIP">WIP</a>** | pull requests | yes | Identify pull requests which are not ready (from the submitter point of view) to be merged.
**<a name="label-ci_verified">ci_verified</a>** | pull requests | yes | Identify pull requests for which CI failed. A pull request must successfully pass CI in order to be merged.
**<a name="label-needs_info">needs_info</a>** | issues | N/A | Identify issues for which reviewer requested further information.
**<a name="label-waiting_on_contributor">waiting_on_contributor</a>** | issues pull requests | Identify issues for which help is needed
**<a name="label-needs_revision">needs_revision</a>** | pull requests | yes | Used for pull request which fail continuous integration tests or if a maintainer has requested a review/revision of the code. This label can be cleared by fixing any failed tests or by commenting [`ready_for_review`](#cmd-ready_for_review).
**<a name="label-needs_rebase">needs_rebase</a>** | pull requests | yes | Pull requests which are out of sync with ansible/ansible's `devel` branch. Please review the [rebase guide](http://docs.ansible.com/ansible/dev_guide/developing_rebasing.html) for further information.
**<a name="label-needs_triage">needs_triage</a>** | issues pull requests | no | This label will be added if your issue is being labeled for the first time. We (ansible staff and maintainers) use this label to find issues that need a human first touch. We'll remove it once we've given the issue a quick look for any labeling problems or missing data.
**<a name="label-filament">filament</a>** | pull requests | no | Identify pull requests related to [Ansible Lightbulb](https://github.com/ansible/lightbulb) project.
**<a name="label-owner_pr">owner_pr</a>** | pull requests | no | Identify pull requests made by module maintainers.
**<a name="label-shipit">shipit</a>** | pull requests | no | Identify pull requests for which the required number of `shipit` has been reached. For [community](#community) reviewed pull requests, if `automerge` workflow applies, then pull request should be automatically merged. For all other cases, merge should be performed by a core team members. If your pull request gets no comment and becomes tagged with [`stale_review`](#label-stale_review), you can add it to the [IRC core team meeting agenda](https://github.com/ansible/community/blob/master/meetings/core-team.yaml) to receive more comments.
**<a name="label-automerge">automerge</a>** | pull requests | no | Identify pull requests automatically merged by the bot.
**<a name="label-bot_broken">bot_broken</a>** | pull requests | no | Allow to identify pull requests for which [`bot_broken`](#cmd-bot_broken) had been used.

Some labels are used to categorize issues and pull requests:

* [Working group](https://github.com/ansible/community/wiki) labels:
  * `aws`
  * `vmware`
  * `networking`
  * `test`
* Category labels:
  * `azure`
  * `cloud`
  * `digital_ocean`
  * `docker`
  * ̀`gce`
  * `openstack`

### When to use label commands

The `+label` and `-label` commands are restricted to a subset of available labels and are not meant to replace the other bot commands:

* `needs_triage` - a human being still needs to validate the issue is properly labeled and has all the information required.
* `module` - classifies the issue as a module related issue.
* `affects_X.Y` - indicates that the issue is relevant to a particular ansible *major.minor* version.
* `easyfix` - a maintainer has decided that this is a trivial fix that new contributors would be able to tackle.
* `c:...` - these labels categorize issues or pull requests by their relevant source code files.
* `easyfix` - indicates that the issue an easy entrance point for people who are looking to start contributing.
* Working group and category labels

### How to use label commands

To use the commands, please type the the command and label on one line each in a comment.
Example:
```
-label needs_triage
+label cloud
+label gce
```
