#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

PAGE_SIZE = 200;

def getAge(name):
	r = praw.Reddit(
		client_id = CLIENT_ID,
		client_secret = CLIENT_SECRET,
		password = BOT_PASSWORD,
		user_agent = USER_AGENT,
		username = BOT_NAME
	)

	created = r.redditor(name).created_utc
	ago = timeago.format(created, datetime.datetime.now())

	return {'created':ago}


def getUsers(retries):
	try:
		con = sqlite3.connect("/var/www/bot/database.db")
		con.row_factory = sqlite3.Row
		#mentions = con.execute("SELECT *, COUNT(rowid) as counter FROM ticker_mentions GROUP BY user, ticker ORDER BY time_created DESC")
		cur = con.execute("SELECT *, COUNT(rowid) as counter FROM ticker_mentions GROUP BY user, ticker ORDER BY time_created DESC LIMIT ?", [PAGE_SIZE])
		mentions = cur.fetchall()
		cur.close()

		users = []
		# string indices failed
		for m in mentions:
			if not any(m['user'] == u['name'] for u in users):
				users.append({'name':m['user'], 'mentions':[], 'mention_count':0})
			u = [u for u in users if u['name'] == m['user']][0]

			ago = timeago.format(round(m[4]/1000), datetime.datetime.now())
			link = "https://reddit.com/"+m['content_id'] if m['content_id'] else ''

			u['mentions'].append({'ticker':m['ticker'], 'time':ago, 'rawtime':m['time_created'], 'blacklisted':m['blacklisted'], 'tagged':m['tagged'], 'count':m['counter'], 'link':link})
			u['mention_count'] += m['counter']

		# mentions.close()

	except sqlite3.OperationalError as e:
		if retries > 2:
			return {'error':'database locked'}
		else:
			retries += 1
			time.sleep(3)
			return getUsers(retries)

	return users


def getLastSeen():
	con = sqlite3.connect("/var/www/bot/database.db")
	cur = con.execute("SELECT time_created FROM ticker_mentions ORDER BY time_created DESC LIMIT 1")
	lastSeen = cur.fetchone()[0]
	cur.close()
	ago = timeago.format(round(lastSeen/1000), datetime.datetime.now())

	return {'lastSeen':ago}


def getTickers(retries):
	try:
		con = sqlite3.connect("/var/www/bot/database.db")
		cur = con.cursor()

		day = 1000*60*60*24
		now = round(time.time()*1000)
		times = {'24h': day, '7d':day*7, '14d':day*14, '30d':day*30}

		mentions = {}
		for t in times:
			mentions[t] = cur.execute("SELECT ticker, COUNT(rowid) as counter FROM ticker_mentions WHERE time_created > ? GROUP BY ticker ORDER BY counter DESC LIMIT ?", [now-times[t], PAGE_SIZE]).fetchall()
		mentions['mention_count'] = cur.execute("SELECT ticker, COUNT(rowid) as counter FROM ticker_mentions GROUP BY ticker ORDER BY counter DESC LIMIT ?", [PAGE_SIZE]).fetchall()
		cur.close()

		tickers = []
		for m in mentions:
			for mention in mentions[m]:
				if not any(t['ticker'] == mention[0] for t in tickers):
					ticker = {'ticker':mention[0]}
					for i in times:
						ticker[i] = ''
					tickers.append(ticker)
				t = [tic for tic in tickers if tic['ticker'] == mention[0]][0]
				t[m] = mention[1]

	except sqlite3.OperationalError as e:
		if retries > 2:
			return {'error':'database locked'}
		else:
			retries += 1
			time.sleep(3)
			return getTickers(retries)

	return tickers


def whoMentioned(ticker):
	try:
		con = sqlite3.connect("/var/www/bot/database.db")
		con.row_factory = sqlite3.Row
		cur = con.cursor()

		data = cur.execute("SELECT user, content_id, COUNT(rowid) as counter, time_created FROM ticker_mentions WHERE ticker = ? GROUP BY user ORDER BY counter DESC", [ticker]).fetchall()
		cur.close()

		mentions = [{'user':d['user'],'link':d['content_id'],'counter':d['counter'], 'ago':timeago.format(round(d['time_created']/1000), datetime.datetime.now())} for d in data]

	except sqlite3.OperationalError as e:
		mentions = str(e)
	
	return mentions


print("Content-Type: application/json;charset=utf-8")
print()
import json
import timeago
import datetime
import time
import traceback

class ArgumentError(Exception):
	pass

try:
	import cgi
	args = cgi.FieldStorage()
	output = {}

	if 'mode' not in args:
		raise ArgumentError("no mode argument")

	mode = args['mode'].value

	if mode == 'age':
		if 'user' not in args:
			raise ArgumentError("no user argument")

		import praw
		# get config module from parent dir
		import os,sys,inspect
		current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
		parent_dir = os.path.dirname(current_dir)
		sys.path.insert(0, parent_dir) 
		from config import *
		output = getAge(args['user'].value)

	if mode == 'lastSeen':
		import sqlite3
		output = getLastSeen()

	if mode == 'users':
		import sqlite3
		output = getUsers(0)

	if mode == 'tickers':
		import sqlite3
		output = getTickers(0)

	if mode == 'whoMentioned':
		if 'ticker' not in args:
			raise ArgumentError("no ticker argument")

		import sqlite3
		output = whoMentioned(args['ticker'].value)


except Exception as e:
	if 'debug' in args:
		output = traceback.format_exc()
	else:
		output = str(e)

print(json.dumps(output))

