#!/usr/bin/env python

"""Generates a report of repositories for a GitHub user or organization."""

import argparse
import collections
import csv
import functools
import json
import locale
import logging
import operator
import os
import os.path
import re
import shutil
import stat
import sys
import tempfile
import urllib.parse

import dateutil.parser
import dateutil.tz
import git
import humanize
import requests
from tabulate import tabulate


locale.setlocale(locale.LC_ALL, '')


def fetch_repos(user=None, organization=None, repo=None, access_token=None):
  """Gets the metadata about the list of repositories.

  Args:
    user: The GitHub username of the user whose repositories should be analyzed.
        Must be mutually exclusive with `organization`. If neither is specified
        the user associated with the `access_token` will be implied.
    organization: A GitHub organization name to analyze. Must be mutually
        exclusive with `user`.
    repo: The name of a specific repository to analyze. This can be specified
        as `<user>/<repo>` or `<organization>/<repo>` in which case the `user`
        or `organization` should match (or be left unspecified). If no user or
        organization is specified in this property, the `user` or `organization`
        will be used.
    access_token: A GitHub personal access token (or OAuth token) to
        authenticate a user. If unspecified, only public repos will be analyzed
        (and an explicit user or organization must be specified).
  Returns:
    A list of repository metadata dictionaries.
  """
  if user and organization:
    raise ValueError('Specify either a user or organization, not both.')
  headers = {}
  if access_token:
    headers['Authorization'] = 'token {}'.format(access_token)
  if repo:
    if '/' in repo:
      owner, repo = repo.split('/')
      if (user or organization) and owner != (user or organization):
        raise ValueError(
            'Specified repo owner doesn\'t match user/organization')
    else:
      owner = user or organization
    if owner is None:
      logging.debug('Fetching GitHub username...')
      r = requests.get('https://api.github.com/user', headers=headers)
      r.raise_for_status()
      owner = r.json()['login']
    url = '/repos/{}/{}'.format(owner, repo)
  else:
    if user:
      url = '/users/{}/repos'.format(user)
    elif organization:
      url = '/orgs/{}/repos'.format(organization)
    else:
      url = '/user/repos'
  url = urllib.parse.urljoin('https://api.github.com/', url)
  logging.debug('Fetching repo meta data from {}...'.format(url))
  r = requests.get(url, headers=headers)
  r.raise_for_status()
  repos = r.json()
  if repo:
    repos = [repos]
  return repos


def get_lfs_usage(repo):
  """Gets the total size of all LFS files for a repo.

  This will clone the repo to a temp directory and run git lfs ls-files.

  Args:
    repo: The repository metadata dictionary.
  Returns:
    The total LFS size in bytes.
  """
  tempdir = tempfile.TemporaryDirectory()
  try:
    g = git.Git(tempdir.name)
    logging.info('Cloning {}...'.format(repo['clone_url']))
    g.clone(repo['clone_url'], '.', bare=True)
    logging.debug('Summing LFS file sizes...')
    lfs_files = g.lfs('ls-files', insert_kwargs_after='ls-files', all=True,
                      deleted=True, debug=True)
    return sum(map(int, re.findall(r'^\s*size:\s*(\d+)\s*$', lfs_files, re.M)))
  finally:
    def on_rm_error(func, path, exc_info):
      os.chmod(path, stat.S_IWRITE)
      os.remove(path)
    shutil.rmtree(tempdir.name, onerror=on_rm_error)
    try:
      tempdir.cleanup()
    except FileNotFoundError:
      pass
    except:
      logging.debug('Error cleaning up temp dir: {}'.format(tempdir.name),
                    exc_info=True)


FIELD_ALIASES = {
    'owner': 'owner__login',
    'forks': 'forks_count',
    'stars': 'startgazers_count',
    'watchers': 'watchers_count',
    'subscribers': 'subscribers_count',
    'open_issues': 'open_issues_count',
    'pushed': 'pushed_at',
    'created': 'created_at',
    'updated': 'updated_at',
}


def humanize_datetime(datetime_str):
  """Parses a datetime string and then formats it.

  Args:
    datetime_str: A datetime string in ISO format.
  Returns:
    A locale formatted datetime string.
  """
  dt = dateutil.parser.isoparse(datetime_str)
  dt = dt.astimezone(dateutil.tz.tzlocal())
  return dt.strftime('%x %X')


HUMANIZE = {
    'size': lambda size: humanize.naturalsize(size * 1024, binary=True,
                                              format='%.2f'),
    'lfs': functools.partial(humanize.naturalsize, binary=True, format='%.2f'),
    'forks_count': humanize.intcomma,
    'startgazers_count': humanize.intcomma,
    'watchers_count': humanize.intcomma,
    'subscribers_count': humanize.intcomma,
    'open_issues_count': humanize.intcomma,
    'pushed_at': humanize_datetime,
    'created_at': humanize_datetime,
    'updated_at': humanize_datetime,
}


DEFAULT_FIELDS = {
    'table': [
        'name',
        'size',
        'lfs',
    ],
    'list': [
        'name',
        'size',
        'lfs',
    ],
    'csv': [
        'owner',
        'name',
        'description',
        'created',
        'updated',
        'pushed',
        'forks',
        'stars',
        'watches',
        'subscribers',
        'size',
        'lfs',
    ]
}


def sort_key(field):
  """Gets a sort key function for a field.

  Args:
    field: The field to sort on.
  Returns:
    A key function.
  """
  if field.startswith('-'):
    field = field[1:]
  def key_func(obj):
    if '__' in field:
      value = obj
      for key in field.split('__'):
        if value is None:
          break
        value = value.get(key, None)
    elif (field in FIELD_ALIASES and
          (field not in obj or isinstance(obj[field], dict))):
      value = obj
      for key in FIELD_ALIASES[field].split('__'):
        if value is None:
          break
        value = value.get(key, None)
    else:
      value = obj.get(field, None)
    return value
  return key_func


def get_fields(fields, format='list', multi_owners=False, lfs=False):
  """Gets a list of fields based on the format.

  Args:
    fields: A manual list of fields to use or None to use format-specific
        defaults. If it is a string it will be split on commas.
    format: The output format. Used to determine default fields.
    multi_owners: Whether there are going to be repos by different owners.
    lfs: Whether LFS parsing was done. If not, the `lfs` field will be removed
        from defaults.
  Returns:
    A cleaned list of fields.
  """
  if fields is None:
    if format == 'json':
      return None
    else:
      fields = DEFAULT_FIELDS[format]
      if not lfs and 'lfs' in fields:
        fields = [field for field in fields if field != 'lfs']
      if (multi_owners and 'owner' not in fields and 'full_name' not in fields):
        fields = ['full_name' if field == 'name' else field for field in fields]
  elif isinstance(fields, str):
    fields = fields.split(',')

  if not lfs and 'lfs' in fields:
    logging.warning('lfs included in fields but --lfs not specified')

  return fields


def format_repo(repo, fields, format='list', humanize=False, totals=None):
  """Gets a formatted dictionary with select fields for a repo.

  Args:
    repo: The full repository metadata dictionary.
    fields: A list of fields to output. This should be cleaned by `get_fields`.
        Fields can use aliases and can dig into sub-objects with __ notation.
    format: The output format. This is used to handle some JSON special cases.
    humanize: Convert select fields to human-readable formats.
    totals: If a dictionary, it will be used to store sums of numeric fields.
  Returns:
    A dictionary with only select field keys and string values.
  """
  if fields is None and format == 'json':
    fields = list(repo.keys())

  ret = collections.OrderedDict()

  for field in fields:
    if '__' in field:
      value = repo
      for key in field.split('__'):
        if value is None:
          break
        value = value.get(key, None)
    elif (field in FIELD_ALIASES and
          (field not in repo or (format != 'json' and
                                 isinstance(repo[field], dict)))):
      value = repo
      for key in FIELD_ALIASES[field].split('__'):
        if value is None:
          break
        value = value.get(key, None)
    else:
      value = repo.get(field, None)

    if isinstance(totals, dict) and isinstance(value, (int, float)):
      totals[field] = totals.get(field, 0) + value

    if (humanize and value is not None and
        FIELD_ALIASES.get(field, field) in HUMANIZE):
      value = HUMANIZE[FIELD_ALIASES.get(field, field)](value)

    if format == 'csv':
      value = str(value) if value is not None else ''
    ret[field] = value

  return ret


def main():
  parser = argparse.ArgumentParser(add_help=False)
  parser.add_argument('-u', '--user', help='User to analyze')
  parser.add_argument('-o', '--organization', help='Organization to analyze')
  parser.add_argument('-r', '--repo', help='Repository to analyze')
  parser.add_argument('-t', '--token', help='Personal access token')
  parser.add_argument('--token-file', default='.token',
                      help='File to load personal access token from, if '
                          '--token isn\'t specified (default: %(default)s)')
  parser.add_argument('--lfs', action='store_true',
                      help='Clone repo to calculate LFS usage')
  parser.add_argument('-s', '--sort', default='full_name',
                      help='Repository metadata field to sort by. Prefix with '
                      '- to sort descending. (default: %(default)s)'),
  parser.add_argument('--fields', metavar='FIELD[,FIELD...]',
                      help='Comma-separated list of fields to show')
  parser.add_argument('-h', '--humanize', action='store_true',
                      help='Convert certain fields to human-readable format')
  parser.add_argument('--totals', action='store_true',
                      help='Generate totals row')
  parser.add_argument('-f', '--format', choices=('list', 'table', 'json', 'csv'),
                      default='list',
                      help='Format the output as a list, table, json, or csv '
                          '(default: %(default)s)')
  parser.add_argument('-c', '--csv', action='store_const', dest='format',
                      const='csv', help='Output as CSV')
  parser.add_argument('-j', '--json', action='store_const', dest='format',
                      const='json', help='Output as JSON')
  parser.add_argument('-l', '--log', action='store', metavar='FILE',
                      help='Log output to a file')
  parser.add_argument('-v', '--verbose', action='count', default=1,
                      help='Increase verbosity.')
  parser.add_argument('-q', '--quiet', action='count', default=0,
                      help='Decrease verbosity.')
  parser.add_argument('--help', action='help')

  args = parser.parse_args()

  args.verbose -= args.quiet

  console = logging.StreamHandler()
  console.setFormatter(logging.Formatter('%(levelname)-8s %(message)s'))
  console.setLevel(logging.WARNING)
  logging.getLogger().addHandler(console)
  if args.verbose >= 2:
    console.setLevel(logging.DEBUG)
  elif args.verbose >= 1:
    console.setLevel(logging.INFO)
  else:
    console.setLevel(logging.WARNING)
  logging.getLogger().addHandler(console)

  if args.log:
    logfile = logging.FileHandler(args.log, 'w')
    logfile.setLevel(logging.DEBUG)
    logfile.setFormatter(
        logging.Formatter('%(asctime)s %(levelname)-8s %(message)s'))
    logging.getLogger().addHandler(logfile)

  logging.getLogger().setLevel(logging.DEBUG)
  logging.captureWarnings(True)

  if not args.token and args.token_file and os.path.exists(args.token_file):
    logging.debug('Reading token from {}...'.format(args.token_file))
    with open(args.token_file) as fp:
      args.token = fp.read().strip()

  repos = fetch_repos(user=args.user, organization=args.organization,
                      repo=args.repo, access_token=args.token)

  if args.lfs:
    for repo in repos:
      try:
        repo['lfs'] = get_lfs_usage(repo)
      except:
        logging.exception('Error getting LFS usage for {}'.format(
            repo['full_name']))

  repos.sort(key=sort_key(args.sort), reverse=args.sort.startswith('-'))

  multi_owners = len(set(repo['owner']['login'] for repo in repos)) > 1

  fields = get_fields(args.fields, format=args.format,
                      multi_owners=multi_owners, lfs=args.lfs)

  id_field = 'full_name' if multi_owners else 'name'
  if fields is not None:
    for field in ('full_name', 'name'):
      if field in fields:
        id_field = field
        break
    else:
      fields.insert(0, id_field)

  totals = {id_field: 'Totals'} if args.totals else None

  formatted = [format_repo(repo, fields=fields, format=args.format,
                           humanize=args.humanize, totals=totals)
               for repo in repos]

  if args.totals and fields:
    totals_row = collections.OrderedDict()
    for field in fields:
      value = totals.get(field, None)
      if (args.humanize and value is not None and
          FIELD_ALIASES.get(field, field) in HUMANIZE):
        value = HUMANIZE[FIELD_ALIASES.get(field, field)](value)

      if args.format == 'csv':
        value = str(value) if value is not None else ''
      totals_row[field] = value
    formatted.append(totals_row)

  if args.format == 'json':
    print(json.dumps(formatted, indent=2))
  elif args.format == 'csv':
    writer = csv.DictWriter(sys.stdout, fields)
    writer.writeheader()
    writer.writerows(formatted)
  elif args.format == 'table':
    print(tabulate(formatted, headers='keys'))
  else:
    non_id_fields = [field for field in fields if field != id_field]
    if len(non_id_fields) == 1:
      widest_id = max(len(repo[id_field]) for repo in formatted)
      for repo in formatted:
        print('{1:{0}} {2}'.format(widest_id, repo[id_field],
                                   repo[non_id_fields[0]]))
    elif len(non_id_fields) == 0:
      for repo in formatted:
        print(repo[id_field])
    else:
      widest_field = max(len(field) for field in non_id_fields)
      for repo in formatted:
        print(repo[id_field])
        for field in fields:
          if field == id_field:
            continue
          print(' - {1:>{0}}: {2}'.format(widest_field, field, repo.get(field)))
        print()


if __name__ == '__main__':
  main()
