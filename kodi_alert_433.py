#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from datetime import datetime
import requests
import json

import logging
import configparser
import os
import sys
import socket
import signal

from rpi_rf import RFDevice

from email.utils import formataddr
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
import smtplib

import argparse


# global settings
_max_waittime_ = 10


def is_mailaddress(a):
  try:
    t = a.split('@')[1].split('.')[1]
  except:
    return False

  return True


def is_hostname(h):
  try:
    t = h.split('.')[2]
  except:
    return False

  return True


def is_int(n):
  try:
    t = int(n)
  except:
    return False

  return True


def log(message, level='INFO'):
  if _log_file_:
    if level == 'DEBUG' and _debug_:
      logging.debug(message)
    if level == 'INFO':
      logging.info(message)
    if level == 'WARNING':
      logging.warning(message)
    if level == 'ERROR':
      logging.error(message)
    if level == 'CRITICAL':
      logging.crtitcal(message)
  else:
     if level != 'DEBUG' or _debug_:
       print('[' + level + ']: ' + message)


def read_config():
  global _kodi_hosts_, _kodi_port_, _kodi_user_, _kodi_passwd_
  global _smtp_server_, _smtp_realname_, _smtp_user_, _smtp_passwd_
  global _mail_to_, _mail_subject_, _mail_body_, _mail_attach_, _time_fmt_
  global _gpio_rxdata_, _rf_alertcode_, _rf_description_, _notify_title_, _notify_text_
  global _exec_local_

  if not os.path.exists(_config_file_):
    log('Could not find configuration file \'{}\'.'.format(_config_file_), level='ERROR')
    return False

  log('Reading configuration from file ...')

  config = configparser.ConfigParser(interpolation=None)
  config.read([os.path.abspath(_config_file_)], encoding='utf-8')
  try:
    # Read the config file
    #config = configparser.ConfigParser(interpolation=None)
    #config.read([os.path.abspath(_config_file_)], encoding='utf-8')

    _kodi_hosts_     = [p.strip(' "\'') for p in config.get('KODI JSON-RPC', 'hostname').split(',')]
    _kodi_port_      = config.get('KODI JSON-RPC', 'port').strip(' "\'')
    _kodi_user_      = config.get('KODI JSON-RPC', 'username').strip(' "\'')
    _kodi_passwd_    = config.get('KODI JSON-RPC', 'password').strip(' "\'')

    for host in _kodi_hosts_:
      if not is_hostname(host):
        log('Wrong or missing value(s) in configuration file (section: [KODI JSON-RPC]).')
        return False

    if not is_int(_kodi_port_):
      log('Wrong or missing value(s) in configuration file (section: [KODI JSON-RPC]).')
      return False

    _smtp_server_    = config.get('Mail Account', 'smtpserver').strip(' "\'')
    _smtp_realname_  = config.get('Mail Account', 'realname').strip(' "\'')
    _smtp_user_      = config.get('Mail Account', 'username').strip(' "\'')
    _smtp_passwd_    = config.get('Mail Account', 'password').strip(' "\'')

    if is_hostname(_smtp_server_):
      if not is_mailaddress(_smtp_user_) or not _smtp_passwd_:
        log('Wrong or missing value(s) in configuration file (section [Mail Account]).')
        return False

      _mail_to_        = [p.strip(' "\'') for p in config.get('Alert Mail', 'recipient').split(',')]
      _mail_subject_   = config.get('Alert Mail', 'subject').strip(' "\'')
      _mail_body_      = config.get('Alert Mail', 'body').strip(' "\'')
      _mail_attach_    = [p.strip() for p in config.get('Alert Mail', 'attach').split(',')]
      _time_fmt_       = config.get('Alert Mail', 'timeformat').strip(' "\'')

      if _mail_attach_ == ['']:
        _mail_attach_ = None

      if _time_fmt_ == '':
        _time_fmt_ = "%Y-%m-%d %H:%M:%S"

      for addr in _mail_to_:
        if not is_mailaddress(addr):
          log('Wrong or missing value(s) in configuration file (section [Alert Mail]).')
          return False

      if not _mail_subject_ or not _mail_body_:
        log('Wrong or missing value(s) in configuration file (section [Alert Mail]).')
        return False

    value = config.get('GPIO', 'rxdata').strip(' "\'')
    if not is_int(value):
      log('Wrong or missing value(s) in configuration file (section: [GPIO]).')
      return False
    else:
      _gpio_rxdata_ = int(value)

    try:
      _rf_alertcode_   = [int(p.strip(' "\'')) for p in config.get('RF Alert', 'code').split(',')]
      _rf_description_ = [p.strip(' "\'') for p in config.get('RF Alert', 'description').split(',')]
    except:
      log('Wrong or missing value(s) in configuration file (section: [RF Alert]).')
      return False

    _notify_title_   = config.get('Alert Notification', 'title').strip(' "\'')
    _notify_text_    = config.get('Alert Notification', 'text').strip(' "\'')

    _exec_local_     = config.get('Local', 'command').strip(' "\'')

  except:
    log('Could not process configuration file.', level='ERROR')
    return False

  log('Configuration OK.')

  return True


def kodi_request(host, method, params):
  url  = 'http://{}:{}/jsonrpc'.format(host, _kodi_port_)
  headers = {'content-type': 'application/json'}
  data = {'jsonrpc': '2.0', 'method': method, 'params': params,'id': 1}

  if _kodi_user_ and _kodi_passwd_:
    base64str = base64.encodestring('{}:{}'.format(_kodi_user_, _kodi_passwd_))[:-1]
    header['Authorization'] = 'Basic {}'.format(base64str)

  try:
    response = requests.post(url, data=json.dumps(data), headers=headers, timeout=10)
  except:
    return False

  data = response.json()
  return (data['result'] == 'OK')


def host_is_up(host, port):
  try:
    sock = socket.create_connection((host, port), timeout=3)
  #except socket.timout:
  #  return False
  except:
    return False

  return True


def sendmail(subject, message, attachments=None):
  #
  # https://code.tutsplus.com/tutorials/sending-emails-in-python-with-smtp--cms-29975
  #

  if not message:
    return False

  msg = MIMEMultipart()

  if _smtp_realname_:
    msg['From']  = formataddr((str(Header(_smtp_realname_, 'utf-8')), _smtp_user_))
  else:
    msg['From']  = _smtp_user_
  msg['To']      = ', '.join(_mail_to_)
  msg['Subject'] = subject

  msg.attach(MIMEText(message, 'plain'))

  for attachment in attachments or []:
    try:
      if os.path.isfile(attachment):
        with open(attachment, "rb") as f:
          part = MIMEApplication(f.read(), Name=os.path.basename(attachment))
          part['Content-Disposition'] = 'attachment; filename="{}"'.format(os.path.basename(attachment))
          msg.attach(part)
    except:
      continue

  try:
    server = smtplib.SMTP(_smtp_server_)
    server.starttls()
    server.login(_smtp_user_, _smtp_passwd_)
    server.sendmail(_smtp_user_, _mail_to_, msg.as_string())

  except:
    log('Unable to send mail.', level='ERROR')
    return False

  finally:
    server.quit()

  return True


def alert(timestamp, alertcode):
  # This will execute  the configured local command passing the alertcode as add. argument
  # Attention: Script waits for command to terminate and return
  if _exec_local_:
    try:
      os.system(_exec_local_ + ' ' + str(alertcode))
    except:
      log('Could not execute local command \'{}\'.'.format(_exec_local_), level='ERROR')
      pass

  for host in _kodi_hosts_:
    if not host_is_up(host, _kodi_port_):
      log('Host {} is down. Requests canceled.'.format(host), level='DEBUG')
      continue

    if _notify_title_ and _notify_text_:
      try:
        text = _notify_text_.format(_rf_description_[_rf_alertcode_.index(alertcode)])
      except:
        text = _notify_text_

      log('Requesting notification \'{}: {}\' from host {} ...'.format(_notify_title_, text, host), level='DEBUG')
      kodi_request(host, 'GUI.ShowNotification', {'title': _notify_title_, 'message': text, 'displaytime': 2000})

    if _addon_id_:
      log('Requesting execution of addon \'{}\' from host {} ...'.format(_addon_id_, host), level='DEBUG')
      kodi_request(host, 'Addons.ExecuteAddon', {'addonid': _addon_id_})

  if _smtp_server_:
    try:
      subject = _mail_subject_.format(_rf_description_[_rf_alertcode_.index(alertcode)])
    except:
      subject = _mail_subject_

    try:
      body    = '{}: '.format(timestamp) + _mail_body_.format(_rf_description_[_rf_alertcode_.index(alertcode)])
    except:
      body    = _mail_body_

    if _mail_attach_ and os.path.isdir(_mail_attach_[0]):

      waittime = 0
      while not next(os.walk(_mail_attach_[0]))[2] and waittime < _max_waittime_:
        waittime += 1
        time.sleep(1)

      p = _mail_attach_[0]
      files = [os.path.join(p, f) for f in os.listdir(p) if os.path.isfile(os.path.join(p, f))]
    else:
      files = _mail_attach_

    log('Sending mail to configured recipients via {} ...'.format(_smtp_server_.split(':')[0]), level='DEBUG')
    sendmail(subject, body, files)


if __name__ == '__main__':
  global _config_file_, _log_file_, _addon_id_, _debug_, _test_

  parser = argparse.ArgumentParser(description='Sends a notification to a kodi host and triggers addon execution on receipt of an external 433 MHz signal')

  parser.add_argument('-d', '--debug', dest='debug', action='store_true', help="Output debug messages (Default: False)")
  parser.add_argument('-l', '--logfile', dest='log_file', default=None, help="Path to log file (Default: None=stdout)")
  parser.add_argument('-c', '--config', dest='config_file', default=os.path.splitext(os.path.basename(__file__))[0] + '.ini', help="Path to config file (Default: <Script Name>.ini)")
  parser.add_argument('-a', '--addonid', dest='addon_id', default='script.securitycam', help="Addon ID (Default: script.securitycam)")
  parser.add_argument('-t', '--test', dest='test', action='store_true', help="Test Alert (Default: False)")

  args = parser.parse_args()

  _config_file_ = args.config_file
  _log_file_ = args.log_file
  _addon_id_ = args.addon_id
  _debug_ = args.debug
  _test_  = args.test

  if _log_file_:
    logging.basicConfig(filename=_log_file_, format='%(asctime)s [%(levelname)s]: %(message)s', datefmt='%m/%d/%Y %H:%M:%S', filemode='w', level=logging.DEBUG)

  log('Output Debug: {}'.format(_debug_), level='DEBUG')
  log('Log file:     {}'.format(_log_file_), level='DEBUG')
  log('Config file:  {}'.format(_config_file_), level='DEBUG')
  log('Addon ID:     {}'.format(_addon_id_), level='DEBUG')

  if not read_config():
    sys.exit(1)

  if _test_:
    log('Simulating alert event ...')
    now = datetime.now().strftime(_time_fmt_)
    alert(now, _rf_alertcode_[0])
    sys.exit(0)

  rfdevice = None

  try:
    rfdevice = RFDevice(_gpio_rxdata_)
    rfdevice.enable_rx()
    timestamp = None

    log('Listening for RF codes ...')

    while True:

      try:
        if rfdevice.rx_code_timestamp != timestamp:
          timestamp = rfdevice.rx_code_timestamp
          log('{} [pulselength {}, protocol {}]'.format(rfdevice.rx_code, rfdevice.rx_pulselength, rfdevice.rx_proto), level='DEBUG')

          if rfdevice.rx_code in _rf_alertcode_:
            now = datetime.now().strftime(_time_fmt_)
            log('Received 433 MHz signal with matching alert code {}'.format(rfdevice.rx_code))
            alert(now, rfdevice.rx_code)

        time.sleep(0.01)

      except (KeyboardInterrupt, SystemExit):
        log('Abort requested by user or system.')
        break

      except Exception as e:
        log('Abort due to exception: \"{}\"'.format(e))
        break

  finally:
    rfdevice.cleanup()
