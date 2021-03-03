
$(document).ready(function(){

	buildList();
	getLastSeen();

});

function buildList(){

	$('main').html('loading...');

	$.getJSON("api.py", function(data){

		console.log(data);
		//data = $.parseJSON(data);

		data.sort(function(a,b){
			return a['mentions'].length > b['mentions'].length ? -1 : 1;
		});
		
		html = "<div class='table-responsive'><table id='main-table' class='table'>";
		html += "<thead><tr><th scope='col'>User</th><th scope='col'># of Mentions</th><th scope='col'>Acct Created</th><th scope='col'>Tickers</th></tr></thead><tbody>";
		for(var i = 0; i < data.length; i++){
			tickers = "";
			data[i]['mentions'].sort(function(a,b){
				return a['rawtime'] > b['rawtime'] ? -1 : 1;
			});
			for (var j = 0; j < data[i]['mentions'].length; j++){
				count = data[i]['mentions'][j]['count'] > 1 ? " x"+data[i]['mentions'][j]['count'] : "";
				tickers += "<span class='commaMe'><span title='"+data[i]['mentions'][j]['time']+"' class='tickerSymbol'>"+data[i]['mentions'][j]['ticker']+"</span>"+count+"</span>";
			}
			html += "<tr class='tickerListItem'><td><a href='https://reddit.com/u/"+data[i]['name']+"' class='username'>"+data[i]['name']+"</a></td><td>"+data[i]['mentions'].length+"</td><td><button class='btn btn-secondary btn-sm ageFetcher' data-user='"+data[i]['name']+"'>fetch</button></td><td>"+tickers+"</td></tr>";
		}
		html += "</tbody></table></div>";

		$('main').html(html);

		readyListeners();

	});
}

function getLastSeen(){
	$.getJSON("api.py?lastSeen=1", function(data){
		$('#lastSeen').html("last mention logged "+data['lastSeen']);
	});
}

function readyListeners(){

	// search listener
	$('#searchbox').prop('disabled',false).on('input', function(){
		cont = $(this).val();

		if (cont.length < 2)
			searchFilter(null, null);

		else if (cont.startsWith("$"))
			searchFilter(cont.substring(1), "ticker");

		else if (cont.startsWith("u/"))
			searchFilter(cont.substring(2), "user");

		else if (cont.startsWith("/u/"))
			searchFilter(cont.substring(3), "user");
		
		else
			searchFilter(cont, "both");

	});

	// age button listener
	$('.ageFetcher').click(function(){
		let mytd = $(this).closest('td');
		mytd.html('loading...');
		name = $(this).attr('data-user');
		$.getJSON("api.py?age="+name, function(data){
			//console.log(data);
			mytd.html(data['created']);
		});
	});
}

function searchFilter(query, by){
	if (by === null){
		$(".tickerListItem").show();
		return;
	}

	$('.tickerListItem').hide();

	if (by == "ticker" || by == "both")
		$(".tickerSymbol").filter(function(){return $(this).text().toLowerCase() == query.toLowerCase()}).closest(".tickerListItem").show();

	if (by == "user" || by == "both")
		$(".username").filter(function(){return $(this).text().toLowerCase().includes(query.toLowerCase())}).closest(".tickerListItem").show();

}

