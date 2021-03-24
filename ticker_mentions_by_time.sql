WITH alltickers AS (
	SELECT ticker FROM (SELECT ticker FROM ticker_mentions 
	WHERE time_created > strftime('%s','now')*1000 - 1000*60*60*24
	GROUP BY ticker
	ORDER BY COUNT(rowid) DESC
	LIMIT 100)

	UNION SELECT ticker FROM (SELECT ticker FROM ticker_mentions 
	WHERE time_created > strftime('%s','now')*1000 - 1000*60*60*24*7
	GROUP BY ticker
	ORDER BY COUNT(rowid) DESC
	LIMIT 100)

	UNION SELECT ticker FROM (SELECT ticker FROM ticker_mentions 
	WHERE time_created > strftime('%s','now')*1000 - 1000*60*60*24*14
	GROUP BY ticker
	ORDER BY COUNT(rowid) DESC
	LIMIT 100)

	UNION SELECT ticker FROM (SELECT ticker FROM ticker_mentions 
	WHERE time_created > strftime('%s','now')*1000 - 1000*60*60*24*30
	GROUP BY ticker
	ORDER BY COUNT(rowid) DESC
	LIMIT 100)

	UNION SELECT ticker FROM (SELECT ticker FROM ticker_mentions 
	GROUP BY ticker
	ORDER BY COUNT(rowid) DESC
	LIMIT 100)
)

SELECT 
	alltickers.ticker AS ticker,
	oneday.counter AS oneday,
	sevday.counter AS sevday,
	ftnday.counter AS ftnday,
	thrday.counter AS thrday,
	altime.counter AS altime

FROM 
	alltickers

	LEFT OUTER JOIN (	
		SELECT ticker, COUNT(rowid) AS counter FROM ticker_mentions 
			WHERE ticker IN alltickers
			AND time_created > strftime('%s','now')*1000 - 1000*60*60*24
		GROUP BY ticker
		ORDER BY counter DESC
	) oneday ON alltickers.ticker = oneday.ticker

	LEFT OUTER JOIN (	
		SELECT ticker, COUNT(rowid) AS counter FROM ticker_mentions 
			WHERE ticker IN alltickers
			AND time_created > strftime('%s','now')*1000 - 1000*60*60*24*7
		GROUP BY ticker
		ORDER BY counter DESC
	) sevday ON alltickers.ticker = sevday.ticker

	LEFT OUTER JOIN (	
		SELECT ticker, COUNT(rowid) AS counter FROM ticker_mentions 
			WHERE ticker IN alltickers
			AND time_created > strftime('%s','now')*1000 - 1000*60*60*24*14
		GROUP BY ticker
		ORDER BY counter DESC
	) ftnday ON alltickers.ticker = ftnday.ticker

	LEFT OUTER JOIN (	
		SELECT ticker, COUNT(rowid) AS counter FROM ticker_mentions 
			WHERE ticker IN alltickers
			AND time_created > strftime('%s','now')*1000 - 1000*60*60*24*30
		GROUP BY ticker
		ORDER BY counter DESC
	) thrday ON alltickers.ticker = thrday.ticker

	LEFT OUTER JOIN (	
		SELECT ticker, COUNT(rowid) AS counter FROM ticker_mentions 
			WHERE ticker IN alltickers
		GROUP BY ticker
		ORDER BY counter DESC
	) altime ON alltickers.ticker = altime.ticker
