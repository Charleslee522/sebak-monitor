import os
from time import sleep
import requests
from multiprocessing import Pool
from itertools import product
import logging
from datetime import datetime
from datetime import timedelta
import time
import json

# `total` is the total number of nodes to resolve to the URL.
# Find 'https: // mainnet-node- {} .blockchainos.org /' with a value from 0 to total to find the valid url.
total = 20

# `interval_sec` is second time interval for checking blocks
interval_sec = 10

class InvalidBehavior(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

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

def get_urls():
    url_format = 'https://mainnet-node-{}.blockchainos.org/'

    urls = []
    for i in range(0, total):
        urls.append(url_format.format(i))

    return urls

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
        if block['height'] != height:
            raise InvalidBehavior(
                'In {}, height({}) is different with {}(height:{})'.format(
                block['url'].split('/')[2], block['height'],
                blocks[0]['url'].split('/')[2], height))
        if block['hash'] != hash:
            raise InvalidBehavior(
                'In {}, block-hash({}) is different with {}(hash:{}) in height'.format(
                block['url'].split('/')[2], block['height'],
                blocks[0]['url'].split('/')[2], height))

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
    return datetime.strptime(confirmed_time.split('.')[0],'%Y-%m-%dT%H:%M:%S')

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

def run(urls, prev_latest_height):
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
        raise InvalidBehavior('The latest_height is not changed for {} seconds'.format(interval_sec))

    n = len(valid_urls)

    if n < 1:
        raise InvalidBehavior('The number of nodes is zero')

    if latest_height < 1:
        raise InvalidBehavior('latest_height(%d) is valid'.format(latest_height))

    sleep(interval_sec)

    get_block_urls = []
    for url in valid_urls:
        get_block_urls.append(url+'api/v1/blocks/'+str(latest_height))

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

if __name__ == '__main__':
    urls = get_urls()
    prev_latest_height = 0

    while (True):
        try:
            ret = run(urls, prev_latest_height)
        except requests.exceptions.RequestException:
            continue
        except json.decoder.JSONDecodeError:
            continue
        except InvalidBehavior as e:
            print(e)    # alarm with email and slack
            break       # should be removed

        prev_latest_height = ret['latest-height']

        first_consensused_block_height = 2
        time_diff = get_time_diff(ret['valid-urls'][0]+'api/v1/blocks/%d', first_consensused_block_height, ret['latest-height'])
        n = ret['n']
        height = ret['blocks'][0]['height']
        round = ret['blocks'][0]['round']
        user_txs = ret['node']['block']['total-txs'] - height
        user_ops = ret['node']['block']['total-ops'] - (height*2)

        # Print for logging
        log.info('nodes: %d, height: %d, round: %d, user-txs: %d, user-ops: %d, time-diff: %s', n, height, round, user_txs, user_ops, time_diff)
