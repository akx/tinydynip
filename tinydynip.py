import json
import logging
import os
import random
import re
import sys
import time

import click
import requests

IP_RE = re.compile(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}')

CHECKIP_URLS = [
    'http://checkip.dy.fi/',
    'http://checkip.dyn.com/',
    'http://checkip.dyndns.org/',
    'http://ifconfig.me/ip',
    'http://checkip.net/ip.shtml',
]


def get_current_ip():
    checkip_urls = CHECKIP_URLS[:]
    random.shuffle(checkip_urls)
    with requests.session() as s:
        for url in checkip_urls:
            try:
                resp = s.get(url, timeout=5)
                resp.raise_for_status()
                return IP_RE.search(resp.text).group(0)
            except requests.RequestException:
                logging.debug('failed checkip from %s', url, exc_info=True)
        raise RuntimeError('could not get IP')


def check_should_update(state, current_ip, days=4, force=False):
    old_ip = state.get('ip')
    old_time = state.get('update_time', 0)
    update_reasons = []
    if old_ip != current_ip:
        update_reasons.append('IP changed from %s to %s' % (old_ip, current_ip))
    if old_time and (time.time() - old_time) >= days * 86400:
        time_since_last = (time.time() - old_time)
        update_reasons.append('Last update happened %.1f days ago' % (time_since_last / 86400.))
    if force:
        update_reasons.append('Update forced')
    return update_reasons


def load_state(state_file):
    if os.path.isfile(state_file):
        with open(state_file, 'r') as state_fp:
            return json.load(state_fp)
    return {}


@click.command()
@click.option('--auth', '-a', envvar='DYNIP_AUTH', required=True)
@click.option('--update-url', '-u', required=True)
@click.option('--state-file', '-s', type=click.Path(dir_okay=False), default='./dynip.state')
@click.option('--host', '-h', multiple=True, required=True)
@click.option('--days', '-d', default=4, type=int)
@click.option('--force/--no-force', '-f', default=False)
@click.option('--debug/--no-debug', '-d', default=False)
def cli(update_url, state_file, host, auth, days, force, debug):
    if ':' in auth:
        auth = tuple(auth.split(':', 1))
    if debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    retcode = 0
    state = load_state(state_file)

    current_ip = get_current_ip()
    update_reasons = check_should_update(state, current_ip, days, force)
    if update_reasons:
        logging.info('Updating hosts %s: %s' % (','.join(host), update_reasons))
        try:
            with requests.session() as s:
                resp = s.get(update_url, params={'hostname': ','.join(host)}, auth=auth)
                resp.raise_for_status()
                logging.info('Result from %s: %s', update_url, resp.text)
                state.update(ip=current_ip, update_time=time.time())
        except requests.RequestException:
            logging.error('Update failed', exc_info=True)
            retcode = 1
    state.update(last_run_time=time.time(), last_run_update=update_reasons, last_run_success=(retcode == 0))

    with open(state_file, 'w') as state_fp:
        json.dump(state, state_fp)
    sys.exit(retcode)


if __name__ == '__main__':
    cli()
