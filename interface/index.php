

<!DOCTYPE html>
<meta charset="utf-8">
<style>
  html, body{
    font-family: sans-serif;
    margin: 0px;
    padding: 0px
  }
  svg,
  .menu {
    padding: 0 20px;
    display: inline-block;
    margin: 0px auto;
  }

  .menu select {
    height: 35px;
    margin: 0px 5px;
    border-radius: 3px;
    outline: none;
    font-size: 15px;
  }



  .menu .btn, a {
    border-radius: 0px;
    color: #ff7f0e;
    font-weight: 600;
    /*padding: 5px 15px;
    margin: 0px 10px;
    box-shadow: 0 1px 2px rgb(0 0 0 / 30%), inset 0 1px 1px rgb(255 255 255 / 30%);
    border: 1px solid #ccc;
    cursor: pointer;
*/
    text-decoration: none;
  }

  .btn:hover, a:hover {
    color: #000;
  }


  .menu span a {
    text-decoration: none !important;
    color: #000;
  }

  .y-menu select, #y-menu-min, #y-menu-max{
    border: solid 2px #1f77b4 !important;;
  }

   #logs select{
    border: solid 2px #ccc !important;;
  }

  .y-menu2 select, #hide-y-menu2, #y-menu2-min, #y-menu2-max {
    border: solid 2px #ff7f0e !important;
  }
  #y-menu-min, #y-menu-max, #y-menu2-min, #y-menu2-max{
    position: absolute;
    width: 80px;
    font-size: 15px;
    height: 28px;
    text-align: center;
  }

  #y-menu-max{
     margin-left: 0px;
     margin-top: 10px
  }

  #y-menu-min{
     margin-left: 0px;
     margin-top: 395px
  }

  #y-menu2-max{
     margin-left: 1070px;
     margin-top: 10px
  }

  #y-menu2-min{
    margin-left: 1070px;
     margin-top: 395px
  }


  #hide-y-menu2 {
    padding: 5px 15px;
    margin: 0px 10px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3), inset 0 1px 1px rgba(255, 255, 255, 0.3);
    border: 1px solid #ccc;
    cursor: pointer;
    background-color: #fff;
    color: #ff7f0e;
    border: none!important;
  }

  #resetZoom {
    padding: 5px 15px;
    margin: 0px 10px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3), inset 0 1px 1px rgba(255, 255, 255, 0.3);
    border: 2px solid #ccc;
    cursor: pointer;
    color: #000;
    height: 35px;
    background-color: #eeebeb;
    cursor: pointer;
    border: none!important;
  }
  #svg-container{
    width: 1140px;
    margin: 0px auto;
    display: block;
  }
    #setRange:hover, #resetZoom:hover {

    border: 1px solid #cfffff !important;
  }


  h3 {
    text-align: center;
  }

  path {

    stroke-width: 2;
    fill: none;
  }

  .tooltip {
    padding: 3px;
    background-color: #ccc;
    border: 1px solid rgb(175, 175, 175);
    width: auto;
    border-radius: 3px;
    position: absolute;
    left: 0px;
    font-size: 11px;
    display: inline-block;
    opacity: 0;
  }

  .selected-time-line {
    stroke-width: 2;
    stroke: rgb(168, 167, 167);
    stroke-linecap: round;
  }
</style>

<body>
  <a href="" id="download" style="display: none;"></a>

<br />

<?php

function clearAddressBar()
{

    if (!isset($_SESSION))
    {
        session_start();
    }

    if ($_SERVER['REQUEST_METHOD'] == 'POST')
    {
        $_SESSION['postdata'] = $_POST;
        unset($_POST);
        header("Location: " . $_SERVER['PHP_SELF']);
        exit;
    }
}

function getPID()
{
  $VERSION =  "0.9.6 04.02.2022";
    $grep = shell_exec('ps aux | grep bcMeter.py | grep -Fv grep | grep -Fv www-data | grep -Fv sudo | grep -Fiv screen | grep python3');
    preg_match_all('!\d+!', $grep, $numbers);
    $PID = $numbers[0][0];
    $STARTED = $numbers[0][7] . ":" . $numbers[0][8];
    if (!isset($grep))
    {
        echo "<pre style='text-align:center;'>bcMeter not (yet) running properly. After update, start script from administration menu.  <br/>
  Further Information will appear. Copy or screenshot and send to jd@bcmeter.org</pre>";
    }
    else {
         echo "<h3 style='text-align: center; display: block;'>bcMeter data to show</h3><pre style='text-align:center;'>(Running with PID $PID since $STARTED) v $VERSION </pre>";
    }
    return $PID;
}
$PID = getPID();
?>



   <!-- CONTAINER FOR DROP DOWN MENU -->
  <div class="menu" style="display: block; text-align: center;">
    <!-- get the list of log -->
<?php

$folder_path = '../logs';
$logString = "<select id = 'logs_select'>";
$logFiles = scandir($folder_path);

foreach ($logFiles as $key => $value)
{
    if ($key > 1)
    {
        $logString .= "<option value='{$value}'>{$value}</option>";
    }
}
$logString .= "<option value='combine_logs'>Combine Logs</option></select>";
echo '<span id="logs">' . $logString . '</span>';
?>

   
    <span class="y-menu">
      <select id="y-menu"></select>
    </span>

    <span class="y-menu2">
        <select id="y-menu2"></select>
    </span>

    <span class="btn" id="hide-y-menu2">Show 2nd Graph!</span>
    <span class="btn" id="resetZoom">Reset Zoom</span>

  </div>

  <br />  <span style="display:block; text-align:center;font-size: 10px!important;  font-weight: 200;">BCngm3_6 and _12 are rolling averages.<br />Depending on the conditions, the Graph my fluctuate <strong>a lot</strong>. Display the rolling averages, then. They are available after minimum 6 or 12 samples taken (default 1hr)</span>

  <br />
  <!-- CONTAINER FOR CHART -->
  <div class="tooltip"></div>
  <div id="svg-container">
       <input type="number"  id="y-menu-min" placeholder="min">
       <input type="number"  id="y-menu-max" placeholder="max">
       <input type="number" id="y-menu2-min" placeholder="min">
       <input type="number" id="y-menu2-max" placeholder="max">
    <svg id="line-chart" width="1100" height="480" style="margin: 0px auto 10px auto">
  </div>
    <style type="text/css">
      text {
        font-size: 11px;
        font-weight: bold;
      }

      #line-chart .tick line,
      #line-chart .domain {
        stroke: #eeebeb
      }

      #line-chart .domain {
        stroke: #ddd
      }

      #line-chart .x-axis-label,
      #line-chart .y-axis-label,
      #line-chart .y-axis-label2 {
        font-size: 12px;
        color: #ccc;
        font-weight: 200;

      }
    </style>
  </svg>




<div class="menu" style="text-align:center!important; display: block; ">
     <h3>Save Graph</h3>
    as <span class="btn" id="svg">SVG</span> or 
    <span class="btn" id="png"> PNG</span> or 
    <span class="btn" id="csv"> CSV</a></span>

</div>
  
  <!-- load the d3.js library -->
  <script src="js/d3.min.js"></script>

  <script>

    if(typeof window.history.pushState == 'function') {
        window.history.pushState({}, "Hide", '<?php echo $_SERVER['PHP_SELF']; ?>');
    }
    let selectLogs = document.getElementById("logs_select")
    current_file = selectLogs.value;
  

    /* VARS*/
    let yColumn2 = "BCngm3_12",
      yColumn = "BCngm3",
      tooltip,
      hoveredTime = 0,
      idx = 0,
      isHidden = true,
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
    const svg = d3.select("svg")
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
    yMin2Doc.style.opacity = 0
    yMax2Doc.style.opacity = 0
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
        .style('opacity', 0 )
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
        .style('opacity', 0 )
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

           let idx  = -new Date(data[bi_lower]["bcmTime"]).getTime() - -new Date(hoveredTime).getTime() > -new Date(hoveredTime).getTime() - -new Date(data[bi_upper]["bcmTime"]).getTime() ? bi_upper : bi_lower

            const temp = data[idx];
           // const maxLeft = e.pageX > xScale(data[data.length - 1][xLabel]) ? xScale(data[idx][xLabel]) : e.pageX;
            const maxLeft = e.pageX > xScale(data[data.length - 1][xLabel]) ? xScale(data[idx][xLabel])+margin.left+margin.right-5 : xScale(data[idx][xLabel])+margin.left+margin.right +125
            let tooltipMessage = (!isHidden) ? `<div><b>Date:</b>  ${temp["bcmTimeRaw"]}</div>
                        <div><b>${yColumn}:</b>  ${temp[yColumn]}</div>
                         <div><b>${yColumn2}:</b>  ${temp[yColumn2]}</div>
                        ` : `<div><b>Date:</b>  ${temp["bcmTimeRaw"]}</div>
                        <div><b>${yColumn}:</b>  ${temp[yColumn]}</div>
                        `
            d3.select('.tooltip').style("left", maxLeft + 10 + "px")
              .style("top", "150px")
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
      dataFile(`${logPath}log_current.csv`)
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
      render()
        if(current_file == 'log_current.csv'){
           updateCurrentLogsFunction()
      }
      else{
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
        yValueScale = (d) => d["BCngm3"];
        yValueScale2 = (d) => d["BCngm3"];
      } else {
        yValueScale = yValue;
        yValueScale2 = yValue2;
      }
      yLabel = yColumn;
      yLabel2 = yColumn2;
      plotChart();
    };

    const dataFile = (file, isCombineLogsSelected = false ) => {
      data = []
      data["columns"] = ["BCngm3", "BCngm3_6", "BCngm3_12", "bcmATN", "bcmRef", "bcmSen","Temperature","sampleDuration"]
      d3.dsv(';', file).then((rawData) => {
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
         
            /* MOVING AVERAGE = 6 */
            if (i < 6) {
              d.BCngm3_6 = null;
            } else {
              d.BCngm3_6 = +(((data.slice(i - 5, i).reduce((c, a) => c + a.BCngm3, 0)) / 6).toFixed(2))
            }
            /* MOVING AVERAGE = 12 */
            if (i < 12) {
              d.BCngm3_12 = null;
            } else {
              d.BCngm3_12 = +(((data.slice(i - 11, i).reduce((c, a) => c + a.BCngm3, 0)) / 12).toFixed(2))
            }
            data.push(d)
             if(isCombineLogsSelected){
                dataObj[file.split("/")[2]] = data
                combineLogs.push(d)
          }
          }

        });
        if(isCombineLogsSelected){
              combinedLogCurrentIndex++;
              if(combinedLogCurrentIndex < logFilesSize){
                dataFile(`${logPath}${logFiles[combinedLogCurrentIndex]}`, true)
              }
              else{
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

      img.onload = function () {
        ct.drawImage(img, 0, 0);
        bolbURL.createObjectURL(serializeData()["svgBlob"]);
        downloadFile(dom.toDataURL('image/png'), "png")
      };
      img.src = serializeData()["svgURL"];
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

    document.getElementById("svg").addEventListener("click", saveSVG);
    document.getElementById("png").addEventListener("click", savePNG);
    document.getElementById("csv").addEventListener("click", saveCSV);
    
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
<br />
<h3>Administration</h3>
<form style="display: block; text-align:center;">
<input type="submit" name="shutdown" value="Shutdown"/>
<input type="submit" name="restart" value="Reboot"/>
<input type="submit" name="stopbcm" value="Stop sampling"/>
<input type="submit" name="startbcm" value="Start sampling"/>
<input type="submit" name="newlog" value="New Logfile"/>
<input type="submit" name="debug" value="Debug Mode"/>
<input type="submit" name="editor" value="Script Editor"/>
<input type="submit" name="update" value="Update Script"/><br/><br />

</form>
<h3>Messages</h3>
<?php


if (isset($_GET["editor"])) 
{
?>
<script type="text/javascript">
window.location = "editor-form.php";
</script>      
    <?php
}
if (isset($_GET["shutdown"]))
{

    clearAddressBar();
    echo "<pre style='text-align:center;'>Shutting down bcMeter. Safe to disconnect Power in 20s</pre><br/>";
    $output = shell_exec('sudo shutdown now');
    sleep(5);
    echo "<script>window.location.reload()</script>";

}

if (isset($_GET["restart"]))
{

    clearAddressBar();
    echo "<pre style='text-align:center;'>Rebooting bcMeter. Will be back in a Minute.</pre><br/>";
    sleep(5);
    clearAddressBar();
    $output = shell_exec('sudo reboot now');
    echo "<script>window.location.reload()</script>";


}

if (isset($_GET["stopbcm"]))
{   
    clearAddressBar();
    $output = shell_exec("sudo kill -9 $PID");
    sleep(5);
    clearAddressBar();
    echo "<script>window.location.reload()</script>";
}


if (isset($_GET["debug"]))
{   
    clearAddressBar();
    $output = shell_exec('sudo python3 /home/pi/bcMeter.py debug 1 5 true');
    echo "<pre style='text-align:center;'>$output</pre>";
}

if (isset($_GET["startbcm"]))
{
    echo "<pre style='text-align:center;'>Starting script. Wait approx 2-5 Minutes for the first sample to appear.</pre>";
    shell_exec("sudo screen python3 /home/pi/bcMeter.py");
    sleep(5);
    clearAddressBar();
    echo "<script>window.location.reload()</script>";
}

if (isset($_GET["newlog"]))
{

    $output1 = nl2br(shell_exec("sudo kill -9 $PID"));
    echo "<pre style='text-align:center;'><strong>Sent termination. Wait a bit... </strong></pre>";
    $output2 = nl2br(shell_exec('sudo screen python3 /home/pi/bcMeter.py'));
    echo "<pre style='text-align:center;'>" . str_replace("\n","<br />",$output1) . " <br />" . str_replace("\n","<br />",$output2) . "</pre>";
    sleep(5);
    clearAddressBar();
    echo "<script>window.location.reload()</script>";
}   


if (isset($_GET["update"]))
{ 
 shell_exec("sudo kill -9 $PID");

  while (@ ob_end_flush()); // end all output buffers if any
$cmd = 'cd /home/pi && sudo wget -N https://raw.githubusercontent.com/bcmeter/bcmeter/main/install.sh -P /home/pi/ && sudo bash /home/pi/install.sh update' ;
$proc = popen($cmd, 'r');
echo '<pre>';
while (!feof($proc))
{
    echo fread($proc, 4096);
    @ flush();
}

echo '</pre>';

sleep(5);
clearAddressBar();
echo "<script>window.location.reload()</script>";



}   
?>

</body>
</html>
