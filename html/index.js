
userData = null;
tickerData = null;
cloudsData = null;
mostRecentQuery = null;

$(document).ready(function(){

	getLastSeen();
	readyListeners("nav");
	setHashHistory();

});

function buildUserList(){

	//console.log('bUL');

	userData = "loading";

	$.getJSON("api.py?mode=users", function(data){

		//console.log(data);
		if (data.hasOwnProperty('error') && data['error'] == "database locked"){
			$('#users .container').html("error fetching data; refresh to try again");
			return;
		}

		//data = $.parseJSON(data);

		// to sort by recency just remove this
		/*data.sort(function(a,b){
			return a['mention_count'] > b['mention_count'] ? -1 : 1;
		});*/
		
		html = "<div class='table-responsive'><table id='users-table' class='table'>";
		html += "<thead><tr><th scope='col'>User</th><th scope='col'># of Mentions</th><th scope='col'>Acct Created</th><th scope='col'>Tickers</th></tr></thead><tbody>";
		for(var i = 0; i < data.length; i++){
			html += parseUserData(data[i]);
		}
		html += "</tbody></table></div>";

		$('#users .container').html(html);

		userData = "done";
		readyListeners("users ready");

	});
}

function parseUserData(data){
	tickers = "";
	data['mentions'].sort(function(a,b){
		return a['rawtime'] > b['rawtime'] ? -1 : 1;
	});
	for (var j = 0; j < data['mentions'].length; j++){
		mention = data['mentions'][j];
		count = mention['count'] > 1 ? " x"+mention['count'] : "";
		tag = mention['link'] ? "a" : "span";
		href = mention['link'] ? "href='"+mention['link']+"' target='_blank'" : "";
		tickers += " <span class='commaMe'><"+tag+" title='"+mention['time']+"' class='tickerSymbol' "+href+">"+mention['ticker']+"</"+tag+">"+count+"</span>";
	}
	return "<tr class='userListItem'><td><a href='https://reddit.com/u/"+data['name']+"' class='username'>"+data['name']+"</a></td><td>"+data['mention_count']+"</td><td><button class='btn btn-secondary btn-sm ageFetcher' data-user='"+data['name']+"'>fetch</button></td><td>"+tickers+"</td></tr>";
}

function buildTickerList(){
	//console.log('bTL');

	tickerData = "loading";

	$.getJSON("api.py?mode=tickers", function(data){

		// console.log(data);

		printTickerData(data, "mention_count");
		tickerData = data;
		readyListeners("tickers ready");
	});
}

function buildClouds(){
	console.log('bC')

	if (tickerData === null || tickerData == "loading"){
		tickerData = "loading";
		$.getJSON("api.py?mode=tickers", function(data){
			console.log(data);
			formatCloudsData(data);
			printClouds();
			printTickerData(data, "mention_count");
			readyListeners("tickers ready");
			tickerData = data;
		})
	} else{
		formatCloudsData(tickerData)
		setTimeout(printClouds, 500)
	}
}

function formatCloudsData(data){
	cloudsData = {'total':[],'24h':[],'7d':[],'14d':[],'30d':[]}

	for (var i=0; i<data.length; i++){
		for(var time in data[i]){
			if (time == 'ticker' || data[i][time] == '')
				continue
			tname = time == 'mention_count' ? 'total' : time;
			weight = data[i][time] == '' ? 0 : data[i][time];

			cloudsData[tname].push({word: data[i]['ticker'], weight: weight});
		}
	}

	for (var time in cloudsData){
		cloudsData[time].sort(function(a,b){return a.weight > b.weight ? -1 : 1})
		cloudsData[time] = cloudsData[time].slice(0,199)
	}
}

function printClouds(){

	if (window.location.hash && window.location.hash !== '#clouds'){
		setTimeout(printClouds, 500)
		return
	}

	data = cloudsData;
	$('#clouds .container-fluid').html('');

	html = "<div class='card-group'>";
	for (var time in cloudsData)
		html += printCloud(time);
	html += "</div>";
	$('#clouds .container-fluid').html(html);

	for (var time in cloudsData){
		if (!cloudsData[time].length)
			continue
		$('#wCloud-'+time).jQWCloud({
			title: time,
			words: cloudsData[time],
			padding_left: 1
		})
	}
}

function printCloud(title){
	html = "<div class='card'>"
	html += "<div class='card-body'>";
	html += "<h5 class='card-title'>"+title+"</h5>";
	html += "<div class='wCloud' id='wCloud-"+title+"' style='height:400px;line-height:400px;'>&nbsp;</div>";
	html += "</div></div>";
	return html
}

function getLastSeen(){
	$.getJSON("api.py?mode=lastSeen", function(data){
		if (data == "database is locked"){
			$('#lastSeen').html("error fetching data; refresh to try again");
			return;
		}
		$('#lastSeen').html("last mention logged "+data['lastSeen']);
	});
}

function getWhoMentioned(event){
	let mytd = $(event.target).closest('td');
	mytd.html('loading...');
	name = $(event.target).attr('data-ticker');
	//console.log(name);
	$.getJSON("api.py?mode=whoMentioned&ticker="+name, function(data){
		//console.log(data);
		mytd.html('')
		usersRow = "<tr class='tickerListItem'><td><a class='tickerName' style='display:none'>"+name+"</a></td><td colspan='6'>";
		for (var i=0; i<data.length; i++){
			count = data[i]['counter'] > 1 ? " x"+data[i]['counter'] : "";
			usersRow += "<span class='commaMe'><a title='"+data[i]['ago']+"' class='userTag' href='https://reddit.com/u/"+data[i]['user']+"' target='_blank'>"+data[i]['user']+"</a>"+count+"</span> ";
		}
		usersRow += "</td></tr>";
		mytd.closest('tr').after(usersRow);
	});
}


function printTickerData(data, by){
	data.sort(function(a,b){
		if (by == 'ticker')
			return a[by] <= b[by] ? -1 : 1;
		return a[by] > b[by] ? -1 : 1;
	});

	if (data.hasOwnProperty('error') && data['error'] == "database locked"){
		$('#users .container').html("error fetching data; refresh to try again");
		return;
	}
	
	html = "<div class='table-responsive'><table id='tickers-table' class='table'>";
	html += "<thead><tr><th scope='col' data-by='ticker'>Ticker</th><th scope='col' data-by='24h'>24h</th><th scope='col' data-by='7d'>7d</th><th scope='col' data-by='14d'>14d</th><th scope='col' data-by='30d'>30d</th><th scope='col' data-by='mention_count'>total</th><th scope='col'></th></tr></thead><tbody>";
	for(var i = 0; i < data.length; i++){
		html += "<tr class='tickerListItem'><td class='tickerName'>"+data[i]['ticker']+"</td><td>"+data[i]['24h']+"</td><td>"+data[i]['7d']+"</td><td>"+data[i]['14d']+"</td><td>"+data[i]['30d']+"</td><td>"+data[i]['mention_count']+"</td><td><button class='btn btn-secondary btn-sm whoFetcher' data-ticker='"+data[i]['ticker']+"'>Who?</button></td></tr>";
	}
	html += "</tbody></table></div>";

	$('#tickers .container').html(html);
}

function readyListeners(phase){

	if(phase == "nav"){
		$('#pbTabs a').unbind().click(navigateTab);
		$('#pbTabs a[href="'+location.hash+'"]').tab('show');
	}

	if(phase == "users ready"){
		// search listener
		if (tickerData != "loading")
			$('#searchbox').prop('disabled',false).unbind().on('input', filterFor);
		// age button listener
		$('.ageFetcher').unbind().click(fetchAge);
	}

	if(phase == "tickers ready"){
		// search listener
		if (userData != "loading")
			$('#searchbox').prop('disabled',false).unbind().on('input', filterFor);
		// who button listener
		$('.whoFetcher').unbind().click(getWhoMentioned);
		// sort button listener
		$('#tickers th').unbind().click(sortTickers);
	}
}


function sortTickers(event){
	printTickerData(tickerData, $(event.target).attr('data-by'));
	readyListeners("tickers ready");
}


function filterFor(event){
	cont = $(event.target).val();

	if (cont.length < 2)
		searchFilter(null, null);

	else if (cont.startsWith("$"))
		searchFilter(cont.substring(1), "ticker");

	else if (cont.length < 3)
		searchFilter(null, null);

	else if (cont.startsWith("u/"))
		searchFilter(cont.substring(2), "user");

	else if (cont.startsWith("/u/")){
		if (cont.length < 4)
			searchFilter(null,null)
		else
			searchFilter(cont.substring(3), "user");
	}
	
	else
		searchFilter(cont, "both");
}

function fetchAge(event){
	let mytd = $(event.target).closest('td');
	mytd.html('loading...');
	let name = $(event.target).attr('data-user');
	$.getJSON("api.py?mode=age&user="+name, function(data){
		//console.log(name,data);
		mytd.html(data['created']);
	});
}

function searchFilter(query, by){
	if (by === null){
		$(".userListItem").show();
		$('.tickerListItem').show();
		$('#userSearchInfo').hide();
		return;
	}

	$('.userListItem').hide();
	$('.tickerListItem').hide();

	if (by == "ticker" || by == "both"){
		$("#users .tickerSymbol").filter(function(){return $(this).text().toLowerCase() == query.toLowerCase()}).closest(".userListItem").show();
		$("#tickers .tickerName").filter(function(){return $(this).text().toLowerCase().includes(query.toLowerCase())}).closest(".tickerListItem").show();
	}

	if (by == "user" || by == "both")
		$("#users .username").filter(function(){return $(this).text().toLowerCase().includes(query.toLowerCase())}).closest(".userListItem").show();

	getUserSearch(query, by);
}

function getUserSearch(query, by){
	// query db, set most recent query glob, display loading notice on user page
	$('#userSearchInfo').text("Fetching more data...").show()
	mostRecentQuery = query;

	$.getJSON("api.py?mode=search-user&by="+by+"&query="+query, function(data){
		if (mostRecentQuery !== query)
			return;
		console.log(data);

		for(var i=0; i<data.length; i++){
			if ($('.ageFetcher[data-user='+data[i]['name']+']').length > 0)
				continue;
			$('#users-table tbody').append(parseUserData(data[i]));
		}

		readyListeners("users ready");
		$('#userSearchInfo').hide()
	});
}

/// NEW NAVIGATION

function setHashHistory(){
	// on page load, show the appropriate tab
	var hash = window.location.hash;
	if (hash && hash != '#') {
	    $('#pbTabs a[href="'+hash+'"]').tab('show');
	    getTab(hash.substring(1,hash.length));
	} else {
		getTab('clouds');
	}
	
	// if history is modified/navigated, show the active tab
	window.addEventListener("popstate", function(e){
		var activeTab = $('#pbTabs a[href="'+location.hash+'"]');
		if (activeTab.length)
			activeTab.tab('show');
	});
}

function navigateTab(e){
	if(history.pushState)
		history.pushState(null,null,e.target.hash);
	else
		window.location.hash = e.target.hash;
	getTab(e.target.hash.substring(1,e.target.hash.length));
}

function getTab(tab){
	if (tab == 'users' && userData === null){
		$('#searchbox').prop('disabled', true)
		buildUserList();
	}
	if (tab == 'tickers' && tickerData === null){
		$('#searchbox').prop('disabled', true)
		buildTickerList();
	}
	if (tab == 'clouds' && cloudsData === null){
		buildClouds();
	}
}
