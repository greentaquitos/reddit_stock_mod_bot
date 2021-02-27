
$(document).ready(function(){

	buildList();
	getLastSeen();

});

function buildList(){

	$('main').html('loading...');

	$.getJSON("api.py", function(data){

		//console.log(data);
		data = $.parseJSON(data);

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
			for (var j = 0; j < data[i]['mentions'].length; j++)
				tickers += "<span title='"+data[i]['mentions'][j]['time']+"' class='commaMe'>"+data[i]['mentions'][j]['ticker']+"</span>";
			html += "<tr><td>"+data[i]['name']+"</td><td>"+data[i]['mentions'].length+"</td><td><button class='btn btn-secondary btn-sm ageFetcher' data-user='"+data[i]['name']+"'>fetch</button></td><td>"+tickers+"</td></tr>";
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

function getAge(element){

}
