#!/usr/bin/python3

print("Content-Type: text/plain;charset=utf-8")
print()

print("pennystock bot info will go here")
print()

import sqlite3
import time

con = sqlite3.connect("/var/www/bot/database.db")

c = con.cursor()
c.execute("SELECT * FROM tickers")
item = c.fetchone()
print(item)
print("sleeping 60s but cursor isn't closed...")
time.sleep(60)
print("done")
