# Ansibot Help

Making progress in resolving issues for modules depends upon your interaction! Please be sure to respond to requests or additional information as needed.

If at anytime you think this bot is misbehaving, please leave a comment of "bot_broken" and an Ansible staff member will intervene.

## For issue submitters
Please note that if you have a question about how to use this module with Ansible, that's probably something you should ask on the ansible-project mailing list, rather than submitting a bug report. For more details, please see http://docs.ansible.com/ansible/community.html#i-ve-got-a-question ."

If the module maintainer or ansibot needs further information, please respond to the request, so that you can help us to help you! 

The bot requires a minimal subset of information from the issue template 
* issue type
* component name
* ansible version
* summary

If any of those items are missing or empty, ansibot will keep the issue in a "needs info" state until the data is provided in the issue's description. The bot is expecting a structor similar to the issue template, so please use that whenever possible.


## For module maintainers
Thanks in advance for taking a look at this bug report and for your ongoing work in maintaining this module. If you are unable to troubleshoot this issue with the information provided, please ping the submitter of the issue in a comment to let them know. 

* If you need more information from the submitter, leave a comment stating needs_info and we will notify the submitter and apply the needs_info label.
* If you do not need any more information and just need time to work the issue, leave a comment with !needs_info and the needs_info label will be removed and waiting_on_maintainer will be applied.
* If, after further investigation, you believe this is not a bug, please leave a comment stating notabug, along with any additional information as to why it is not, and we will close this issue.
* If you believe this issue is resolved, please leave a comment stating bug_resolved, and we will close this issue. 
* If you believe this issue has been resolved by a pull request, please leave a comment stating resolved_by_pr, and reference the pull request # if possible. 
* If this is a bug that you can't or won't fix, please leave a comment including the word wontfix, along with any reasons why.
* If this bug or feature request is something that you want implemented but do not have the time or expertise to do, comment with needs_contributor and the issue will be but into a waiting_on_contributor state.

## For anyone else also experiencing this issue
Please leave a +1 reaction so we can determine if this issue is affecting a number of people. Any additional details you can provide, such as your environment, steps to reproduce, or workarounds you have found, can help out with resolving this issue.
