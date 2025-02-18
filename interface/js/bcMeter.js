
$(document).ready(function() {
/* VARS*/

let tooltip,
		hoveredTime = 0,
		idx = 0,
		isHidden = false,
		yValue,
		yValue2,
		yValueScale,
		yValueScale2,
		yLabel,
		yLabel2,
		data = [],
		combineLogs = [],
		combinedLogCurrentIndex = 2,
		yMinInputted = "",
		yMin2Inputted = "",
		yMaxInputted = "",
		yMax2Inputted = "",
		yRange = [],
		yRange2 = [],
		yScale2,
		brushedX = [],
		dataObj = {},
		updateCurrentLogs;

<?php

if ($is_ebcMeter === true) {
		echo "let is_ebcMeter = true;";
		echo "let yColumn = 'BCngm3_unfiltered';";
		echo "let yColumn2 = 'bcmSen';";
}
else {
	echo "let is_ebcMeter = false;";
	echo "let yColumn = 'BCngm3';";
	echo "let yColumn2 = 'BC_rolling_avg_of_6';";
}

?>


const updateCurrentLogsFunction = () => {
		updateCurrentLogs = setInterval(() => {

				dataFile(`${logPath}log_current.csv`);
		}, 5000)

}


let selectLogs = document.getElementById("logs_select")
current_file = selectLogs.value;
if (current_file == 'log_current.csv') {
		updateCurrentLogsFunction()
}


if (typeof is_hotspot === 'undefined') {
		is_hotspot = false;
}





/* CONSTANTS */
const noData = "<div class='alert alert-warning' role='alert'>Not enough data yet.</div>";
const svg = d3.select("svg");
const width = +svg.attr("width");
const height = +svg.attr("height");
const parseTime = d3.timeParse("%d-%m-%Y %H:%M:%S");
const title = "bcMeter";
const margin = {
		top: 15,
		right: 110,
		bottom: 55,
		left: 110
};
const innerWidth = width - margin.left - margin.right;
const innerHeight = height - margin.top - margin.bottom;
const xValue = (d) => d.bcmTime;
const download = document.getElementById("download");
const yMinDoc = document.getElementById("y-menu-min");
const yMaxDoc = document.getElementById("y-menu-max");
const yMin2Doc = document.getElementById("y-menu2-min");
const yMax2Doc = document.getElementById("y-menu2-max");
const resetZoom = document.getElementById("resetZoom");
const yMenuDom = document.getElementById("y-menu")
const yMenuDom2 = document.getElementById("y-menu2")
const bisect = d3.bisector(d => d.bcmTime).left;
const xLabel = "bcmTime";

/* PRESET AND PREPOPULATE */
combineLogs["columns"] = ["BCngm3", "BCngm3_unfiltered", "BC_rolling_avg_of_6", "BC_rolling_avg_of_12", "bcmATN", "bcmRef", "bcmSen", "Temperature", "sht_humidity", "airflow"]
data["columns"] = ["BCngm3", "BCngm3_unfiltered", "BC_rolling_avg_of_6", "BC_rolling_avg_of_12", "bcmATN", "bcmRef", "bcmSen", "Temperature", "sht_humidity", "airflow"]

/* FUNCTION AND EVENT LISTENER */
/* EVENT LISTENER FOR MIN AND MAX VALUES */
yMinDoc.addEventListener("focusout", () => {
		yMinInputted = yMinDoc.value;
		render()
})

yMaxDoc.addEventListener("focusout", () => {
		yMaxInputted = yMaxDoc.value;
		render()
})

yMin2Doc.addEventListener("focusout", () => {
		yMin2Inputted = yMin2Doc.value;
		render()
})

yMax2Doc.addEventListener("focusout", () => {
		yMax2Inputted = yMax2Doc.value;
		render()
})

/* TO RESET TO DEFAULT AFTER ZOOMING */
resetZoom.addEventListener("click", () => {
		brushedX = [];
		plotChart();
})

/* FUNTION TO SET Y AXIS VALUE TO USE, EITHER INPUTTED OR D3.JS CALCULATED */
const setYAxis = () => {
		const yMin = yMinDoc.value;
		const yMax = yMaxDoc.value;
		const yMin2 = yMin2Doc.value;
		const yMax2 = yMax2Doc.value;

		let [yDataMin, yDataMax] = d3.extent(data, yValueScale);
		let [yDataMin2, yDataMax2] = d3.extent(data, yValueScale2);

		yRange = [];
		yRange2 = [];


		yRange.push(yMinInputted === '' ? yDataMin : Number(yMin));
		yRange.push(yMaxInputted === '' ? yDataMax : Number(yMax));
		yRange2.push(yMin2Inputted === '' ? yDataMin2 : Number(yMin2));
		yRange2.push(yMax2Inputted === '' ? yDataMax2 : Number(yMax2));


		yMinDoc.value = yRange[0];
		yMaxDoc.value = yRange[1];

		if (!isHidden) {
				yMin2Doc.value = yRange2[0];
				yMax2Doc.value = yRange2[1];
		}
};



/* FUNCTION CALLED ON MENU SELECT */
const yOptionClicked = (value) => {
		yColumn = value
		render();
}
const yOptionClicked2 = (value) => {
		yColumn2 = value
		render();
}

/* WHEN BRUSH END THIS FUNCTION IS TRIGGER TO CREATE THE BRUSH ZOOM */
const brushed = (event) => {
		let [x1, x2] = event.selection
		brushedX = []
		brushedX.push(xScale.invert(x1))
		brushedX.push(xScale.invert(x2))
		d3.select(".selection")
				.style("display", "none")
		plotChart()
}

/* THE BRUSH */
const brush = d3.brushX()
		.extent([
				[0, 0],
				[innerWidth, innerHeight]
		])
		.on("end", brushed)


/* FUNCTION THAT PLOT THE CHART */
const plotChart = () => {
		setYAxis();
		xScaleRange = brushedX.length == 0 ? d3.extent(data, xValue) : brushedX;

		/* CHART CONTAINER */
		const g = svg.selectAll('.container').data([null]);
		const gEnter = g
				.enter().append("g")
				.attr('class', 'container');
		gEnter.merge(g)
				.attr("transform", `translate(${margin.left}, ${margin.top})`);

		// SCALE FOR BOTH X AND Y AXIS
		xScale = d3.scaleTime()
				.domain(xScaleRange)
				.range([0, innerWidth])
				.nice();

		yScale = d3.scaleLinear()
				.domain(yRange)
				.range([innerHeight, 0])
				.nice();

		yScale2 = d3.scaleLinear()
				.domain(yRange2)
				.range([innerHeight, 0])
				.nice();

		/*CLIP PATH*/
		gEnter.append("clipPath")
				.attr("id", "rectClipPath")
				.append("rect")
				.attr("width", innerWidth)
				.attr("height", innerHeight)
				.attr("fill", "red")

		/* Y-AXIS */
		const yAxis = d3.axisLeft(yScale)
				.ticks(9)
				.tickSize(-innerWidth)
				.tickPadding(8);
		const yAxisG = g.select('.y-axis');
		const yAxisGEnter = gEnter
				.append('g')
				.attr('class', 'y-axis');
		yAxisG.merge(yAxisGEnter)
				.call(yAxis);
		yAxisG.selectAll(".domain").remove();
		const yAxisLabelText = yAxisGEnter
				.append("text")
				.attr('class', 'y-axis-label')
				.attr("y", -70)
				.attr("x", -innerHeight / 2)
				.attr("text-anchor", "middle")
				.attr("transform", `rotate(-90)`)
				.attr("fill", "black")
				.merge(yAxisG.select('.y-axis-label'))
				.transition().duration(1000)
				.text(yLabel);

		const yAxis2 = d3.axisRight(yScale2)
				.ticks(9)
				.tickSize(innerWidth)
				.tickPadding(8);
		const yAxisG2 = g.select('.y-axis2');
		const yAxisGEnter2 = gEnter
				.append('g')
				.attr('class', 'y-axis2')
		yAxisG2.merge(yAxisGEnter2)
				.call(yAxis2);
		yAxisG2.selectAll(".domain").remove();
		const yAxisLabelText2 = yAxisGEnter2
				.append("text")
				.attr('class', 'y-axis-label2')
				.attr("y", innerWidth + 70)
				.attr("x", -innerHeight / 2)
				.attr("text-anchor", "middle")
				.attr("transform", `rotate(-90)`)
				.attr("fill", "black")
				.merge(yAxisG2.select('.y-axis-label2'))
				.transition().duration(1000)
				.text(yLabel2);

		/* X-AXIS */
		const xAxis = d3
				.axisBottom(xScale)
				.tickSize(-innerHeight)
				.tickPadding(15);
		const xAxisG = g.select('.x-axis');
		const xAxisGEnter = gEnter
				.append("g")
				.attr('class', 'x-axis');
		xAxisG.merge(xAxisGEnter)
				.attr("transform", `translate(0, ${innerHeight})`)
				.call(xAxis);
		const xAxisLabelText = xAxisGEnter
				.append("text")
				.attr('class', 'x-axis-label')
				.attr("y", 50)
				.attr("x", innerWidth / 2)
				.attr("fill", "black")
				.attr("text-anchor", "middle")

				.merge(xAxisG.select('.x-axis-label'))
				.text(xLabel);

		/* LINE CHART GENERATOR */
		const lineGenerator = d3.line()
				.x((d) => xScale(xValue(d)))
				.y((d) => yScale(yValue(d)))

		const lineGenerator2 = d3.line()
				.x((d) => xScale(xValue(d)))
				.y((d) => yScale2(yValue2(d)))

		/* TO HANDLE NULL VALUE FOR ROLLING AVERAGE */
		if (yColumn == "BC_rolling_avg_of_6" || yColumn == "BC_rolling_avg_of_12") {
				lineGenerator.defined(d => d[yColumn] !== null)
		}
		if (yColumn2 == "BC_rolling_avg_of_6" || yColumn2 == "BC_rolling_avg_of_12") {
				lineGenerator2.defined(d => d[yColumn2] !== null)
		}

		/* GENERATE PATH */

		gEnter.append("path")
				.attr('class', 'line-chart')
				.attr('stroke', '#1f77b4')
				.attr('fill', 'none')
				.attr("stroke-width", "2")
				.attr("clip-path", "url(#rectClipPath)")
				.merge(g.select('.line-chart'))
				.transition().duration(1000)
				.attr('d', lineGenerator(data));


		gEnter.append("path")
				.attr('class', 'line-chart2')
				.attr('stroke', '#ff7f0e')
				.attr('fill', 'none')
				.attr("stroke-width", "2")
				.attr("clip-path", "url(#rectClipPath)")
				.merge(g.select('.line-chart2'))
				.transition().duration(1000)
				.attr('d', lineGenerator2(data));



		/* MOVING LINE */
		gEnter.append("line")
				.attr("class", "selected-time-line")
				.attr("y1", 0)
				.style("opacity", "0")
				.merge(g.select('.selected-time-line'))


		/* ADDING CIRCLE ON MOUSE MOVE */
		gEnter.append("circle")
				.attr("r", 4)
				.attr("class", "y-circle")
				.attr("fill", "#1f77b4")
				.style("stroke", "black")
				.style("stroke-width", "1.5px")
				.style("opacity", "0")
				.merge(g.select('.y-circle'))


		gEnter.append("circle")
				.attr("r", 4)
				.attr("class", "y2-circle")
				.attr("fill", "#ff7f0e")
				.style("stroke", "black")
				.style("stroke-width", "1.5px")
				.style("opacity", "0")
				.merge(g.select('.y2-circle'))

		let radar = gEnter.append("g").call(brush)
				.on("mousemove", function(e) {
						if (data.length != 0) {
								const x = d3.pointer(e)[0];
								hoveredTime = xScale.invert(x);
								let bi = bisect(data, hoveredTime) - 1
								bi_lower = bi < 0 ? 0 : bi;
								bi_upper = bi + 1 > data.length - 1 ? data.length - 1 : bi + 1
								let idx = -new Date(data[bi_lower]["bcmTime"]).getTime() - -new Date(hoveredTime).getTime() > -new Date(hoveredTime).getTime() - -new Date(data[bi_upper]["bcmTime"]).getTime() ?
										bi_upper :
										bi_lower

								const temp = data[idx];
								let diff = e.offsetX - e.pageX
								const maxLeft = innerWidth / 2 > e.offsetX ?
										xScale(data[idx][xLabel]) + margin.right + 30 - diff

										:
										xScale(data[idx][xLabel]) - 25 - diff

								let tooltipMessage = (!isHidden) ? `<div><b>Date:</b>  ${temp["bcmTimeRaw"]}</div>
								<div><b>${yColumn}:</b>  ${temp[yColumn]}</div>
								<div><b>${yColumn2}:</b>  ${temp[yColumn2]}</div>
								` : `<div><b>Date:</b>  ${temp["bcmTimeRaw"]}</div>
								<div><b>${yColumn}:</b>  ${temp[yColumn]}</div>
								`
								d3.select('.tooltip').style("left", maxLeft + 10 + "px")
										.style("top", e.pageY + "px")
										.style("pointer-events", "none")
										.style("opacity", "1")
										.html(tooltipMessage)

								d3.select(".selected-time-line")
										.attr("x1", xScale(temp[xLabel]))
										.attr("x2", xScale(temp[xLabel]))
										.attr("y2", innerHeight)
										.style("opacity", "1")

								if (!isHidden) {
										d3.select('.y2-circle')
												.attr("cx", xScale(temp[xLabel]))
												.attr("cy", yScale2(temp[yColumn2]))
												.style("opacity", temp[yColumn2] ? 1 : 0)
								}

								d3.select('.y-circle')
										.attr("cx", xScale(temp[xLabel]))
										.attr("cy", yScale(temp[yColumn]))
										.style("opacity", "1");
						}
				})

				.on("mouseout", function(e) {
						d3.select('.tooltip')
								.style("opacity", "0");
						d3.select(".selected-time-line")
								.style("opacity", "0");
						d3.select('.y-circle')
								.style("opacity", "0");
						d3.select('.y2-circle')
								.style("opacity", "0");
				})
				.attr("clip-path", "url(#rectClipPath)")
}




/* CREATE MENU */
function selectUpdate(options, id, selectedOption) {
		const select = d3.select(id);
		let option = select.selectAll('option').data(options);
		option.enter().append('option')
				.merge(option)
				.attr('value', d => d)
				.property("selected", d => d === selectedOption)
				.text(d => d);
}

selectLogs.addEventListener("change", function() {
		brushedX = [];
		current_file = selectLogs.value;
		data = dataObj[current_file];
		if (data) {
				let len = data.length - 1;
				render();

				// Calculate averages once
				let avg12 = d3.mean([...data].splice(len - 12, 12), BCngm3_value);
				let avgAll = d3.mean(data, BCngm3_value);

				// Prepare output based on is_ebcMeter flag
				let unit = is_ebcMeter ? "µg/m<sup>3</sup>" : "ng/m<sup>3</sup>";

				document.getElementById("report-value").innerHTML = `Averages: <h4 style='display:inline'>
				${(avg12 ).toFixed(is_ebcMeter ? 0 : 0)} ${unit}<sub>avg12</sub> » 
				${(avgAll ).toFixed(is_ebcMeter ? 0 : 0)} ${unit}<sub>avgALL</sub></h4>`;
		}

		if (current_file == 'log_current.csv') {
				updateCurrentLogsFunction()
		} else {
				clearInterval(updateCurrentLogs)
		}
})



yMenuDom.addEventListener("change", function() {
		yOptionClicked(this.value)
})
yMenuDom2.addEventListener("change", function() {
		yOptionClicked2(this.value)
})
selectUpdate(data["columns"], "#y-menu", yColumn);
selectUpdate(data["columns"], "#y-menu2", yColumn2)


let BCngm3_value = (d) => d["BCngm3"];
let BCngm3_unfiltered_value = (d) => d["BCngm3_unfiltered"];
/* RENDER FUNCTION THAT CALLS CHART PLOT */

const render = () => {

		// Clear previous contents
		svg.selectAll("*").remove(); // This clears the previous SVG contents

		if (!data || data.length === 0) {
				updateScales(); // Update scales

				drawGrid(); // Call drawGrid instead of displaying text
				return; // Exit the function
		}

		// P


		yMenuDom.value = yColumn;
		yMenuDom2.value = yColumn2;

		if (yColumn == "" || yColumn2 == "") {
				yColumn = data.columns[0];
				yColumn2 = data.columns[2];
		}
		yValue = (d) => d[yColumn];
		yValue2 = (d) => d[yColumn2];
		if ((((yColumn == "BCngm3_unfiltered") && yColumn2 == "BCngm3") ||
						((yColumn2 == "BCngm3_unfiltered") && yColumn == "BCngm3") && !isHidden)) {
				yValueScale = BCngm3_unfiltered_value;
				yValueScale2 = BCngm3_unfiltered_value;

		}
		if ((((yColumn == "BC_rolling_avg_of_6" || yColumn == "BC_rolling_avg_of_12") && yColumn2 == "BCngm3") ||
						((yColumn2 == "BC_rolling_avg_of_6" || yColumn2 == "BC_rolling_avg_of_12") && yColumn == "BCngm3")) && !isHidden) {
				yValueScale = BCngm3_value;
				yValueScale2 = BCngm3_value;
		} else {
				yValueScale = yValue;
				yValueScale2 = yValue2;
		}
		yLabel = yColumn;
		yLabel2 = yColumn2;
		plotChart();
};


const drawGrid = () => {
		// Basic grid border
		svg.append("rect")
				.attr("x", margin.left)
				.attr("y", margin.top)
				.attr("width", width - margin.left - margin.right)
				.attr("height", height - margin.top - margin.bottom)
				.attr("fill", "none")
				.attr("stroke", "lightgrey");

		// Draw a single horizontal grid line vertically centered
		const centerY = (margin.top + (height - margin.bottom)) / 2; // Vertically centered

		svg.append("line")
				.attr("x1", margin.left)
				.attr("y1", centerY)
				.attr("x2", width - margin.right)
				.attr("y2", centerY)
				.attr("stroke", "lightgrey")

		// Add label "0" for the horizontal line
		svg.append("text")
				.attr("x", margin.left - 40)
				.attr("y", centerY)
				.attr("dy", "0.32em")
				.attr("text-anchor", "end")
				.text("0");

		// Draw a single vertical line representing the current time
		const currentTime = new Date();
		const formatDate = d3.timeFormat("%H:%M:%S"); // Formatting the date
		const middleX = (margin.left + (width - margin.right)) / 2; // Position it in the middle

		svg.append("line")
				.attr("x1", middleX)
				.attr("y1", margin.top)
				.attr("x2", middleX)
				.attr("y2", height - margin.bottom)
				.attr("stroke", "lightgrey")
				.attr("stroke-width", 1); // Default stroke width

		// Add label for the current time
		svg.append("text")
				.attr("x", middleX)
				.attr("y", height - margin.bottom + 40) // Adjust as needed
				.attr("text-anchor", "middle")
				.style("font-size", "12px")
				.text("Nothing to display yet...");
		svg.append("text")
				.attr("x", middleX)
				.attr("y", height - margin.bottom + 25) // Adjust as needed
				.attr("text-anchor", "middle")
				.style("font-size", "12px")
				.text(formatDate(currentTime));
};

let xScale = d3.scaleLinear();
let yScale = d3.scaleLinear();

const updateScales = () => {
		xScale.domain([0, 1000]).range([margin.left, width - margin.right]);
		yScale.domain([0, 1000]).range([height - margin.bottom, margin.top]);
};

let filterStatus;

const dataFile = (file, isCombineLogsSelected = false) => {
		data = []
		data["columns"] = ["BCngm3", "BCngm3_unfiltered", "BC_rolling_avg_of_6", "BC_rolling_avg_of_12", "bcmATN", "bcmRef", "bcmSen", "Temperature", "Humidity", "Airflow"]

		d3.dsv(';', file).then((rawData) => {
				let movingIndex4 = 0
				let movingIndex6 = 0
				let movingIndex12 = 0
				rawData.forEach((d, i) => {
						if (d.bcmTime) {
								d.bcmTimeRaw = d.bcmDate + ' ' + d.bcmTime;
								d.bcmTime = parseTime(d.bcmDate + ' ' + d.bcmTime);
								d.bcmRef = +d.bcmRef;
								d.bcmSen = +d.bcmSen;
								d.bcmATN = +d.bcmATN;
								d.relativeLoad = +d.relativeLoad;
								d.BCngm3 = +d.BCngm3;
								d.BCngm3_unfiltered = +d.BCngm3_unfiltered;
								d.Temperature = +d.Temperature;
								d.sht_humidity = +d.sht_humidity;

								data.push(d)
						}
				});


				let result = file.includes("../logs/log_current.csv");
				if (result == true) {

						let len = data.length - 1;

						if (len > 0) {
								let unit = is_ebcMeter ? "µg/m<sup>3</sup>" : "ng/m<sup>3</sup>";

								// Calculate averages once
								let avg12 = d3.mean([...data].splice(len - 12, 12), BCngm3_value);
								let avgAll = d3.mean(data, BCngm3_value);

								document.getElementById("report-value").innerHTML = `Averages: <h4 style='display:inline'>
								${avg12.toFixed(is_ebcMeter ? 0 : 0)} ${unit}<sub>avg12</sub> » 
								${avgAll.toFixed(is_ebcMeter ? 0 : 0)} ${unit}<sub>avgALL</sub></h4>`;
								let bcmRef = data[len].bcmRef;
								let bcmSen = data[len].bcmSen;
								let btn = document.getElementById("report-button");
								if (bcmSen == 0) {
										if (bcmRef == 0) {
												btn.className = "btn btn-secondary";

										}
								}





										filterStatus = bcmSen / bcmRef;

										if (is_ebcMeter === false) {

												if (filterStatus <= 0.3) {
														btn.className = "btn btn-dark"; 
												} else if (filterStatus > 0.3 && filterStatus <= 0.45) {
														btn.className = "btn btn-secondary";
												} else if (filterStatus > 0.45 && filterStatus <= 0.55) {
														btn.className = "btn btn-danger"; 
												} else if (filterStatus > 0.55 && filterStatus <= 0.7) {
														btn.className = "btn btn-warning"; 
												} else if (filterStatus > 0.7) {
														btn.className = "btn btn-success"; 
												}
										}
										else {


												if (filterStatus <= 0.1) {
														btn.className = "btn btn-dark"; 
												} else if (filterStatus > 0.1 && filterStatus <= 0.2) {
														btn.className = "btn btn-secondary";
												} else if (filterStatus > 0.2 && filterStatus <= 0.25) {
														btn.className = "btn btn-danger"; 
												} else if (filterStatus > 0.25 && filterStatus <= 0.4) {
														btn.className = "btn btn-warning"; 
												} else if (filterStatus > 0.4) {
														btn.className = "btn btn-success"; 
												}


										}
						}

						if (len < 0) {
								document.getElementById("report-value").innerHTML = `<h4> </h4>`;
						}
				}




				/* MOVING AVERAGE = 6 */

				data.map((d, i) => {
						if (i < 4 || i > data.length - 3) {
								d.BC_rolling_avg_of_6 = null;
						} else {
								d.BC_rolling_avg_of_6 = +((((((data.slice(movingIndex6, movingIndex6 + 6).reduce((p, c) => p + c.BCngm3_unfiltered, 0)) / 6)) +
										(((data.slice(movingIndex6 + 1, movingIndex6 + 1 + 6).reduce((p, c) => p + c.BCngm3_unfiltered, 0)) / 6))) / 2).toFixed(0))
								movingIndex6++;
						}
						/* MOVING AVERAGE = 12 */
						if (i < 7 || i > data.length - 6) {
								d.BC_rolling_avg_of_12 = null;
						} else {
								d.BC_rolling_avg_of_12 = +((((((data.slice(movingIndex12, movingIndex12 + 12).reduce((p, c) => p + c.BCngm3_unfiltered, 0)) / 12)) +
										(((data.slice(movingIndex12 + 1, movingIndex12 + 1 + 12).reduce((p, c) => p + c.BCngm3_unfiltered, 0)) / 12))) / 2).toFixed(0))
								movingIndex12++;
						}
						if (isCombineLogsSelected) {
								dataObj[file.split("/")[2]] = data
								combineLogs.push(d)
						}



				})



				if (isCombineLogsSelected) {
						combinedLogCurrentIndex++;
						if (combinedLogCurrentIndex < logFilesSize) {
								dataFile(`${logPath}${logFiles[combinedLogCurrentIndex]}`, true)
						} else {
								dataObj["combine_logs"] = combineLogs;
								selectLogs.value = "log_current.csv";
								selectLogs.dispatchEvent(new Event("change"))
								render();
						}
				} else {
						render();
				}
		});
}



/* INITIAL LOAD */
let logPath = '../logs/';
let updatelogs;
let logFiles = <?php echo json_encode($logFiles); ?>;
let logFilesSize = logFiles.length;
dataFile(`${logPath}${logFiles[combinedLogCurrentIndex]}`, true)

const serializeData = () => {
		var png = (new XMLSerializer()).serializeToString(document.getElementById("line-chart"));
		var svgBlob = new Blob([png], {
				type: "image/svg+xml;charset=utf-8"
		});
		var svgURL = URL.createObjectURL(svgBlob);
		return {
				svgURL,
				svgBlob
		}
}

const saveSVG = () => {
		downloadFile(serializeData()["svgURL"], "svg")
}

const savePNG = () => {
		var dom = document.createElement("canvas");
		var ct = dom.getContext("2d");
		dom.width = width;
		dom.height = height;
		var bolbURL = window.URL;
		var img = new Image();

		img.onload = function() {
				ct.drawImage(img, 0, 0);
				bolbURL.createObjectURL(serializeData()["svgBlob"]);
				downloadFile(dom.toDataURL('image/png'), "png")
		};
		img.src = serializeData()["svgURL"];
		BCngm3
}

const saveCSV = () => {
		downloadCSVFile(`../logs/${current_file}`, "csv")
}

const downloadCSVFile = (url, ext) => {
		var today = new Date();
		var date = today.getFullYear().toString() + (today.getMonth() + 1).toString() + today.getDate().toString();
		var time = today.getHours().toString() + today.getMinutes().toString() + today.getSeconds().toString();
		var dateTime = date + '_' + time;
		// var savingWord = (!isHidden) ? `bcMeter-(${yColumn}-vs-${yColumn2})` : `bcMeter-${yColumn}`;
		download.href = url;
		var hostName = location.hostname;
		download.download = `${hostName}_${dateTime}.${ext}`;
		download.click();
}


const downloadFile = (url, ext) => {
		var today = new Date();
		var date = today.getFullYear() + (today.getMonth() + 1) + today.getDate();
		var time = today.getHours() + today.getMinutes() + today.getSeconds();
		var dateTime = date + '_' + time;
		// var savingWord = (!isHidden) ? `bcMeter-(${yColumn}-vs-${yColumn2})` : `bcMeter-${yColumn}`;
		download.href = url;
		var hostName = location.hostname;
		download.download = `${hostName}_${dateTime}.${ext}`;
		download.click();
}



document.getElementById("hide-y-menu2").addEventListener("click", function() {
		isHidden = !isHidden;
		if ((((yColumn == "BC_rolling_avg_of_6" || yColumn == "BC_rolling_avg_of_12") && yColumn2 == "BCngm3") ||
						((yColumn2 == "BC_rolling_avg_of_6" || yColumn2 == "BC_rolling_avg_of_12") && yColumn == "BCngm3")) && !isHidden) {
				render()
		}
		this.innerHTML = (isHidden) ? `Show` : `Hide`;
		d3.select('.y-axis2').style("opacity", Number(!isHidden))
		d3.select('.line-chart2').style("opacity", Number(!isHidden))
		if (isHidden) {
				yMin2Doc.style.opacity = 0
				yMax2Doc.style.opacity = 0
		} else {
				yMin2Doc.style.opacity = 1
				yMax2Doc.style.opacity = 1
		}

});




function getBaseUrl() {
		// Construct the base URL using the current hostname and specifying port 5000
		return window.location.protocol + '//' + window.location.hostname + ':5000';
}
loadConfig('session'); // Initially load session configurations
loadConfig('device'); // Initially load device configurations
loadConfig('administration'); // Initially load administration configurations
loadConfig('email'); // Initially load administration configurations
loadConfig('compair'); // Initially load administration configurations

let isDirty = false; // Flag to track if changes were made

// Function to check for unsaved changes and ask for confirmation
function handleTabSwitch(newTab) {
		if (isDirty) {
				const confirmSwitch = confirm('You have unsaved changes. Do you want to save them before switching?');
				if (confirmSwitch) {
						let activeTabId = null;
						
						tabsConfig.forEach(tab => {
								if ($(`#${tab.tabId}`).hasClass('active')) {
										activeTabId = tab.tabId;
								}
						});

						if (activeTabId) {
								saveConfigurationBasedOnTab(activeTabId);
						}  
				}
		}
		isDirty = false; // Reset the dirty flag after handling the switch
		activateAndLoadConfig(newTab);
}

function monitorChanges(formId) {
		const form = document.getElementById(formId);
		if (form) {
				// Monitor input fields, select elements, and textareas
				form.querySelectorAll('input, select, textarea').forEach(input => {
						input.addEventListener('change', () => {
								isDirty = true; // Mark the form as "dirty" when a change is detected
						});
				});
		} 
}



// Modify the activateAndLoadConfig to start monitoring changes for the new tab
function activateAndLoadConfig(tabElement) {
		const configType = tabElement.attr('aria-controls');
		loadConfig(configType);
		
		// Monitor the form for changes after loading config
		const formId = getFormIdFromConfigType(configType);
		monitorChanges(formId);
}

// Helper function to get form ID based on config type
function getFormIdFromConfigType(configType) {
		switch (configType) {
				case 'session':
						return 'session-parameters-form';
				case 'device':
						return 'device-parameters-form';
				case 'administration':
						return 'administration-parameters-form';
				case 'email':
						return 'email-parameters-form';
				case 'compair':
						return 'compair-parameters-form';
				default:
						return '';
		}
}

$('#configTabs a').on('click', function (e) {
		e.preventDefault();
		const newTab = $(this);
		handleTabSwitch(newTab);
});



// Ensure the initial tab is loaded and monitored for changes
const initialTab = $('#configTabs a.active');
if (initialTab.length) {
		activateAndLoadConfig(initialTab);
} else {
		activateAndLoadConfig($('#configTabs a').first());
}

function loadConfig(configType) {
	fetch(`${getBaseUrl()}/load-config`)
		.then(response => response.json())
		.then(data => {
				const formId = (() => {
					switch (configType) {
						case 'session':
							return 'session-parameters-form';
						case 'device':
							return 'device-parameters-form';
						case 'administration':
							return 'administration-parameters-form';
						case 'email':
							return 'email-parameters-form'; // Match the id for the email tab
						case 'compair':
							return 'compair-parameters-form'; // Match the id for the compair tab
						default:
							return ''; // Adjust this to handle other cases if needed
					}
				})();
				const tbody = document.querySelector(`#${formId} tbody`);
				tbody.innerHTML = ''; // Clear existing rows
				
				// Generate rows and append to the table
				Object.entries(data).forEach(([key, config]) => {
					if (config.parameter === configType) {
						const description = config.description;
						let valueField = '';
						
						if (config.type === 'boolean') {
							// For boolean, use a Bootstrap Switch
							const checkedAttr = config.value ? 'checked' : ''; // Add checked attribute if value is true
							valueField = `<input name="${key}" type="checkbox" ${checkedAttr} data-toggle="toggle" data-onstyle="info" data-offstyle="light">`;
						} else if (config.type === 'number' || config.type === 'float') {
							// For number, use a number input
							valueField = `<input type="number" class="form-control" name="${key}" value="${config.value}">`;
						} else if (config.type === 'string') {
							// For string, use a text input
							valueField = `<input type="text" class="form-control" name="${key}" value="${config.value}">`;
						} else if (config.type === 'array') {
							// For array, use a text input with JSON representation
							valueField = `<input type="text" class="form-control array" name="${key}" value="${JSON.stringify(config.value)}">`;
						}
						
						const row = `<tr data-toggle="tooltip" data-placement="top" title="${description}">
							<td>${description}</td>
							<td>${valueField}</td>
						</tr>`;
						tbody.innerHTML += row;
					}
				});

				// Initialize Bootstrap Switches after all elements are generated
				$('[data-toggle="toggle"]').bootstrapToggle();
				
				// Now that the form elements are loaded, start monitoring for changes
				monitorChanges(formId);
			})
			.catch(error => console.error('Failed to load configuration:', error));
}


function saveConfiguration(configType) {

		const formId = (() => {
				switch (configType) {
						case 'session':
								return 'session-parameters-form';
						case 'device':
								return 'device-parameters-form';
						case 'administration':
								return 'administration-parameters-form';
						case 'email':
								return 'email-parameters-form'; // Match the id for the email tab
						case 'compair':
								return 'compair-parameters-form'; // Match the id for the compair tab
						default:
								return ''; // Adjust this to handle other cases if needed
				}
		})();
		const form = document.getElementById(formId);
		const updatedConfig = {};

		// Process each input element within the form
		form.querySelectorAll('input[type="checkbox"], input[type="number"], input[type="text"]').forEach(input => {
				const key = input.name;
				let value = input.value;
				// For checkboxes, use the checked state
				if (input.type === 'checkbox') {
						value = input.checked;
				} else if (input.classList.contains('array')) {
						// For array inputs, parse the JSON string back into an array
						try {
								value = JSON.parse(input.value);
						} catch (e) {
								console.error('Failed to parse array input:', e);
						}
				}
				if (input.type === 'number') {
						value = value.replace(/,/g, '.');

				}
				// Retrieve the description from the corresponding tr element if it exists
				const descriptionElement = input.closest('tr').getAttribute('title');
				const description = descriptionElement ? descriptionElement.trim() : '';

				// Skip if the key is empty
				if (key) {
						// Construct the configuration object with description and value
						updatedConfig[key] = {
								value: value,
								description: description,
								type: determineType(input),
								parameter: configType
						};
				}

				function determineType(input) {
						if (input.type === 'checkbox') {
								return 'boolean';
						} else if (input.type === 'number') {
								return 'number';
						} else if (input.classList.contains('array')) {
								return 'array';
						} else if (input.type === 'text') {
								return 'string';
						} else {
								return typeof value;
						}
				}
		});

		// Fetch the existing configurations
		fetch(`${getBaseUrl()}/load-config`)
				.then(response => response.json())
				.then(existingConfig => {
						// Merge the updated configurations with the existing ones
						const mergedConfig = {
								...existingConfig
						};

						// Update the merged configurations with the updated ones
						Object.keys(updatedConfig).forEach(key => {
								mergedConfig[key] = updatedConfig[key];
						});

						// Send the merged configuration to the server for saving
						fetch(`${getBaseUrl()}/save-config`, {
										method: 'POST',
										headers: {
												'Content-Type': 'application/json'
										},
										body: JSON.stringify(mergedConfig)
								})
								.then(response => {
										if (!response.ok) {
												throw new Error('Failed to save configuration');
										}
										console.log('Configuration saved successfully');
								})
								.catch(error => console.error('Failed to save configuration:', error));
				})
				.catch(error => console.error('Failed to load configuration:', error));
}

// Function to handle saving configuration based on active tab
function saveConfigurationBasedOnTab(tabId) {
		const tabToConfigMap = {
				'session-tab': 'session',
				'device-tab': 'device',
				'administration-tab': 'administration',
				'email-tab': 'email',
				'compair-tab': 'compair'
		};

		const configType = tabToConfigMap[tabId];
		if (configType) {
				saveConfiguration(configType);
		}
}


document.addEventListener("keydown", function(event) {

		var isEnterPressed = (event.key === "Enter" || event.keyCode === 13 || event.which === 13);

		if (isEnterPressed) {
				let activeTabId = null;
				
				tabsConfig.forEach(tab => {
						if ($(`#${tab.tabId}`).hasClass('active')) {
								activeTabId = tab.tabId;
						}
				});

				if (activeTabId) {
						saveConfigurationBasedOnTab(activeTabId); // Call the save based on the active tab
				} 


				$('#device-parameters').modal('hide'); // Close the modal if applicable
		}
});


// Define an array of tab IDs and corresponding configuration types
const tabsConfig = [
		{ tabId: 'session-tab', configType: 'session' },
		{ tabId: 'device-tab', configType: 'device' },
		{ tabId: 'administration-tab', configType: 'administration' },
		{ tabId: 'email-tab', configType: 'email' },
		{ tabId: 'compair-tab', configType: 'compair' }
];

// Iterate over the array and create event listeners for each tab
tabsConfig.forEach(tab => {
		document.getElementById(`save${tab.configType.charAt(0).toUpperCase() + tab.configType.slice(1)}Settings`).addEventListener("click", function(event) {
				event.preventDefault();
				saveConfigurationBasedOnTab(tab.tabId);
				$('#device-parameters').modal('hide'); // Close the modal after saving
		});
});

$('#bcMeter_reboot').click(function(e) {
		e.preventDefault(); // Prevent the default submit behavior

		bootbox.dialog({
				title: 'Reboot bcMeter?',
				message: "<p>Do you want to reboot the device?</p>",
				size: 'small',
				buttons: {
						cancel: {
								label: "No",
								className: 'btn-success',
								callback: function() {

								}
						},
						ok: {
								label: "Yes",
								className: 'btn-danger',
								callback: function() {
										window.location.href = 'includes/status.php?status=reboot';

								}
						}
				}
		});

});


$('#bcMeter_stop').click(function(e) {
		e.preventDefault(); // Prevent the default submit behavior

		bootbox.dialog({
				title: 'Stop logging',
				message: "<p>This will stop the current measurement. Sure?</p>",
				size: 'small',
				buttons: {
						cancel: {
								label: "No",
								className: 'btn-success',
								callback: function() {

								}
						},
						ok: {
								label: "Yes",
								className: 'btn-danger',
								callback: function() {


										$.ajax({
												type: 'post',
												data: 'exec_stop',
												success: function(response) {

												}
										});




								}
						}
				}
		});

});




$('#bcMeter_debug').click(function(e) {
		e.preventDefault(); // Prevent the default submit behavior

		bootbox.dialog({
				title: 'Enter debug mode?',
				message: "<p>Do you want to switch to debug mode? Device will be unresponsive for 10-20 seconds</p>",
				size: 'small',
				buttons: {
						cancel: {
								label: "No",
								className: 'btn-success',
								callback: function() {

								}
						},
						ok: {
								label: "Yes",
								className: 'btn-danger',
								callback: function() {

										$.ajax({
												type: 'post',
												data: 'exec_debug',
												success: function(response) {
														window.location.href = 'includes/status.php?status=debug';
												}
										});



								}
						}
				}
		});

});




$('#force_wifi').click(function(e) {
		e.preventDefault(); // Prevent the default submit behavior

		bootbox.dialog({
				title: 'Reset Wifi?',
				message: "<p>This will trigger a manual reload of the WiFi credentials and cut your current connection. </p>",
				size: 'small',
				buttons: {
						cancel: {
								label: "No",
								className: 'btn-success',
								callback: function() {

								}
						},
						ok: {
								label: "Yes",
								className: 'btn-danger',
								callback: function() {
										// Make AJAX call to initiate the backend process
										$.ajax({
												type: 'post',
												data: {
														force_wifi: true
												}, // Adjusted to pass data as an object
												success: function(response) {
														// Handle success
												},
												error: function() {
														// Handle error
												}
										});
								}
						}
				}
		});

});




$('#bcMeter_calibration').click(function(e) {
		e.preventDefault(); // Prevent the default submit behavior

		bootbox.dialog({
				title: 'Calibrate bcMeter?',
				message: "<p>Calibrate only with new filterpaper. Avoid direct sunlight. Continue? </p>",
				size: 'medium',
				buttons: {
						cancel: {
								label: "No",
								className: 'btn-success',
								callback: function() {}
						},
						ok: {
								label: "Yes",
								className: 'btn-danger',
								callback: function() {
										window.location.href = 'includes/status.php?status=calibration';

								}
						}
				}
		});

});



$('#bcMeter_update, #bcMeter_update2').click(function(e) {
		e.preventDefault(); // Prevent the default submit behavior

		// Ask the user if they want to download the config file
		bootbox.confirm({
				title: 'Download Config File?',
				message: "Would you like to download the current configuration file (bcMeter_config.json) before proceeding with the update?",
				buttons: {
						cancel: {
								label: 'No',
								className: 'btn-secondary'
						},
						confirm: {
								label: 'Yes',
								className: 'btn-primary'
						}
				},
				callback: function(result) {
						if (result) {
								// If the user wants to download, fetch and download the file
								fetch('/bcMeter_config.json')
										.then(response => {
												if (!response.ok) {
														throw new Error('Network response was not ok');
												}
												return response.blob();
										})
										.then(blob => {
												// Create a link to download the file
												const downloadUrl = URL.createObjectURL(blob);
												const a = document.createElement('a');
												a.href = downloadUrl;
												a.download = 'bcMeter_config.json';
												document.body.appendChild(a);
												a.click();
												a.remove();
												URL.revokeObjectURL(downloadUrl); // Clean up the URL object

												// Proceed to the update dialog after download
												showUpdateDialog();
										})
										.catch(error => {
												console.error('There was a problem with the fetch operation:', error);
												alert("Failed to download the configuration file.");
										});
						} else {
								// Skip download and proceed directly to the update dialog
								showUpdateDialog();
						}
				}
		});
});

function showUpdateDialog() {
		bootbox.dialog({
				title: 'Update bcMeter?',
				message: "<p>The most recent files will be downloaded. If possible, your parameters will be kept but please save them and check after the update if they are the same.</p>",
				size: 'medium',
				buttons: {
						cancel: {
								label: "No",
								className: 'btn-success',
								callback: function() {}
						},
						ok: {
								label: "Yes",
								className: 'btn-danger',
								callback: function() {
										window.location.href = 'includes/status.php?status=update';
								}
						}
				}
		});
}




$('#saveGraph').click(function(e) {
		e.preventDefault(); // Prevent the default submit behavior

		bootbox.dialog({
				title: 'Save graph as',
				message: "<p>Choose the type of file you want to save the current measurements as</p>",
				size: 'large',
				buttons: {
						1: {
								label: "CSV (MS Office/Google Docs)",
								className: 'btn-info',
								callback: function() {
										saveCSV();

								}
						},
						2: {
								label: "PNG (Web/Mail)",
								className: 'btn-info',
								callback: function() {
										savePNG();

								}
						},
						3: {
								label: "SVG (DTP)",
								className: 'btn-info',
								callback: function() {
										saveSVG();
								}
						}
				}
		});

});




$('#startNewLog').click(function(e) {
		e.preventDefault(); // Prevent the default submit behavior

		bootbox.dialog({
				title: 'Start new log?',
				message: "<p>This will start a new log. It takes a few minutes for the new chart to appear.</p>",
				size: 'small',
				buttons: {
						cancel: {
								label: "No",
								className: 'btn-success',
								callback: function() {
										// Cancel callback
								}
						},
						ok: {
								label: "Yes",
								className: 'btn-danger',
								callback: function() {
										// Make AJAX call to initiate the backend process
										$.ajax({
												type: 'post',
												data: {
														exec_new_log: true
												}, // Adjusted to pass data as an object
												success: function(response) {
														// Handle success
												},
												error: function() {
														// Handle error
												}
										});
								}
						}
				}
		});
});





var optionsButton = document.querySelector('[data-target="#pills-devicecontrol"]');
optionsButton.addEventListener('click', function() {
		var target = document.querySelector(this.getAttribute('data-target'));
		if (target.style.display === "none") {
				target.style.display = "block";
		} else {
				target.style.display = "none";
		}
});


// WiFi Password toggle functionality
$(".toggle-password").click(function() {
  $(this).find('i').toggleClass('fa-eye fa-eye-slash'); 
  var input = $("#pass_log_id");
  input.attr("type", input.attr("type") === "password" ? "text" : "password");
});

// WiFi Edit password button
$(".js-edit-password").click(function() {
    $('.wifi-pwd-field-exist').hide();
    $('.wifi-pwd-field').show();
});

// WiFi network selection handling
var dropdown = document.getElementById('js-wifi-dropdown');
let availableNetworks = [];

// Function to update password field visibility based on network availability
function updatePasswordFieldVisibility(selectedNetwork) {
    const isInRange = availableNetworks.includes(selectedNetwork);
    const hasStoredPassword = currentWifiSsid === selectedNetwork;
    
    if (!isInRange || !hasStoredPassword) {
        $('.wifi-pwd-field-exist').hide();
        $('.wifi-pwd-field').show();
    } else {
        $('.wifi-pwd-field-exist').show();
        $('.wifi-pwd-field').hide();
    }
}

// Handle network selection change
dropdown.onchange = function() {
    const selectedValue = this[this.selectedIndex].value;
    document.getElementById('custom-network').style.display = 
        selectedValue === "custom-network-selection" ? 'block' : 'none';
    
    if (selectedValue !== "custom-network-selection") {
        updatePasswordFieldVisibility(selectedValue);
    }
};

// Fetch and populate available networks
function fetchWifiNetworks() {
    $('.loading-available-networks').show();
    
    $.getJSON('includes/wlan_list.php', function(networks) {
        availableNetworks = networks;
        const dropdown = $('#js-wifi-dropdown');
        
        // Clear existing options except the current and custom
        dropdown.find('option:not(:first):not([value="custom-network-selection"])').remove();
        
        // Add available networks
        networks.forEach(network => {
            if (network !== currentWifiSsid) {
                dropdown.append($('<option></option>').val(network).text(network));
            }
        });
        
        // Update visibility for current network
        updatePasswordFieldVisibility(currentWifiSsid);
        
        $('.loading-available-networks').hide();
    });
}

$('#refreshWifi').click(fetchWifiNetworks);

fetchWifiNetworks();

// Track modal state
let hasShownWarningModal = false;

function showWarningModal(calibrationTime, filterStatus) {
    // Only show if we haven't shown it yet this session
    if (hasShownWarningModal) {
        return;
    }

    const modalHtml = `
    <div class="modal fade" id="warningModal">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header bg-warning">
                <h5 class="modal-title">Device Maintenance Required</h5>
                <button type="button" class="close" data-dismiss="modal">&times;</button>
            </div>
            <div class="modal-body">
                ${!calibrationTime ? '<p>The device was not calibrated lastly. Please calibrate it with new filter.</p>' : ''}
                ${filterStatus < 3 ? `
                    <div class="filter-warning">
                        <p>Filter Status: ${filterStatus}/5</p>
                        <p class="text-danger">Warning: Low filter quality detected!</p>
                        <ul>
                            <li>Current filter status is low (scale 0-5)</li>
                            <li>Low filter status means less light passes through, resulting in inaccurately low measurements</li>
                            <li>At status 1 to 0, measurements will be severely compromised by heavy noise and reduced accuracy over time of ~60-75%</li>
                        </ul>
                        <p><strong>Required Actions:</strong></p>
                        <ol>
                            <li>Replace the filter as soon as possible</li>
                            <li>Calibrate the device with the new filter</li>
                            <li>To extend filter life in heavy polluted air (daily average higher than 1000ng), consider reducing airflow when possible</li>
                        </ol>
                    </div>
                ` : ''}
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-dismiss="modal">Close</button>
            </div>
        </div>
    </div>
</div>`;

    // Only append modal HTML if it doesn't exist
    if (!document.getElementById('warningModal')) {
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    }

    // Show the modal and mark it as shown
    $('#warningModal').modal('show');
    hasShownWarningModal = true;

    // Reset flag when modal is hidden
    $('#warningModal').on('hidden.bs.modal', function () {
        // Don't reset hasShownWarningModal here as we want it to persist until reload
    });
}

function updateStatus(status, deviceName, creationTimeString, calibrationTime, filterStatus) {
	window.deviceName = deviceName;
    if (!calibrationTime || (filterStatus !== null && filterStatus < 3)) {
        showWarningModal(calibrationTime, filterStatus);
    }
    const statusDiv = document.getElementById('statusDiv');
    statusDiv.className = 'status-div';
    
    let formattedCreationTime = formatTimeString(creationTimeString);
    let formattedCalibrationTime = formatTimeString(calibrationTime);
    let statusText = getStatusText(status, deviceName, formattedCreationTime);
    
    // Get the div elements using correct variable declaration
    const calibrationTimeDiv = document.getElementById('calibrationTime');
    const filterStatusDiv = document.getElementById('filterStatusDiv');
    
    // Update calibration time div
    if (calibrationTimeDiv) {
        calibrationTimeDiv.textContent = formattedCalibrationTime ? 
            `Last calibration: ${formattedCalibrationTime}` : 'No calibration data';
    }
    
    // Update filter status div
    if (filterStatusDiv) {
        filterStatusDiv.textContent = filterStatus !== null ? 
            `Filter status: ${filterStatus}/5` : 'No filter status';
    }
    
    // Keep the main status div update
    statusDiv.textContent = statusText;
    
    setStatusColors(statusDiv, status);
    updateHotspotWarning(status);
}

// Reset modal state on page reload
window.addEventListener('load', function() {
    hasShownWarningModal = false;
});

function formatTimeString(timeString) {
   if (!timeString || timeString.length < 13) return '';
   
   const year = parseInt("20" + timeString.substring(0, 2));
   const month = parseInt(timeString.substring(2, 4)) - 1;
   const day = parseInt(timeString.substring(4, 6));
   const hours = parseInt(timeString.substring(7, 9));
   const minutes = parseInt(timeString.substring(9, 11));
   const seconds = parseInt(timeString.substring(11, 13));
   
   if ([year, month, day, hours, minutes, seconds].some(isNaN)) return '';
   
   return new Date(year, month, day, hours, minutes, seconds).toLocaleString();
}

function getStatusText(status, deviceName, formattedCreationTime) {
   const statusMessages = {
       '-1': `${deviceName} status unknown`,
       '0': `${deviceName} stopped`,
       '1': `${deviceName} initializing`,
       '2': `${deviceName} running since ${formattedCreationTime}`,
       '3': `${deviceName} running in Hotspot Mode since ${formattedCreationTime}`,
       '4': `Hotspot mode active, ${deviceName} not measuring`,
       '5': `${deviceName} stopped by user`
   };
   return statusMessages[status] || `${deviceName} has an unrecognized status`;
}

function setStatusColors(statusDiv, status) {
   const statusColors = {
       '-1': 'bg-secondary',
       '0': 'bg-danger',
       '1': 'bg-warning',
       '2': 'bg-success',
       '3': 'bg-info',
       '4': 'bg-info',
       '5': 'bg-warning'
   };
   statusDiv.classList.add(statusColors[status] || '', 'text-white');
}

function updateHotspotWarning(status) {
   const hotspotWarningDiv = document.getElementById('hotspotwarning');
   if (status === 4) {
       hotspotWarningDiv.style.display = 'block';
       hotspotWarningDiv.className = 'alert alert-warning';
   } else {
       hotspotWarningDiv.style.display = 'none';
   }
}

function fetchStatus() {
   fetch('/tmp/BCMETER_WEB_STATUS')
       .then(response => response.ok ? response.text() : Promise.reject('Network error'))
       .then(data => {
           const jsonData = JSON.parse(data);
           const status = jsonData.bcMeter_status;
           const hostname = jsonData.hostname;
           const logCreationTime = jsonData.log_creation_time;
           const calibrationTime = jsonData.calibration_time;
           const filterStatus = jsonData.filter_status;

           updateStatus(status, hostname, logCreationTime, calibrationTime, filterStatus);
           return {status, hostname, logCreationTime, calibrationTime, filterStatus};
       })
       .catch(error => {
           console.error('Fetch error:', error);
           return {
               status: -1, 
               hostname: "Device", 
               logCreationTime: null,
               calibrationTime: null,
               filterStatus: null
           };
       });
}



// Fetch status on page load
fetchStatus();
// Refresh status every 5 seconds
setInterval(fetchStatus, 5000);





setInterval(function() {
		var date = new Date();
		var timestamp = (date.getTime() / 1000).toFixed(0);
		var currentDateTime = date.toLocaleString('default', {
				month: 'short'
		}) + " " + date.getDate() + " " + date.getFullYear() + " " + date.getHours() + ":" + date.getMinutes() + ":" + date.getSeconds();


		$.ajax({
				url: "includes/gettime.php", // The page containing php script
				type: "post", // Request type
				data: {
						datetime: "now"
				},
				cache: false, // Prevent the browser from caching the result
				timeout: 1000, // Set timeout for the request (e.g., 5000 milliseconds)
				success: function(result) {
						document.getElementById("datetime_local").innerHTML = "Current time based on your Browser: <br/>" + currentDateTime;
						document.getElementById("set_time").value = timestamp;
						document.getElementById("datetime_note").innerHTML = "Synchronize the time of bcMeter to get correct timestamps";
						document.getElementById("datetime_device").innerHTML = "Current time set on your bcMeter: " + result;
						if (document.getElementById("devicetime")) {
								document.getElementById("devicetime").innerHTML = "Time on bcMeter: " + result;
						}
						document.getElementById('hotspotwarning').classList.remove('alert-danger');
						document.getElementById('hotspotwarning').classList.add('alert');
				},
				error: function(xhr, status, error) {
						var errorMessage = xhr.status + ': ' + xhr.statusText;
						var deviceURL = (deviceName !== "") ? "http://" + deviceName : "";

						document.getElementById("datetime_device").innerHTML = "No connection to bcMeter<br /> click <a href=\"" + deviceURL + "\">here </a>to force reload after WiFi Setup ";
						document.getElementById("datetime_local").innerHTML = "";
						document.getElementById("set_time").value = "";
						document.getElementById("datetime_note").innerHTML = "";
						if (document.getElementById("devicetime")) {
								document.getElementById("devicetime").innerHTML = "";
						}
						document.getElementById('hotspotwarning').classList.remove('alert');
						document.getElementById('hotspotwarning').classList.add('alert-danger');
				}
		});
}, 1000);



$('#force_wifi').click(function() {
$('#wifisetup').modal('hide'); 
});


$('#filterStatusModal').on('show.bs.modal', function (event) {
		var modal = $(this);
		// Calculate the percentage and round it to the nearest integer
		var percentage = Math.round((1 - filterStatus) * 100);
		// Update the content of the span element with the percentage value
		modal.find('#filterStatusValue').text(percentage);
});


});







