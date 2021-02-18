##!/usr/bin/python3.6
# -*- coding: utf-8 -*-

import time
import sqlite3
import praw
import traceback
import requests

from config import *

class Bot:

	def __init__(self,debug=False):
		self.running = True
		self.initdb()
		self.initReddit()
		self.run()


	def run (self):
		print("running...")

		#subCommentStream = self.r.subreddit(SUBREDDIT).stream.comments(skip_existing=True,pause_after=-1)
		#subPostStream = self.r.subreddit(SUBREDDIT).stream.submissions(skip_existing=True,pause_after=-1)
		
		subCommentStream = self.r.subreddit("wallstreetbets").stream.comments(skip_existing=True,pause_after=-1)
		subPostStream=self.r.subreddit("wallstreetbets").stream.submissions(skip_existing=True,pause_after=-1)

		while self.running:

			try:
				for comment in subCommentStream:
					if comment is None:
						break
					self.onSubComment(comment)

			except Exception as e:
				self.handleRuntimeError(e)

			print('=== END OF COMMENTS ===')

			try:
				for post in subPostStream:
					if not self.running or post is None:
						break
					self.onSubPost(post)

			except Exception as e:
				self.handleRuntimeError(e)

			print('=== END OF POSTS ===')	

		print("running stopped!")


	def onSubComment(self, comment):
		b = comment.body[:40]+'..' if len(comment.body) > 40 else comment.body
		print("c "+comment.id+": "+ascii(b))

		tickers = self.tickerTest(comment.body)
		if len(tickers) > 0:
			print("ticker: "+' '.join(tickers))


	def onSubPost(self, post):
		b = post.title[:40]+'..' if len(post.title) > 40 else post.title
		print("p "+post.id+": "+ascii(b))

		tickers = self.tickerTest(post.title) + self.tickerTest(post.selftext)
		if len(tickers) > 0:
			print("ticker: "+' '.join(tickers))


	def tickerTest(self, content):

		#todo - narrow results 
			# filter common words unless preceded by $ and in caps ?
			# filter all unless in caps ?
			# only save tickers from particular markets ?

		t1 = round(time.time()*1000)
		content = set(content.upper().split())
		tickers = list(self.tickers & content)
		t3 = round(time.time()*1000)
		print(str(t3-t1))
		return tickers


	def handleRuntimeError(self, error):
		if False:
			self.running = False

		if False:
			self.notifyError(error)
		
		self.con.execute("INSERT INTO bot_errors (info, time_created) VALUES (?, ?)", [str(error), round(time.time()*1000)])
		self.con.commit()

		# print(traceback.format_exc())
		print(error)


	def notifyError(self, error):
		print("notifyError() not developed")


	def initdb(self):
		con = self.con = sqlite3.connect("database.db")

		try:
			con.execute("SELECT * FROM test_table LIMIT 1")
		except sqlite3.OperationalError as e:
			if str(e).startswith("no such table"):
				self.createdb()
				self.updateTickerList()
			else:
				print("Error with initdb: "+str(e))
				self.running = False

		tickers = self.con.execute("SELECT symbol FROM tickers").fetchall()
		self.tickers = set([t[0] for t in tickers])

	def initReddit(self):
		self.r = praw.Reddit(
			client_id = CLIENT_ID,
			client_secret = CLIENT_SECRET,
			password = BOT_PASSWORD,
			user_agent = USER_AGENT,
			username = BOT_NAME
		)
		print("logged in as "+self.r.user.me().name)


	def updateTickerList(self):
		print("updating ticker list (this may take a while)...")

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
				self.con.execute("INSERT OR IGNORE INTO tickers (symbol, name, time_created) VALUES (?,?,?)", [ticker['symbol'],ticker['name'],round(time.time()*1000)])
			i+=1

		self.con.commit()

		print("built ticker list")


	def createdb(self):
		print("building database...")
		con = self.con

		tables = [
			"users (name string UNIQUE, account_age int, whitelisted int, time_created int)",
			"ticker_mentions (ticker string, user string, blacklisted int, time_created int)",
			"bot_actions (type string, user string, note string, time_created int)",
			"bot_errors (info string, time_created int)",
			"outside_activity (subreddit string, user string, time_created int)",
			"tickers (symbol string UNIQUE, name string, last_close string, time_updated int, time_created int)",
			"test_table (test_data string)"
		]

		for t in tables:
			try:
				con.execute("CREATE TABLE IF NOT EXISTS "+t)
			except Exception as e:
				print("Error with SQL:\n"+t+"\n"+str(e))
				self.running = False
				break

		con.commit()


b = Bot()