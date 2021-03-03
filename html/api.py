#!/usr/local/bin/python3
# -*- coding: utf-8 -*-


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


def getUsers():
	con = sqlite3.connect("/var/www/bot/database.db")
	mentions = con.execute("SELECT *, COUNT(rowid) as counter FROM ticker_mentions GROUP BY user, ticker ORDER BY time_created DESC").fetchall()
	users = []
	# string indices failed
	for m in mentions:
		if not any(m['user'] == u['name'] for u in users):
			users.append({'name':m['user'], 'mentions':[]})
		u = [u for u in users if u['name'] == m['user']][0]

		ago = timeago.format(round(m[4]/1000), datetime.datetime.now())

		u['mentions'].append({'ticker':m['ticker'], 'time':ago, 'rawtime':m['time_created'], 'blacklisted':m['blacklisted'], 'tagged':m['tagged'], 'count':m['counter']})

	return users


def getLastSeen():
	con = sqlite3.connect("/var/www/bot/database.db")
	lastSeen = con.execute("SELECT time_created FROM ticker_mentions ORDER BY time_created DESC LIMIT 1").fetchone()[0]
	ago = timeago.format(round(lastSeen/1000), datetime.datetime.now())

	return {'lastSeen':ago}


print("Content-Type: application/json;charset=utf-8")
print()
import json
import timeago
import datetime

try:
	import cgi
	args = cgi.FieldStorage()
	output = {}

	if 'age' in args:
		import praw
		# get config module from parent dir
		import os,sys,inspect
		current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
		parent_dir = os.path.dirname(current_dir)
		sys.path.insert(0, parent_dir) 
		from config import *
		output = getAge(args['age'].value)

	elif 'lastSeen' in args:
		import sqlite3
		output = getLastSeen()

	else:
		import sqlite3
		output = getUsers()

except Exception as e:
	output = str(e)

print(json.dumps(output))

