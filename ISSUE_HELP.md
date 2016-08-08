
# Ansibot Help

Making progress in resolving issues for modules depends upon your interaction! Please be sure to respond to requests or additional information as needed.

If at anytime you think this bot is misbehaving, please leave a comment containing the keyword `bot_broken` and an Ansible staff member will intervene.

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

To streamline the maintenance process, we've added some commands to the ansibot that you can use to help direct the work flow. Using the automation is simply a matter of adding one of the following commands in your comments:

* **bot_broken** - Use this command if you think the ansibot is misbehaving, and an Ansible staff member will investigate.
* **needs_info** - Use this command if you need more information from the submitter. We will notify the submitter and apply the needs_info label.
* **!needs_info** - If you do not need any more information and just need time to work the issue, leave a comment that contains the command `!needs_info` and the *needs_info* label will be replaced with `waiting_on_maintainer`.
* **notabug** - If you believe this is not a bug, please leave a comment stating `notabug`, along with any additional information as to why it is not, and we will close this issue.
* **bug_resolved** - If you believe this issue is resolved, please leave a comment stating bug_resolved, and we will close this issue. 
* **resolved_by_pr** - If you believe this issue has been resolved by a pull request, please leave a comment stating `resolved_by_pr` followed by the pull request number. 
* **wontfix** - If this is a bug that you can't or won't fix, please leave a comment including the word `wontfix`, along with an explanation for why it won't be fixed.
* **needs_contributor** - If this bug or feature request is something that you want implemented but do not have the time or **expertise** to do, comment with `needs_contributor`, and the issue will be put into a `waiting_on_contributor` state.
* **dupicate_of**** - If this bug or feature request is a duplicate of another issue, comment with `dupicate_of` followed by the issue number that it duplicates, and the issue will be closed.

## For anyone else also experiencing this issue
Please leave a +1 reaction so we can determine if this issue is affecting a number of people. Any additional details you can provide, such as your environment, steps to reproduce, or workarounds you have found, can help out with resolving this issue.
