##!/usr/bin/python3
# -*- coding: utf-8 -*-

import time
import sqlite3
import praw
import prawcore
import traceback
import requests
import re
import timeago
import datetime

from config import *

class Bot:

	def __init__(self,debug=False):
		# run config
		self.running = True
		self.debug = debug

		# track error handling
		self.lastErrorNotif = 0
		self.lastErrorDelay = 0
		self.lastResetTime = 0

		# init data
		self.initWords()
		self.initdb()

		if debug:
			return

		self.initReddit()
		self.run()


	def log(self, content):
		print(content)


	def run (self):
		self.log("running...")

		subCommentStream = self.r.subreddit(SUBREDDIT).stream.comments(skip_existing=True,pause_after=-1)
		subPostStream = self.r.subreddit(SUBREDDIT).stream.submissions(skip_existing=True,pause_after=-1)

		while self.running:

			try:
				for comment in subCommentStream:
					if comment is None or comment.author.name == BOT_NAME:
						break
					self.onSubComment(comment)

			except Exception as e:
				self.handleRuntimeError(e)

			self.log('=== END OF COMMENTS ===')

			if not self.running:
				break

			try:
				for post in subPostStream:
					if not self.running or post is None or post.author.name == BOT_NAME:
						break
					self.onSubPost(post)

			except Exception as e:
				self.handleRuntimeError(e)

			self.log('=== END OF POSTS ===')	

		self.log("running stopped!")


	def onSubComment(self, comment):
		b = comment.body[:40]+'..' if len(comment.body) > 40 else comment.body
		self.log("c "+comment.id+": "+ascii(b))

		tickers = self.getTickersFromString(comment.body)
		self.saveTickerMentions(comment.author.name, tickers)
		

	def onSubPost(self, post):
		b = post.title[:40]+'..' if len(post.title) > 40 else post.title
		self.log("p "+post.id+": "+ascii(b))

		tickers = self.getTickersFromString(post.title+' '+post.selftext)
		self.engageWith(post, tickers)
		self.saveTickerMentions(post.author.name, tickers)


	def engageWith(self, post, tickers):
		# check for flair
		if not hasattr(post,'link_flair_template_id') or post.link_flair_template_id != FLAIR_TO_ENGAGE or len(FLAIR_TO_ENGAGE) < 1:
			return
		self.log("yes this flair")
		
		table = self.makeMentionTable(post.author, tickers)

		tickers = ", ".join(["$"+t['ticker'] for t in tickers])
		ago = timeago.format(post.author.created_utc, datetime.datetime.now())

		responses = []

		if len(tickers) > 0 and len(POSTER_INFO_TEMPLATE_THESE_TICKERS) > 0:
			responses.append(POSTER_INFO_TEMPLATE_THESE_TICKERS.format(tickers))
		if not table == None and len(POSTER_INFO_TEMPLATE_OTHER_TICKERS) > 0:
			responses.append(POSTER_INFO_TEMPLATE_OTHER_TICKERS.format(post.author.name, table))
		if len(POSTER_INFO_TEMPLATE) > 0:
			responses.append(POSTER_INFO_TEMPLATE.format(post.author.name, ago, post.author.comment_karma, post.author.link_karma))
		if len(BOT_SIGNATURE) > 0:
			responses.append(BOT_SIGNATURE)

		if len(responses) < 1:
			return

		response = '\n\n'.join(responses)

		# reply + sticky
		sticky = post.reply(response)
		sticky.mod.distinguish(how="yes",sticky=True)


	def makeMentionTable(self, author, tickers):
		mentions = self.con.execute("SELECT ticker, COUNT(rowid) as counter FROM ticker_mentions WHERE user = ? GROUP BY ticker ORDER BY counter DESC", [author.name]).fetchall()

		table = ['||','|:-','**ticker**','**mentions**']
		for mention in mentions:
			table[0] += '|'
			table[1] += '|:-'
			m0 = "|**"+mention[0]+"**" if any(t['ticker'] == mention[0] for t in tickers) else '|'+mention[0]
			m1 = '|**'+str(mention[1])+'**' if any(t['ticker'] == mention[0] for t in tickers) else '|'+str(mention[1])
			table[2] += m0
			table[3] += m1
		table = "\n".join(table) if len(mentions) > 0 else None
		
		return table



	def getTickersFromString(self, content):

		oc = content.upper()
		content = re.split('[^\w$]+', oc)

		# words that start with $
		tagged_content = set([x[1:] for x in content if x.startswith('$')])
		# same list but includes the $
		tagged_content_with_tag = set([x for x in content if x.startswith('$')])
		# all other words
		untagged_content = set(content) - tagged_content_with_tag

		# untagged symbols that aren't common words
		tickers = (self.tickers & untagged_content) - self.words
		# plus tagged symbols
		tagged_tickers = self.tickers & tagged_content
		tickers.update(tagged_tickers)

		# plus symbols of mentioned ticker names that aren't common words
		ticker_names = [x for x in self.ticker_names if str(x).upper() in oc and len(str(x)) > 0]
		for tn in ticker_names:
			tickers.update(self.con.execute("SELECT symbol FROM tickers WHERE name = ? LIMIT 1", [tn]).fetchone())

		# make them objs w/ tag info
		tickers = [{'ticker':x, 'is_over':0, 'is_crypto':0, 'was_tagged':(1 if x in tagged_content else 0)} for x in set(tickers)]

		return tickers


	def saveTickerMentions(self, author, tickers):
		for ticker in tickers:
			blacklisted = 1 if ticker['is_over'] == 1 or ticker['is_crypto'] == 1 else 0
			self.con.execute("INSERT INTO ticker_mentions (ticker, user, blacklisted, time_created, tagged) VALUES (?,?,?,?,?)", [ticker['ticker'], author, blacklisted, round(time.time())*1000, ticker['was_tagged']])
		if len(tickers) > 0:
			self.con.commit()

			self.log("tickers: "+' '.join([t['ticker'] for t in tickers]))
			self.log('-')


	def handleRuntimeError(self, error):
		infostring = str(type(error)) + ': ' + str(error)

		self.con.execute("INSERT INTO bot_errors (info, time_created) VALUES (?, ?)", [infostring, round(time.time()*1000)])
		self.con.commit()

		self.log(traceback.format_exc())

		if time.time() - self.lastErrorNotif > 1800:
			self.notifyError(infostring)
			self.lastErrorNotif = time.time()

		if isinstance(error, prawcore.exceptions.ServerError):
			resetStreamUntilFixed()


	def resetStreamUntilFixed(self):
		self.running = False

		if self.lastErrorDelay == 0 or time.time() - self.lastResetTime > 256:
			self.lastErrorDelay = delay = 2
		elif self.lastErrorDelay < 128:
			self.lastErrorDelay = delay = self.lastErrorDelay*2

		self.lastResetTime = time.time()

		print("Server Error: retrying in "+str(delay))
		time.sleep(delay)
		print("retrying")
		self.run()


	def notifyError(self, error):
		if NOTIFY == '':
			self.log("NOTIFY not set")
			return
		try:
			self.r.redditor(NOTIFY).message("encountered an error",str(error))
		except Exception as e:
			self.log("ERROR NOTIFY FAILED")


	def initdb(self):
		con = self.con = sqlite3.connect("database.db")

		try:
			con.execute("SELECT * FROM test_table LIMIT 1")
		except sqlite3.OperationalError as e:
			if str(e).startswith("no such table"):
				self.createdb()
				self.updateTickerList()
			else:
				self.log("Error with initdb: "+str(e))
				self.running = False

		tickers = self.con.execute("SELECT symbol,name FROM tickers WHERE symbol NOT LIKE '%.%' AND symbol IS NOT NULL AND name IS NOT NULL AND symbol != '' and name != ''").fetchall()
		self.tickers = set([t[0] for t in tickers])
		self.ticker_names = set([t[1] for t in tickers if str(t[1]).upper() not in self.words and len(str(t[1])) > 4])


	def initReddit(self):
		self.r = praw.Reddit(
			client_id = CLIENT_ID,
			client_secret = CLIENT_SECRET,
			password = BOT_PASSWORD,
			user_agent = USER_AGENT,
			username = BOT_NAME
		)
		self.log("logged in as "+self.r.user.me().name)


	def initWords(self):
		self.words = open("resources/common_words.txt").read().splitlines()
		self.words = set([w.upper() for w in self.words])


	def updateTickerList(self):
		self.log("updating ticker list (this may take a while)...")

		start_time = round(time.time()*1000)
		total = 1001
		i = 0
		while 1000*i < int(total):
			p = {"access_key": MARKETSTACK_API_KEY, "limit":"1000"}
			total = rj['pagination']['total'] if i == 1 else total
			p["offset"] = str(1000*i)
			r = requests.get("http://api.marketstack.com/v1/tickers", params=p)
			rj = r.json()
			for ticker in rj['data']:
				self.con.execute("INSERT OR IGNORE INTO tickers (symbol, name, time_created, is_crypto) VALUES (?,?,?, 0)", [ticker['symbol'],ticker['name'],round(time.time()*1000)])
			i+=1

		self.con.commit()

		self.log("built ticker list")


	def createdb(self):
		self.log("building database...")
		con = self.con

		tables = [
			"users (name string UNIQUE, account_age int, whitelisted int, time_created int)",
			"ticker_mentions (ticker string, user string, blacklisted int, tagged int, time_created int)",
			"bot_actions (type string, user string, note string, time_created int)",
			"bot_errors (info string, time_created int)",
			"outside_activity (subreddit string, user string, time_created int)",
			"tickers (symbol string UNIQUE, name string, last_close string, is_crypto int, time_updated int, time_created int)",
			"test_table (test_data string)"
		]

		for t in tables:
			try:
				con.execute("CREATE TABLE IF NOT EXISTS "+t)
			except Exception as e:
				self.log("Error with SQL:\n"+t+"\n"+str(e))
				self.running = False
				break

		con.commit()


b = Bot()