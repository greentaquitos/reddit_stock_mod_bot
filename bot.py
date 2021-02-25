##!/usr/bin/python3.6
# -*- coding: utf-8 -*-

import time
import sqlite3
import praw
import traceback
import requests
import re

from config import *

class Bot:

	def __init__(self,debug=False):
		self.running = True
		self.tickersFound = set()
		self.startTime = time.time()
		self.lastTallyReport = time.time()
		self.debug = debug
		self.lastErrorNotif = 0

		self.initWords()
		self.initdb()

		if debug:
			return

		self.initReddit()
		self.run()


	def log(self, content):
		if self.debug:
			print(content)


	def run (self):
		self.log("running...")

		subCommentStream = self.r.subreddit(SUBREDDIT).stream.comments(skip_existing=True,pause_after=-1)
		subPostStream = self.r.subreddit(SUBREDDIT).stream.submissions(skip_existing=True,pause_after=-1)

		while self.running:

			try:
				for comment in subCommentStream:
					if comment is None:
						break
					self.onSubComment(comment)

			except Exception as e:
				self.handleRuntimeError(e)

			self.log('=== END OF COMMENTS ===')

			try:
				for post in subPostStream:
					if not self.running or post is None:
						break
					self.onSubPost(post)

			except Exception as e:
				self.handleRuntimeError(e)

			self.log('=== END OF POSTS ===')	

		self.log("running stopped!")


	def onSubComment(self, comment):
		b = comment.body[:40]+'..' if len(comment.body) > 40 else comment.body
		self.log("c "+comment.id+": "+ascii(b))

		tickers = self.tickerTest(comment.body)

		if len(tickers) > 0:
			self.log("ticker: "+' '.join([t['ticker'] for t in tickers]))
			self.saveTickerMentions(comment.author.name, tickers)
			self.log('-')


	def onSubPost(self, post):
		b = post.title[:40]+'..' if len(post.title) > 40 else post.title
		self.log("p "+post.id+": "+ascii(b))

		tickers = self.tickerTest(post.title) + self.tickerTest(post.selftext)

		if len(tickers) > 0:
			self.log("ticker: "+' '.join([t['ticker'] for t in tickers]))
			self.saveTickerMentions(post.author.name, tickers)
			self.log('-')


	def tickerTest(self, content):

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
		if len(ticker_names) > 0:
			self.log("ticker names: "+", ".join(ticker_names))
		for tn in ticker_names:
			tickers.update(self.con.execute("SELECT symbol FROM tickers WHERE name = ? LIMIT 1", [tn]).fetchone())

		self.tickersFound.update(tickers)

		if time.time() - self.lastTallyReport > 60:
			self.lastTallyReport = time.time()
			self.log("=====")
			self.log("TALLY REPORT: ")
			self.log("count: "+str(len(self.tickersFound)))
			self.log("tickers: ")
			self.log(self.tickersFound)

		# make them objs w/ tag info
		tickers = [{'ticker':x, 'is_over':0, 'is_crypto':0, 'was_tagged':(1 if x in tagged_content else 0)} for x in tickers]

		return tickers


	def saveTickerMentions(self, author, tickers):
		for ticker in tickers:
			# todo: this happens beforehand
			blacklisted = 1 if ticker['is_over'] == 1 or ticker['is_crypto'] == 1 else 0
			self.con.execute("INSERT INTO ticker_mentions (ticker, user, blacklisted, time_created, tagged) VALUES (?,?,?,?,?)", [ticker['ticker'], author, blacklisted, round(time.time())*1000, ticker['was_tagged']])
		self.con.commit()


	def handleRuntimeError(self, error):
		if False:
			self.running = False

		if time.time() - self.lastErrorNotif > 360:
			self.notifyError(error)
		
		self.con.execute("INSERT INTO bot_errors (info, time_created) VALUES (?, ?)", [str(error), round(time.time()*1000)])
		self.con.commit()

		self.log(traceback.format_exc())
		self.log(error)


	def notifyError(self, error):
		if NOTIFY == '':
			self.log("NOTIFY not set")
			return
		self.r.redditor(NOTIFY).message("encountered an error",str(error))


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
		self.ticker_names = set([t[1] for t in tickers if str(t[1]).upper() not in self.words])

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