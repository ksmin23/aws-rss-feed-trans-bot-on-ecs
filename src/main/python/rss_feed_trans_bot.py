#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
# vim: tabstop=2 shiftwidth=2 softtabstop=2 expandtab

import sys
from datetime import datetime
import time
import collections
import logging
import io
import os
import pprint
import random
import traceback

import boto3
import feedparser
from bs4 import BeautifulSoup
from googletrans import Translator
import redis

LOGGER = logging.getLogger()
if len(LOGGER.handlers) > 0:
  # The Lambda environment pre-configures a handler logging to stderr.
  # If a handler is already configured, `.basicConfig` does not execute.
  # Thus we set the level directly.
  LOGGER.setLevel(logging.INFO)
else:
  logging.basicConfig(level=logging.INFO)

random.seed(47)

DRY_RUN = True if 'true' == os.getenv('DRY_RUN', 'true') else False

AWS_REGION = os.getenv('REGION_NAME', 'us-east-1')

S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')
S3_OBJ_KEY_PREFIX = os.getenv('S3_OBJ_KEY_PREFIX', 'whats-new')

PRESIGNED_URL_EXPIRES_IN = int(os.getenv('PRESIGNED_URL_EXPIRES_IN', 86400*15))

EMAIL_FROM_ADDRESS = os.getenv('EMAIL_FROM_ADDRESS')
EMAIL_TO_ADDRESSES = os.getenv('EMAIL_TO_ADDRESSES')
EMAIL_TO_ADDRESSES = [e.strip() for e in EMAIL_TO_ADDRESSES.split(',')]

TRANSLATE_ALL_FEEDS = True if 'true' == os.getenv('TRANSLATE_ALL_FEEDS', 'false') else False

TRANS_DEST_LANG = os.getenv('TRANS_DEST_LANG', 'ko')
TRANS_REQ_INTERVALS = [0.1, 0.3, 0.5, 0.7, 1.0]

WHATS_NEW_URL = 'https://aws.amazon.com/about-aws/whats-new/recent/feed/'

ELASTICACHE_HOST = os.getenv('ELASTICACHE_HOST', 'localhost')

TRANS_CLIENT = None



def split_list(x, n=10):
  return [x[i:i + n] for i in range(0, len(x), n)]


def strip_html_tags(html):
  soup = BeautifulSoup(html, features='html.parser')
  text = soup.get_text()
  a_hrefs = soup.find_all('a')
  return {'text': text, 'a_hrefs': a_hrefs}


def parse_feed(feed_url):
  parsed_rss_feed = feedparser.parse(feed_url)

  status = parsed_rss_feed['status']
  if 200 != status:
    return

  ENTRY_KEYS = '''link,id,title,summary,published_parsed'''.split(',')
  entry_list = []
  for entry in parsed_rss_feed['entries']:
    doc = {k: entry[k] for k in ENTRY_KEYS}
    doc['tags'] = [e['term'] for e in entry['tags']]
    doc['summary_parsed'] = strip_html_tags(doc['summary'])
    entry_list.append(doc)
  return {'entries': entry_list, 'updated_parsed': parsed_rss_feed['updated_parsed'], 'count': len(entry_list)}


def mk_translator(region_name=AWS_REGION):
  global TRANS_CLIENT

  if not TRANS_CLIENT:
    TRANS_CLIENT = boto3.client('translate', region_name=region_name)
  assert TRANS_CLIENT
  return TRANS_CLIENT


def translate(translator, texts, src='en', dest='ko', interval=1):
  trans_texts = collections.OrderedDict()

  for key, elem in texts:
    trans_res = translator.translate_text(Text=elem,
      SourceLanguageCode=src, TargetLanguageCode=dest)
    trans_texts[key] = trans_res['TranslatedText'] if 200 == trans_res['ResponseMetadata']['HTTPStatusCode'] else None
    time.sleep(interval)
  return trans_texts


def gen_html(res):
  HTML_FORMAT = '''<!DOCTYPE html>
<html>
<head>
<style>
table {{
  font-family: arial, sans-serif;
  border-collapse: collapse;
  width: 100%;
}}

td, th {{
  border: 1px solid #dddddd;
  text-align: left;
  padding: 8px;
}}

tr:nth-child(odd) {{
  background-color: #dddddd;
}}
</style>
</head>
<body>
  <h2><a href="https://aws.amazon.com/ko/new/">AWS의 새로운 소식</a></h2>
  <table>
    <tr>
      <th>section</th>
      <th>content</th>
    </tr>
    {table_rows}
  </table>
  <p>Last updated: {last_updated}</p>
</body>
</html>'''

  HTML_TABLE_ROW_FORMAT = '''<tr>
    <td>title</td>
    <td><a href="{link}">{title}</a></td>
  </tr>
  <tr>
    <td>title_{lang}</td>
    <td>{title_trans}</td>
  </tr>
  <tr>
    <td>summary</td>
    <td>{summary}</td>
  </tr>
  <tr>
    <td>summary_{lang}</td>
    <td><p>{summary_trans}</p></td>
  </tr>
  <tr>
    <td>pub_date</td>
    <td>{pub_date}</td>
  </tr>
  <tr>
    <td>tags</td>
    <td>{tags}</td>
  </tr>'''

  html_table_rows = []
  for elem in res['entries']:
    html_tr_elem = HTML_TABLE_ROW_FORMAT.format(link=elem['link'],
      pub_date=time.strftime('%Y-%m-%dT%H:%M:%S', elem['published_parsed']),
      title=elem['title'], summary=elem['summary'],
      title_trans=elem['title_trans']['text'], summary_trans=elem['summary_trans']['text'],
      lang=elem['title_trans']['lang'], tags=','.join(elem['tags']))
    html_table_rows.append(html_tr_elem)

  html_doc = HTML_FORMAT.format(
    last_updated=time.strftime('%Y-%m-%dT%H:%M:%S', res['updated_parsed']),
    lang='ko', table_rows='\n'.join(html_table_rows))

  return html_doc


def fwrite_s3(s3_client, doc, s3_bucket, s3_obj_key):
  output = io.StringIO()
  output.write(doc)

  ret = s3_client.put_object(Body=output.getvalue(),
    Bucket=s3_bucket,
    Key=s3_obj_key)

  output.close()
  try:
    status_code = ret['ResponseMetadata']['HTTPStatusCode']
    return (200 == status_code)
  except Exception as ex:
    return False


def send_email(from_addr, to_addrs, subject, html_body):
  ses_client = boto3.client('ses', region_name=AWS_REGION)
  ret = ses_client.send_email(Destination={'ToAddresses': to_addrs},
    Message={'Body': {
        'Html': {
          'Charset': 'UTF-8',
          'Data': html_body
        }
      },
      'Subject': {
        'Charset': 'UTF-8',
        'Data': subject
      }
    },
    Source=from_addr
  )
  return ret


def get_feeds_translated(redis_client, feed_ids):
  if not redis_client:
    return {}

  feed_key_ids = [('id:{}'.format(e), e) for e in feed_ids]
  chunked_feed_key_ids = split_list(feed_key_ids)

  feeds_translated = {}
  with redis_client.pipeline() as pipe:
    for elems in chunked_feed_key_ids:
       pipe.mget([k for k, v in elems])
       res = pipe.execute()
       feeds_translated.update({e.decode('utf-8'): True for e in res[0] if e})
  return feeds_translated


def save_feeds_translated(redis_client, feed_ids, ttl_sec=86400*3):
  if not redis_client:
    return

  feed_key_ids = [('id:{}'.format(e), e) for e in feed_ids]
  chunked_feed_key_ids = split_list(feed_key_ids)

  with redis_client.pipeline() as pipe:
    cnt = 0
    for elems in chunked_feed_key_ids:
       pipe.mset({k: v for k, v in elems})
       for k, _ in elems:
         pipe.expire(k, ttl_sec)
       pipe.execute()


def lambda_handler(event, context):
  LOGGER.info('start to get rss feed')

  redis_client = redis.Redis(host=ELASTICACHE_HOST, port=6379, db=0) if not TRANSLATE_ALL_FEEDS else None

  feeds_parsed = parse_feed(WHATS_NEW_URL)

  LOGGER.info('rss_feed: count={count}, last_updated="{last_updated}"'.format(count=feeds_parsed['count'],
    last_updated=time.strftime('%Y-%m-%dT%H:%M:%S', feeds_parsed['updated_parsed'])))

  LOGGER.info('filter new rss feeds')

  feed_ids = [e['id'] for e in feeds_parsed['entries']]
  feeds_translated = get_feeds_translated(redis_client, feed_ids)
  if len(feeds_translated):
    LOGGER.info('new_rss_feed: count=0')
    LOGGER.info('end')
    return

  feed_entries = [elem for elem in feeds_parsed['entries'] if elem['id'] not in feeds_translated]
  res = {
    'count': len(feed_entries),
    'updated_parsed': feeds_parsed['updated_parsed'],
    'entries': feed_entries
  }

  LOGGER.info('new_rss_feed: count={count}, last_updated="{last_updated}"'.format(count=res['count'],
    last_updated=time.strftime('%Y-%m-%dT%H:%M:%S', res['updated_parsed'])))

  LOGGER.info('translate rss feed')
  translator = mk_translator(region_name=AWS_REGION)
  title_texts = [(e['id'], e['title']) for e in res['entries']]
  title_texts_trans = translate(translator, title_texts,
    dest=TRANS_DEST_LANG, interval=random.choice(TRANS_REQ_INTERVALS))

  summary_texts = [(e['id'], e['summary_parsed']['text']) for e in res['entries']]
  summary_texts_trans = translate(translator, summary_texts,
    dest=TRANS_DEST_LANG, interval=random.choice(TRANS_REQ_INTERVALS))

  LOGGER.info('add translated rss feed')

  entry_ids_by_idx = {e['id']: idx for idx, e in enumerate(res['entries'])}
  for k, idx in entry_ids_by_idx.items():
    title_trans = title_texts_trans.get(k, '')
    summary_trans = summary_texts_trans.get(k, '')
    res['entries'][idx]['title_trans'] = {'text': title_trans, 'lang': TRANS_DEST_LANG}
    res['entries'][idx]['summary_trans'] = {'text': summary_trans, 'lang': TRANS_DEST_LANG}

  html_doc = gen_html(res)

  if not DRY_RUN:
    LOGGER.info('send translated rss feed by email')
    subject = '''[translated] AWS Recent Announcements'''
    send_email(EMAIL_FROM_ADDRESS, EMAIL_TO_ADDRESSES, subject, html_doc)

  LOGGER.info('save translated rss feeds in S3')

  s3_file_name = 'anncmt-{}.html'.format(time.strftime('%Y%m%d%H', res['updated_parsed']))
  s3_obj_key = '{prefix}-html/{file_name}'.format(prefix=S3_OBJ_KEY_PREFIX, file_name=s3_file_name)
  s3_client = boto3.client('s3', region_name=AWS_REGION)
  fwrite_s3(s3_client, html_doc, s3_bucket=S3_BUCKET_NAME, s3_obj_key=s3_obj_key)

  LOGGER.info('log translated rss feeds')

  feed_ids = [e['id'] for e in res['entries']]
  save_feeds_translated(redis_client, feed_ids)

  LOGGER.info('end')


if __name__ == '__main__':
  event = {
    "id": "cdc73f9d-aea9-11e3-9d5a-835b769c0d9c",
    "detail-type": "Scheduled Event",
    "source": "aws.events",
    "account": "",
    "time": "1970-01-01T00:00:00Z",
    "region": "us-east-1",
    "resources": [
      "arn:aws:events:us-east-1:123456789012:rule/ExampleRule"
    ],
    "detail": {}
  }
  event['time'] = datetime.utcnow().strftime('%Y-%m-%dT%H:00:00')

  start_t = time.time()
  lambda_handler(event, {})
  end_t = time.time()
  LOGGER.info('run_time: {:.2f}'.format(end_t - start_t))
