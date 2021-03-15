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
import logging

from config import *

class Bot:

	def __init__(self,debug=False):
		# set up logging
		logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', datefmt='%Y-%m-%d %I:%M:%S %p', level=logging.INFO)
		if debug:
			logging.basicConfig(level=logging.DEBUG)
		
		# run config
		self.running = True
		self.debug = debug

		# track error handling
		self.lastErrorNotif = 0
		self.lastErrorDelay = 0
		self.lastResetTime = 0
		self.actionQueue = []

		# init data
		self.initWords()
		self.initdb()
		self.initReddit()

		if debug:
			return

		self.run()


	def run (self):
		logging.debug("running...")

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

			logging.debug('=== END OF COMMENTS ===')

			if not self.running:
				break

			try:
				for post in subPostStream:
					if not self.running or post is None or post.author.name == BOT_NAME:
						break
					self.onSubPost(post)

			except Exception as e:
				self.handleRuntimeError(e)

			logging.debug('=== END OF POSTS ===')

			try:
				for item in self.actionQueue[:]:
					if self.running == False or time.time() - item['time'] < 0:
						break
					self.actionQueue.remove(item)
					if item['action'] == 'engageWith':
						self.engageWith(item['args'][0], item['args'][1])
	
			except Exception as e:
				self.handleRuntimeError(e)

			logging.debug('=== END OF QUEUE === ' + str(len(self.actionQueue)))

		logging.warning("running stopped!")


	def onSubComment(self, comment):
		b = comment.body[:40]+'..' if len(comment.body) > 40 else comment.body
		logging.info("c "+comment.id+": "+ascii(b))

		tickers = self.getTickersFromString(comment.body)
		self.saveTickerMentions(comment, tickers)
		

	def onSubPost(self, post):
		b = post.title[:40]+'..' if len(post.title) > 40 else post.title
		logging.info("p "+post.id+": "+ascii(b))

		tickers = self.getTickersFromString(post.title+' '+post.selftext)
		self.engageWith(post, tickers)
		self.saveTickerMentions(post, tickers)


	def engageWith(self, post, tickers):
		# check for flair
		if hasattr(post,'link_flair_template_id') and post.link_flair_template_id in FLAIRS_TO_IGNORE:
			return

		# wait a minute to respond to mod posts to see if they get distinguished / stickied
		if SUBREDDIT in post.author.moderated():
			if time.time() - post.created_utc < 60:
				logging.info("delaying post "+post.id)
				self.actionQueue.append({'action':'engageWith','args':[post, tickers],'time':time.time()+60})
				return
			else:
				logging.info("came back to post "+post.id)
				post = self.r.submission(post.id)

		# don't respond to distinguished / sticked posts
		if post.distinguished or post.stickied:
			return				

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
		
		if len(responses) < 1:
			return

		if len(tickers) > 0 or not table == None or len(BOT_SIGNATURE) > 0:
			responses.append('-----')

		if len(tickers) > 0 or not table == None:
			responses.append(POSTER_INFO_TEMPLATE_MENTIONS)

		if len(BOT_SIGNATURE) > 0:
			responses.append(BOT_SIGNATURE)

		response = '\n\n'.join(responses)

		# reply + sticky
		sticky = post.reply(response)
		sticky.mod.distinguish(how="yes",sticky=True)


	def makeMentionTable(self, author, tickers):
		cur = self.con.execute("SELECT ticker, COUNT(rowid) as counter FROM ticker_mentions WHERE user = ? GROUP BY ticker ORDER BY counter DESC", [author.name])
		mentions = cur.fetchall()
		cur.close()

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
			cur = self.con.execute("SELECT symbol FROM tickers WHERE name = ? LIMIT 1", [tn])
			t = cur.fetchone()
			cur.close()

			tickers.update(t)

		# make them objs w/ tag info
		tickers = [{'ticker':x, 'is_over':0, 'is_crypto':0, 'was_tagged':(1 if x in tagged_content else 0)} for x in set(tickers)]

		return tickers


	def saveTickerMentions(self, content, tickers):
		if len(tickers) < 1:
			return

		cur = self.con.cursor()
		for ticker in tickers:
			user = content.author.name
			blacklisted = 1 if ticker['is_over'] == 1 or ticker['is_crypto'] == 1 else 0
			time_created = round(time.time())*1000
			tagged = ticker['was_tagged']
			content_type = 'c' if isinstance(content, praw.models.Comment) else 'p'
			content_id = content.permalink
			cur.execute("INSERT INTO ticker_mentions (ticker, user, blacklisted, time_created, tagged, content_type, content_id) VALUES (?,?,?,?,?,?,?)", [ticker['ticker'], user, blacklisted, time_created, tagged, content_type, content_id])

		self.con.commit()
		cur.close()

		logging.info("tickers: "+' '.join([t['ticker'] for t in tickers]))
		logging.info('-')


	def handleRuntimeError(self, error):
		infostring = str(type(error)) + ': ' + str(error)

		if not isinstance(error, sqlite3.OperationalError):
			self.saveError(infostring)

		logging.error(traceback.format_exc())

		if time.time() - self.lastErrorNotif > 1800:
			self.notifyError(infostring)

		if isinstance(error, prawcore.exceptions.ServerError) or isinstance(error, prawcore.exceptions.RequestException):
			self.resetStreamUntilFixed()


	def saveError(self, infostring):
		cur = self.con.execute("INSERT INTO bot_errors (info, time_created) VALUES (?, ?)", [infostring, round(time.time()*1000)])
		self.con.commit()
		cur.close()


	def resetStreamUntilFixed(self):
		self.running = False

		if self.lastErrorDelay == 0 or time.time() - self.lastResetTime > 256:
			self.lastErrorDelay = delay = 2
		elif self.lastErrorDelay < 128:
			self.lastErrorDelay = delay = self.lastErrorDelay*2
		else:
			delay = self.lastErrorDelay

		self.lastResetTime = time.time()

		logging.warning("Server Error: retrying in "+str(delay))
		time.sleep(delay)
		logging.warning("retrying")
		self.running = True
		self.initReddit()
		self.run()


	def notifyError(self, error):
		if NOTIFY == '':
			logging.warning("NOTIFY not set")
			return
		try:
			self.r.redditor(NOTIFY).message("encountered an error",str(error))
		except Exception as e:
			logging.error("ERROR NOTIFY FAILED")

		self.lastErrorNotif = time.time()


	def initdb(self):
		con = self.con = sqlite3.connect("database.db")

		try:
			cur = con.execute("SELECT * FROM test_table LIMIT 1")
			cur.close()
		except sqlite3.OperationalError as e:
			if str(e).startswith("no such table"):
				self.createdb()
				self.updateTickerList()
			else:
				logging.error("Error with initdb: "+str(e))
				self.running = False

		cur = self.con.execute("SELECT symbol,name FROM tickers WHERE symbol NOT LIKE '%.%' AND symbol IS NOT NULL AND name IS NOT NULL AND symbol != '' and name != ''")
		tickers = cur.fetchall()
		cur.close()

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
		logging.info("logged in as "+self.r.user.me().name)


	def initWords(self):
		self.words = open("resources/common_words.txt").read().splitlines()
		self.words = set([w.upper() for w in self.words])


	def updateTickerList(self):
		logging.info("updating ticker list (this may take a while)...")

		start_time = round(time.time()*1000)
		total = 1001
		i = 0

		cur = self.con.cursor()

		while 1000*i < int(total):
			p = {"access_key": MARKETSTACK_API_KEY, "limit":"1000"}
			total = rj['pagination']['total'] if i == 1 else total
			p["offset"] = str(1000*i)
			r = requests.get("http://api.marketstack.com/v1/tickers", params=p)
			rj = r.json()
			for ticker in rj['data']:
				cur.execute("INSERT OR IGNORE INTO tickers (symbol, name, time_created, is_crypto) VALUES (?,?,?, 0)", [ticker['symbol'],ticker['name'],round(time.time()*1000)])
			i+=1

		self.con.commit()
		cur.close()

		logging.info("built ticker list")


	def createdb(self):
		logging.info("building database...")
		con = self.con

		tables = [
			"users (name string UNIQUE, account_age int, whitelisted int, time_created int)",
			"ticker_mentions (ticker string, user string, blacklisted int, tagged int, time_created int, content_type string, content_id string)",
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
				logging.error("Error with SQL:\n"+t+"\n"+str(e))
				self.running = False
				break

		con.commit()


# b = Bot()