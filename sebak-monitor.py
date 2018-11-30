import sys
from time import sleep
import requests
from multiprocessing import Pool
import logging
from datetime import datetime
from datetime import timedelta
import json
import configparser

from _email import sendmail


config = None
email_to_addresses = None


class InvalidBehavior(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return self.value


def get_block_obj(url):
    try:
        obj = requests.get(url).json()
        obj['url'] = url
    except requests.exceptions.RequestException:
        raise
    return obj


def get_latest_block_height(url):
    try:
        obj = requests.get(url).json()
    except requests.exceptions.RequestException:
        raise

    return obj['block']['height'], obj


def get_valid_urls(urls):
    valid_urls = []
    for url in urls:
        try:
            r = requests.get(url)
        except requests.exceptions.RequestException:
            continue
        if r.status_code == 200:
            try:
                if r.json()['node']['state'] == 'CONSENSUS':
                    valid_urls.append(url)
            except KeyError:
                continue
    return valid_urls


def check_have_same_blocks(blocks):
    height = blocks[0]['height']
    hash = blocks[0]['hash']
    for block in blocks:
        if block['hash'] != hash:
            form = 'At height {}, the block hashes of the two nodes are different\n\n{}\n{}\n\n{}\n{}\n'
            text = form.format(
                height,
                block['url'],
                json.dumps(block, indent=4, sort_keys=True),
                blocks[0]['url'],
                json.dumps(blocks[0], indent=4, sort_keys=True),
            )
            raise InvalidBehavior(text)

    return ''


log = logging.getLogger("monitor")
log.addHandler(logging.StreamHandler())
log.setLevel(logging.DEBUG)


def get_time(url):
    try:
        block = requests.get(url).json()
    except requests.exceptions.RequestException:
        raise

    confirmed_time = block['confirmed']
    return datetime.strptime(confirmed_time.split('.')[0], '%Y-%m-%dT%H:%M:%S')


def get_expected_date_time(first_block_time, latest_height):
    expected_seconds_by_block_time = ((latest_height - 2) * 5)
    return first_block_time + timedelta(seconds=expected_seconds_by_block_time)


def get_time_diff(get_block_url, first_consensused_block_height, latest_height):
    try:
        first_block_time = get_time(get_block_url % first_consensused_block_height)
    except requests.exceptions.RequestException:
        raise

    try:
        latest_block_time = get_time(get_block_url % latest_height)
    except requests.exceptions.RequestException:
        raise

    expected = get_expected_date_time(first_block_time, latest_height)
    actual = latest_block_time

    return actual - expected


def parse_conf(ini_file):
    config = configparser.ConfigParser()
    config.read(ini_file)
    return config


def run(urls, prev_latest_height, block_confirm_wait):
    try:
        valid_urls = get_valid_urls(urls)
    except requests.exceptions.RequestException as e:
        raise

    if len(valid_urls) < 1:
        raise InvalidBehavior('There is no valid url')

    try:
        latest_height, node = get_latest_block_height(valid_urls[0])
    except requests.exceptions.RequestException as e:
        raise

    if prev_latest_height == latest_height:
        raise InvalidBehavior('The latest_height is not changed for {} seconds'.format(
            checking_block_interval,
        ))

    n = len(valid_urls)

    if n < 1:
        raise InvalidBehavior('The number of nodes is zero')

    if latest_height < 1:
        raise InvalidBehavior('latest_height(%d) is valid'.format(latest_height))

    sleep(block_confirm_wait)

    get_block_urls = []
    for url in valid_urls:
        get_block_urls.append(url + '/api/v1/blocks/' + str(latest_height))

    try:
        with Pool(n) as p:
            blocks = p.map(get_block_obj, get_block_urls)
    except requests.exceptions.RequestException:
        raise
    except json.decoder.JSONDecodeError:
        raise

    try:
        check_have_same_blocks(blocks)
    except InvalidBehavior:
        raise

    ret = {}
    ret['n'] = n
    ret['valid-urls'] = valid_urls
    ret['latest-height'] = latest_height
    ret['blocks'] = blocks
    ret['node'] = node
    return ret


def slack_out(url, prefix, text):
    if len(url) < 1:
        return

    log.debug('send slack')
    try:
        time_str = datetime.now().strftime('[%m-%d|%H:%M:%S]')
        requests.post(url, json={"text": '{} {} {}'.format(prefix, time_str, text)})
    except requests.exceptions.RequestException as e:
        log.error(e)
        pass


def email_out(out_str):
    log.debug('send email')
    ret = sendmail(
        smtp_config=config['smtp'],
        from_addr=config['smtp']['from_address'],
        to_addr=email_to_addresses,
        subject='SEBAK: Invalid benavior found',
        body=out_str,
    )

    return ret


logging.basicConfig()
log = logging.getLogger('main')
log.setLevel(logging.DEBUG)


if __name__ == '__main__':
    log.info('start sebak-monitor')

    if len(sys.argv) < 2:
        log.fatal('The number of arguments should be 1(ini file for configuration)')
        exit(1)

    ini_file = sys.argv[1]

    config = parse_conf(ini_file)
    checking_block_interval = int(config['INTERVAL']['CheckingBlock'])
    block_confirm_wait = int(config['INTERVAL']['BlockConfirmWait'])
    alarm_interval = int(config['INTERVAL']['Alarm'])
    slack_url_info=config['URL']['SlackWebhookInfo']
    slack_url_error=config['URL']['SlackWebhookError']

    email_to_addresses = list(map(lambda x: x.strip(), config['mail']['to_address'].split(',')))

    urls = list(map(lambda x: x.strip(), config['NODES']['nodes'].split(',')))
    log.debug('urls: %s', urls)

    prev_latest_height = 0
    alarm_time = datetime.now() - timedelta(days=1)  # init to yesterday for alarming at first immediately

    while True:
        try:
            ret = run(urls, prev_latest_height, block_confirm_wait)
        except requests.exceptions.RequestException as e:
            log.exception(e)
            continue
        except json.decoder.JSONDecodeError as e:
            log.exception(e)
            continue
        except InvalidBehavior as e:
            email_out(str(e))
            slack_out(slack_url_error, '@here ERROR', str(e))
            break

        prev_latest_height = ret['latest-height']

        first_consensused_block_height = 2
        time_diff = get_time_diff(
            ret['valid-urls'][0] + '/api/v1/blocks/%d',
            first_consensused_block_height,
            ret['latest-height'],
        )
        n = ret['n']
        height = ret['blocks'][0]['height']
        user_txs = ret['node']['block']['total-txs'] - height
        user_ops = ret['node']['block']['total-ops'] - (height * 2)

        alarm_time_diff = datetime.now() - alarm_time
        if alarm_time_diff > timedelta(minutes=alarm_interval):
            text = 'Nodes: {}, Height: {}, UserTxs: {}, UserOps: {}, TimeDiff: {}'.format(
                n, height, user_txs, user_ops, time_diff,
            )
            slack_out(slack_url_info, 'INFO', text)
            alarm_time = datetime.now()

        sleep(checking_block_interval - block_confirm_wait)
