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
import pytz
import logging

from config import *

class Bot:

	def __init__(self,debug=False):
		# set up logging
		level = logging.DEBUG if debug else logging.INFO
		logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', datefmt='%Y-%m-%d %I:%M:%S %p', level=level)
		
		# run config
		self.running = True
		self.debug = debug
		self.nytime = pytz.timezone('US/Eastern')
		self.utc = pytz.utc

		# track error handling
		self.lastErrorNotif = 0
		self.lastErrorDelay = 0
		self.lastResetTime = 0
		self.actionQueue = []
		self.timedEvents = []

		# init data
		self.initWords()
		self.initdb()
		self.initReddit()
		self.scheduleTickerUpdate()

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

			try:
				for event in self.timedEvents[:]:
					if self.running == False:
						break
					if event['time'] > datetime.datetime.today().astimezone(self.utc):
						continue
					self.timedEvents.remove(event)
					if event['name'] == 'updateTickerList':
						self.updateTickerList()
						self.scheduleTickerUpdate()

			except Exception as e:
				self.handleRuntimeError(e)

			logging.debug('=== END OF TIMERS ===')

		logging.warning("running stopped!")


	def onSubComment(self, comment):
		b = comment.body[:40]+'..' if len(comment.body) > 40 else comment.body
		logging.info("c "+comment.id+": "+ascii(b))

		tickers = self.getTickersFromString(comment.body)
		self.saveTickerMentions(comment, tickers)
		
		if any(t['is_over'] for t in tickers):
			self.flagContent(comment)
		

	def onSubPost(self, post):
		b = post.title[:40]+'..' if len(post.title) > 40 else post.title
		logging.info("p "+post.id+": "+ascii(b))

		tickers = self.getTickersFromString(post.title+' '+post.selftext)
		self.engageWith(post, tickers)
		self.saveTickerMentions(post, tickers)

		if any(t['is_over'] for t in tickers):
			self.flagContent(post)


	def flagContent(self, content):
		logging.debug("flagContent")


	def isPennyStock(self, ticker):
		logging.debug("isPennyStock? "+ticker)
		month_ago = round(time.time()*1000 - (1000*60*60*24*30))

		# we've logged it as under 5 in the past month

		cur = self.con.execute("SELECT * FROM ticker_prices WHERE time_created > ? AND symbol = ? AND price < 5 LIMIT 1", [month_ago, ticker])
		logged_low = len(cur.fetchall()) > 0
		cur.close()

		if logged_low:
			logging.debug("data found: yes")
			return True

		# we haven't logged it recently

		price = self.getPriceFromMarketstack(ticker)

		if price == None:
			logging.debug("no price data: yes?")
			return True

		cur = self.con.execute("INSERT INTO ticker_prices (symbol, price, time_created) VALUES (?,?,?)", [ticker, str(price['rn']), round(time.time()*1000)])
		self.con.commit()
		cur.close()

		if price['30dlow'] < 5:
			logging.debug("data requested: yes")
			return True
		else:
			logging.debug("data requested: no")
			return False


	def getPriceFromMarketstack(self, ticker):
		p = {"access_key": MARKETSTACK_API_KEY, "symbols":ticker, "limit":20}
		r = requests.get("http://api.marketstack.com/v1/eod", params=p)
		rj = r.json()
		
		if len(rj['data']) < 1:
			self.handleRuntimeError("no price data for ticker: "+ticker)
			return None

		return {'30dlow': min(d['low'] for d in rj['data']), 'rn':rj['data'][0]['low']}


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

		self.logBotAction("engageWith", post.author.name, post.permalink)


	def makeMentionTable(self, author, tickers):
		cur = self.con.execute("SELECT ticker, COUNT(rowid) as counter FROM ticker_mentions WHERE user = ? AND content_type = 'c' GROUP BY ticker ORDER BY counter DESC", [author.name])
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
		tickers = [{'ticker':x, 'is_over':(0 if self.isPennyStock(x) else 1), 'is_crypto':0, 'was_tagged':(1 if x in tagged_content else 0)} for x in set(tickers)]

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
			else:
				logging.error("Error with initdb: "+str(e))
				self.running = False

		self.initTickerSets()
	

	def initTickerSets(self):
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


	def scheduleTickerUpdate(self):
		# nextTickerTime = self.getNextTickerTime()		
		# nextTickerTime = now_utc + datetime.timedelta(minutes=2)
		
		now_utc = datetime.datetime.today().astimezone(self.utc)

		# update ticker list daily at slowest hour or monthly for the test bot
		if MARKETSTACK_SUB:
			nextTickerTime = (now_utc + datetime.timedelta(1)).replace(hour=6, minute=5) if now_utc.hour >= 6 else now_utc.replace(hour=6, minute=5)
		else:
			nextTickerTime = (now_utc.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)

		self.timedEvents.append({'name':"updateTickerList",'time':nextTickerTime})

	# gets next open or close -- unused
	def getNextTickerTime(self):
		if MARKETSTACK_SUB:
			# next open or close
			ny_now = datetime.datetime.today().astimezone(self.nytime)
			
			target_hour = 9 if ny_now.hour > 15 or ny_now.weekday() > 4 else 16
			target_minute = 35 if target_hour == 9 else 5

			if target_hour == 9:
				ny_now = self.nytime.normalize(ny_now + datetime.timedelta(1))

			while ny_now.weekday() > 4 or (ny_now.weekday() == 4 and ny_now.hour > 15):
				ny_now = self.nytime.normalize( ny_now + datetime.timedelta(1) )

			return ny_now.replace(hour=target_hour, minute=target_minute)
		
		else:
			# first of the month, not picky about time
			return (datetime.datetime.today().replace(day=1) + datetime.timedelta(days=32)).replace(day=1).astimezone(self.utc)


	def updateTickerList(self):
		logging.info("updating ticker list (this may take a while)...")

		total = 1001
		i = 0

		while 1000*i < int(total):
			p = {"access_key": MARKETSTACK_API_KEY, "limit":"1000"}
			total = rj['pagination']['total'] if i == 1 else total
			p["offset"] = str(1000*i)

			r = requests.get("http://api.marketstack.com/v1/tickers", params=p)
			rj = r.json()
			tickers = [(t['symbol'], t['name'], round(time.time()*1000)) for t in rj['data']]
			
			cur = self.con.executemany("INSERT OR IGNORE INTO tickers (symbol, name, time_created, is_crypto) VALUES (?,?,?, 0)", tickers)
			logging.debug("got "+p['offset']+" tickers out of "+str(total)+"; saved "+str(cur.rowcount))
			self.con.commit()
			cur.close()

			i+=1

		logging.info("built ticker list")
		self.logBotAction("updateTickerList", None, None)
		self.initTickerSets()


	def logBotAction(self, action, user, note):
		cur = self.con.execute("INSERT INTO bot_actions (type, time_created) VALUES (?,?)", [action, round(time.time()*1000)])
		self.con.commit()
		cur.close()


	# get all ticker prices -- unused
	def updateTickerPrices(self):
		logging.info("updating ticker prices...")

		total = 101
		i = 0

		tod = datetime.datetime.today().astimezone(self.nytime)

		endpoint = "/eod/latest" if tod.hour > 16 or tod.hour < 9 or (tod.hour == 9 and tod.minute < 30) or tod.weekday() > 4 else "/intraday/latest"
		ttype = "close" if endpoint == "/eod/latest" else "open"
		tlist = list(self.tickers)

		cur = self.con.cursor()

		while 100*i < int(total):
			offset = 100*i
			logging.debug("getting tickers "+str(offset)+" thru "+str(offset+100))
			tickers = tlist[offset:offset+100]
			symbols = ','.join([t for t in tickers])			
			p = {"access_key": MARKETSTACK_API_KEY,"symbols":symbols}
			# only do 2 pages if we don't have a sub / using test account
			total = rj['pagination']['total'] if i == 1 and MARKETSTACK_SUB else total
			r = requests.get("http://api.marketstack.com/v1"+endpoint,params=p)
			rj = r.json()
			for ticker in rj['data']:
				cur.execute("INSERT INTO ticker_info (symbol, time_created, price, type) VALUES (?,?,?,?)", [ticker['symbol'],round(time.time()*1000),ticker[ttype],ttype])
			i += 1

		self.con.commit()
		cur.close()

		logging.info("updated ticker prices")


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
			"ticker_prices (symbol string, price string, price_type string, time_created int)",
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


b = Bot()