<?php
// Start the PHP session
session_start();
$_SESSION['valid_session'] = 1;
?>

<!DOCTYPE html>
<meta charset="utf-8">
<head>    
  <link rel="stylesheet" type="text/css" href="css/bootstrap.min.css">
  <link rel="stylesheet" type="text/css" href="css/bcmeter.css">

</head>


<body>
	<a href="" id="download" style="display: none;"></a>

<br />




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
       if (!isset($grep))
      {
          echo "<script type='text/javascript'>setTimeout(() => {if (location.href.indexOf('stopped') === -1) { location.href = location.href + '?stopped';}}, 2000);</script>";
      }
      else
      {
                  echo "<script type='text/javascript'>setTimeout(() => {if (location.href.indexOf('stopped') >= 1) { location.href = location.href.replace('?stopped', '');}}, 1000);</script>";
      }
?>

<img src="bcMeter-logo.png" style="width: 300px; display:block; margin: 0 auto;"/>


<!-- Bootstrap Layout -->
<div class="container">
  <div class="row">
    <div class="col-sm-12">
        <?php
      $output = exec('ps -A | grep -i hostapd');
 
// Check if the command returned any output
        echo "<div class='alert alert-"; 


                   if(!isset($grep)){echo "warning'";}
          else {echo "success'";} 
          echo " role='alert'>";
          $numbers = preg_replace('/^\s+| python3 \/home\/pi\/bcMeter.py/', "", $grep);
          $numbers = explode(" ", $numbers);
          $PID = $numbers[0];
          $DEVICETIME = shell_exec('date');
          $STARTED = implode(" ", array_slice($numbers,1));
       if (!isset($grep))
      {
          echo "<div style='text-align:center;'>bcMeter stopped.<br/></div>";

          if(!empty($output)) {
                  echo "<div style='text-align:center;' id='devicetime'></div>";
                ?><div style="text-align: center";>
                <form method="POST">
                  <input type="hidden" id="set_time" name="set_time" value="">
                  <input type="submit" value="Set clock on bcMeter to your time" class="btn btn-primary" >
                </form>
              </div>
              <?php
                                   echo "<div style='text-align:center;'><strong>You're currently in Hotspot mode! Device may turn off soon, check Parameters for continous Hotspot Operation or setup WiFi below!</strong></div>";

              }

      }
      else {
           echo "<div style='text-align:center;'>Current log running since $STARTED<br /></div>";
                     if(!empty($output)) {
                     echo "<div style='text-align:center;'><strong>You're currently in Hotspot mode! Device may turn off soon, check Parameters for continous Hotspot Operation or setup WiFi below!</strong></div>";
                     }
      }
      ?>
      </div>
    </div>
  </div>
</div>

  <div id="report-value" style="text-align: center;"></div><br /><br />
<div style="text-align: center"> Filter: <button type="button" class="btn btn-btn-white" id="report-button"></button></div><br />

	 <!-- CONTAINER FOR DROP DOWN MENU -->
	<div class="menu" style="display: block; text-align: center;">
			 <h4 style='text-align: center; display: inline;'>Select Dataset:</h4>
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

	<!-- br />  <span style="display:block; text-align:center;font-size: 10px!important;  font-weight: 200;">BCngm3_6 and _12 are rolling averages.<br />Depending on the conditions, the Graph my fluctuate <strong>a lot</strong>. Display the rolling averages, then. They are available after minimum 6 or 12 samples taken (default 1hr)</span>

	<br /-->
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
    if(window.location.href.indexOf("stopped") === -1){
    if ( typeof window.history.pushState == 'function' ) {
        window.history.pushState({}, "Hide", '<?php echo $_SERVER['PHP_SELF'];?>');
    }
  }
    let selectLogs = document.getElementById("logs_select")
    current_file = selectLogs.value;
    if (current_file == 'log_current.csv') {
        updateCurrentLogsFunction()
      } 
    /* VARS*/
    let yColumn2 = "BCngm3_12",
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
      xScale, 
      yScale, 
      yScale2,
      brushedX = [],
      dataObj = {},
      updateCurrentLogs;

    /* CONSTANTS */
    const noData ="<div class='alert alert-warning' role='alert'>Not enough data yet. Graph will appear 15 Minutes after start.</div>";
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
    combineLogs["columns"] = ["BCngm3", "BCngm3_6", "BCngm3_12", "bcmATN", "bcmRef", "bcmSen", "Temperature"]
    data["columns"] = ["BCngm3", "BCngm3_6", "BCngm3_12", "bcmATN", "bcmRef", "bcmSen", "Temperature"]

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
      if (yColumn == "BCngm3_6" || yColumn == "BCngm3_12") {
        lineGenerator.defined(d => d[yColumn] !== null)
      }
      if (yColumn2 == "BCngm3_6" || yColumn2 == "BCngm3_12") {
        lineGenerator2.defined(d => d[yColumn2] !== null)
      }

      /* GENERATE PATH */
      gEnter.append("path")
        .attr('class', 'line-chart2')
        .attr('stroke', '#ff7f0e')
        .attr('fill', 'none')
        .attr("stroke-width", "2")
        .attr("clip-path", "url(#rectClipPath)")
        .merge(g.select('.line-chart2'))
        .transition().duration(1000)
        .attr('d', lineGenerator2(data));

      gEnter.append("path")
        .attr('class', 'line-chart')
        .attr('stroke', '#1f77b4')
        .attr('fill', 'none')
        .attr("stroke-width", "2")
        .attr("clip-path", "url(#rectClipPath)")
        .merge(g.select('.line-chart'))
        .transition().duration(1000)
        .attr('d', lineGenerator(data));

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
    }, 10000)

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
        render()
        document.getElementById("report-value").innerHTML = `<h4>
        ${data[len]["BCngm3"].toFixed(0)} ng/m<sup>3</sup><sub>current</sub> » 
        ${d3.mean([...data].splice(len-12, 12), BCngm3_value).toFixed(0)} ng/m<sup>3</sup><sub>avg60</sub> » 
        ${d3.mean(data, BCngm3_value).toFixed(0)} ng/m<sup>3</sup><sub>avgALL</sub></h4>`;
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
    /* RENDER FUNCTION THAT CALLS CHART PLOT */
    const render = () => {
    yMenuDom.value = yColumn;
    yMenuDom2.value = yColumn2;

    if (yColumn == "" || yColumn2 == "") {
    yColumn = data.columns[0];
    yColumn2 = data.columns[2];
       }
      yValue = (d) => d[yColumn];
      yValue2 = (d) => d[yColumn2];
      if ((((yColumn == "BCngm3_6" || yColumn == "BCngm3_12") && yColumn2 == "BCngm3") ||
        ((yColumn2 == "BCngm3_6" || yColumn2 == "BCngm3_12") && yColumn == "BCngm3")) && !isHidden) {
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
data
    const dataFile = (file, isCombineLogsSelected = false ) => {
      data = []
      data["columns"] = ["BCngm3", "BCngm3_6", "BCngm3_12", "bcmATN", "bcmRef", "bcmSen","Temperature"]
      
      d3.dsv(';', file).then((rawData) => {
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
            d.Temperature = +d.Temperature;
            data.push(d)
          }
        });


          let result = file.includes("../logs/log_current.csv");
          if (result == true) { 

              let len = data.length - 1;

              if (len>0) {
                document.getElementById("report-value").innerHTML = `<h4>
                ${data[len]["BCngm3"].toFixed(0)} ng/m<sup>3</sup><sub>current</sub> » 
                ${d3.mean([...data].splice(len-12, 12), BCngm3_value).toFixed(0)} ng/m<sup>3</sup><sub>avg60</sub> » 
                ${d3.mean(data, BCngm3_value).toFixed(0)} ng/m<sup>3</sup><sub>avgALL</sub></h4>`;
                let bcmRef = data[len]["bcmRef"].toFixed(0);
                let bcmSen = data[len]["bcmSen"].toFixed(0);
                let btn = document.getElementById("report-button");
                if (bcmSen == 0){
                  if (bcmRef == 0) {
                    btn.className = "btn btn-white";

                  }
                }

                if (bcmRef > 6000) {
                  if (bcmSen > 8000) {
                    btn.className = "btn btn-success";
                  } else if (bcmSen > 6000 && bcmSen <= 8000) {
                    btn.className = "btn btn-warning";
                  } else if (bcmSen > 4000 && bcmSen <= 6000) {
                    btn.className = "btn btn-danger";
                  } else if (bcmSen > 2000 && bcmSen <= 4000) {
                    btn.className = "btn btn-dark";
                  } else if (bcmSen <= 2000) {
                    btn.className = "btn btn-black";
                  }
                }
                }
              if (len<0) {
                document.getElementById("report-value").innerHTML = `<h4>Not enough data for graph/averages. Will appear after 15 Minutes after starting.</h4>`;
              }
}


          


    

        data.map((d, i) => {
          if (i < 4 || i > data.length - 3) {
            d.BCngm3_6 = null;
        } else {
          d.BCngm3_6 = +((((((data.slice(movingIndex6,  movingIndex6 + 6).reduce((p, c) => p + c.BCngm3, 0)) / 6)) 
          +(((data.slice(movingIndex6 + 1, movingIndex6 + 1 + 6).reduce((p, c) =>  p + c.BCngm3, 0)) / 6))) / 2).toFixed(2))
          movingIndex6++;
        }
        /* MOVING AVERAGE = 12 */
        if (i < 7 || i > data.length - 6) {
          d.BCngm3_12 = null;
        } else {
          d.BCngm3_12 = +((((((data.slice(movingIndex12, movingIndex12 + 12).reduce((p, c) => p + c.BCngm3, 0)) / 12)) 
          +(((data.slice(movingIndex12 + 1, movingIndex12 + 1 + 12).reduce((p, c) => p + c.BCngm3, 0)) / 12))) / 2).toFixed(2))
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
      if ((((yColumn == "BCngm3_6" || yColumn == "BCngm3_12") && yColumn2 == "BCngm3") ||
        ((yColumn2 == "BCngm3_6" || yColumn2 == "BCngm3_12") && yColumn == "BCngm3")) && !isHidden) {
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
  </script>


<ul class="nav nav-pills mb-3 nav-fill" id="pills-tab" role="tablist" style="width: 50%;margin:0 auto 0 auto;">
  <li class="nav-item">
    <a class="nav-link active" id="pills-log-tab" data-toggle="pill" href="#pills-log" role="tab" aria-controls="pills-log" aria-selected="true">General</a>
  </li>
  <li class="nav-item">
    <a class="nav-link" id="pills-admin-tab" data-toggle="pill" href="#pills-admin" role="tab" aria-controls="pills-admin" aria-selected="false">Administration</a>
  </li>

    
</ul>
<div class="tab-content" id="pills-tabContent">
  <div class="tab-pane fade show active" id="pills-log" role="tabpanel" aria-labelledby="pills-log-tab">

      <form style="display: block; text-align:center;" method="post">
              <input type="submit" name="newlog" value="Start" class="btn btn-info"/>  
              <input type="submit" name="stopbcm" value="Stop" class="btn btn-info"/>
          <button type="button" class="btn btn-warning" data-toggle="modal" data-target="#wifisetup">
            WiFi Config
          </button>
              <input type="submit" name="saveGraph" value="Save Log" class="btn btn-secondary bootbox-accept"/>

            <button type="button" class="btn btn-secondary" data-toggle="modal" data-target="#downloadOld">
              All logs
            </button>



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
                                  <td><a href='<?= $dir ."/". $file ?>'><button type="button" value='Test' class='btn btn-primary'>Download</button></a></td>
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



          

        </form>
        </div>
  <div class="tab-pane fade" id="pills-admin" role="tabpanel" aria-labelledby="pills-admin-tab">
    
          <form style="display: block; text-align:center;" method="post">

          <button type="button" class="btn btn-info" data-toggle="modal" data-target="#editparameters">
            Settings
          </button>
          <input type="hidden" name="randcheck" />
            <!--button type="button" class="btn btn-info" data-toggle="modal" data-target="#editdate">
              Set clock on bcMeter
           </button-->


          <input type="submit" name="deleteOld" value="Delete old logs" class="btn btn-secondary"/>


          <input type="submit" name="restart" value="Reboot" class="btn btn-secondary"/>

          <input type="submit" name="update" value="Update bcMeter" class="btn btn-secondary"/>
          <input type="submit" name="shutdown" value="Shutdown" class="btn btn-danger"/>
          <!--input type="submit" name="phpdebug" value="Debug" class="btn btn-danger"/-->
          </form>


  </div>
  

</div>

<!-- begin edit parameters modal -->
            <div class="modal fade" id="editparameters" tabindex="-1" role="dialog" aria-labelledby="exampleModalCenterTitle1" aria-hidden="true">
            <div class="modal-dialog modal-dialog-centered" role="document" style="max-width: 90%;">
              <div class="modal-content">
                <div class="modal-header">
                  <h5 class="modal-title" id="exampleModalLongTitle">Edit parameters of bcMeter</h5>
                  <button type="button" class="close" data-dismiss="modal" aria-label="Close">
                    <span aria-hidden="true">&times;</span>
                  </button>
                </div>
                <div class="modal-body">


                  <?php 

                  $file = "/home/pi/bcMeterConf.py";

                  if (isset($_POST['save'])) {
                      $fileContent = "";
                      foreach ($_POST['var'] as $key => $var) {
                          $value = $_POST['value'][$key];
                          if ($value !== ""){
                          $comment = $_POST['comment'][$key];
                          if (($var !="")) {
                          $fileContent .= $var . "=" . $value . "#" . $comment . "\n";
                      }
                      }
                      }
                      //echo($fileContent);
                      file_put_contents($file, $fileContent);
                      echo "File updated successfully";
                  }

                  if (isset($_POST['cancel'])) {
                      echo "Action canceled";
                  }

                  $content = file_get_contents($file);
                  $lines = explode("\n", $content);

                  ?>


                  <form method="post">
                      <table class="table table-bordered">
                          <thead>
                              <tr>
                                  <th scope="col" style="width: 60%;">Description</th>
                                  <th scope="col" style="width: 20%;">Value</th>
                                  <th scope="col" style="width: 20%;">Name of Variable</th>
                              </tr>
                          </thead>
                          <tbody>
                              <?php foreach ($lines as $line) : 
                                  $parts = explode("=", $line);
                                    if (count($parts) > 1) {
                                        $skipline = 0;
                                      $variable = $parts[0];
                                      $rest = $parts[1];
                                      $value = "";
                                      $comment = "";
                                      if (strpos($rest, "#") !== false) {
                                          $valueParts = explode("#", $rest);
                                          $value =  preg_replace('/[\s\t]+/', '', $valueParts[0]);
                                          if(!strpos($value, '[') && !strpos($value, ']')){
                                           $value =  preg_replace('/,/', '.', $valueParts[0]);
                                          }
                                          $comment = $valueParts[1];
                                      } 

                                  }
                                  else {
                                    $skipline = 1;
                                  }
                                if ($skipline==0) {
                              ?>
                              <tr>
                                  <td><input type="text" class="form-control" name="comment[]" value="<?php echo $comment; ?>" readonly></td>

                                  <?php if ($value == 'True' || $value == 'False') { ?>
                                    <td>
                                        <select class="form-control" name="value[]">
                                            <option value="True"<?php if ($value == 'True') { ?> selected<?php } ?>>True</option>
                                            <option value="False"<?php if ($value == 'False') { ?> selected<?php } ?>>False</option>
                                        </select>
                                    </td>
                                  <?php } 

                                  else { ?>
                                  <td><input type="text" class="form-control" name="value[]" value="<?php echo $value; ?>"></td>
                                  <?php } ?>
                                  <td><input type="text" class="form-control" name="var[]" value="<?php echo $variable; ?>" readonly></td>




                              </tr>
                              <?php } endforeach; ?>
                          </tbody>
                      </table>
                      <button type="submit" class="btn btn-primary" name="save">Save</button>
                      <button type="submit" class="btn btn-secondary" name="cancel">Cancel</button>
                      <button type="button" class="btn btn-info" id="addNew">Add new</button> 
                      (Airflow is taken to account immediately, the rest upon start of the next measurement)

                  </form>


                  <script>
                      document.getElementById("addNew").onclick = function() {
                          var table = document.getElementsByTagName('tbody')[0];
                          var newRow = table.insertRow(-1);

                          var cell1 = newRow.insertCell(0);
                          var cell2 = newRow.insertCell(1);
                          var cell3 = newRow.insertCell(2);

                          cell1.innerHTML = '<input type="text" class="form-control" name="var[]" value="">';
                          cell2.innerHTML = '<input type="text" class="form-control" name="value[]" value="">';
                          cell3.innerHTML = '<input type="text" class="form-control" name="comment[]" value="">';
                      };
                  </script>


                </div>

              </div>
            </div>
          </div>

<!-- End Edit Parameters -->
<!-- Begin Set Time -->


            <div class="modal fade" id="editdate" tabindex="-1" role="dialog" aria-labelledby="exampleModalCenterTitle1" aria-hidden="true">
            <div class="modal-dialog modal-dialog-centered" role="document" style="max-width: 90%;">
              <div class="modal-content">
                <div class="modal-header">
                  <h2 class="modal-title" id="exampleModalLongTitle" style="text-align: center;">This is crucial if you plan to use the device without internet access in hotspot mode</h2>
                  <button type="button" class="close" data-dismiss="modal" aria-label="Close">
                    <span aria-hidden="true">&times;</span>
                  </button>
                </div>
                <div class="modal-body">

                      <script type="text/javascript">
                     // Create a timestamp using JavaScript
                        setInterval(function(){
                          var date = new Date();
                          var timestamp = (date.getTime()/1000).toFixed(0);
                          var currentDateTime = date.toLocaleString('default', { month: 'short' }) + " " + date.getDate() + " " + date.getFullYear() + " " + date.getHours() + ":" + date.getMinutes() + ":" + date.getSeconds();
                          document.getElementById("datetime_local").innerHTML = "Current time based on your Browser: <br/>" + currentDateTime;
                           document.getElementById("set_time").value = timestamp;
                           $.ajax({
                            url:"includes/gettime.php",    //the page containing php script
                            type: "post",    //request type,
                            data: {datetime: "now"},
                            success:function(result){
                               document.getElementById("datetime_device").innerHTML = "Current time set on your bcMeter: " + result;
                               if( document.getElementById("devicetime") ) {

                                 document.getElementById("devicetime").innerHTML = "Time on bcMeter: " + result;
                              }
                            }
                        });
                        }, 1000);


                       


                      </script>
                     <p style="text-align: center;"> If both times are not matching, set the time of your browser to be the time of the bcmMeter now. </p>
                      <pre style='text-align:center;' id='datetime_device'></pre>
                       <pre style='text-align:center;' id='datetime_local'></pre>
                      <form method="POST">
                        <input type="hidden" id="set_time" name="set_time" value="">
                        <input type="submit" value="Set Time" class="btn btn-info btn-block" >
                      </form>
        
                  
                </div>

              </div>
            </div>
          </div>
<!-- end set time modal-->

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

                  <!-- start dynamic content for wifi setup -->

                        <?php
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

                          echo "<script>window.location.href='includes/status.php?status=reboot';</script>";
                        }

                        // check for existing wifi credentials
                        $data=json_decode(file_get_contents($wifiFile),TRUE);
                        $currentWifiSsid=$data["wifi_ssid"];
                        $currentWifiPwd=$data["wifi_pwd"];
                        $currentWifiPwdHidden=str_repeat("•", strlen($currentWifiPwd));

                         if (isset($_POST['reset_wifi_json'])) {
                        $wifiFile='/home/pi/bcMeter_wifi.json';
                          $wifi_ssid = "";
                           $wifi_pwd ="";
                         $data = array("wifi_ssid"=>$wifi_ssid, "wifi_pwd"=>$wifi_pwd);
                          file_put_contents($wifiFile, json_encode($data, JSON_PRETTY_PRINT));
                          echo "<script>window.location.href='includes/status.php?status=reboot';</script>";

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
                        ?>

                        <script>
                          var currentWifiSsid = "<?php echo $currentWifiSsid; ?>";
                          
                          var progressBarStarted = false;
                          var progressBarTimeSec = 40000;
                          
                          let mac = "<?php echo $macAddressDec ?>";
                          let conn_location=null;
                          let telraam_online = null;
                          
                          //set check_time when the connect button was clicked
                          let check_time = null;
                          if("<?php echo $interruptSent; ?>"){
                            check_time=new Date().getTime()/1000;                 //epoch in seconds
                          }
                          
                          //set the title after the languages are loaded
                          $("#page_title").html('<?php echo $language["welcome_title"]; ?>');
                        </script>
                        <script src="js/main.js?version=5"></script>


                          <body>
                           
                            <div class="making-the-connection" style="display:none;">
                              <h2><?php echo $language["making_the_connection_title"]; ?></h2>
                              <span class="connection-info"><?php echo $language["making_the_connection_info"]; ?></span><br><br>
                              <div id="progress-container">
                                <div id="progress" class="waiting">
                                   <dt></dt>
                                   <dd></dd>
                                 </div>
                              </div>
                              <div id="progress-note-ok" class="progress-note success-notifcation no-background" style="display:none;"><?php echo $language["progress_note_ok"]; ?></div>
                              <div id="progress-note-nok" class="progress-note error" style="display:none;"><?php echo $language["progress_note_nok"]; ?></div>
                              <div class="progress-close-button js-close-connection-modal" style="display: none">
                                <?php echo $language["making_the_connection_btn"]; ?>
                              </div>


                            </div>

                            <?php // if ($version!=='') { ?>
                              <div class="version"> <?php //echo $version; ?></div>
                            <?php// } ?>

                            <!--ul class="lang-link">
                              <?php $now=time() //add epoch time to urls to prevent caching?>
                              <li><a href="?lang=nl&t=<?php echo $now; ?>">nl</a></li>
                              <li><a href="?lang=fr&t=<?php echo $now; ?>">fr</a></li>
                              <li><a href="?lang=en&t=<?php echo $now; ?>">en</a></li>
                              <li><a href="?lang=si&t=<?php echo $now; ?>">si</a></li>
                              <li><a href="?lang=es&t=<?php echo $now; ?>">es</a></li>
                              <li><a href="?lang=de&t=<?php echo $now; ?>">de</a></li>
                            </ul-->
                            <div class="box" <?php echo ($credsUpdated==true) ? 'style="display: block"' :'style="display: none"';?>>
                               <div class='success-notifcation' <?php echo ($credsUpdated==true) ? 'style="display: block"' :'style="display: none"';?>>
                                 <?php echo $language["save_success"]; ?>
                               </div>
                            </div>

                            
                              <div class="content">

                            
                               
                                <form name="connect_now_form" method="POST" action="index.php"><br />
                                  <?php
                                    if ($currentWifiSsid!==null && $currentWifiSsid!=='') {
                                        echo "<div class=\"alert alert-success\" role=\"alert\">".$language["current_wifi_setup"]. ": ". $currentWifiSsid. "</div>";
                                
                                    } else {
                                      
                                    }
                                  ?>
                                  </form>
                              
                              <div class="tab-content tab-wifi" >
                                
                              
                                
                                <div class="entering-the-connection-info">
                                  

                                  <br />
                                  <form name="conn_form" method="POST" action="index.php">
                                    <!--
                                    <input type="TEXT" onfocus="if(this.value == 'wifi netwerk') {this.value='';}" name="wifi_ssid" value="<?php echo $language["wifi_network"]; ?>">
                                    -->
                                    <label><?php echo $language["wifi_network"]; ?>:</label>
                                    <div class="select-container">
                                      <select name="wifi_ssid" id="js-wifi-dropdown">
                                        <?php if ($currentWifiSsid===null) { ?>
                                          <option selected="selected"><?php echo $language["wifi_network_loading_short"]; ?></option>
                                        <?php } else { ?>
                                          <option selected="selected"><?php echo $currentWifiSsid; ?></option>
                                        <?php } ?>
                                          <option value="custom-network-selection"><?php echo $language["add_custom_network"]; ?></option>
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
                                        </div>
                                        <?php if(!empty($currentWifiPwd)) { ?>
                                            <div class="wifi-pwd-field-exist">
                                                <div class="password-dots">
                                                    <input type="text" value="<?php echo $currentWifiPwdHidden ?>" readonly></div>
                                            </div>
                                        <?php } ?>


                                        </div>

                                    <div class="submit-container">
                                      <input type="Submit" name="conn_submit" value="<?php echo $language["save_and_connect"]; ?>" class="btn btn-primary">
                                      <button type="button" class="btn btn-secondary" data-dismiss="modal">Cancel</button>
                                       <input type="Submit" name="reset_wifi_json" value="Delete Wifi" class="btn btn-warning">
                                    </div><br />
                                    <div class="alert alert-warning" role="alert">
                                     Deleting/saving wifi credentials will take immediate effect and may cut connection.
                                    </div>
                                    <sub>If you like to run the bcMeter independently without being connected to a WiFi, you can adjust it in the Settings!
                                  </form>
                                </div> <!-- end entering-the-connection-info -->
                              </div>  <!-- tab-wifi -->
                             
                            </div>  
                  <!-- end dynamic content for wifi setup --> 
                </div>
              </div>
            </div>
          </div>
<!-- end set WiFi modal-->




<br /><br />


<?php


echo "<div style='text-align:center;'>v$VERSION</div>";

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





if (isset($_POST["phpdebug"]))
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
                window.location.href='includes/status.php?status=debug';

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

if (!empty($_POST["restart"]) )
{

	 echo <<< javascript
<script>
var dialog = bootbox.dialog({
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
</script>
javascript;

}

if (isset($_POST["stopbcm"]))
{   

echo <<<JS
<script>
var dialog = bootbox.dialog({
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
									 setTimeout(window.location.reload.bind(window.location), 3000);
								}
						 });
		
							




						}
				}
		}
});
</script>

JS;
}   		


if (isset($_POST["exec_stop"]))
{
shell_exec("sudo systemctl stop bcMeter");
}


if (isset($_POST["debug"]))
{

echo <<< javascript
<script>
var dialog = bootbox.dialog({
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
</script>
javascript;

}


if (isset($_POST["exec_debug"]))
{
	shell_exec("sudo kill -SIGINT $PID");

}


if (isset($_POST["startbcm"]))
{
	 echo "<script>bootbox.alert('Starting new log. Wait 15 Minutes for graph to appear');</script>";
      shell_exec("sudo systemctl stop bcMeter");
    sleep(3);
		shell_exec("sudo systemctl start bcMeter");
		echo "<script>setTimeout(window.location.reload.bind(window.location), 10000);</script>";
}

if (isset($_POST["newlog"]))
{

echo <<<JS
<script>
var dialog = bootbox.dialog({
		title: 'Start new log?',
		message: "<p>This will start a new log. It takes 15 Minutes for the new chart to appear. </p>",
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
								data: 'exec_new_log',
								success: function(response){
									 setTimeout(window.location.reload.bind(window.location), 3000);
								}
						 });



						}
				}
		}
});
</script>

JS;
}   

if (isset($_POST["exec_new_log"])){

		shell_exec("sudo systemctl stop bcMeter");
		sleep(3);
		shell_exec('sudo systemctl start bcMeter');
		sleep(3);
		echo "setTimeout(window.location.reload.bind(window.location), 10000);";

}




if (isset($_POST["saveGraph"]))
{

echo <<<END
		<script>var dialog = bootbox.dialog({
		title: 'Save graph as',
		message: "<p>Choose the type of file you want to save the current measurements as</p>",
		size: 'large',
		buttons: {
				1: {
						label: "CSV for Excel",
						className: 'btn-info',
						callback: function(){
								saveCSV();

						}
				},
				2: {
						label: "PNG for web/mail",
						className: 'btn-info',
						callback: function(){
								savePNG();

						}
				},
				3: {
						label: "SVG Vector for Print",
						className: 'btn-info',
						callback: function(){
								saveSVG();
						}
				}
		}
});;</script>

END;

}






if (isset($_POST["update"]))
{ 


echo <<< javascript
<script>
var dialog = bootbox.dialog({
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
</script>
javascript;



}   



?>

</body>
</html>