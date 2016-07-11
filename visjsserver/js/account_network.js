// (c) Bernhard Tittelbach, 2015-2016

Chart.types.Doughnut.extend({
	// Passing in a name registers this chart in the Chart namespace in the same way
	name: "DoughnutWithText",
	draw: function(arg) {
		Chart.types.Doughnut.prototype.draw.apply(this,[arg]);
		this.chart.ctx.font = "50px Calibri";
		textoffset=Math.floor(50/3)
		this.chart.ctx.fillStyle = "white";
		this.chart.ctx.textAlign = "center";
		this.chart.ctx.fillText(this.options.centerText,this.chart.canvas.width/2,this.chart.canvas.height/2+textoffset);
		return this;
	}
});

function clusterSubAccounts(network, mainaccount) {
	network.cluster({joinCondition:function(nodeOpts){
		return nodeOpts.label.search(mainaccount) == 0;
	},
	"clusterNodeProperties":{label:mainaccount+":..."},
	processProperties: function (clusterOptions,
		  childNodes, childEdges) {
		var totalMass = 0;
		var totalValue = 0;
		for (var i = 0; i < childNodes.length; i++) {
		  totalMass += childNodes[i].mass;
		  totalValue += childNodes[i].value ? childNodes[i].value : 0;
		}
		clusterOptions.mass = totalMass;
		if (totalValue > 0) {
		  clusterOptions.value = totalValue;
		}
		clusterOptions.group = childNodes[0].group;
		return clusterOptions;
	},
	"clusterEdgeProperties": {smooth:false}
	});
}

function httpGetJsonAsync(theUrl, callback)
{
	var xmlHttp = new XMLHttpRequest();
	xmlHttp.onreadystatechange = function() {
		if (xmlHttp.readyState == 4 && xmlHttp.status == 200)
			callback(JSON.parse(xmlHttp.responseText));
	}
	xmlHttp.open("GET", theUrl, true); // true for asynchronous
	xmlHttp.send(null);
}

function cleanElementOfChildren(e) {
	while (e.hasChildNodes()) {
		e.removeChild(e.lastChild);
	}
}

function renderAccountHistory(date_currency_float_data) {
	if (date_currency_float_data.dataset.length == 0)
		return;
	nodehistorydiv = document.getElementById("nodehistory");
	while (nodehistorydiv.hasChildNodes()) {
		nodehistorydiv.removeChild(nodehistorydiv.lastChild);
	}
	var dataset = new vis.DataSet(date_currency_float_data.dataset);
	var groupset = new vis.DataSet(date_currency_float_data.groupset);
	//date_currency_float_data.groupset.forEach(function(g) {groupset.add(g)});
	var histoptions = {
		stack: true,
		style: "bar",
		//style: "lines",
		start: date_currency_float_data.dataset[0].x,
		end: date_currency_float_data.dataset[date_currency_float_data.dataset.length -1].x,
		barChart: {align:"center", sideBySide: true},
		legend: {enabled:true},
		interpolation: false,

	}
	//var graph2d = new vis.Graph2d(nodehistorydiv, dataset, groupset, histoptions);
	var graph2d = new vis.Graph2d(nodehistorydiv, dataset, groupset, histoptions);
}

function renderStepLineCummulativeHistory(account_datapoints) {
	var chartoptions = {
		zoomEnabled:true,
		title:{
			// text: "Account History"
		},
		animationEnabled: false,
		axisY:{
		    includeZero: true,
		    labelFontColor: "#369EAD",
		    lineColor: "#369EAD",
		    lineThickness: 3,
		  },
	      toolTip: {
	        shared: false
	      },
	      axisX: {
	        lineThickness: 2,
	        valueFormatString: "YYYY-MM-DD",
	      },
	      data: [],
	};
	$.each(account_datapoints, function(acct, dataPoints) {
		chartoptions.data.push({
			type: "stepLine",
			lineThickness: 3,
			showInLegend: true,
			xValueType: "dateTime",
			toolTipContent: "{y} {currency} <br/><pre style=\"background-color:lightgray;\">{transaction}</pre>",
			name:acct,
			dataPoints: dataPoints
		});
	});
	var chart = $("#nodehistory").CanvasJSChart(chartoptions);
}

function showAccountHistoryOfNodes(nodeids) {
	var accountargs="";
	if (nodeids.length == 0) {
		cleanElementOfChildren(document.getElementById("nodehistory"));
		return;
	}
	fillaccountargs = function(nid) {
		if (network.isCluster(nid) == true) {
			network.getNodesInCluster(nid).forEach(fillaccountargs);
		} else {
			accountargs+="&account="+nodes.get(nid).label;
		}
	}
	nodeids.forEach(fillaccountargs);

	if ($("#button-graph-stepline").prop('checked'))
	{
		//show step-line graph of running sum with multiple values per day and transaction in tooltip
		httpGetJsonAsync("/canvasjsaccounthistory.json?limit=1000&maxlinelength=60"+accountargs, renderStepLineCummulativeHistory);
	} else if ($("#button-graph-steplinedaysonly").prop('checked'))
	{
		//show step-line graph of running sum with one value per day
		httpGetJsonAsync("/canvasjsaccounthistoryindays.json?limit=1000"+accountargs, renderStepLineCummulativeHistory);
	} else if (false) //no button for this
	{
		//show Register with running sum increasing/decreasing each day
		httpGetJsonAsync("/accounthistory.json?limit=100"+accountargs, renderAccountHistory);
	}
	else
	{
		//show Journal with each single entry verbatim
		httpGetJsonAsync("/accountjournal.json?limit=1000"+accountargs, renderAccountHistory);
	}
}

function renderAccountInfo(cashflow_data) {
	var nodeinfodiv = document.getElementById("nodeinfo");
	cleanElementOfChildren(nodeinfodiv);
	if (cashflow_data.in.length > 0) {
		indiv = document.createElement("canvas");
		inlegenddiv = document.createElement("div");
		indiv.style.width=nodeinfodiv.offsetWidth+"px";
		indiv.style.height=nodeinfodiv.offsetWidth+"px";
		inlegenddiv.style.width="100%";
		nodeinfodiv.appendChild(indiv);
		nodeinfodiv.appendChild(inlegenddiv);
		var ctxin = indiv.getContext("2d");
		var pac_in = new Chart(ctxin).DoughnutWithText(cashflow_data.in, {centerText:"IN"});
		inlegenddiv.innerHTML = pac_in.generateLegend();
	}
	if (cashflow_data.out.length > 0) {
		outdiv = document.createElement("canvas");
		outlegenddiv = document.createElement("div");
		outdiv.style.width=nodeinfodiv.offsetWidth+"px";
		outdiv.style.height=nodeinfodiv.offsetWidth+"px";
		outlegenddiv.style.width="100%";
		nodeinfodiv.appendChild(outdiv);
		nodeinfodiv.appendChild(outlegenddiv);
		var ctxout = outdiv.getContext("2d");
		var pac_out = new Chart(ctxout).DoughnutWithText(cashflow_data.out, {centerText:"OUT"});
		outlegenddiv.innerHTML = pac_out.generateLegend();
	}
}


function renderAccountBalance(balance_data) {
	var nodebalancediv = document.getElementById("nodebalance");
	cleanElementOfChildren(nodebalancediv);
	$(nodebalancediv).append("<h2>"+balance_data.account+"</h2>")
	$.each(balance_data.balance, function(i,balance_str) {
		$(nodebalancediv).append("<h3>"+balance_str+"</h3>")
	})
}

function showNodeInfo(nodeids) {
	nodeinfodiv = document.getElementById("nodeinfo");
	if (nodeids.length == 0) {
		cleanElementOfChildren(nodeinfodiv);
		cleanElementOfChildren(document.getElementById("nodebalance"));
		return;
	}
	if (nodeids.length == 1) {
	  while (nodeinfodiv.hasChildNodes()) {
		nodeinfodiv.removeChild(nodeinfodiv.lastChild);
	  }
	  var account;
	  if (network.isCluster(nodeids[0]) == true) {
		  account = network.body.nodes[nodeids[0]].options.label;
		  account = account.substr(0, account.lastIndexOf(":"));
/*          clusternodes = network.getNodesInCluster(nodeids[0]);
		  var ul = document.createElement("ul");
		  nodeinfodiv.appendChild(ul);
		  clusternodes.forEach(function(cnodeid){
			var li = document.createElement("li");
			li.appendChild(document.createTextNode(nodes.get(cnodeid).label));
			ul.appendChild(li);
		  });*/
	  } else {
		  account = nodes.get(nodeids[0]).label;
	  }
	  httpGetJsonAsync("/accountbalance.json?account="+account, renderAccountBalance);
	  httpGetJsonAsync("/accountcashflow.json?account="+account, renderAccountInfo);
	}
}

function handleSelectNode(params) {
	showAccountHistoryOfNodes(params.nodes);
	showNodeInfo(params.nodes);
}

function handleDeSelectNode(params) {
	showAccountHistoryOfNodes([]);
	showNodeInfo([]);
}

function selectAccountFromDropdown(nodeid) {
	clusternode = network.clustering.clusteredNodes[nodeid[0]];
	if (clusternode)
	{
		nodeid = [clusternode.clusterId];
	}
	network.selectNodes([nodeid]);
	handleSelectNode({nodes:nodeid});
	network.focus(nodeid, {scale:1.5, animation:true});
}

var network;
var networkcontainer;
var nodes;
var edges;
var data;

function displayNetwork(json) {
	var options = {
	"nodes":{"mass":1,"shape":"ellipse","scaling":{"label":{"enabled":true}}, "font":{"size":15}},
	"edges":{"shadow":false,"color":{"inherit":false, "color":"#AFA5A5", "hover":"#D0D0D0", "highlight":"#2181AE"}, "arrows":"to","scaling":{"label":{"enabled":true}}},
	"groups":
		{"equity":{"color":{"background":"DeepPink","border":"black"},"borderWidth":3},
		 "balancesheet":{"color":{"background":"LawnGreen","border":"black"},"borderWidth":3},
		 "incomestatement":{"color":{"background":"SkyBlue","border":"black"},"borderWidth":3},
		},
	"physics":{
		"barnesHut":
			{"gravitationalConstant": -8000,
			"centralGravity": 0.5,
			"springLength": 150,
			"damping":0.44,
			},
		"repulsion": {
			"centralGravity": 0.2,
			"springLength": 300,
			"springConstant": 0.2,
			"nodeDistance": 400,
			"damping":0.25
		},
		"minVelocity":10,
		"solver":"barnesHut",
		// "solver":"repulsion",
		// "solver":"forceAtlas2Based",
		},
	"interaction":
		{"multiselect":true, "selectable":true,
		},
	"autoResize":true,
	"height": '100%',
	"width": '100%',
	};
	nodes = new vis.DataSet(json.nodes)
	edges = new vis.DataSet(json.edges);
	data = {nodes: nodes, edges: edges};
	networkcontainer = document.getElementById('mynetwork');
	cleanElementOfChildren(networkcontainer);
	network = new vis.Network(networkcontainer, data, options);
	network.setOptions(json.options); //merge in options from python
	json.clusterme.forEach(function(acc) { clusterSubAccounts(network, acc)});
	setNodeShape("ellipse");
	network.on("doubleClick", function(params) {
		  if (params.nodes.length == 1) {
			  if (network.isCluster(params.nodes[0]) == true) {
				  network.openCluster(params.nodes[0]);
			  }
		  }
	  });
	//install select/deselect node handlers
	network.on("selectNode", handleSelectNode);
	network.on("deselectNode", handleDeSelectNode);

	//fill dropdown box
	selectaccountelem = document.getElementById("selectaccount");
	cleanElementOfChildren(selectaccountelem);
	selectaccountelem.appendChild(new Option("--- No Selection ---",-1));
	nodes.forEach(function(n) {selectaccountelem.appendChild(new Option(n.label,n.id))});
}

function resizeNetworkDiv() {
	$("#mynetwork").height(document.documentElement.clientHeight - $("#control").height() - $("#nodehistoryclipbox").height());
}

function setNodeShape(shape) {
	$("#ellipses-nodeshape").removeClass("active");
	$("#dot-nodeshape").addClass("active");
	if (shape == "dot")
	{
		network.setOptions({nodes:{shape:'dot', font:{color:"white", background:'#222'}}});
		$("#ellipses-nodeshape").removeClass("active");
		$("#dot-nodeshape").addClass("active");
	}
	else if (shape == "ellipse")
	{
		network.setOptions({nodes:{shape:'ellipse', font:{color:"black", background:""}}});
		$("#ellipses-nodeshape").addClass("active");
		$("#dot-nodeshape").removeClass("active");
	}
	else
		network.setOptions({nodes:{shape:shape}});
}

window.onload=function() {
	resizeNetworkDiv();
	// $(window).resize(resizeNetworkDiv);
	httpGetJsonAsync("/network.json", displayNetwork);
	$("#dot-nodeshape").on("click",function(ev){
		setNodeShape("dot");
		return true;
	});
	$("#ellipses-nodeshape").on("click",function(ev){
		setNodeShape("ellipse");
		return true;
	});
	$("#button-model-barneshut").on("click",function(ev){
		network.setOptions({"physics":{"solver":"barnesHut"}});
		$("#button-model-barneshut").addClass("active");
		$("#button-model-atlas2").removeClass("active");
	});
	$("#button-model-atlas2").on("click",function(ev){
		network.setOptions({"physics":{"solver":"repulsion"}});
		$("#button-model-barneshut").removeClass("active");
		$("#button-model-atlas2").addClass("active");
	});
	$("#button-unclusterall").on("click",function(ev){
		$.each(network.clustering.clusteredNodes,function(i,v) {
			network.clustering.openCluster(v.clusterId);
		});
	});
	$("#btngrp-graphstyle").on("click",function(ev){
		//update graph on click on any button in button-group
		//but only after the bootstrap handler has updates the button classes
		//which showAccountHistoryOfNodes queries
		setTimeout(function(){showAccountHistoryOfNodes(network.getSelectedNodes())}, 30);
	});
	$("#button-physics-onoff").on("click",function(ev){
		elem=$(ev.target);
		if (elem.hasClass("active"))
		{
			elem.text("Physics Off");
			elem.removeClass("active");
			elem.attr("aria-pressed","false");
			network.setOptions({physics:{enabled:false}});
		} else {
			elem.text("Physics On");
			elem.addClass("active");
			elem.attr("aria-pressed","true");
			network.setOptions({physics:{enabled:true}});
		}
		return true;
	});
};
