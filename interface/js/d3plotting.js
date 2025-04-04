document.addEventListener('DOMContentLoaded', () => {
  let tooltip, hoveredTime = 0, idx = 0, isHidden = false, yValue, yValue2, yValueScale,
      yValueScale2, yLabel, yLabel2, data = [], combineLogs = [], combinedLogCurrentIndex = 2,
      yMinInputted = "", yMin2Inputted = "", yMaxInputted = "", yMax2Inputted = "",
      yRange = [], yRange2 = [], yScale2, brushedX = [], dataObj = {},
      updateCurrentLogs = null, xScale, yScale;

  const CSV_PATTERN_REGEX = /^\d{2}-\d{2}-\d{2}_\d{6}\.csv$/;
  const logPath = '../../logs/';
  window.is_ebcMeter = typeof is_ebcMeter !== 'undefined' && is_ebcMeter === true;
  
  initializeColumnData();

function refreshFileList() {
  return fetch('index.php?action=get_log_files')
    .then(response => response.json())
    .then(files => {
      const filteredFiles = Array.isArray(files) ? files.filter(file => CSV_PATTERN_REGEX.test(file)) : [];
      const oldLogFiles = window.logFiles || [];
      window.logFiles = filteredFiles;
      
      if (JSON.stringify(oldLogFiles) !== JSON.stringify(filteredFiles)) {
        const mostRecentFile = filteredFiles.length > 0 ? sortLogFiles(filteredFiles.slice())[0] : null;
          if (mostRecentFile && mostRecentFile !== window.current_file) {
          window.current_file = mostRecentFile;
          dataFile(`${logPath}${mostRecentFile}`);
          updateLogSelectDropdown(filteredFiles, window.current_file);
        } else {
          updateLogSelectDropdown(filteredFiles, window.current_file);
        }
      }
    })
    .catch(err => console.error('Error refreshing log files:', err));
}
  
function formatLogNameForDisplay(filename) {
  const match = filename.match(/^(\d{2})-(\d{2})-(\d{2})_(\d{6})\.csv$/);
  if (!match) return filename;
  const [_, day, month, year, timeStr] = match;
  const time = timeStr.replace(/(\d{2})(\d{2})(\d{2})/, '$1:$2:$3');
  return `${day}-${month}-${year} ${time}`;
}

function sortLogFiles(files) {
  return files.sort((a, b) => {
    const dateA = a.replace('.csv', '');
    const dateB = b.replace('.csv', '');
    return dateB.localeCompare(dateA);
  });
}

function updateLogSelectDropdown(files, selectedFile) {
  const selectLogs = document.getElementById("logs_select");
  if (!selectLogs) return;
  const currentSelection = selectLogs.value;
  const previousHTML = selectLogs.innerHTML;
  const wasFocused = document.activeElement === selectLogs;
  let newOptionsHTML = '';
  const sortedFiles = sortLogFiles(files.slice());
  
  Promise.all(sortedFiles.map(file => 
    fetch(`${logPath}${file}`)
      .then(response => response.text())
      .then(content => {
        const lineCount = content.split('\n').filter(line => line.trim().length > 0).length;
        return { file, lineCount };
      })
      .catch(() => ({ file, lineCount: 0 }))
  )).then(results => {
    const validFiles = sortLogFiles(results.filter(item => item.lineCount > 2).map(item => item.file));
    
    if (validFiles.length > 0) {
      const firstFile = validFiles[0];
      const firstDisplayName = formatLogNameForDisplay(firstFile);
      newOptionsHTML += `<option value="${firstFile}" ${firstFile === selectedFile ? 'selected' : ''}>${firstDisplayName}</option>`;
      
      for (let i = 1; i < validFiles.length; i++) {
        const file = validFiles[i];
        const displayName = formatLogNameForDisplay(file);
        newOptionsHTML += `<option value="${file}" ${file === selectedFile ? 'selected' : ''}>${displayName}</option>`;
      }
    }
    
    newOptionsHTML += `<option value="combine_logs" ${selectedFile === 'combine_logs' ? 'selected' : ''}>Combine Logs</option>`;
    
    if (newOptionsHTML !== previousHTML) {
      selectLogs.innerHTML = newOptionsHTML;
      let selectionFound = false;
      for (let i = 0; i < selectLogs.options.length; i++) {
        if (selectLogs.options[i].value === selectedFile || selectLogs.options[i].value === currentSelection) {
          selectLogs.selectedIndex = i;
          selectionFound = true;
          break;
        }
      }
      if (!selectionFound && selectLogs.options.length > 0) {
        selectLogs.selectedIndex = 0;
        window.current_file = selectLogs.options[0].value;
      }
      if (wasFocused) selectLogs.focus();
    }
  });
}
  const noData = "<div class='alert alert-warning' role='alert'>Not enough data yet.</div>";
  const svg = d3.select("svg");
  const width = +svg.attr("width");
  const height = +svg.attr("height");
  const parseTime = d3.timeParse("%d-%m-%Y %H:%M:%S");
  const title = "bcMeter";
  const margin = { top: 15, right: 110, bottom: 55, left: 110 };
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

  function initializeColumnData() {
    window.yColumn = '';
    window.yColumn2 = '';

    const baseColumns = [
      "BC_rolling_avg_of_6", "BC_rolling_avg_of_12", "bcmATN", "bcmRef", 
      "bcmSen", "Temperature", "sht_humidity", "airflow"
    ];
    
    let deviceColumns = [];
    
    if (window.is_ebcMeter) {
      window.yColumn = 'BCugm3';
      window.yColumn2 = 'Temperature';
      deviceColumns = ["BCugm3", "BCugm3_unfiltered", "BCugm3_ona"];
    } else {
      window.yColumn = 'BCngm3';
      window.yColumn2 = 'BC_rolling_avg_of_6';
      deviceColumns = ["BCngm3", "BCngm3_unfiltered", "BCngm3_ona"];
    }
    
    const allColumns = [...deviceColumns, ...baseColumns];
    combineLogs.columns = allColumns;
    data.columns = allColumns;
    
    if (window.yMenuDom && data.columns) {
      selectUpdate(data.columns, "#y-menu", window.yColumn);
    }
    
    if (window.yMenuDom2 && data.columns) {
      selectUpdate(data.columns, "#y-menu2", window.yColumn2);
    }
  }

  xScale = d3.scaleLinear();
  yScale = d3.scaleLinear();
  
function initializeAll() {
  initializeEventListeners();
  refreshFileList()
    .then(() => {
      setDefaultLogSelection();
      loadInitialData();
    })
    .catch(err => console.error('Error during initial loading:', err));
}
  
  function setDefaultLogSelection() {
    const selectLogs = document.getElementById("logs_select");
    if (!selectLogs || !window.logFiles || !Array.isArray(window.logFiles)) return;
    
    const filteredLogFiles = window.logFiles.filter(file => CSV_PATTERN_REGEX.test(file));
    
    filteredLogFiles.sort((a, b) => {
      const aTimestamp = a.replace('.csv', '');
      const bTimestamp = b.replace('.csv', '');
      return bTimestamp.localeCompare(aTimestamp);
    });
    
    if (filteredLogFiles.length > 0) {
      updateLogSelectDropdown(filteredLogFiles, filteredLogFiles[0]);
      window.current_file = filteredLogFiles[0];
    }
    
    const event = new Event('change');
    selectLogs.dispatchEvent(event);
  }

  function initializeEventListeners() {
    const selectLogs = document.getElementById("logs_select");
    if (selectLogs) {
      selectLogs.removeEventListener("change", handleLogSelectChange);
      selectLogs.addEventListener("change", handleLogSelectChange);
      window.current_file = selectLogs.value;
      
      if (window.logFiles && window.logFiles.length > 0 && window.current_file === window.logFiles[0]) {
        updateCurrentLogsFunction();
      }
    
    if (yMinDoc) {
      yMinDoc.addEventListener("focusout", () => {
        yMinInputted = yMinDoc.value;
        render();
      });
    }
    
    if (yMaxDoc) {
      yMaxDoc.addEventListener("focusout", () => {
        yMaxInputted = yMaxDoc.value;
        render();
      });
    }
    
    if (yMin2Doc) {
      yMin2Doc.addEventListener("focusout", () => {
        yMin2Inputted = yMin2Doc.value;
        render();
      });
    }
    
    if (yMax2Doc) {
      yMax2Doc.addEventListener("focusout", () => {
        yMax2Inputted = yMax2Doc.value;
        render();
      });
    }
    
    if (resetZoom) {
      resetZoom.addEventListener("click", () => {
        brushedX = [];
        plotChart();
      });
    }
    
    if (yMenuDom) {
      yMenuDom.addEventListener("change", function() {
        yOptionClicked(this.value);
      });
    }
    
    if (yMenuDom2) {
      yMenuDom2.addEventListener("change", function() {
        yOptionClicked2(this.value);
      });
    }
    
    document.getElementById("hide-y-menu2")?.addEventListener("click", function() {
      toggleYMenu2();
    });
    
    if (yMenuDom && data.columns) {
      selectUpdate(data.columns, "#y-menu", yColumn);
    }
    
    if (yMenuDom2 && data.columns) {
      selectUpdate(data.columns, "#y-menu2", yColumn2);
    }
  }
}
  

function handleLogSelectChange() {
  brushedX = [];
  current_file = this.value;
  if (updateCurrentLogs) {
    clearInterval(updateCurrentLogs);
    updateCurrentLogs = null;
  }
  data = [];
  data.columns = combineLogs.columns;
  if (current_file === "combine_logs") {
    if (dataObj["combine_logs"] && dataObj["combine_logs"].length > 0) {
      data = dataObj["combine_logs"];
      if (data.length > 0) {
        let len = data.length - 1;
        updateAverageDisplay(len);
      }
      render();
    } else {
      combineLogs = [];
      combineLogs.columns = data.columns;
      combinedLogCurrentIndex = 0;
      if (window.logFiles && window.logFiles.length > 0) {
        loadBackgroundFiles();
      } else {
        document.getElementById("report-value").innerHTML = `<h4>No log files available to combine</h4>`;
        render();
      }
    }
  } else {
    let filePath = `../../logs/${current_file}`;
    dataFile(filePath);
    if (window.logFiles && window.logFiles.length > 0 && current_file === window.logFiles[0]) {
      updateCurrentLogsFunction();
    }
  }
}

function loadBackgroundFiles() {
  combineLogs = []; 
  combineLogs.columns = data.columns; 
  combinedLogCurrentIndex = 0;
  processNextFile(0);
}

function processNextFile(index) {
  if (!window.logFiles || index >= window.logFiles.length) {
    if (combineLogs.length > 0) {
      combineLogs.sort((a, b) => a.bcmTime - b.bcmTime);
      dataObj["combine_logs"] = combineLogs;
      if (current_file === "combine_logs") {
        data = combineLogs;
        if (data.length > 0) {
          let len = data.length - 1;
          updateAverageDisplay(len);
        }
        render();
      }
    }
    return;
  }
  dataFile(`${logPath}${window.logFiles[index]}`, true, () => processNextFile(index + 1));
}

function updateCurrentLogsFunction() {
  if (updateCurrentLogs) {
    clearInterval(updateCurrentLogs);
    updateCurrentLogs = null;
  }
    if (window.logFiles && window.logFiles.length > 0 && window.current_file === window.logFiles[0]) {
    updateCurrentLogs = setInterval(() => {
      refreshFileList().then(() => {
        const mostRecentFile = window.logFiles && window.logFiles.length > 0 ? 
          window.logFiles[0] : window.current_file;
        
        dataFile(`${logPath}${mostRecentFile}`);
      });
    }, 5000);
  }
}
  function updateAverageDisplay(len) {
    if (len < 0 || !data || data.length === 0) {
      document.getElementById("report-value").innerHTML = `<h4>No data available</h4>`;
      return;
    }
    
    let unit = is_ebcMeter ? "µg/m<sup>3</sup>" : "ng/m<sup>3</sup>";
    
    let avg12Values = data.slice(Math.max(0, len - 12), len + 1).map(BCngm3_value).filter(val => !isNaN(val));
    let allValues = data.map(BCngm3_value).filter(val => !isNaN(val));
    
    let avg12 = avg12Values.length > 0 ? d3.mean(avg12Values) : 0;
    let avgAll = allValues.length > 0 ? d3.mean(allValues) : 0;
    
    let averageHtml = `Averages: <h4 style='display:inline'>
      ${avg12.toFixed(is_ebcMeter ? 2 : 0)} ${unit}<sub>avg12</sub> » 
      ${avgAll.toFixed(is_ebcMeter ? 2 : 0)} ${unit}<sub>avgALL</sub></h4>`;
    
    document.getElementById("report-value").innerHTML = averageHtml;
  }
  
  function toggleYMenu2() {
    isHidden = !isHidden;
    
    d3.select('.y-axis2').style("opacity", Number(!isHidden));
    d3.select('.line-chart2').style("opacity", Number(!isHidden));
    
    if (isHidden) {
      yMin2Doc.style.opacity = 0;
      yMax2Doc.style.opacity = 0;
    } else {
      yMin2Doc.style.opacity = 1;
      yMax2Doc.style.opacity = 1;
    }
    
    this.innerHTML = (isHidden) ? `Show` : `Hide`;
    
    if ((((yColumn == "BC_rolling_avg_of_6" || yColumn == "BC_rolling_avg_of_12") && yColumn2 == (is_ebcMeter ? "BCugm3" : "BCngm3")) ||
         ((yColumn2 == "BC_rolling_avg_of_6" || yColumn2 == "BC_rolling_avg_of_12") && yColumn == (is_ebcMeter ? "BCugm3" : "BCngm3"))) && !isHidden) {
      render();
    }
  }

  function yOptionClicked(value) {
    yColumn = value;
    render();
  }
  
  function yOptionClicked2(value) {
    yColumn2 = value;
    render();
  }
  
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
  
  function handleBrushEnd(event) {
    if (!event.selection) return;
    
    let [x1, x2] = event.selection;
    brushedX = [];
    brushedX.push(xScale.invert(x1));
    brushedX.push(xScale.invert(x2));
    d3.select(".selection").style("display", "none");
    plotChart();
  }
  
  const brush = d3.brushX()
    .extent([
      [0, 0],
      [innerWidth, innerHeight]
    ])
    .on("end", handleBrushEnd);
  
  function updateScales() {
    xScale.domain([0, 1000]).range([margin.left, width - margin.right]);
    yScale.domain([0, 1000]).range([height - margin.bottom, margin.top]);
  }
  
  function drawGrid() {
    svg.append("rect")
      .attr("x", margin.left)
      .attr("y", margin.top)
      .attr("width", width - margin.left - margin.right)
      .attr("height", height - margin.top - margin.bottom)
      .attr("fill", "none")
      .attr("stroke", "lightgrey");
    
    const centerY = (margin.top + (height - margin.bottom)) / 2;
    
    svg.append("line")
      .attr("x1", margin.left)
      .attr("y1", centerY)
      .attr("x2", width - margin.right)
      .attr("y2", centerY)
      .attr("stroke", "lightgrey");
    
    svg.append("text")
      .attr("x", margin.left - 40)
      .attr("y", centerY)
      .attr("dy", "0.32em")
      .attr("text-anchor", "end")
      .text("0");
    
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
    
    svg.append("text")
      .attr("x", middleX)
      .attr("y", height - margin.bottom + 40)
      .attr("text-anchor", "middle")
      .style("font-size", "12px")
      .text("Device warming up ~10-15 minutes");
    
    svg.append("text")
      .attr("x", middleX)
      .attr("y", height - margin.bottom + 25)
      .attr("text-anchor", "middle")
      .style("font-size", "12px")
      .text(formatDate(currentTime));
  }
  
  function plotChart(skipFullRedraw = false, existingChartState = {}) {
    setYAxis();
    xScaleRange = brushedX.length == 0 ? d3.extent(data, xValue) : brushedX;
    if (skipFullRedraw) {
      xScale.domain(xScaleRange).nice();
      yScale.domain(yRange).nice();
      yScale2.domain(yRange2).nice();
      svg.select('.x-axis').transition().duration(500).call(d3.axisBottom(xScale).tickSize(-innerHeight).tickPadding(15));
      svg.select('.y-axis').transition().duration(500).call(d3.axisLeft(yScale).ticks(9).tickSize(-innerWidth).tickPadding(8));
      svg.select('.y-axis2').transition().duration(500).call(d3.axisRight(yScale2).ticks(9).tickSize(innerWidth).tickPadding(8));
      svg.select('.y-axis-label').text(yLabel);
      svg.select('.y-axis-label2').text(yLabel2);
      const lineGenerator = d3.line().x((d) => xScale(xValue(d))).y((d) => yScale(yValue(d)));
      const lineGenerator2 = d3.line().x((d) => xScale(xValue(d))).y((d) => yScale2(yValue2(d)));
      if (yColumn == "BC_rolling_avg_of_6" || yColumn == "BC_rolling_avg_of_12") lineGenerator.defined(d => d[yColumn] !== null);
      if (yColumn2 == "BC_rolling_avg_of_6" || yColumn2 == "BC_rolling_avg_of_12") lineGenerator2.defined(d => d[yColumn2] !== null);
      svg.select('.line-chart').transition().duration(500).attr('d', lineGenerator(data));
      svg.select('.line-chart2').transition().duration(500).attr('d', lineGenerator2(data));
      return;
    }
    const g = svg.selectAll('.container').data([null]);
    const gEnter = g.enter().append("g").attr('class', 'container');
    gEnter.merge(g).attr("transform", `translate(${margin.left}, ${margin.top})`);
    xScale = d3.scaleTime().domain(xScaleRange).range([0, innerWidth]).nice();
    yScale = d3.scaleLinear().domain(yRange).range([innerHeight, 0]).nice();
    yScale2 = d3.scaleLinear().domain(yRange2).range([innerHeight, 0]).nice();
    
    gEnter.append("clipPath")
      .attr("id", "rectClipPath")
      .append("rect")
      .attr("width", innerWidth)
      .attr("height", innerHeight)
      .attr("fill", "red");
    
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
    
    const lineGenerator = d3.line()
      .x((d) => xScale(xValue(d)))
      .y((d) => yScale(yValue(d)));
    
    const lineGenerator2 = d3.line()
      .x((d) => xScale(xValue(d)))
      .y((d) => yScale2(yValue2(d)));
    
    if (yColumn == "BC_rolling_avg_of_6" || yColumn == "BC_rolling_avg_of_12") {
      lineGenerator.defined(d => d[yColumn] !== null);
    }
    
    if (yColumn2 == "BC_rolling_avg_of_6" || yColumn2 == "BC_rolling_avg_of_12") {
      lineGenerator2.defined(d => d[yColumn2] !== null);
    }
    
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
    
    gEnter.append("line")
      .attr("class", "selected-time-line")
      .attr("y1", 0)
      .style("opacity", "0")
      .merge(g.select('.selected-time-line'));
    
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
    
    let radar = gEnter.append("g")
      .call(brush)
      .on("mousemove", handleMouseMove)
      .on("mouseout", handleMouseOut)
      .attr("clip-path", "url(#rectClipPath)");
  }
  
  function handleMouseMove(e) {
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
  
  function handleMouseOut(e) {
    d3.select('.tooltip').style("opacity", "0");
    d3.select(".selected-time-line").style("opacity", "0");
    d3.select('.y-circle').style("opacity", "0");
    d3.select('.y2-circle').style("opacity", "0");
  }
  
  function selectUpdate(options, id, selectedOption) {
    const select = d3.select(id);
    let option = select.selectAll('option').data(options);
    
    option.enter().append('option')
      .merge(option)
      .attr('value', d => d)
      .property("selected", d => d === selectedOption)
      .text(d => d);
  }
  
  const BCngm3_value = (d) => is_ebcMeter ? d["BCugm3"] : d["BCngm3"];
  const BCngm3_unfiltered_value = (d) => is_ebcMeter ? d["BCugm3_unfiltered"] : d["BCngm3_unfiltered"];
  

function render() {
  const existingChartState = {
    hasChart: svg.select('.container').size() > 0,
    xRange: brushedX.length ? brushedX : (xScale && xScale.domain ? xScale.domain() : []),
    yRange: yRange.slice(),
    yRange2: yRange2.slice()
  };
  const skipFullRedraw = existingChartState.hasChart && data && data.length > 0 && yColumn && yColumn2;
  if (!skipFullRedraw) svg.selectAll("*").remove();
  if (!data || data.length === 0) {
    updateScales();
    drawGrid();
    document.getElementById("report-value").innerHTML = `<h5>Device warming up ~10-15 minutes before showing data</h5>`;
    return;
  }
  const currentYValue = yMenuDom.value;
  const currentY2Value = yMenuDom2.value;
  if (currentYValue !== yColumn) yMenuDom.value = yColumn;
  if (currentY2Value !== yColumn2) yMenuDom2.value = yColumn2;
  if (yColumn === "" || yColumn2 === "") {
    yColumn = data.columns[0];
    yColumn2 = data.columns[2];
  }
  yValue = (d) => d[yColumn];
  yValue2 = (d) => d[yColumn2];
  if (is_ebcMeter) {
    if ((((yColumn == "BCugm3_unfiltered") && yColumn2 == "BCugm3") || ((yColumn2 == "BCugm3_unfiltered") && yColumn == "BCugm3") && !isHidden)) {
      yValueScale = BCngm3_unfiltered_value;
      yValueScale2 = BCngm3_unfiltered_value;
    }
    if ((((yColumn == "BC_rolling_avg_of_6" || yColumn == "BC_rolling_avg_of_12") && yColumn2 == "BCugm3") || ((yColumn2 == "BC_rolling_avg_of_6" || yColumn2 == "BC_rolling_avg_of_12") && yColumn == "BCugm3")) && !isHidden) {
      yValueScale = BCngm3_value;
      yValueScale2 = BCngm3_value;
    } else {
      yValueScale = yValue;
      yValueScale2 = yValue2;
    }
  } else {
    if ((((yColumn == "BCngm3_unfiltered") && yColumn2 == "BCngm3") || ((yColumn2 == "BCngm3_unfiltered") && yColumn == "BCngm3") && !isHidden)) {
      yValueScale = BCngm3_unfiltered_value;
      yValueScale2 = BCngm3_unfiltered_value;
    }
    if ((((yColumn == "BC_rolling_avg_of_6" || yColumn == "BC_rolling_avg_of_12") && yColumn2 == "BCngm3") || ((yColumn2 == "BC_rolling_avg_of_6" || yColumn2 == "BC_rolling_avg_of_12") && yColumn == "BCngm3")) && !isHidden) {
      yValueScale = BCngm3_value;
      yValueScale2 = BCngm3_value;
    } else {
      yValueScale = yValue;
      yValueScale2 = yValue2;
    }
  }
  yLabel = yColumn;
  yLabel2 = yColumn2;
  plotChart(skipFullRedraw, existingChartState);
}
  
function dataFile(file, isCombineLogsSelected = false, callback = null) {
  const loadingEl = document.getElementById("report-value");
  const isPeriodicUpdate = file.includes(window.logFiles[0]) && window.current_file === window.logFiles[0];
  if (!isCombineLogsSelected && !isPeriodicUpdate) loadingEl.innerHTML = "<h5>Loading data...</h5>";

  if (!data.columns || data.columns.length === 0) initializeColumnData();
  d3.dsv(';', file).then((rawData) => {
    if (rawData.length === 0) { loadingEl.innerHTML = ""; render(); if (callback) callback(); return; }
    let newData = []; let movingIndex4 = 0, movingIndex6 = 0, movingIndex12 = 0;
    rawData.forEach((d, i) => {
      if (d.bcmTime) {
        d.bcmTimeRaw = d.bcmDate + ' ' + d.bcmTime;
        d.bcmTime = parseTime(d.bcmDate + ' ' + d.bcmTime);
        d.bcmRef = +d.bcmRef; d.bcmSen = +d.bcmSen; d.bcmATN = +d.bcmATN; d.relativeLoad = +d.relativeLoad;
        if (is_ebcMeter) { d.BCugm3 = +d.BCugm3; d.BCugm3_unfiltered = +d.BCugm3_unfiltered; } 
        else { d.BCngm3 = +d.BCngm3; d.BCngm3_unfiltered = +d.BCngm3_unfiltered; }
        d.Temperature = +d.Temperature; d.sht_humidity = +d.sht_humidity;
        newData.push(d);
      }
    });
    if (newData.length === 0) { loadingEl.innerHTML = ""; render(); if (callback) callback(); return; }
    let processedData = newData; processedData.columns = combineLogs.columns;
    processedData.forEach((d, i) => {
      if (i < 4 || i > processedData.length - 3) d.BC_rolling_avg_of_6 = null;
      else {
        const bcColumn = is_ebcMeter ? 'BCugm3_unfiltered' : 'BCngm3_unfiltered';
        d.BC_rolling_avg_of_6 = +((((((processedData.slice(movingIndex6, movingIndex6 + 6).reduce((p, c) => p + c[bcColumn], 0)) / 6)) + (((processedData.slice(movingIndex6 + 1, movingIndex6 + 1 + 6).reduce((p, c) => p + c[bcColumn], 0)) / 6))) / 2).toFixed(0));
        movingIndex6++;
      }
      if (i < 7 || i > processedData.length - 6) d.BC_rolling_avg_of_12 = null;
      else {
        const bcColumn = is_ebcMeter ? 'BCugm3_unfiltered' : 'BCngm3_unfiltered';
        d.BC_rolling_avg_of_12 = +((((((processedData.slice(movingIndex12, movingIndex12 + 12).reduce((p, c) => p + c[bcColumn], 0)) / 12)) + (((processedData.slice(movingIndex12 + 1, movingIndex12 + 1 + 12).reduce((p, c) => p + c[bcColumn], 0)) / 12))) / 2).toFixed(0));
        movingIndex12++;
      }
    });
    if (!isCombineLogsSelected) {
      data = processedData;
      if (current_file) dataObj[current_file] = data;
      if (window.logFiles && window.logFiles.length > 0 && window.current_file === window.logFiles[0]) {
        let len = data.length - 1;
        if (len >= 0) {
          updateAverageDisplay(len);
          if (len > 0) {
            let bcmRef = data[len].bcmRef; let bcmSen = data[len].bcmSen;
            let btn = document.getElementById("report-button");
            if (bcmSen == 0 && bcmRef == 0) btn.className = "btn btn-secondary";
            filterStatus = bcmSen / bcmRef;
            btn.className = (!is_ebcMeter ? (filterStatus > 0.8 ? "btn btn-success" : filterStatus > 0.7 ? "btn btn-warning" : filterStatus > 0.55 ? "btn btn-danger" : filterStatus > 0.45 ? "btn btn-secondary" : "btn btn-dark") : (filterStatus <= 0.1 ? "btn btn-dark" : filterStatus <= 0.2 ? "btn btn-secondary" : filterStatus <= 0.25 ? "btn btn-danger" : filterStatus <= 0.4 ? "btn btn-warning" : "btn btn-success"));
          } else document.getElementById("report-value").innerHTML = `<h5>Device warming up ~10-15 minutes before showing data</h5>`;
        } else document.getElementById("report-value").innerHTML = `<h5>Device warming up ~10-15 minutes before showing data</h5>`;
      }
      loadingEl.innerHTML = ""; render();
    } else {
      if (!window.skipBackgroundLoading) {
        const fileName = file.split("/").pop();
        dataObj[fileName] = processedData;
        combineLogs = [...combineLogs, ...processedData];
        if (current_file === "combine_logs") {
          data = combineLogs;
          if (data.length > 0) updateAverageDisplay(data.length - 1);
          loadingEl.innerHTML = ""; render();
        }
      }
      if (callback) callback();
    }
  }).catch(error => {
    if (isCombineLogsSelected) { if (callback) callback(); }
    else { loadingEl.innerHTML = ""; render(); }
  });
}

function loadInitialData() {
  if (!data.columns || !combineLogs.columns) initializeColumnData();
  const mostRecentFile = window.logFiles && window.logFiles.length > 0 ? sortLogFiles(window.logFiles.slice())[0] : null;
  if (mostRecentFile) {
    window.current_file = mostRecentFile;
    dataFile(`${logPath}${mostRecentFile}`);
    if (window.logFiles && window.logFiles.length > 0 && window.current_file === window.logFiles[0]) {
      updateCurrentLogsFunction();
    }
  }
}


function loadAllFilesForCombine(index) {
  if (!window.logFiles || index >= window.logFiles.length) {
    if (combineLogs.length > 0) {
      combineLogs.sort((a, b) => a.bcmTime - b.bcmTime);
      dataObj["combine_logs"] = combineLogs;
    }
    if (window.mainViewFile && window.mainViewFile !== 'combine_logs') {
      const mostRecentFile = window.logFiles && window.logFiles.length > 0 ? window.logFiles[0] : null;
      window.current_file = mostRecentFile; // Important: restore the most recent file
      dataFile(`${logPath}${mostRecentFile}`);
    }
    return;
  }
  const file = window.logFiles[index];
  dataFile(`${logPath}${file}`, true, () => {
    loadAllFilesForCombine(index + 1);
  });
}


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
  
  function saveSVG() {
    downloadFile(serializeData().svgURL, "svg");
  }
  
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
  
  function saveCSV() {
    downloadCSVFile(`../../logs/${current_file}`, "csv");
  }
  
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
  initializeAll();
  window.render = render;
  window.saveSVG = saveSVG;
  window.savePNG = savePNG;
  window.saveCSV = saveCSV;
  setInterval(refreshFileList, 30000);
});

