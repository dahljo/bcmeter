/**
 * bcMeter D3.js Plotting Functions
 * Handles all data visualization and chart interactions
 */

document.addEventListener('DOMContentLoaded', () => {
  /* GLOBAL VARIABLES */
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
      updateCurrentLogs,
      xScale,
      yScale;

  // Set default columns based on device type
  if (typeof is_ebcMeter !== 'undefined' && is_ebcMeter === true) {
    window.is_ebcMeter = true;
    window.yColumn = 'BCugm3';
    window.yColumn2 = 'Temperature';
    
    combineLogs.columns = ["BCugm3", "BCugm3_unfiltered", "BC_rolling_avg_of_6", "BC_rolling_avg_of_12", "bcmATN", "bcmRef", "bcmSen", "Temperature", "sht_humidity", "airflow"];
    data.columns = ["BCugm3", "BCugm3_unfiltered", "BC_rolling_avg_of_6", "BC_rolling_avg_of_12", "bcmATN", "bcmRef", "bcmSen", "Temperature", "sht_humidity", "airflow"];
  } else {
    window.is_ebcMeter = false;
    window.yColumn = 'BCngm3';
    window.yColumn2 = 'BC_rolling_avg_of_6';
    
    combineLogs.columns = ["BCngm3", "BCngm3_unfiltered", "BC_rolling_avg_of_6", "BC_rolling_avg_of_12", "bcmATN", "bcmRef", "bcmSen", "Temperature", "sht_humidity", "airflow"];
    data.columns = ["BCngm3", "BCngm3_unfiltered", "BC_rolling_avg_of_6", "BC_rolling_avg_of_12", "bcmATN", "bcmRef", "bcmSen", "Temperature", "sht_humidity", "airflow"];
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
  const yMenuDom = document.getElementById("y-menu");
  const yMenuDom2 = document.getElementById("y-menu2");
  const bisect = d3.bisector(d => d.bcmTime).left;
  const xLabel = "bcmTime";
  
  // Initialize scales
  xScale = d3.scaleLinear();
  yScale = d3.scaleLinear();
  
  // Initialize UI
  initializeEventListeners();
  
  // Initial load
  let logPath = '../../logs/';
  let updatelogs;
  let logFiles = window.logFiles || [];  // Expecting logFiles from PHP
  let logFilesSize = logFiles.length;
  loadInitialData();
  
  /**
   * Initialize event listeners
   */
  function initializeEventListeners() {
    // Select menu change events
    const selectLogs = document.getElementById("logs_select");
    if (selectLogs) {
      // Make sure to bind 'this' correctly in the event handler
      selectLogs.addEventListener("change", handleLogSelectChange);
      
      window.current_file = selectLogs.value;
      if (current_file == 'log_current.csv') {
        updateCurrentLogsFunction();
      }
    }
      

    
    // Min/Max value inputs
    yMinDoc?.addEventListener("focusout", () => {
      yMinInputted = yMinDoc.value;
      render();
    });
    
    yMaxDoc?.addEventListener("focusout", () => {
      yMaxInputted = yMaxDoc.value;
      render();
    });
    
    yMin2Doc?.addEventListener("focusout", () => {
      yMin2Inputted = yMin2Doc.value;
      render();
    });
    
    yMax2Doc?.addEventListener("focusout", () => {
      yMax2Inputted = yMax2Doc.value;
      render();
    });
    
    // Reset zoom button
    resetZoom?.addEventListener("click", () => {
      brushedX = [];
      plotChart();
    });
    
    // Y-axis menu selection
    yMenuDom?.addEventListener("change", function() {
      yOptionClicked(this.value);
    });
    
    yMenuDom2?.addEventListener("change", function() {
      yOptionClicked2(this.value);
    });
    
    // Update menus with default values
    if (yMenuDom && data.columns) {
      selectUpdate(data.columns, "#y-menu", yColumn);
    }
    
    if (yMenuDom2 && data.columns) {
      selectUpdate(data.columns, "#y-menu2", yColumn2);
    }
  }
  
  /**
   * Handle log selection change
   */
  function handleLogSelectChange() {
    brushedX = [];
    current_file = this.value;
    
    console.log("Selected log file:", current_file); // Debug output
    
    // Get the data for the selected file
    if (current_file === "combine_logs") {
      data = dataObj["combine_logs"] || [];
    } else {
      // If the file needs to be loaded, load it
      if (!dataObj[current_file]) {
        // Load the file with the correct path
        let filePath = `../../logs/${current_file}`;
        dataFile(filePath);
        return; // Return early as dataFile will call render() when done
      } else {
        data = dataObj[current_file];
      }
    }
    
    if (data && data.length > 0) {
      let len = data.length - 1;
      if (len > 0) {
        updateAverageDisplay(len);
      }
    }
    
    if (current_file == 'log_current.csv') {
      updateCurrentLogsFunction();
    } else {
      clearInterval(updateCurrentLogs);
    }
    
    // Make sure to render after changing data
    render();
  }
  
  /**
   * Update average display values
   */
  function updateAverageDisplay(len) {
    let unit = is_ebcMeter ? "µg/m<sup>3</sup>" : "ng/m<sup>3</sup>";
    
    // Calculate averages
    let avg12 = d3.mean([...data].splice(len - 12, 12), BCngm3_value);
    let avgAll = d3.mean(data, BCngm3_value);
    
    document.getElementById("report-value").innerHTML = `Averages: <h4 style='display:inline'>
    ${avg12.toFixed(is_ebcMeter ? 2 : 0)} ${unit}<sub>avg12</sub> » 
    ${avgAll.toFixed(is_ebcMeter ? 2 : 0)} ${unit}<sub>avgALL</sub></h4>`;
  }
  
  /**
   * Update current logs function
   */
  function updateCurrentLogsFunction() {
    updateCurrentLogs = setInterval(() => {
      dataFile(`${logPath}log_current.csv`);
    }, 5000);
  }
  
  /**
   * Toggle visibility of y-menu2
   */
  function toggleYMenu2() {
    isHidden = !isHidden;
    
    if ((((yColumn == "BC_rolling_avg_of_6" || yColumn == "BC_rolling_avg_of_12") && yColumn2 == "BCngm3") ||
         ((yColumn2 == "BC_rolling_avg_of_6" || yColumn2 == "BC_rolling_avg_of_12") && yColumn == "BCngm3")) && !isHidden) {
      render();
    }
    
    this.innerHTML = (isHidden) ? `Show` : `Hide`;
    d3.select('.y-axis2').style("opacity", Number(!isHidden));
    d3.select('.line-chart2').style("opacity", Number(!isHidden));
    
    if (isHidden) {
      yMin2Doc.style.opacity = 0;
      yMax2Doc.style.opacity = 0;
    } else {
      yMin2Doc.style.opacity = 1;
      yMax2Doc.style.opacity = 1;
    }
  }
  
  /**
   * Function for y-axis option selection
   */
  function yOptionClicked(value) {
    yColumn = value;
    render();
  }
  
  function yOptionClicked2(value) {
    yColumn2 = value;
    render();
  }
  
  /**
   * Set Y axis values (inputted or calculated)
   */
  function setYAxis() {
    const yMin = yMinDoc.value;
    const yMax = yMaxDoc.value;
    const yMin2 = yMin2Doc.value;
    const yMax2 = yMax2Doc.value;
    
    let [yDataMin, yDataMax] = d3.extent(data, yValueScale);
    let [yDataMin2, yDataMax2] = d3.extent(data, yValueScale2);
    
    yRange = [];
    yRange2 = [];
    
    if (is_ebcMeter && yColumn.toLowerCase().startsWith('bcug')) {
      if (yMinInputted === '') {
        yDataMin = (data.length === 0 || yDataMin === undefined) ? -1.0 : 
                   Math.min(yDataMin, -10.0);
      }
      if (yMaxInputted === '') {
        yDataMax = (data.length === 0 || yDataMax === undefined) ? 1.0 : 
                   Math.max(yDataMax, 10.0);
      }
    }
    
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
  }
  
  /**
   * Handle brush end event
   */
  function handleBrushEnd(event) {
    if (!event.selection) return;
    
    let [x1, x2] = event.selection;
    brushedX = [];
    brushedX.push(xScale.invert(x1));
    brushedX.push(xScale.invert(x2));
    d3.select(".selection").style("display", "none");
    plotChart();
  }
  
  /**
   * Create brush
   */
  const brush = d3.brushX()
    .extent([
      [0, 0],
      [innerWidth, innerHeight]
    ])
    .on("end", handleBrushEnd);
  
  /**
   * Update scales for drawing
   */
  function updateScales() {
    xScale.domain([0, 1000]).range([margin.left, width - margin.right]);
    yScale.domain([0, 1000]).range([height - margin.bottom, margin.top]);
  }
  
  /**
   * Draw empty grid
   */
  function drawGrid() {
    // Basic grid border
    svg.append("rect")
      .attr("x", margin.left)
      .attr("y", margin.top)
      .attr("width", width - margin.left - margin.right)
      .attr("height", height - margin.top - margin.bottom)
      .attr("fill", "none")
      .attr("stroke", "lightgrey");
    
    // Draw a single horizontal grid line vertically centered
    const centerY = (margin.top + (height - margin.bottom)) / 2;
    
    svg.append("line")
      .attr("x1", margin.left)
      .attr("y1", centerY)
      .attr("x2", width - margin.right)
      .attr("y2", centerY)
      .attr("stroke", "lightgrey");
    
    // Add label "0" for the horizontal line
    svg.append("text")
      .attr("x", margin.left - 40)
      .attr("y", centerY)
      .attr("dy", "0.32em")
      .attr("text-anchor", "end")
      .text("0");
    
    // Draw a single vertical line representing the current time
    const currentTime = new Date();
    const formatDate = d3.timeFormat("%H:%M:%S");
    const middleX = (margin.left + (width - margin.right)) / 2;
    
    svg.append("line")
      .attr("x1", middleX)
      .attr("y1", margin.top)
      .attr("x2", middleX)
      .attr("y2", height - margin.bottom)
      .attr("stroke", "lightgrey")
      .attr("stroke-width", 1);
    
    // Add label for the current time
    svg.append("text")
      .attr("x", middleX)
      .attr("y", height - margin.bottom + 40)
      .attr("text-anchor", "middle")
      .style("font-size", "12px")
      .text("Nothing to display yet...");
    
    svg.append("text")
      .attr("x", middleX)
      .attr("y", height - margin.bottom + 25)
      .attr("text-anchor", "middle")
      .style("font-size", "12px")
      .text(formatDate(currentTime));
  }
  
  /**
   * Plot the chart
   */
  function plotChart() {
    setYAxis();
    xScaleRange = brushedX.length == 0 ? d3.extent(data, xValue) : brushedX;
    
    /* CHART CONTAINER */
    const g = svg.selectAll('.container').data([null]);
    const gEnter = g
      .enter().append("g")
      .attr('class', 'container');
    
    gEnter.merge(g)
      .attr("transform", `translate(${margin.left}, ${margin.top})`);
    
    // SCALE FOR X AND Y AXES
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
    
    /* CLIP PATH */
    gEnter.append("clipPath")
      .attr("id", "rectClipPath")
      .append("rect")
      .attr("width", innerWidth)
      .attr("height", innerHeight)
      .attr("fill", "red");
    
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
      .attr('class', 'y-axis2');
    
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
      .y((d) => yScale(yValue(d)));
    
    const lineGenerator2 = d3.line()
      .x((d) => xScale(xValue(d)))
      .y((d) => yScale2(yValue2(d)));
    
    /* HANDLE NULL VALUES FOR ROLLING AVERAGE */
    if (yColumn == "BC_rolling_avg_of_6" || yColumn == "BC_rolling_avg_of_12") {
      lineGenerator.defined(d => d[yColumn] !== null);
    }
    
    if (yColumn2 == "BC_rolling_avg_of_6" || yColumn2 == "BC_rolling_avg_of_12") {
      lineGenerator2.defined(d => d[yColumn2] !== null);
    }
    
    /* GENERATE PATHS */
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
      .merge(g.select('.selected-time-line'));
    
    /* ADDING CIRCLES ON MOUSE MOVE */
    gEnter.append("circle")
      .attr("r", 4)
      .attr("class", "y-circle")
      .attr("fill", "#1f77b4")
      .style("stroke", "black")
      .style("stroke-width", "1.5px")
      .style("opacity", "0")
      .merge(g.select('.y-circle'));
    
    gEnter.append("circle")
      .attr("r", 4)
      .attr("class", "y2-circle")
      .attr("fill", "#ff7f0e")
      .style("stroke", "black")
      .style("stroke-width", "1.5px")
      .style("opacity", "0")
      .merge(g.select('.y2-circle'));
    
    /* MOUSE TRACKING */
    let radar = gEnter.append("g")
      .call(brush)
      .on("mousemove", handleMouseMove)
      .on("mouseout", handleMouseOut)
      .attr("clip-path", "url(#rectClipPath)");
  }
  
  /**
   * Handle mouse move over chart
   */
  function handleMouseMove(e) {
    // Check if data exists and has items
    if (!data || !Array.isArray(data) || data.length === 0) return;
    
    const x = d3.pointer(e)[0];
    hoveredTime = xScale.invert(x);
    
    let bi = bisect(data, hoveredTime) - 1;
    bi_lower = bi < 0 ? 0 : bi;
    bi_upper = bi + 1 > data.length - 1 ? data.length - 1 : bi + 1;
    
    let idx = -new Date(data[bi_lower]["bcmTime"]).getTime() - -new Date(hoveredTime).getTime() > 
              -new Date(hoveredTime).getTime() - -new Date(data[bi_upper]["bcmTime"]).getTime() ?
              bi_upper : bi_lower;
    
    const temp = data[idx];
    let diff = e.offsetX - e.pageX;
    const maxLeft = innerWidth / 2 > e.offsetX ?
                    xScale(data[idx][xLabel]) + margin.right + 30 - diff :
                    xScale(data[idx][xLabel]) - 25 - diff;
    
    let tooltipMessage = (!isHidden) ? 
      `<div><b>Date:</b>  ${temp["bcmTimeRaw"]}</div>
      <div><b>${yColumn}:</b>  ${temp[yColumn]}</div>
      <div><b>${yColumn2}:</b>  ${temp[yColumn2]}</div>` : 
      `<div><b>Date:</b>  ${temp["bcmTimeRaw"]}</div>
      <div><b>${yColumn}:</b>  ${temp[yColumn]}</div>`;
    
    d3.select('.tooltip')
      .style("left", maxLeft + 10 + "px")
      .style("top", e.pageY + "px")
      .style("pointer-events", "none")
      .style("opacity", "1")
      .html(tooltipMessage);
    
    d3.select(".selected-time-line")
      .attr("x1", xScale(temp[xLabel]))
      .attr("x2", xScale(temp[xLabel]))
      .attr("y2", innerHeight)
      .style("opacity", "1");
    
    if (!isHidden) {
      d3.select('.y2-circle')
        .attr("cx", xScale(temp[xLabel]))
        .attr("cy", yScale2(temp[yColumn2]))
        .style("opacity", temp[yColumn2] ? 1 : 0);
    }
    
    d3.select('.y-circle')
      .attr("cx", xScale(temp[xLabel]))
      .attr("cy", yScale(temp[yColumn]))
      .style("opacity", "1");
  }
  
  /**
   * Handle mouse out event
   */
  function handleMouseOut(e) {
    d3.select('.tooltip').style("opacity", "0");
    d3.select(".selected-time-line").style("opacity", "0");
    d3.select('.y-circle').style("opacity", "0");
    d3.select('.y2-circle').style("opacity", "0");
  }
  
  /**
   * Update select menu options
   */
  function selectUpdate(options, id, selectedOption) {
    const select = d3.select(id);
    let option = select.selectAll('option').data(options);
    
    option.enter().append('option')
      .merge(option)
      .attr('value', d => d)
      .property("selected", d => d === selectedOption)
      .text(d => d);
  }
  
  /**
   * Value accessor functions
   */
  const BCngm3_value = (d) => is_ebcMeter ? d["BCugm3"] : d["BCngm3"];
  const BCngm3_unfiltered_value = (d) => is_ebcMeter ? d["BCugm3_unfiltered"] : d["BCngm3_unfiltered"];
  
  /**
   * Render the chart
   */
  function render() {
    // Clear previous contents
    svg.selectAll("*").remove();
    
    if (!data || data.length === 0) {
      updateScales();
      drawGrid();
      return;
    }
    
    yMenuDom.value = yColumn;
    yMenuDom2.value = yColumn2;
    
    if (yColumn === "" || yColumn2 === "") {
      yColumn = data.columns[0];
      yColumn2 = data.columns[2];
    }
    
    yValue = (d) => d[yColumn];
    yValue2 = (d) => d[yColumn2];
    
    if (is_ebcMeter) {
      if ((((yColumn == "BCugm3_unfiltered") && yColumn2 == "BCugm3") ||
           ((yColumn2 == "BCugm3_unfiltered") && yColumn == "BCugm3") && !isHidden)) {
        yValueScale = BCngm3_unfiltered_value;
        yValueScale2 = BCngm3_unfiltered_value;
      }
      if ((((yColumn == "BC_rolling_avg_of_6" || yColumn == "BC_rolling_avg_of_12") && yColumn2 == "BCugm3") ||
           ((yColumn2 == "BC_rolling_avg_of_6" || yColumn2 == "BC_rolling_avg_of_12") && yColumn == "BCugm3")) && !isHidden) {
        yValueScale = BCngm3_value;
        yValueScale2 = BCngm3_value;
      } else {
        yValueScale = yValue;
        yValueScale2 = yValue2;
      }
    } else {
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
    }
    
    yLabel = yColumn;
    yLabel2 = yColumn2;
    plotChart();
  }
  
  /**
   * Process and load CSV data
   */
  function dataFile(file, isCombineLogsSelected = false) {
    data = [];
    data.columns = ["BCngm3", "BCngm3_unfiltered", "BC_rolling_avg_of_6", "BC_rolling_avg_of_12", "bcmATN", "bcmRef", "bcmSen", "Temperature", "Humidity", "Airflow"];
    
    d3.dsv(';', file).then((rawData) => {
      let movingIndex4 = 0;
      let movingIndex6 = 0;
      let movingIndex12 = 0;
      
      rawData.forEach((d, i) => {
        if (d.bcmTime) {
          d.bcmTimeRaw = d.bcmDate + ' ' + d.bcmTime;
          d.bcmTime = parseTime(d.bcmDate + ' ' + d.bcmTime);
          d.bcmRef = +d.bcmRef;
          d.bcmSen = +d.bcmSen;
          d.bcmATN = +d.bcmATN;
          d.relativeLoad = +d.relativeLoad;
          
          if (is_ebcMeter) {
            d.BCugm3 = +d.BCugm3;
            d.BCugm3_unfiltered = +d.BCugm3_unfiltered;
          } else {
            d.BCngm3 = +d.BCngm3;
            d.BCngm3_unfiltered = +d.BCngm3_unfiltered;
          }
          
          d.Temperature = +d.Temperature;
          d.sht_humidity = +d.sht_humidity;
          
          data.push(d);
        }
      });
      
      // Check if this is the current log file
      let result = file.includes("../../logs/log_current.csv");
      if (result == true) {
        let len = data.length - 1;
        
        if (len > 0) {
          updateAverageDisplay(len);
          
          let bcmRef = data[len].bcmRef;
          let bcmSen = data[len].bcmSen;
          let btn = document.getElementById("report-button");
          
          if (bcmSen == 0) {
            if (bcmRef == 0) {
              btn.className = "btn btn-secondary";
            }
          }
          
          filterStatus = bcmSen / bcmRef;
          btn.className = (
            !is_ebcMeter ? (
              filterStatus > 0.8 ? "btn btn-success" :
              filterStatus > 0.7 ? "btn btn-warning" :
              filterStatus > 0.55 ? "btn btn-danger" :
              filterStatus > 0.45 ? "btn btn-secondary" :
              filterStatus > 0.3 ? "btn btn-dark" :
              "btn btn-dark"  // for <= 0.3
            ) : (
              filterStatus <= 0.1 ? "btn btn-dark" :
              filterStatus <= 0.2 ? "btn btn-secondary" :
              filterStatus <= 0.25 ? "btn btn-danger" :
              filterStatus <= 0.4 ? "btn btn-warning" :
              "btn btn-success"
            )
          );
        }
        
        if (len < 0) {
          document.getElementById("report-value").innerHTML = `<h4> </h4>`;
        }
      }
      
      // Calculate moving averages
      data.map((d, i) => {
        // MOVING AVERAGE = 6
        if (i < 4 || i > data.length - 3) {
          d.BC_rolling_avg_of_6 = null;
        } else {
          const bcColumn = is_ebcMeter ? 'BCugm3_unfiltered' : 'BCngm3_unfiltered';
          d.BC_rolling_avg_of_6 = +((((((data.slice(movingIndex6, movingIndex6 + 6).reduce((p, c) => p + c[bcColumn], 0)) / 6)) +
                          (((data.slice(movingIndex6 + 1, movingIndex6 + 1 + 6).reduce((p, c) => p + c[bcColumn], 0)) / 6))) / 2).toFixed(0));
          movingIndex6++;
        }
        
        // MOVING AVERAGE = 12
        if (i < 7 || i > data.length - 6) {
          d.BC_rolling_avg_of_12 = null;
        } else {
          const bcColumn = is_ebcMeter ? 'BCugm3_unfiltered' : 'BCngm3_unfiltered';
          d.BC_rolling_avg_of_12 = +((((((data.slice(movingIndex12, movingIndex12 + 12).reduce((p, c) => p + c[bcColumn], 0)) / 12)) +
                          (((data.slice(movingIndex12 + 1, movingIndex12 + 1 + 12).reduce((p, c) => p + c[bcColumn], 0)) / 12))) / 2).toFixed(0));
          movingIndex12++;
        }
        
        if (isCombineLogsSelected) {
          dataObj[file.split("/")[2]] = data;
          combineLogs.push(d);
        }
      });
      
      if (isCombineLogsSelected) {
        combinedLogCurrentIndex++;
        if (combinedLogCurrentIndex < logFilesSize) {
          dataFile(`${logPath}${logFiles[combinedLogCurrentIndex]}`, true);
        } else {
          dataObj["combine_logs"] = combineLogs;
          // Get the dropdown by ID instead of using a variable
          const selectLogsElement = document.getElementById("logs_select");
          if (selectLogsElement) {
            selectLogsElement.value = "log_current.csv";
            selectLogsElement.dispatchEvent(new Event("change"));
          }
          render();
        }
      } else {
        render();
      }
    });
  }
  
  /**
   * Load initial data
   */
  function loadInitialData() {
    dataFile(`${logPath}${logFiles[combinedLogCurrentIndex]}`, true);
  }
  
  /**
   * Serialize SVG data for download
   */
  function serializeData() {
    var png = (new XMLSerializer()).serializeToString(document.getElementById("line-chart"));
    var svgBlob = new Blob([png], {
      type: "image/svg+xml;charset=utf-8"
    });
    var svgURL = URL.createObjectURL(svgBlob);
    return {
      svgURL,
      svgBlob
    };
  }
  
  /**
   * Save SVG function
   */
  function saveSVG() {
    downloadFile(serializeData().svgURL, "svg");
  }
  
  /**
   * Save PNG function
   */
  function savePNG() {
    var dom = document.createElement("canvas");
    var ct = dom.getContext("2d");
    dom.width = width;
    dom.height = height;
    var bolbURL = window.URL;
    var img = new Image();
    
    img.onload = function() {
      ct.drawImage(img, 0, 0);
      bolbURL.createObjectURL(serializeData().svgBlob);
      downloadFile(dom.toDataURL('image/png'), "png");
    };
    img.src = serializeData().svgURL;
  }
  
  /**
   * Save CSV function
   */
  function saveCSV() {
    downloadCSVFile(`../../logs/${current_file}`, "csv");
  }
  
  /**
   * Download CSV file
   */
  function downloadCSVFile(url, ext) {
    var today = new Date();
    var date = today.getFullYear().toString() + (today.getMonth() + 1).toString() + today.getDate().toString();
    var time = today.getHours().toString() + today.getMinutes().toString() + today.getSeconds().toString();
    var dateTime = date + '_' + time;
    
    download.href = url;
    var hostName = location.hostname;
    download.download = `${hostName}_${dateTime}.${ext}`;
    download.click();
  }
  
  /**
   * Download file
   */
  function downloadFile(url, ext) {
    var today = new Date();
    var date = today.getFullYear() + (today.getMonth() + 1) + today.getDate();
    var time = today.getHours() + today.getMinutes() + today.getSeconds();
    var dateTime = date + '_' + time;
    
    download.href = url;
    var hostName = location.hostname;
    download.download = `${hostName}_${dateTime}.${ext}`;
    download.click();
  }
  
  // Expose functions to window object for external access
  window.render = render;
  window.saveSVG = saveSVG;
  window.savePNG = savePNG;
  window.saveCSV = saveCSV;
});