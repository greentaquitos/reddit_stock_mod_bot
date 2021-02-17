
import time
import sqlite3
import praw
import traceback

from config import *

class Bot:

	def __init__(self,debug=False):
		self.running = True
		self.initdb()
		self.initReddit()
		self.run()


	def run (self):
		print("running...")

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

			try:
				for post in subPostStream:
					if not self.running or post is None:
						break
					self.onSubPost(post)

			except Exception as e:
				self.handleRuntimeError(e)

		print("running stopped!")


	def onSubComment(self, comment):
		print(comment.body)


	def onSubPost(self, post):
		print(post.title)


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
			else:
				print("Error with initdb: "+str(e))
				self.running = False

	def initReddit(self):
		self.r = praw.Reddit(
			client_id = CLIENT_ID,
			client_secret = CLIENT_SECRET,
			password = BOT_PASSWORD,
			user_agent = USER_AGENT,
			username = BOT_NAME
		)
		print("logged in as "+self.r.user.me().name)
				

	def createdb(self):
		con = self.con
		tables = [
			"users (id int PRIMARY KEY, name string UNIQUE, account_age int, whitelisted int, time_created int)",
			"ticker_mentions (id int PRIMARY KEY, ticker string, user string, blacklisted int, time_created int)",
			"bot_actions (id int PRIMARY KEY, type string, user string, note string, time_created int)",
			"bot_errors (id int PRIMARY KEY, info string, time_created int)",
			"outside_activity (id int PRIMARY KEY, subreddit string, user string, time_created int)",
			"test_table (id int PRIMARY KEY, test_data string)"
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