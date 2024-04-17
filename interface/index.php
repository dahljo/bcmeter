<?php
// Start the PHP session
session_start();
$_SESSION['valid_session'] = 1;
header('X-Accel-Buffering: no');

?>

<?php
$macAddr = exec("/sbin/ifconfig wlan0 | grep 'ether' | awk '{print $2}'");
$macAddr = str_replace(':', '', $macAddr);


$filename = '/home/pi/bcMeterConf.py';
$is_ebcMeter = false; // Default value

if (file_exists($filename)) {
    $lines = file($filename, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);

    foreach ($lines as $line) {
        if (strpos($line, 'is_ebcMeter=True') !== false) {
            $is_ebcMeter = true;
        } 
    }
}



?>



<!DOCTYPE html>
<meta charset="utf-8">
<head>    
  <link rel="stylesheet" type="text/css" href="css/bootstrap.min.css">
  <link rel="stylesheet" type="text/css" href="css/bootstrap4-toggle.min.css">

  <link rel="stylesheet" type="text/css" href="css/bcmeter.css">


</head>


<body>
	<a href="" id="download" style="display: none;"></a>

<br />


 <?php 
 echo "<a href=\"index.php\"><img src=\"bcMeter-logo.png\" style=\"width: 250px; display:block; margin: 0 auto;\"/></a>";
if ($is_ebcMeter === true) {
  echo "<p style='text-align:center;font-weight:bold;'>emission measurement prototype</p>";
}

 ?>
 <div class="status-div" id="statusDiv"></div>

 <div class="container">
  <div class="row">
<div class="col-sm-12">

      <div style='display:none; margin: 20px 0;' id='hotspotwarning' class='alert'>


      <div style='text-align:center;'><strong>You're currently offline</strong></div>
      


                  <!-- Begin Set Time -->
                  <div style="display: block;margin: 0 auto;">
                  <p style="text-align: center;" id="datetime_note"></p>
                  <pre style='text-align:center;' id='datetime_device'></pre>
                  <pre style='text-align:center;' id='datetime_local'></pre>
                   </div>
                <!-- end set time modal-->



                  <div style="text-align: center";>
                  <form method="POST">
                    <input type="hidden" id="set_time" name="set_time" value="">
                    <input type="submit" value="Set clock on bcMeter to your time" class="btn btn-primary" >
                  </form>
                </div>
</div>
      </div>
    </div>
  </div>

  <div id="report-value" style="text-align: center; display: block;margin: 20px 0;"></div>

       <?php



 $version = '';
    $localfile = '/home/pi/bcMeter.py';
    for($i = 1; $i <= 50; $i++) {
      $line = trim(exec("head -$i $localfile| tail -1"));
      if (strpos($line, 'bcMeter_version') === 0) {
        $version = explode('"', $line)[1];
        break;
      }
    }

    $version_parts = explode('.', $version);


    $VERSION = $version_parts[0] . "." . $version_parts[1]  . "." .  $version_parts[2];



    $grep = shell_exec('ps -eo pid,lstart,cmd | grep bcMeter.py | grep -Fv grep | grep -Fv www-data | grep -Fv sudo | grep -Fiv screen | grep python3');

?>


        



<!-- Bootstrap Layout -->





	 <!-- CONTAINER FOR DROP DOWN MENU -->
	<div class="menu" style="display: block; text-align: center;">Selected View:
		<!-- get the list of log -->
    <?php
      $folder_path = '../logs';
      $logString = "<select id = 'logs_select'>";
      $logFiles = scandir($folder_path);
      foreach ($logFiles as $key => $value) {
        if ($key > 1) {
          $logString .= "<option value='{$value}'>{$value}</option>"; 
        }
      }
      $logString .= "<option value='combine_logs'>Combine Logs</option></select>";
      echo '<span id="logs">'.$logString.'</span>'; 
    ?>

		<span class="y-menu">
			<select id="y-menu"></select>
		</span>

		<span class="y-menu2">
				<select id="y-menu2"></select>
		</span>

		<span class="btn btn-light" id="hide-y-menu2">Hide</span>
		<span class="btn" id="resetZoom">Reset Zoom</span>

	</div>


	<!-- CONTAINER FOR CHART -->
	<div id="svg-container">
			 <input type="number"  id="y-menu-min" placeholder="min">
			 <input type="number"  id="y-menu-max" placeholder="max">
			 <input type="number" id="y-menu2-min" placeholder="min">
			 <input type="number" id="y-menu2-max" placeholder="max">
    <div class="tooltip" style="position: absolute;"></div>

		<svg id="line-chart" width="1100" height="480" style="margin: 0px auto 10px">
	</div>

	</svg>





	<!-- load the d3.js library -->
	<script src="js/d3.min.js"></script>
	<script src="js/jquery-3.6.0.min.js"></script>
	<script src="js/bootstrap.min.js"></script>
	<script src="js/bootbox.min.js"></script>

<script>
$(document).ready(function() {



    let selectLogs = document.getElementById("logs_select")
    current_file = selectLogs.value;
    if (current_file == 'log_current.csv') {
        updateCurrentLogsFunction()
      } 
    /* VARS*/
    let yColumn2 = "BC_rolling_avg_of_6",
      yColumn = "BCngm3",
      tooltip,
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

  if (typeof is_ebcmeter === 'undefined') {
    is_ebcmeter = false;
  }

  if (is_ebcmeter === true) {
    yColumn = "BCngm3_unfiltered";
    yColumn2 = "bcmSen";
  }


    /* CONSTANTS */
    const noData ="<div class='alert alert-warning' role='alert'>Not enough data yet.</div>";
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
    const yMax2Doc= document.getElementById("y-menu2-max");
    const resetZoom = document.getElementById("resetZoom");
    const yMenuDom = document.getElementById("y-menu")
    const yMenuDom2= document.getElementById("y-menu2")
    const bisect = d3.bisector(d => d.bcmTime).left;
    const xLabel = "bcmTime";

    /* PRESET AND PREPOPULATE */
    combineLogs["columns"] = ["BCngm3", "BCngm3_unfiltered", "BC_rolling_avg_of_6", "BC_rolling_avg_of_12", "bcmATN", "bcmRef", "bcmSen", "Temperature", "sht_humidity", "airflow"]
    data["columns"] = ["BCngm3", "BCngm3_unfiltered", "BC_rolling_avg_of_6", "BC_rolling_avg_of_12", "bcmATN", "bcmRef", "bcmSen", "Temperature", "sht_humidity", "airflow"]

    /* FUNCTION AND EVENT LISTENER */
    /* EVENT LISTENER FOR MIN AND MAX VALUES */
    yMinDoc.addEventListener("focusout", ()=>{
      yMinInputted = yMinDoc.value;
      render()
    }) 

    yMaxDoc.addEventListener("focusout", ()=>{
      yMaxInputted = yMaxDoc.value;
      render()
    }) 

    yMin2Doc.addEventListener("focusout", ()=>{
      yMin2Inputted = yMin2Doc.value;
      render()
    }) 

    yMax2Doc.addEventListener("focusout", ()=>{
      yMax2Inputted = yMax2Doc.value;
      render()
    }) 

    /* TO RESET TO DEFAULT AFTER ZOOMING */
    resetZoom.addEventListener("click", ()=>{
      brushedX = [];
      plotChart();
    })

    /* FUNTION TO SET Y AXIS VALUE TO USE, EITHER INPUTTED OR D3.JS CALCULATED */
    const setYAxis = () => {

      const yMin = yMinDoc.value; 
      const yMax = yMaxDoc.value; 
      const yMin2 = yMin2Doc.value; 
      const yMax2= yMax2Doc.value;  
      
      let [yDataMin, yDataMax] = d3.extent(data, yValueScale)
      let [yDataMin2, yDataMax2]= d3.extent(data, yValueScale2)

      yRange = [];
      yRange2 = [];

      yMinInputted == '' ? yRange.push(yDataMin) : yRange.push(Number(yMin));
      yMaxInputted == '' ? yRange.push(yDataMax) : yRange.push(Number(yMax))
      yMin2Inputted == '' ? yRange2.push(yDataMin2) : yRange2.push(Number(yMin2))
      yMax2Inputted == '' ? yRange2.push(yDataMax2) : yRange2.push(Number(yMax2))

      yMinDoc.value = yRange[0]; 
      yMaxDoc.value = yRange[1]; 

      if(!isHidden){
        yMin2Doc.value = yRange2[0]; 
        yMax2Doc.value = yRange2[1]; 
      } 
    }


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
      .extent([[0, 0], [innerWidth, innerHeight]])
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
        .on("mousemove", function (e) {
          if (data.length != 0) {
            const x = d3.pointer(e)[0];
            hoveredTime = xScale.invert(x);
            let bi = bisect(data, hoveredTime)-1
            bi_lower = bi < 0 ? 0 : bi;
            bi_upper = bi + 1 > data.length-1 ? data.length-1 : bi + 1
            let idx  = -new Date(data[bi_lower]["bcmTime"]).getTime() - -new Date(hoveredTime).getTime() > -new Date(hoveredTime).getTime() - -new Date(data[bi_upper]["bcmTime"]).getTime() 
            ? bi_upper 
            : bi_lower

            const temp = data[idx];
            let diff = e.offsetX - e.pageX
            const maxLeft = innerWidth/2 > e.offsetX
            ? xScale(data[idx][xLabel])+margin.right + 30 - diff

            : xScale(data[idx][xLabel]) - 25 - diff

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
              .html( tooltipMessage )

            d3.select(".selected-time-line")
              .attr("x1", xScale(temp[xLabel]))
              .attr("x2", xScale(temp[xLabel]))
              .attr("y2", innerHeight)
              .style("opacity", "1")
              
            if(!isHidden){
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

        .on("mouseout", function (e) {
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

    const updateCurrentLogsFunction = () => {
     updateCurrentLogs = setInterval(() => {  

        dataFile(`${logPath}log_current.csv`);
    }, 5000)

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
    
    selectLogs.addEventListener("change", function(){
      brushedX = [];
      current_file = selectLogs.value; 
      data = dataObj[current_file];
       if(data) {
        let len = data.length - 1;
        render();

        // Calculate averages once
        let avg12 = d3.mean([...data].splice(len-12, 12), BCngm3_value);
        let avgAll = d3.mean(data, BCngm3_value);

        // Prepare output based on is_ebcmeter flag
        let unit = is_ebcmeter ? "µg/m<sup>3</sup>" : "ng/m<sup>3</sup>";

        document.getElementById("report-value").innerHTML = `Averages: <h4 style='display:inline'>
        ${(avg12 ).toFixed(is_ebcmeter ? 3 : 0)} ${unit}<sub>avg12</sub> » 
        ${(avgAll ).toFixed(is_ebcmeter ? 3 : 0)} ${unit}<sub>avgALL</sub></h4>`;
      }

      if (current_file == 'log_current.csv') {
        updateCurrentLogsFunction()
      } else {
      clearInterval(updateCurrentLogs)
      }
  })



    yMenuDom.addEventListener("change", function(){
      yOptionClicked(this.value)
    })
    yMenuDom2.addEventListener("change", function(){
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
      if ((((yColumn ==  "BCngm3_unfiltered") && yColumn2 == "BCngm3") ||
        ((yColumn2 ==  "BCngm3_unfiltered") && yColumn == "BCngm3") && !isHidden)) {
        yValueScale = BCngm3_unfiltered_value;
        yValueScale2 = BCngm3_unfiltered_value;

      } 
      if ((((yColumn ==  "BC_rolling_avg_of_6" || yColumn == "BC_rolling_avg_of_12") && yColumn2 == "BCngm3") ||
        ((yColumn2 ==  "BC_rolling_avg_of_6" || yColumn2 == "BC_rolling_avg_of_12") && yColumn == "BCngm3")) && !isHidden) {
        yValueScale = BCngm3_value;
        yValueScale2 = BCngm3_value;
      } 

      
      else {
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


    const dataFile = (file, isCombineLogsSelected = false ) => {
      data = []
      data["columns"] = ["BCngm3","BCngm3_unfiltered", "BC_rolling_avg_of_6", "BC_rolling_avg_of_12", "bcmATN", "bcmRef", "bcmSen","Temperature","Humidity","Airflow"]
      
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
            d.BCngm3_unfiltered= +d.BCngm3_unfiltered;
            d.Temperature = +d.Temperature;
            d.sht_humidity = +d.sht_humidity;

            data.push(d)
          }
        });


          let result = file.includes("../logs/log_current.csv");
          if (result == true) { 

              let len = data.length - 1;

              if (len>0) {
                let unit = is_ebcmeter ? "µg/m<sup>3</sup>" : "ng/m<sup>3</sup>";

                // Calculate averages once
                let avg12 = d3.mean([...data].splice(len-12, 12), BCngm3_value);
                let avgAll = d3.mean(data, BCngm3_value);

                document.getElementById("report-value").innerHTML = `Averages: <h4 style='display:inline'>
                ${avg12.toFixed(is_ebcmeter ? 3 : 0)} ${unit}<sub>avg12</sub> » 
                ${avgAll.toFixed(is_ebcmeter ? 3 : 0)} ${unit}<sub>avgALL</sub></h4>`;
                let bcmRef = data[len].bcmRef;
                let bcmSen = data[len].bcmSen;
                let btn = document.getElementById("report-button");
                if (bcmSen == 0){
                  if (bcmRef == 0) {
                    btn.className = "btn btn-secondary";

                  }
                }




                let filterStatus = bcmRef/bcmSen;
                if (filterStatus <= 2) {
                    btn.className = "btn btn-success";
                  } else if (filterStatus > 2 && filterStatus <= 3) {
                    btn.className = "btn btn-warning";
                  } else if (filterStatus > 3 && filterStatus <= 4) {
                    btn.className = "btn btn-danger";
                  } else if (filterStatus > 4 && filterStatus <= 6) {
                    btn.className = "btn btn-secondary";
                  } else if (filterStatus > 6) {
                    btn.className = "btn btn-dark";
                  }
                }
                
              if (len<0) {
                document.getElementById("report-value").innerHTML = `<h4> </h4>`;
              }
}


          


     /* MOVING AVERAGE = 6 */

        data.map((d, i) => {
        if (i < 4 || i > data.length - 3) {
            d.BC_rolling_avg_of_6 = null;
        } else {
          d.BC_rolling_avg_of_6 = +((((((data.slice(movingIndex6,  movingIndex6 + 6).reduce((p, c) => p + c.BCngm3_unfiltered, 0)) / 6)) 
          +(((data.slice(movingIndex6 + 1, movingIndex6 + 1 + 6).reduce((p, c) =>  p + c.BCngm3_unfiltered, 0)) / 6))) / 2).toFixed(0))
          movingIndex6++;
        }
        /* MOVING AVERAGE = 12 */
        if (i < 7 || i > data.length - 6) {
          d.BC_rolling_avg_of_12 = null;
        } else {
          d.BC_rolling_avg_of_12 = +((((((data.slice(movingIndex12, movingIndex12 + 12).reduce((p, c) => p + c.BCngm3_unfiltered, 0)) / 12)) 
          +(((data.slice(movingIndex12 + 1, movingIndex12 + 1 + 12).reduce((p, c) => p + c.BCngm3_unfiltered, 0)) / 12))) / 2).toFixed(0))
          movingIndex12++;
        }
        if(isCombineLogsSelected){
          dataObj[file.split("/")[2]] = data
          combineLogs.push(d)
        }



        })

  

        if(isCombineLogsSelected){
          combinedLogCurrentIndex++;
          if(combinedLogCurrentIndex < logFilesSize){
            dataFile(`${logPath}${logFiles[combinedLogCurrentIndex]}`, true)
          } else {
            dataObj["combine_logs"] = combineLogs;
            selectLogs.value = "log_current.csv";
            selectLogs.dispatchEvent(new Event("change"))
            render();                
          }
        }
      else{
          render();
      }
      });
    }
    


    /* INITIAL LOAD */
    let logPath = '../logs/';
    let updatelogs;
    let logFiles = <?php echo json_encode($logFiles);  ?>;
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

      img.onload = function () {
        ct.drawImage(img, 0, 0);
        bolbURL.createObjectURL(serializeData()["svgBlob"]);
        downloadFile(dom.toDataURL('image/png'), "png")
      };
      img.src = serializeData()["svgURL"];BCngm3
    }

    const saveCSV = () => { 
      downloadCSVFile(`../logs/${current_file}`, "csv")
    }

    const downloadCSVFile = (url, ext) => {
      var today = new Date();
      var date = today.getFullYear().toString() + (today.getMonth()+1).toString() + today.getDate().toString();
      var time = today.getHours().toString() + today.getMinutes().toString() + today.getSeconds().toString();
      var dateTime = date+'_'+time;
     // var savingWord = (!isHidden) ? `bcMeter-(${yColumn}-vs-${yColumn2})` : `bcMeter-${yColumn}`;
      download.href = url;
      var hostName = location.hostname;
      download.download = `${hostName}_${dateTime}.${ext}`;
      download.click();
    }


    const downloadFile = (url, ext) => {
      var today = new Date();
      var date = today.getFullYear()+(today.getMonth()+1) + today.getDate();
      var time = today.getHours() + today.getMinutes() + today.getSeconds();
      var dateTime = date+'_'+time;
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
      if(isHidden){
        yMin2Doc.style.opacity = 0
        yMax2Doc.style.opacity = 0
      }
      else{
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

  function activateAndLoadConfig(tabElement) {
    tabElement.tab('show');
    const configType = tabElement.attr('aria-controls');
    loadConfig(configType);
  }



          // Listen to tab changes to refresh configurations if needed
  $('#configTabs a').on('click', function(e) {
    e.preventDefault();
    activateAndLoadConfig($(this));
  });



  const initialTab = $('#configTabs a.active');
  if (initialTab.length) {
    activateAndLoadConfig(initialTab);
  } else {
    // If no active tab, load the first tab or a specific tab as needed
    activateAndLoadConfig($('#configTabs a').first());
  }


          function loadConfig(configType) {
            fetch(`${getBaseUrl()}/load-config`)
              .then(response => response.json())
              .then(data => {
                const formId = configType === 'session' ? 'session-parameters-form' : configType === 'device' ? 'device-parameters-form' : 'administration-parameters-form';
                const tbody = document.querySelector(`#${formId} tbody`);
                tbody.innerHTML = ''; // Clear existing rows
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
              })
              .catch(error => console.error('Failed to load configuration:', error));
          }

          function saveConfiguration(configType) {
           const formId = configType === 'session' ? 'session-parameters-form' : configType === 'device' ? 'device-parameters-form' : 'administration-parameters-form';
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

            // Retrieve the description from the corresponding tr element if it exists
            const descriptionElement = input.closest('tr').getAttribute('title');
            const description = descriptionElement ? descriptionElement.trim() : '';

            // Skip if the key is empty
            if (key) {
              // Construct the configuration object with description and value
              updatedConfig[key] = {
                value: value,
                description: description,
                type: input.type === 'checkbox' ? 'boolean' : input.classList.contains('array') ? 'array' : typeof value,
                parameter: configType
              };
            }
          });

            // Fetch the existing configurations
            fetch(`${getBaseUrl()}/load-config`)
              .then(response => response.json())
              .then(existingConfig => {
                // Merge the updated configurations with the existing ones
                const mergedConfig = { ...existingConfig };

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
  if (tabId === 'session-tab') {
    saveConfiguration('session');
  } else if (tabId === 'device-tab') {
    saveConfiguration('device');
  } else if (tabId === 'administration-tab') {
    saveConfiguration('administration');
  }
}

// Event listener for saving on "Enter" key press
document.addEventListener("keydown", function(event) {
  if (event.key === "Enter") {
    // Check if the modal is open before triggering save
    if ($('#device-parameters').hasClass('show')) {
      var activeTabId = $('.nav-tabs .nav-link.active').attr('id');
      saveConfigurationBasedOnTab(activeTabId);
      $('#device-parameters').modal('hide'); // Close the modal after saving
    }
  }
});

// Event listeners for saving on button click
document.getElementById("saveSessionSettings").addEventListener("click", function(event) {
  event.preventDefault();
  saveConfigurationBasedOnTab('session-tab');
  $('#device-parameters').modal('hide'); // Close the modal after saving
});

document.getElementById("saveDeviceSettings").addEventListener("click", function(event) {
  event.preventDefault();
  saveConfigurationBasedOnTab('device-tab');
  $('#device-parameters').modal('hide'); // Close the modal after saving
});

document.getElementById("saveAdministrationSettings").addEventListener("click", function(event) {
  event.preventDefault();
  saveConfigurationBasedOnTab('administration-tab');
  $('#device-parameters').modal('hide'); // Close the modal after saving
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
                          callback: function(){

                          }
                      },
                      ok: {
                          label: "Yes",
                          className: 'btn-danger',
                          callback: function(){
                              window.location.href='includes/status.php?status=reboot';

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
                          callback: function(){

                          }
                      },
                      ok: {
                          label: "Yes",
                          className: 'btn-danger',
                          callback: function(){


                          $.ajax({
                              type: 'post',
                              data: 'exec_stop',
                              success: function(response){
                              
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
                          callback: function(){

                          }
                      },
                      ok: {
                          label: "Yes",
                          className: 'btn-danger',
                          callback: function(){

                            $.ajax({
                              type: 'post',
                              data: 'exec_debug',
                              success: function(response){
                                 window.location.href='includes/status.php?status=debug';
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
                          callback: function(){

                          }
                      },
                      ok: {
                          label: "Yes",
                          className: 'btn-danger',
                        callback: function() {
                            // Make AJAX call to initiate the backend process
                            $.ajax({
                                type: 'post',
                                data: {force_wifi: true}, // Adjusted to pass data as an object
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
                      callback: function(){
                      }
                  },
                  ok: {
                      label: "Yes",
                      className: 'btn-danger',
                      callback: function(){
                          window.location.href='includes/status.php?status=calibration';

                      }
                  }
              }
          });
           
        });





        $('#bcMeter_update').click(function(e) {
            e.preventDefault(); // Prevent the default submit behavior

          bootbox.dialog({
              title: 'Update bcMeter?',
              message: "<p>The most recent files will be downloaded. If possible, your parameters will be kept but please save them and check after the update if they are the same. </p>",
              size: 'medium',
              buttons: {
                  cancel: {
                      label: "No",
                      className: 'btn-success',
                      callback: function(){
                      }
                  },
                  ok: {
                      label: "Yes",
                      className: 'btn-danger',
                      callback: function(){
                          window.location.href='includes/status.php?status=update';

                      }
                  }
              }
          });
           
        });






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
                    callback: function(){
                        saveCSV();

                    }
                },
                2: {
                    label: "PNG (Web/Mail)",
                    className: 'btn-info',
                    callback: function(){
                        savePNG();

                    }
                },
                3: {
                    label: "SVG (DTP)",
                    className: 'btn-info',
                    callback: function(){
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
                                data: {exec_new_log: true}, // Adjusted to pass data as an object
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



        /*document.getElementById("fetchWifiButton").addEventListener("click", function() {
          // Function to fetch Wi-Fi list
          $.get("includes/wlan_list.php", function(data, status) {
              var ssid_arr = JSON.parse(data);
              var select = document.getElementById("js-wifi-dropdown");

              for (var i = 0; i < ssid_arr.length; i++) {
                  if (currentWifiSsid != ssid_arr[i]) { // current ssid is added in setup/index.php
                      var el = document.createElement("option");
                      el.textContent = ssid_arr[i];
                      el.value = ssid_arr[i];
                      select.appendChild(el);
                  }
              }

              // Hide loading indicator after fetching
              $('.loading-available-networks').hide();
          });*/



    var optionsButton = document.querySelector('[data-target="#pills-devicecontrol"]');
    optionsButton.addEventListener('click', function() {
        var target = document.querySelector(this.getAttribute('data-target'));
        if (target.style.display === "none") {
            target.style.display = "block";
        } else {
            target.style.display = "none";
        }
    });




  // ----------- password
  $( ".toggle-password" ).click(function() {
      $(this).toggleClass("closed");
      var input = $("#pass_log_id");
      if (input.attr("type") === "password") {
      input.attr("type", "text");
      } else {
      input.attr("type", "password");
      }
  });
  // ----------- edit existing password
  $( ".js-edit-password" ).click(function() {
    $('.wifi-pwd-field-exist').hide();
    $('.wifi-pwd-field').show();
  });
  

  // ---------- wifi  
  var dropdown = document.getElementById('js-wifi-dropdown');
    dropdown.onchange = function () {
    if(this[this.selectedIndex].value == "custom-network-selection"){
      document.getElementById('custom-network').style.display='block';
    }else {
      document.getElementById('custom-network').style.display='none';
    }
  };
  
  
  
  
  //get wlan list from jquery get  --> 
  $.get("includes/wlan_list.php", function(data, status){
    
    var ssid_arr = JSON.parse(data);
    var select = document.getElementById("js-wifi-dropdown");
  
    for(var i = 0; i < ssid_arr.length; i++) {
      if(currentWifiSsid!=ssid_arr[i]){         // current ssid is added in setup/index.php
        var el = document.createElement("option");
        el.textContent = ssid_arr[i];
        el.value = ssid_arr[i];
        select.appendChild(el);
      }
    }
    
    $('.loading-available-networks').hide();
    
  });





    setInterval(function() {
      var date = new Date();
      var timestamp = (date.getTime() / 1000).toFixed(0);
      var currentDateTime = date.toLocaleString('default', {
        month: 'short'
      }) + " " + date.getDate() + " " + date.getFullYear() + " " + date.getHours() + ":" + date.getMinutes() + ":" + date.getSeconds();
      document.getElementById("datetime_local").innerHTML = "Current time based on your Browser: <br/>" + currentDateTime;
      document.getElementById("set_time").value = timestamp;

      $.ajax({
        url: "includes/gettime.php", // The page containing php script
        type: "post", // Request type
        data: { datetime: "now" },
        cache: false, // Prevent the browser from caching the result
        timeout: 1000, // Set timeout for the request (e.g., 5000 milliseconds)
        success: function(result) {
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
          document.getElementById("datetime_device").innerHTML = "No connection to bcMeter";
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
        $('#wifisetup').modal('hide'); // This line uses Bootstrap's jQuery plugin to hide the modal
    });





});










  </script>


<form style="display: block; text-align:center;" method="post">
    <input type="submit" id="startNewLog" name="newlog" value="Start" class="btn btn-info" />
    <input type="submit" id="bcMeter_stop" name="bcMeter_stop" value="Stop" class="btn btn-secondary" />
    <input type="submit" id="saveGraph" name="saveGraph" value="Download" class="btn btn-info bootbox-accept" />
<button type="button" class="btn btn-info" data-toggle="pill" data-target="#pills-devicecontrol" role="tab">Administration</button>

    <!-- Trigger Modal Button for Filter Status -->
    <button type="button" class="btn btn-info" data-toggle="modal" data-target="#filterStatusModal" id="report-button">Filter</button>
</form>

<!-- Filter Status Modal -->
<div class="modal fade" id="filterStatusModal" tabindex="-1" role="dialog" aria-labelledby="filterStatusModalLabel" aria-hidden="true">
    <div class="modal-dialog" role="document">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title" id="filterStatusModalLabel">Filter Status</h5>
                <button type="button" class="close" data-dismiss="modal" aria-label="Close">
                    <span aria-hidden="true">&times;</span>
                </button>
            </div>
            <div class="modal-body">
                <p>5 colors are possible: Green, red, orange, grey and black. Red means: be prepared to change. <br /> When grey, it should be changed. <br />Data will still be gathered. When black, the paper cannot load any more black carbon.</p>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-dismiss="modal">Close</button>
            </div>
        </div>
    </div>
</div>

<br />

<div class="tab-pane fade" id="pills-devicecontrol" role="tabpanel" aria-labelledby="pills-devicecontrol-tab" style="display: none;">
    <form style="text-align:center;" method="post">
          <button type="button" class="btn btn-primary" data-toggle="modal" data-target="#wifisetup">WiFi Settings</button>
        <button type="button" class="btn btn-secondary" data-toggle="modal" data-target="#device-parameters">Settings</button>
        <button type="button" class="btn btn-info" data-toggle="modal" data-target="#downloadOld"> All logs </button>
                <input type="submit" name="deleteOld" value="Delete old logs" class="btn btn-info" />
        <input type="submit" id="bcMeter_calibration" name="bcMeter_calibration" value="Calibration" class="btn btn-info" />

                <button type="button" class="btn btn-info" data-toggle="modal" data-target="#systemlogs"> System Logs </button>
        <input type="hidden" name="randcheck" />
        <input type="submit" id="bcMeter_update" name="bcMeter_update" value="Update bcMeter" class="btn btn-info" />
        <button type="button" class="btn btn-info" data-toggle="modal" data-target="#edithostname"> Change Hostname </button> 
                <input type="submit" name="bcMeter_reboot" id="bcMeter_reboot" value="Reboot" class="btn btn-info" />

            <input type="submit" name="shutdown" value="Shutdown" class="btn btn-danger" />

        <?php
            $hostname = $_SERVER['HTTP_HOST'];
            $macAddr = 'bcMeter_0x' . $macAddr;
            echo "<br />thingID: $macAddr<br />Version: $VERSION";
        ?>
    </form>

    <!-- Modal for Downloading Old Logs -->
    <div class="modal fade" id="downloadOld" tabindex="-1" role="dialog" aria-labelledby="exampleModalCenterTitle" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered" role="document">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="exampleModalLongTitle">Old logs</h5>
                    <button type="button" class="close" data-dismiss="modal" aria-label="Close">
                        <span aria-hidden="true">&times;</span>
                    </button>
                </div>
                <div class="modal-body">
                    <table class='container'>
                        <thead>
                            <tr>
                                <th>Download log from</th>
                            </tr>
                        </thead>
                        <tbody>
                            <?php
                            $hostname = $_SERVER['HTTP_HOST'];
                            // List all .csv files in current directory
                            $dir = "../logs";
                            $files = scandir($dir);

                            foreach ($files as $file) :
                                if (pathinfo($file, PATHINFO_EXTENSION) === 'csv' && $file != 'log_current.csv') :

                                    // Extract the date and time from the filename
                                    $date_time = explode("_", substr($file, 0, -4))[1];
                                    $date_time_day = explode("_", substr($file, 0, -4))[0];

                                    $date_time = $date_time_day ." ". substr($date_time, 0, 2) . ":" . substr($date_time, 2, 2) . ":" . substr($date_time, 4, 2);
                            ?>
                                    <tr>
                                        <td><?= $date_time ?></td>
                                        <td><a href='<?= $dir ."/". $file ?>' download='<?=$hostname . '_' . $file;?>'><button type="button" value='Test' class='btn btn-primary'>Download</button></a></td>
                                    </tr>
                            <?php endif; ?>
                            <?php endforeach; ?>
                        </tbody>
                    </table>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-dismiss="modal">Cancel</button>
                </div>
            </div>
        </div>
    </div>
</div>




<div class="container mt-5">
    <div class="log-container">
       
     

    </div>
</div>

  </div>
</div>
<!-- begin edit hostname modal -->
<div class="modal fade" id="edithostname" tabindex="-1" role="dialog" aria-labelledby="exampleModalCenterTitle1" aria-hidden="true">
  <div class="modal-dialog modal-dialog-centered" role="document">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title" id="exampleModalLongTitle">Change the Hostname of the device</h5>
        <button type="button" class="close" data-dismiss="modal" aria-label="Close">
          <span aria-hidden="true">&times;</span>
        </button>
      </div>
      <div class="modal-body">
        <form action="/interface/includes/status.php" method="GET">
          <label for="new_hostname">New Hostname:</label>
          <input type="text" id="new_hostname" name="new_hostname" pattern="[a-zA-Z0-9]+" required>
          <input type="hidden" name="status" value="change_hostname">
          <input type="submit" value="Submit">
        </form>
      </div>
    </div>
  </div>
</div>
<!-- End Edit Parameters -->


<!-- begin Log modal -->
<div class="modal fade" id="systemlogs" tabindex="-1" role="dialog" aria-labelledby="exampleModalCenterTitle1" aria-hidden="true">
  <div class="modal-dialog modal-dialog-centered" role="document" style="max-width: 90%;">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title" id="exampleModalLongTitle">bcMeter Logs</h5>
        <button type="button" class="close" data-dismiss="modal" aria-label="Close">
          <span aria-hidden="true">&times;</span>
        </button>
      </div>
      <div class="modal-body"> 

        <p style="text-align:center"></p>
        <div class="accordion" id="accordionExample">
    <div class="card">
        <div class="card-header" id="headingOne">
            <h2 class="mb-0">
                <button class="btn btn-link btn-block text-left collapsed" type="button" data-toggle="collapse" data-target="#collapseOne" aria-expanded="false" aria-controls="collapseOne">
                    bcMeter.log
                </button>
            </h2>
        </div>
        <div id="collapseOne" class="collapse" aria-labelledby="headingOne" data-parent="#accordionExample">
            <div class="card-body">
                <div class="log-box" id="logBcMeter">
                    <!-- Log content will be injected here -->
                </div>
            </div>
        </div>
    </div>
    <div class="card">
        <div class="card-header" id="headingTwo">
            <h2 class="mb-0">
                <button class="btn btn-link btn-block text-left collapsed" type="button" data-toggle="collapse" data-target="#collapseTwo" aria-expanded="false" aria-controls="collapseTwo">
                    ap_control_loop.log
                </button>
            </h2>
        </div>
        <div id="collapseTwo" class="collapse" aria-labelledby="headingTwo" data-parent="#accordionExample">
            <div class="card-body">
                <div class="log-box" id="logApControlLoop">
                    <!-- Log content will be injected here -->
                </div>
            </div>
        </div>
    </div>
    <div class="card">
        <div class="card-header" id="headingThree">
            <h2 class="mb-0">
                <button class="btn btn-link btn-block text-left collapsed" type="button" data-toggle="collapse" data-target="#collapseThree" aria-expanded="false" aria-controls="collapseThree">
                    compair_frost_upload.log
                </button>
            </h2>
        </div>
        <div id="collapseThree" class="collapse" aria-labelledby="headingThree" data-parent="#accordionExample">
            <div class="card-body">
                <div class="log-box" id="logCompairFrostUpload">
                    <!-- Log content will be injected here -->
                </div>
            </div>
        </div>
    </div>
</div>

<script>
function fetchAndProcessLogFile(logType, elementId) {
    fetch(`../maintenance_logs/${logType}.log`)
        .then(response => {

            if (!response.ok) {
                document.getElementById(elementId).innerHTML = 'Log file not found.';
            }
            else {
               return response.text();
          }

        })
        .then(data => {
            const lines = data.split('\n');
            let prevContent = '';
            let contentCount = 0;
            let output = '';

            lines.forEach(line => {
                const matches = line.match(/(DEBUG|ERROR): (.+)/);
                if (matches) {
                    const content = matches[2];
                    if (content === prevContent) {
                        contentCount++;
                    } else {
                        if (contentCount > 1) {
                            output += `${prevContent} (Repeated ${contentCount} times)<br>`;
                        } else if (prevContent !== '') {
                            output += `${prevContent}<br>`;
                        }
                        prevContent = content;
                        contentCount = 1;
                    }
                }
            });

            if (contentCount > 1) {
                output += `${prevContent} (Repeated ${contentCount} times)<br>`;
            } else if (prevContent !== '') {
                output += `${prevContent}<br>`;
            }

            document.getElementById(elementId).innerHTML = output;
        })
        .catch(error => {

        });
}


function startLogFetching() {
    const logs = [
        { type: 'bcMeter', elementId: 'logBcMeter' },
        { type: 'ap_control_loop', elementId: 'logApControlLoop' },
        { type: 'compair_frost_upload', elementId: 'logCompairFrostUpload' }
    ];

    logs.forEach(log => {

        fetchAndProcessLogFile(log.type, log.elementId);
      
        setInterval(() => fetchAndProcessLogFile(log.type, log.elementId), 15000);
    });
}

document.addEventListener('DOMContentLoaded', startLogFetching);
</script>


<br />

<form method="post" action="">
    <input type="submit" name="syslog" value="Download logs" class="btn btn-info" style="display: block;width: 50%;margin: 0 auto;" />
</form><br />
<p style="display:block; margin 0 auto;">In case of problems, please download the logs and send it to jd@bcmeter.org!</p>
      </div>
    </div>
  </div>
</div>
<!-- End Log Parameters -->
<!-- Start Edit device Parameters -->
<script src="js/bootstrap4-toggle.min.js"></script>
<!-- begin edit device parameters modal -->
<div class="modal fade" id="device-parameters" tabindex="-1" role="dialog" aria-labelledby="exampleModalCenterTitle1" aria-hidden="true">
  <div class="modal-dialog modal-dialog-centered" role="document" style="max-width: 90%;">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title" id="exampleModalLongTitle">Edit Parameters</h5>
        <button type="button" class="close" data-dismiss="modal" aria-label="Close">
          <span aria-hidden="true">&times;</span>
        </button>
      </div>
      <div class="modal-body">
        <div class="container mt-3">
          <!-- Nav tabs -->
          <ul class="nav nav-tabs" id="configTabs" role="tablist">
            <li class="nav-item">
              <a class="nav-link active" id="session-tab" data-toggle="tab" href="#session" role="tab" aria-controls="session" aria-selected="true">Session Parameters</a>
            </li>
            <li class="nav-item">
              <a class="nav-link" id="device-tab" data-toggle="tab" href="#device" role="tab" aria-controls="device" aria-selected="false">Device Parameters</a>
            </li>
            <li class="nav-item">
              <a class="nav-link" id="administration-tab" data-toggle="tab" href="#administration" role="tab" aria-controls="administration" aria-selected="false">Administration Parameters</a>
            </li>
          </ul>
          <!-- Tab panes -->
          <div class="tab-content">
            <div class="tab-pane active" id="session" role="tabpanel" aria-labelledby="session-tab">
              <!-- Session parameters form -->
              <form id="session-parameters-form">
                <table class="table table-bordered">
                  <thead>
                    <tr>
                      <th scope="col" style="width: 80%;" data-toggle="tooltip" data-placement="top" title="Variable Name">Description</th>
                      <th scope="col" style="width: 20%;">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                      <!-- Dynamic Session Configuration Rows Will Be Inserted Here by JavaScript -->
                  </tbody>
                </table>
                <button type="button" class="btn btn-primary" id="saveSessionSettings">Save Session Settings</button>
              </form>
            </div>
            <div class="tab-pane" id="device" role="tabpanel" aria-labelledby="device-tab">
              <!-- Device parameters form -->
              <form id="device-parameters-form">
                <table class="table table-bordered">
                  <thead>
                    <tr>
                      <th scope="col" style="width: 90%;" data-toggle="tooltip" data-placement="top" title="Variable Name">Description</th>
                      <th scope="col" style="width: 10%;">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                      <!-- Dynamic Device Configuration Rows Will Be Inserted Here by JavaScript -->
                  </tbody>
                </table>
                <button type="button" class="btn btn-primary" id="saveDeviceSettings">Save Device Settings</button>
              </form>
            </div>
            <div class="tab-pane" id="administration" role="tabpanel" aria-labelledby="administration-tab">
              <!-- Administration parameters form -->
              <form id="administration-parameters-form">
                <table class="table table-bordered">
                  <thead>
                    <tr>
                      <th scope="col" style="width: 90%;" data-toggle="tooltip" data-placement="top" title="Variable Name">Description</th>
                      <th scope="col" style="width: 10%;">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                      <!-- Dynamic Administration Configuration Rows Will Be Inserted Here by JavaScript -->
                  </tbody>
                </table>
                <button type="button" class="btn btn-primary" id="saveAdministrationSettings">Save Administration Settings</button>
              </form>
            </div>
          </div>
        </div>

      </div>
    </div>
  </div>
</div>
<!-- End Edit device Parameters -->





<!-- Begin Set WiFi -->
<div class="modal fade" id="wifisetup" tabindex="-1" role="dialog" aria-labelledby="exampleModalCenterTitle2" aria-hidden="true">
  <div class="modal-dialog modal-dialog-centered" role="document">
    <div class="modal-content">
      <div class="modal-header">
        <h2 class="modal-title" id="exampleModalLongTitle" style="text-align: center;">Wifi Setup</h2>
        <button type="button" class="close" data-dismiss="modal" aria-label="Close">
          <span aria-hidden="true">&times;</span>
        </button>
      </div>
      <div class="modal-body" style="text-align: center;">
        <!-- start dynamic content for wifi setup --> <?php
                        //languages
                        if(isset($_GET['lang']) && in_array($_GET['lang'],['nl', 'en', 'si', 'es', 'de', 'fr'])) {
                          $lang = $_GET['lang'];
                          $_SESSION['lang'] = $lang;
                        } else {
                          $lang = isset($_SESSION['lang']) ? $_SESSION['lang'] : 'en';
                        }
                        require_once("lang/lang.".$lang.".php");


                        //mac adress and checksum
                        $macAddressHex = exec('cat /sys/class/net/wlan0/address');
                        $macAddressDec = base_convert($macAddressHex, 16,10);
                        $readableMACAddressDec = trim(chunk_split($macAddressDec, 4, '-'), '-');
                        $convert_arr=range('A', 'Z');
                          //split into 2 chunks -> max integer on 32bit system is 2147483647
                          //otherwise the modulo operation does work as expected
                        $chunk1=substr($macAddressDec, 0, 8);
                        $chunk2=substr($macAddressDec, 8);
                        $chunk1_mod=$chunk1 % 23;   //mod 23 because there are 26 letters
                        $chunk2_mod=$chunk2 % 23;
                        $checkModulo=$convert_arr[$chunk1_mod].$convert_arr[$chunk2_mod];

            
                        // wifi vars
                        $wifiFile='/home/pi/bcMeter_wifi.json';

                        $currentWifiSsid=null;
                        $currentWifiPwd=null;
                        $sendBackground=true;
                        $credsUpdated=false;

                        // save wifi credentials to json file
                        if (isset($_POST['conn_submit'])) {
                          $wifi_ssid=null;
                          if(trim($_POST['wifi_ssid'])==='custom-network-selection'){     //Own custom network, not in the network list
                            $wifi_ssid = trim($_POST['custom_wifi_name']);
                          }
                          else{
                            $wifi_ssid = trim($_POST['wifi_ssid']);
                          }

                          $wifi_pwd = trim($_POST['wifi_pwd']);
                          if(empty($wifi_pwd)){ 
                            $data=json_decode(file_get_contents($wifiFile),TRUE);                     //no pwd given, resubmit of old wifi network
                            $wifi_pwd = $data["wifi_pwd"];
                          }

                          $data = array("wifi_ssid"=>$wifi_ssid, "wifi_pwd"=>$wifi_pwd);
                          file_put_contents($wifiFile, json_encode($data, JSON_PRETTY_PRINT));
                          
                          $credsUpdated=true;

                        }

                        // check for existing wifi credentials
                        $data=json_decode(file_get_contents($wifiFile),TRUE);
                        $currentWifiSsid=$data["wifi_ssid"];
                        $currentWifiPwd=$data["wifi_pwd"];
                        $currentWifiPwdHidden=str_repeat("•", strlen($currentWifiPwd));

                        if (isset($_POST['reset_wifi_json'])) {
                            $wifiFile='/home/pi/bcMeter_wifi.json';
                            $wifi_ssid = "";
                            $wifi_pwd = "";
                            $data = array("wifi_ssid" => $wifi_ssid, "wifi_pwd" => $wifi_pwd);
                            file_put_contents($wifiFile, json_encode($data, JSON_PRETTY_PRINT));

                            // Redirect to the same page to reload it
                            header('Location: ' . $_SERVER['PHP_SELF']);
                        }
                        $sendBackground=false;

                        // send interrupt to bcMeter_ap_control_loop service and try to connect to the wifi network
                        $interruptSent=false;
                        if (isset($_POST['conn_submit'])) {
                          // get this pid for the bcMeter_ap_control_loop service
                          exec('systemctl show --property MainPID --value bcMeter_ap_control_loop.service', $output);
                          $pid=$output[0];
                          
                          if($pid==0){
                            echo("<div class='error'>". $language["service_not_running"]."</div>");
                          }
                          else{
                            // send SIGUSR1 signal to the bcMeter_ap_control_loop service
                            //exec('sudo kill -SIGUSR1 '.$pid, $output);
                            $interruptSent=true;
                          }
                        }
                        ?> <script>
          var currentWifiSsid = "<?php echo $currentWifiSsid; ?>";


          //set the title after the languages are loaded


  


        </script>
       


          <div class="box" <?php echo ($credsUpdated==true) ? 'style="display: block"' :'style="display: none"';?>>
            <div class='success-notifcation' <?php echo ($credsUpdated==true) ? 'style="display: block"' :'style="display: none"';?>> <?php echo $language["save_success"]; ?> </div>
          </div>
          <div class="content">
            <div class="tab-content tab-wifi">
              <div class="entering-the-connection-info">
                <br />
                <form name="conn_form" method="POST" action="index.php">
                  <!--
                                    <input type="TEXT" onfocus="if(this.value == 'wifi netwerk') {this.value='';}" name="wifi_ssid" value="<?php echo $language["wifi_network"]; ?>">
                                    -->
                  <label><?php echo $language["wifi_network"]; ?>:</label>
                  <div class="select-container">
                    <select name="wifi_ssid" id="js-wifi-dropdown"> <?php if ($currentWifiSsid===null) { ?> <option selected="selected"><?php echo $language["wifi_network_loading_short"]; ?></option> <?php } else { ?> <option selected="selected"><?php echo $currentWifiSsid; ?></option> <?php } ?> <option value="custom-network-selection"><?php echo $language["add_custom_network"]; ?></option>
                    </select>
                  </div>
                  <div class="loading-available-networks">
                    <img src="css/loading.svg" width="14"> <?php echo $language["wifi_network_loading"]; ?>
                  </div>
                  <div id="custom-network" style="display:none">
                    <div>
                      <label><?php echo $language["custom_network"]; ?>:</label>
                    </div>
                    <input type="TEXT" name="custom_wifi_name" value="">
                  </div>
                  <div id="wifi-pwd">
                    <div>
                      <div class="edit-password"><a href="#" class="js-edit-password"><?php echo $language["edit-password"]; ?></a></div>
                    </div>
                    <div class="wifi-pwd-field" style="display: <?php echo ((!empty($currentWifiPwd)) ? 'none' : 'block') ?>  ">
                      <input type="password" id="pass_log_id" name="wifi_pwd">
                      <span toggle="#password-field" class="icon-field icon-eye toggle-password">Show/Hide</span>
                    </div> <?php if(!empty($currentWifiPwd)) { ?> <div class="wifi-pwd-field-exist">
                      <div class="password-dots">
                        <input type="text" value="<?php echo $currentWifiPwdHidden ?>" readonly>
                      </div>
                    </div> <?php } ?>
                  </div>
                  <div class="submit-container">
                    <input type="Submit" name="conn_submit" value="<?php echo $language["save_and_connect"]; ?>" class="btn btn-primary">
                    <button type="button" class="btn btn-secondary" data-dismiss="modal">Cancel</button>
                    <input type="Submit" name="reset_wifi_json" value="Delete Wifi" class="btn btn-warning">
                  </div><br />
                  <sub>If you like to run the bcMeter independently without being connected to a WiFi, you can adjust it in the Settings.
                </form>
                <br /><!--button id="fetchWifiButton">Scan for Wi-Fi</button-->
                <input type="submit" name="force_wifi" id="force_wifi" value="Reconnect" class="btn btn-info" />

              </div> <!-- end entering-the-connection-info -->
            </div> <!-- tab-wifi -->
          </div>
          <!-- end dynamic content for wifi setup -->
      </div>
    </div>
  </div>
</div>
<!-- end set WiFi modal-->
<br />








<br /> <br />




<script>
function updateStatus(status, deviceName, creationTimeString) {
    const statusDiv = document.getElementById('statusDiv');
    statusDiv.className = 'status-div'; // Reset classes
    let formattedCreationTime = ''; // Declare formattedCreationTime here

    const year = parseInt("20" + creationTimeString.substring(0, 2));
    const month = parseInt(creationTimeString.substring(2, 4)) - 1; // Adjust for 0-indexed month in JavaScript
    const day = parseInt(creationTimeString.substring(4, 6));
    const hours = parseInt(creationTimeString.substring(7, 9));
    const minutes = parseInt(creationTimeString.substring(9, 11));
    const seconds = parseInt(creationTimeString.substring(11, 13));

    if (!isNaN(year) && !isNaN(month) && !isNaN(day) && !isNaN(hours) && !isNaN(minutes) && !isNaN(seconds)) {
        const creationDate = new Date(year, month, day, hours, minutes, seconds);
        formattedCreationTime = creationDate.toLocaleString(); // Assign value to formattedCreationTime
    } else {
        console.error("Invalid creationTimeString format.");
    }

    statusDiv.textContent = 
        (status === -1) ? deviceName + " status unknown" :
        (status === 0) ? deviceName + " stopped" :
        (status === 1) ? deviceName + " initializing" :
        (status === 2) ? deviceName + " running since " + formattedCreationTime :
        (status === 3) ? deviceName + " running in Hotspot Mode since " + formattedCreationTime :
        (status === 4) ? "Hotspot mode active, " + deviceName + " not measuring" : ""; // Added for status 4

    // Adjust class addition for -1 status case if desired
    statusDiv.classList.add(
        status === -1 ? 'bg-secondary' :
        status === 0 ? 'bg-danger' :
        status === 1 ? 'bg-warning' :
        status === 2 ? 'bg-success' :
        status === 3 ? 'bg-info' :
        status === 4 ? 'bg-info' : '' // Added for status 4
    );

    statusDiv.classList.add('text-white');

    var hotspotWarningDiv = document.getElementById('hotspotwarning');

    if (status === 4) {
        hotspotWarningDiv.style.display = 'block';
        hotspotWarningDiv.className = 'alert alert-warning';

    } else {
        hotspotWarningDiv.style.display = 'none';
    }
}


function fetchStatus() {
    fetch('/tmp/BCMETER_WEB_STATUS')
      .then(response => {
        if (!response.ok) {
          throw new Error('Network response was not ok');
        }
        return response.text(); // Change to text() to log the raw response
      })
      .then(data => {
        try {
          const jsonData = JSON.parse(data);
          const status = jsonData.bcMeter_status;
          const creationTimeString = jsonData.log_creation_time;
          const deviceName = jsonData.hostname;

          updateStatus(status, deviceName, creationTimeString);
        } catch (error) {
          console.error('Error parsing JSON:', error);
          //throw new Error('Error parsing JSON');
        }
      })
      .catch(error => {
        console.error('There was a problem with the fetch operation:', error);
        //const defaultDate = new Date().toLocaleString();
        //updateStatus(-1, "Device", defaultDate);
      });
}


  // Fetch status on page load
  fetchStatus();
  // Refresh status every 5 seconds
  setInterval(fetchStatus, 5000);




</script>


<?php










if (isset($_POST["deleteOld"]))
{

echo <<< javascript
<script>
var dialog = bootbox.dialog({
    title: 'Delete old logs from device?',
    message: "<p>This cannot be undone.</p>",
    size: 'small',
    buttons: {
        cancel: {
            label: "No",
            className: 'btn-success',
            callback: function(){

            }
        },
        ok: {
            label: "Yes",
            className: 'btn-danger',
            callback: function(){
                window.location.href='includes/status.php?status=deleteOld';

            }
        }
    }
});
</script>
javascript;


}





if (isset($_POST["set_time"]))
{

  $set_timestamp_to = $_POST['set_time'];

echo("<script>window.location.href='includes/status.php?status=timestamp&timestamp=$set_timestamp_to'</script>");

}





if (isset($_POST["syslog"]))
{

echo <<< javascript
<script>
var dialog = bootbox.dialog({
    title: 'Download Syslog?',
    message: "<p>Do you want to download the syslog for debugging?</p>",
    size: 'small',
    buttons: {
        cancel: {
            label: "No",
            className: 'btn-success',
            callback: function(){

            }
        },
        ok: {
            label: "Yes",
            className: 'btn-danger',
            callback: function(){
                window.location.href='includes/status.php?status=syslog';

            }
        }
    }
});
</script>
javascript;


}





if (isset($_POST["shutdown"]))
{

echo <<< javascript
<script>
var dialog = bootbox.dialog({
		title: 'Turn off bcMeter?',
		message: "<p>Do you want to shutdown the device?</p>",
		size: 'small',
		buttons: {
				cancel: {
						label: "No",
						className: 'btn-success',
						callback: function(){

						}
				},
				ok: {
						label: "Yes",
						className: 'btn-danger',
						callback: function(){
								window.location.href='includes/status.php?status=shutdown';

						}
				}
		}
});
</script>
javascript;


}


if (isset($_POST["force_wifi"]))
{
shell_exec("sudo systemctl restart bcMeter_ap_control_loop");
}



if (isset($_POST["exec_stop"]))
{
shell_exec("sudo systemctl stop bcMeter");
}



if (isset($_POST["exec_debug"]))
{
	shell_exec("sudo kill -SIGINT $PID");
}


if (isset($_POST["startbcm"]))
{
	 echo "<script>bootbox.alert('Starting new log. Wait a few minutes for graph to appear');</script>";
      shell_exec("sudo systemctl restart bcMeter");
}


   

if (isset($_POST["exec_new_log"])){
		shell_exec("sudo systemctl restart bcMeter");
}


?>

</body>
</html>