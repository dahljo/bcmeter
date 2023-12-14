$(document).ready(function() {
  let selectLogs = document.getElementById("logs_select")
  current_file = selectLogs.value;
  if (current_file == 'log_current.csv') {
    updateCurrentLogsFunction()
  }
  /* VARS*/
  let yColumn2 = "BC_rolling_avg_of_12",
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
  const noData = "<div class='alert alert-warning' role='alert'>Not enough data yet. Graph will appear 15 Minutes after start.</div>";
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

    let [yDataMin, yDataMax] = d3.extent(data, yValueScale)
    let [yDataMin2, yDataMax2] = d3.extent(data, yValueScale2)

    yRange = [];
    yRange2 = [];

    yMinInputted == '' ? yRange.push(yDataMin) : yRange.push(Number(yMin));
    yMaxInputted == '' ? yRange.push(yDataMax) : yRange.push(Number(yMax))
    yMin2Inputted == '' ? yRange2.push(yDataMin2) : yRange2.push(Number(yMin2))
    yMax2Inputted == '' ? yRange2.push(yDataMax2) : yRange2.push(Number(yMax2))

    yMinDoc.value = yRange[0];
    yMaxDoc.value = yRange[1];

    if (!isHidden) {
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

  selectLogs.addEventListener("change", function() {
    brushedX = [];
    current_file = selectLogs.value;
    data = dataObj[current_file];
    if (data) {
      let len = data.length - 1;
      render()
      document.getElementById("report-value").innerHTML = `<h4>
        ${data[len]["BCngm3"].toFixed(0)} ng/m<sup>3</sup><sub>current</sub> » 
        ${d3.mean([...data].splice(len-12, 12), BCngm3_value).toFixed(0)} ng/m<sup>3</sup><sub>avg12</sub> » 
        ${d3.mean(data, BCngm3_value).toFixed(0)} ng/m<sup>3</sup><sub>avgALL</sub></h4>`;
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
          document.getElementById("report-value").innerHTML = `<h4>
                ${data[len]["BCngm3"].toFixed(0)} ng/m<sup>3</sup><sub>current</sub> » 
                ${d3.mean([...data].splice(len-12, 12), BCngm3_value).toFixed(0)} ng/m<sup>3</sup><sub>avg12</sub> » 
                ${d3.mean(data, BCngm3_value).toFixed(0)} ng/m<sup>3</sup><sub>avgALL</sub></h4>`;
          let bcmRef = data[len].bcmRef;
          let bcmSen = data[len].bcmSen;
          let btn = document.getElementById("report-button");
          if (bcmSen == 0) {
            if (bcmRef == 0) {
              btn.className = "btn btn-secondary";

            }
          }




          let filterStatus = bcmRef / bcmSen;
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

        if (len < 0) {
          document.getElementById("report-value").innerHTML = `<h4>Not enough data for graph/averages. Will appear after 15 Minutes after starting.</h4>`;
        }
      }




      /* MOVING AVERAGE = 6 */

      data.map((d, i) => {
        if (i < 4 || i > data.length - 3) {
          d.BC_rolling_avg_of_6 = null;
        } else {
          d.BC_rolling_avg_of_6 = +((((((data.slice(movingIndex6, movingIndex6 + 6).reduce((p, c) => p + c.BCngm3, 0)) / 6)) +
            (((data.slice(movingIndex6 + 1, movingIndex6 + 1 + 6).reduce((p, c) => p + c.BCngm3, 0)) / 6))) / 2).toFixed(0))
          movingIndex6++;
        }
        /* MOVING AVERAGE = 12 */
        if (i < 7 || i > data.length - 6) {
          d.BC_rolling_avg_of_12 = null;
        } else {
          d.BC_rolling_avg_of_12 = +((((((data.slice(movingIndex12, movingIndex12 + 12).reduce((p, c) => p + c.BCngm3, 0)) / 12)) +
            (((data.slice(movingIndex12 + 1, movingIndex12 + 1 + 12).reduce((p, c) => p + c.BCngm3, 0)) / 12))) / 2).toFixed(0))
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
        }
      } else {

        render();
      }
    });
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

  });
