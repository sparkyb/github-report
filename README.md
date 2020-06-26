Description
-----------

This script helps analyze GitHub repositories for a user or organization. It
fetches a list of repositories owned by a user or organization and generated a
custom report in a number of formats.

In particular, it was designed for showing the size of repositories and the LFS
storage they use. Unfortunately the GitHub API doesn't report the LFS usage,
so this tool with clone the repos in order to get the LFS size. This is slow,
but it is the primary purpose of this tool, since there's no other way to do it.

Requirements
------------

- Python 3.6+
- [requests](https://requests.readthedocs.io/en/master/)
- [GitPython](https://github.com/gitpython-developers/GitPython)
- Git
- [Git LFS](https://git-lfs.github.com/)

Local Development Setup
-----------------------

- Create a virtualenv:
  `virtualenv <path>`
- Activate your virtualenv:
  `source <path>/bin/activate` (on Linux/Mac), `source <path>/Scripts/activate`
  (in bash on Windows), or `<path>\Scripts\activate.bat` (in Windows command
  prompt)
- Use `pip install -r requirements.txt` in your virtualenv to install required
  libraries.
- Run `python github_report.py`. You may need command-line options to
  specify options. See `python github-storage-usage.py -h` for option help.

Authentication
--------------

Without authentication you can generate a report for any user's or organization's
public repos. To include private repos you will need to authenticate as a user
who has permission to see them. To do so, log into GitHub and generate a
[personal access token](https://github.com/settings/tokens) that has at least
the `repo` permission. Pass this token on the command-line to the `--token`
option, or put it in a `.token` file (or some other file that can be read with
the `--token-file` option).

