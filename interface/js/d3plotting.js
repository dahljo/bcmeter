let updateCurrentLogs = null, fileListRefreshInterval = null, refreshInterval = 30000;
let data = {columns: []}, combineLogs = {columns: []}, isHidden = false, isHidden3 = false;
let yRange = [], yRange2 = [], yRange3 = [], yMin = '', yMax = '', yMin2Inputted = '', yMax2Inputted = '', yMin3Inputted = '', yMax3Inputted = '';
let xScale = d3.scaleTime(), yScale = d3.scaleLinear(), yScale2 = d3.scaleLinear(), yScale3 = d3.scaleLinear();
let yValue, yValue2, yValue3, yLabel, yLabel2, yLabel3, current_file = '';
let y1MinIsAuto = localStorage.getItem('y1_min_is_auto') === 'true';
let y1MaxIsAuto = localStorage.getItem('y1_max_is_auto') === 'true';
let y2MinIsAuto = localStorage.getItem('y2_min_is_auto') === 'true';
let y2MaxIsAuto = localStorage.getItem('y2_max_is_auto') === 'true';
let y3MinIsAuto = localStorage.getItem('y3_min_is_auto') === 'true';
let y3MaxIsAuto = localStorage.getItem('y3_max_is_auto') === 'true';
const dataObj = {}, combinedLogCurrentIndex = 0;
let medianFilterKernel1 = parseInt(localStorage.getItem('medianFilterKernel1')) || 0;
let medianFilterKernel2 = parseInt(localStorage.getItem('medianFilterKernel2')) || 0;
let medianFilterKernel3 = parseInt(localStorage.getItem('medianFilterKernel3')) || 0;
let resetPeakThreshold = -1;
let initialXDomain, initialYDomain, initialY2Domain, initialY3Domain;

const EXCLUDED_COLUMNS = ["bcmDate", "bcmTime", "BC_ona", "notice", "sampleDuration", "BCugm3_ona", "ONA_window_size"];
let COLUMN_ALIASES = {
  // Generic column names
  "bcmRef": "Reference voltage",
  "bcmSen": "Sensor voltage",
  "bcmATN": "Attenuation",
  "main_sensor_bias": "Main Sensor Bias",
  "reference_sensor_bias": "Reference Sensor Bias",
  "BC_rolling_avg_of_6": "BC rolling average of 6",
  "BC_rolling_avg_of_12": "BC Rolling average of 12",
  "BCngm3":"Black Carbon (880nm)",
  "BCngm3_unfiltered": "BC Unfiltered (880nm)",

  // Specific 880nm column names
  "bcmRef_880nm": "Reference (880nm)",
  "bcmSen_880nm": "Sensor (880nm)",
  "bcmATN_880nm": "Attenuation (880nm)",
  "BCngm3_unfiltered_880nm": "BC Unfiltered (880nm)",
  "BCngm3_880nm": "Black Carbon (880nm)",
  "BCugm3_unfiltered_880nm": "BC Unfiltered (880nm)",
  "BCugm3_unfiltered": "BC Unfiltered (880nm)",
  "BCugm3": "Black Carbon (880nm)",

  // Specific 520nm column names
  "bcmRef_520nm": "Reference (520nm)",
  "bcmSen_520nm": "Sensor (520nm)",
  "bcmATN_520nm": "Attenuation (520nm)",
  "BCngm3_unfiltered_520nm": "BC Unfiltered (520nm)",
  "BCngm3_520nm": "Black Carbon (520nm)",

  // Specific 370nm column names
  "bcmRef_370nm": "Reference (370nm)",
  "bcmSen_370nm": "Sensor (370nm)",
  "bcmATN_370nm": "Attenuation (370nm)",
  "BCngm3_unfiltered_370nm": "BC Unfiltered (370nm)",
  "BCngm3_370nm": "Black Carbon (370nm)",

  // General & common column names
  "relativeLoad": "Relative Load",
  "AAE": "Ångström Exponent",
  "Temperature": "Temperature (°C)",
  "sht_humidity": "Humidity (%)",
  "airflow": "Air Flow (l/min)"
};

const CSV_PATTERN_REGEX = /^\d{2}-\d{2}-\d{2}_\d{6}\.csv$/, logPath = '../../logs/';
window.is_ebcMeter = typeof is_ebcMeter !== 'undefined' && is_ebcMeter === true;
window.logFiles = [], window.current_file = '', window.configSampleTime = null;

const width = 1100;
const height = 480;
const svg = d3.select("#line-chart")
    .attr("viewBox", `0 0 ${width} ${height}`);
const parseTime = d3.timeParse("%d-%m-%y %H:%M:%S"), title = "bcMeter";
const margin = {top: 15, right: 180, bottom: 55, left: 110};
const innerWidth = width - margin.left - margin.right, innerHeight = height - margin.top - margin.bottom;
const xValue = d => d.bcmTime, download = document.getElementById("download");
const yMinDoc = document.getElementById("y-menu-min"), yMaxDoc = document.getElementById("y-menu-max");
const yMin2Doc = document.getElementById("y-menu2-min"), yMax2Doc = document.getElementById("y-menu2-max");
const yMin3Doc = document.getElementById("y-menu3-min"), yMax3Doc = document.getElementById("y-menu3-max");
const resetZoom = document.getElementById("resetZoom"), yMenuDom = document.getElementById("y-menu");
const yMenuDom2 = document.getElementById("y-menu2"), yMenuDom3 = document.getElementById("y-menu3"), bisect = d3.bisector(d => d.bcmTime).center;
const xLabel = "bcmTime";



const getMostRecentLogFile = () => {
  if (!window.logFiles?.length) return null;
  const validFiles = window.logFiles.filter(file => CSV_PATTERN_REGEX.test(file));
  const sortedFiles = sortLogFiles(validFiles.slice());
  return sortedFiles.length > 0 ? sortedFiles[0] : null;
};

const isViewingMostRecentFile = () => {
  const mostRecentFile = getMostRecentLogFile();
  return window.current_file === mostRecentFile && window.current_file !== 'combine_logs';
};

function updateCurrentLogsFunction() {
  if (updateCurrentLogs) {
    clearInterval(updateCurrentLogs);
    updateCurrentLogs = null;
  }
  
  if (isViewingMostRecentFile()) {
    const sampleTimeSeconds = window.configSampleTime || 300;
    const interval = Math.max(5000, Math.min(sampleTimeSeconds * 500, 60000));
    
    updateCurrentLogs = setInterval(() => {
      if (isViewingMostRecentFile()) {
        const mostRecentFile = getMostRecentLogFile();
        if (mostRecentFile) {
          dataFile(logPath + mostRecentFile);
        }
      } else {
        clearInterval(updateCurrentLogs);
        updateCurrentLogs = null;
      }
    }, interval);
  }
}


function setFileListRefreshInterval() {
  const interval = window.configSampleTime ? Math.max(5000, Math.min(window.configSampleTime * 500, 60000)) : refreshInterval;
  if (fileListRefreshInterval) clearInterval(fileListRefreshInterval);
}

document.addEventListener('bcmeter-config-loaded', e => {
  if (e.detail?.sampleTime) {
    const sampleTimeSeconds = e.detail.sampleTime;
    refreshInterval = Math.max(5000, Math.min(sampleTimeSeconds * 500, 60000));
    console.log(`Setting refresh interval to ${refreshInterval}ms based on sample time ${sampleTimeSeconds}s`);
    updateCurrentLogsFunction();
  }
});

document.addEventListener('DOMContentLoaded', () => {

    setFileListRefreshInterval();
    initializeColumnData();
    initializeAll();
    initializeSliders();
});

function updateAliasesBasedOnUnits(headers) {
  const hasUgUnits = headers.some(h => h.includes('ugm3')), hasNgUnits = headers.some(h => h.includes('ngm3'));
  if (hasUgUnits) {
    COLUMN_ALIASES["BCugm3_unfiltered"] = "Black Carbon (unfiltered) µg/m³";
    COLUMN_ALIASES["BCugm3"] = "Black Carbon µg/m³";
    if (headers.includes("BCugm3_ona")) COLUMN_ALIASES["BCugm3_ona"] = "Black Carbon ONA µg/m³";
  }
  if (hasNgUnits) {
    COLUMN_ALIASES["BCngm3_unfiltered"] = "Black Carbon (unfiltered) ng/m³";
    COLUMN_ALIASES["BCngm3"] = "Black Carbon ng/m³";
    if (headers.includes("BCngm3_ona")) COLUMN_ALIASES["BCngm3_ona"] = "Black Carbon ONA µg/m³";
  }
  if (hasUgUnits) {
    COLUMN_ALIASES["BC_rolling_avg_of_6"] = "BC Rolling Avg (6) µg/m³";
    COLUMN_ALIASES["BC_rolling_avg_of_12"] = "BC Rolling Avg (12) µg/m³";
  } else if (hasNgUnits) {
    COLUMN_ALIASES["BC_rolling_avg_of_6"] = "BC Rolling Avg (6) ng/m³";
    COLUMN_ALIASES["BC_rolling_avg_of_12"] = "BC Rolling Avg (12) ng/m³";
  }
}

function refreshFileList() {
  if (window.logFiles?.length) {
    updateLogSelectDropdown(window.logFiles, window.current_file);
    return Promise.resolve();
  } else {
    return fetch('index.php?action=get_log_files')
      .then(response => response.json())
      .then(files => {
        const filteredFiles = Array.isArray(files) ? files.filter(file => CSV_PATTERN_REGEX.test(file)) : [];
        window.logFiles = filteredFiles;
        updateLogSelectDropdown(filteredFiles, window.current_file);
      })
      .catch(err => console.error('Error refreshing log files:', err));
  }
}

const formatLogNameForDisplay = filename => {
  const match = filename.match(/^(\d{2})-(\d{2})-(\d{2})_(\d{6})\.csv$/);
  if (!match) return filename;
  const [_, day, month, year, timeStr] = match;
  const time = timeStr.replace(/(\d{2})(\d{2})(\d{2})/, '$1:$2:$3');
  return `${day}-${month}-${year} ${time}`;
};

const sortLogFiles = files => files.sort((a, b) => {
  const dateA = a.replace('.csv', ''), dateB = b.replace('.csv', '');
  return dateB.localeCompare(dateA);
});

function updateLogSelectDropdown(files, selectedFile) {
  const selectLogs = document.getElementById("logs_select");
  if (!selectLogs) return;
  const wasFocused = document.activeElement === selectLogs;
  let newOptionsHTML = '';
  const sortedFiles = sortLogFiles(files.slice());

  const mostRecentFile = getMostRecentLogFile();

  Promise.all(sortedFiles.map(file =>
    fetch(logPath + file)
    .then(response => response.text())
    .then(content => {
      const lines = content.trim().split('\n').filter(line => line.trim().length > 0);
      return {file, lineCount: lines.length};
    })
    .catch(() => ({file, lineCount: 0}))
  )).then(results => {
    const validFiles = sortLogFiles(results.filter(item => {
      return item.file === mostRecentFile || item.lineCount > 1;
    }).map(item => item.file));

    if (validFiles.length > 0) {
      Promise.all(validFiles.map(async file => {
        const displayName = formatLogNameForDisplay(file);
        let duration = '', shouldHide = false;
        if (typeof window.getLogDuration === 'function') {
          try {
            duration = await window.getLogDuration(file);
            shouldHide = duration.includes('(<1m)');
          } catch (error) { duration = ''; }
        }
        return {file, displayName: displayName + duration, isSelected: file === selectedFile, shouldHide};
      })).then(fileData => {
        const fileToSelect = selectedFile || mostRecentFile;
        fileData.filter(item => item.file === mostRecentFile || !item.shouldHide).forEach(item => {
          const selectedAttr = item.file === fileToSelect ? 'selected' : '';
          newOptionsHTML += `<option value="${item.file}" ${selectedAttr}>${item.displayName}</option>`;
        });
        newOptionsHTML += `<option value="combine_logs" ${fileToSelect === 'combine_logs' ? 'selected' : ''}>Combine Logs</option>`;
        selectLogs.innerHTML = newOptionsHTML;
        selectLogs.value = fileToSelect;
        window.current_file = fileToSelect;
        if (wasFocused) selectLogs.focus();
        if (selectLogs.value !== current_file) handleLogSelectChange.call(selectLogs);
      });
    } else {
      newOptionsHTML += `<option value="combine_logs" ${selectedFile === 'combine_logs' ? 'selected' : ''}>Combine Logs</option>`;
      selectLogs.innerHTML = newOptionsHTML;
      if (wasFocused) selectLogs.focus();
      data = [];
      render();
    }
  });
}

const filterColumns = columns => columns && Array.isArray(columns) ? columns.filter(column => !EXCLUDED_COLUMNS.includes(column)) : [];

function initializeColumnData() {
    window.yColumn = '', window.yColumn2 = '', window.yColumn3 = '';
    combineLogs.columns = [], data.columns = [];
    let storedState = localStorage.getItem('y2AxisHidden');
    if (storedState === null) {
        isHidden = !window.is_ebcMeter;
        localStorage.setItem('y2AxisHidden', isHidden.toString());
    } else {
        isHidden = storedState === 'true';
    }
    const hideButton = document.getElementById("hide-y-menu2");
    if (hideButton) hideButton.innerHTML = isHidden ? 'Show Second Graph' : 'Hide Second Graph';

    let storedState3 = localStorage.getItem('y3AxisHidden');
    if (storedState3 === null) {
        isHidden3 = true; // Default to hidden
        localStorage.setItem('y3AxisHidden', isHidden3.toString());
    } else {
        isHidden3 = storedState3 === 'true';
    }
    const hideButton3 = document.getElementById("hide-y-menu3");
    if (hideButton3) hideButton3.innerHTML = isHidden3 ? 'Show Third Graph' : 'Hide Third Graph';
}

function initializeAll() {
  initializeEventListeners();
  refreshFileList().then(() => {}).catch(err => console.error('Error during initial loading:', err));
}

function initializeEventListeners() {
  const selectLogs = document.getElementById("logs_select");
  if (selectLogs) {
    selectLogs.removeEventListener("change", handleLogSelectChange);
    selectLogs.addEventListener("change", handleLogSelectChange);

    if (yMenuDom) yMenuDom.addEventListener("change", function() { yOptionClicked(this.value); });
    if (yMenuDom2) yMenuDom2.addEventListener("change", function() { yOptionClicked2(this.value); });
    if (yMenuDom3) yMenuDom3.addEventListener("change", function() { yOptionClicked3(this.value); });
    document.getElementById("hide-y-menu2")?.addEventListener("click", function() { toggleYMenu2(); });
    document.getElementById("hide-y-menu3")?.addEventListener("click", function() { toggleYMenu3(); });
  }
const applyScaleBtn = document.getElementById("applyScaleChanges");
if (applyScaleBtn) {
    applyScaleBtn.addEventListener("click", () => {
        y1MinIsAuto = document.getElementById('y1-min-auto').checked;
        y1MaxIsAuto = document.getElementById('y1-max-auto').checked;
        y2MinIsAuto = document.getElementById('y2-min-auto').checked;
        y2MaxIsAuto = document.getElementById('y2-max-auto').checked;
        y3MinIsAuto = document.getElementById('y3-min-auto').checked;
        y3MaxIsAuto = document.getElementById('y3-max-auto').checked;

        localStorage.setItem('y1_min_is_auto', y1MinIsAuto);
        localStorage.setItem('y1_max_is_auto', y1MaxIsAuto);
        localStorage.setItem('y2_min_is_auto', y2MinIsAuto);
        localStorage.setItem('y2_max_is_auto', y2MaxIsAuto);
        localStorage.setItem('y3_min_is_auto', y3MinIsAuto);
        localStorage.setItem('y3_max_is_auto', y3MaxIsAuto);

        yMin = y1MinIsAuto ? '' : yMinDoc.value;
        yMax = y1MaxIsAuto ? '' : yMaxDoc.value;
        yMin2Inputted = y2MinIsAuto ? '' : yMin2Doc.value;
        yMax2Inputted = y2MaxIsAuto ? '' : yMax2Doc.value;
        yMin3Inputted = y3MinIsAuto ? '' : yMin3Doc.value;
        yMax3Inputted = y3MaxIsAuto ? '' : yMax3Doc.value;


        initialYDomain = null;
        initialY2Domain = null;
        initialY3Domain = null;

        render();
        $('#scaleModal').modal('hide');
    });
}
    const controls = [
        { chk: 'y1-min-auto', input: 'y-menu-min', autoVar: 'y1MinIsAuto' },
        { chk: 'y1-max-auto', input: 'y-menu-max', autoVar: 'y1MaxIsAuto' },
        { chk: 'y2-min-auto', input: 'y-menu2-min', autoVar: 'y2MinIsAuto' },
        { chk: 'y2-max-auto', input: 'y-menu2-max', autoVar: 'y2MaxIsAuto' },
        { chk: 'y3-min-auto', input: 'y-menu3-min', autoVar: 'y3MinIsAuto' },
        { chk: 'y3-max-auto', input: 'y-menu3-max', autoVar: 'y3MaxIsAuto' }
    ];

    controls.forEach(control => {
        const checkbox = document.getElementById(control.chk);
        const inputField = document.getElementById(control.input);
        if (checkbox && inputField) {
            checkbox.addEventListener('change', (e) => {
                const isChecked = e.target.checked;
                inputField.disabled = isChecked;
                window[control.autoVar] = isChecked; // Update global variable
            });
        }
    });
       $('#scaleModal').on('show.bs.modal', function () {
        updateScaleModalValues();
    })
      const resetBtn = document.getElementById("resetPeakBtn");
    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            const currentPeakText = document.getElementById('peak-value').textContent;
            const currentPeakValue = parseFloat(currentPeakText);
            
            if (!isNaN(currentPeakValue)) {
                resetPeakThreshold = currentPeakValue;
            }
            
            document.getElementById('peak-value').innerHTML = '-';
            resetBtn.style.display = 'none';
        });
    }     
  if (resetZoom) {
    resetZoom.removeEventListener("click", handleResetZoom);
    resetZoom.addEventListener("click", handleResetZoom);
  }
}

function handleResetZoom() {
  if (!data || !data.length) return;
  initialXDomain = null;
  initialYDomain = null;
  initialY2Domain = null;
  initialY3Domain = null;
  render();
}

function initializeSliders() {
  const medianFilterSlider1 = new Slider("#medianFilter1", {tooltip: 'hide', min: 2, max: 10, step: 1, value: Math.max(2, medianFilterKernel1)});
  document.getElementById("medianFilterValue1").textContent = Math.max(2, medianFilterKernel1);
  medianFilterSlider1.on("slide", sliderValue => {
    document.getElementById("medianFilterValue1").textContent = sliderValue;
    medianFilterKernel1 = sliderValue;
    localStorage.setItem('medianFilterKernel1', sliderValue);
    render();
  });
  medianFilterSlider1.on("change", event => {
    document.getElementById("medianFilterValue1").textContent = event.newValue;
    medianFilterKernel1 = event.newValue;
    localStorage.setItem('medianFilterKernel1', event.newValue);
    render();
  });

  const medianFilterSlider2 = new Slider("#medianFilter2", {tooltip: 'hide', min: 2, max: 10, step: 1, value: Math.max(2, medianFilterKernel2)});
  document.getElementById("medianFilterValue2").textContent = Math.max(2, medianFilterKernel2);
  medianFilterSlider2.on("slide", sliderValue => {
    document.getElementById("medianFilterValue2").textContent = sliderValue;
    medianFilterKernel2 = sliderValue;
    localStorage.setItem('medianFilterKernel2', sliderValue);
    render();
  });
  medianFilterSlider2.on("change", event => {
    document.getElementById("medianFilterValue2").textContent = event.newValue;
    medianFilterKernel2 = event.newValue;
    localStorage.setItem('medianFilterKernel2', event.newValue);
    render();
  });

  const medianFilterSlider3 = new Slider("#medianFilter3", {tooltip: 'hide', min: 2, max: 10, step: 1, value: Math.max(2, medianFilterKernel3)});
  document.getElementById("medianFilterValue3").textContent = Math.max(2, medianFilterKernel3);
  medianFilterSlider3.on("slide", sliderValue => {
      document.getElementById("medianFilterValue3").textContent = sliderValue;
      medianFilterKernel3 = sliderValue;
      localStorage.setItem('medianFilterKernel3', sliderValue);
      render();
  });
  medianFilterSlider3.on("change", event => {
      document.getElementById("medianFilterValue3").textContent = event.newValue;
      medianFilterKernel3 = event.newValue;
      localStorage.setItem('medianFilterKernel3', event.newValue);
      render();
  });
}

function applyMedianFilter(values, kernelSize) {
  if (kernelSize < 2) return values;
  const filteredValues = [], halfKernel = Math.floor(kernelSize / 2);
  for (let i = 0; i < values.length; i++) {
    const window = [];
    for (let j = -halfKernel; j <= halfKernel; j++) {
      if (i + j >= 0 && i + j < values.length && values[i + j] !== null && values[i + j] !== undefined) {
        window.push(values[i + j]);
      }
    }
    if (window.length > 0) {
      window.sort((a, b) => a - b);
      filteredValues.push(window[Math.floor(window.length / 2)]);
    } else filteredValues.push(null);
  }
  return filteredValues;
}

function handleLogSelectChange() {
  window.current_file = this.value;
  if (updateCurrentLogs) clearInterval(updateCurrentLogs), updateCurrentLogs = null;
    initialXDomain = null;
  initialYDomain = null;
  initialY2Domain = null;
  initialY3Domain = null;
  data = [], data.columns = combineLogs.columns;
if (window.current_file === "combine_logs") {
    combineAllLogs();
} else {
    let filePath = logPath + window.current_file;
    dataFile(filePath);
    updateCurrentLogsFunction();
  }
}


async function combineAllLogs() {
    if (dataObj["combine_logs"]?.length > 0) {
        data = dataObj["combine_logs"];
        render();
        updateAverageDisplay(data.length - 1);
        return;
    }

    const filesToProcess = window.logFiles || [];
    if (filesToProcess.length === 0) {
        document.getElementById("report-message").innerHTML = `<h4>No log files available to combine</h4>`;
        data = [];
        render();
        return;
    }
    
    const modal = bootbox.dialog({
        title: 'Combining Logs...',
        message: `
            <p class="text-center" id="combine-progress-text">Initializing...</p>
            <div class="progress">
                <div id="combine-progress-bar" class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: 0%;"></div>
            </div>`,
        closeButton: false
    });

    const updateProgress = (index, total) => {
        const percent = Math.round((index / total) * 100);
        modal.find('#combine-progress-text').text(`Processing file ${index} of ${total}...`);
        modal.find('#combine-progress-bar').css('width', percent + '%');
    };

    let combinedData = [];
    let headers = null;

    for (let i = 0; i < filesToProcess.length; i++) {
        const file = filesToProcess[i];
        updateProgress(i + 1, filesToProcess.length);
        
        try {
            const rawData = await d3.dsv(';', logPath + file);
            if (!rawData || rawData.length === 0) continue;

            if (!headers) headers = rawData.columns;

            const parsedData = rawData.map(d => {
                    d.bcmTime = parseTime(d.bcmDate + ' ' + d.bcmTime);
                    Object.keys(d).forEach(column => {
                        if (column !== 'bcmDate' && column !== 'bcmTime') {
                            d[column] = isNaN(+d[column]) ? d[column] : +d[column];
                        }
                    });
                    return d;
                }).filter(d => d.bcmTime);

            combinedData.push(...parsedData);
        } catch (error) {
            console.error(`Failed to load or process ${file}:`, error);
        }
    }
    
    modal.find('#combine-progress-text').text('Finalizing...');
    modal.find('#combine-progress-bar').css('width', '100%');

    if (combinedData.length > 0) {
        combinedData.sort((a, b) => a.bcmTime - b.bcmTime);
        data = combinedData;
        data.columns = filterColumns(headers || []);
        dataObj["combine_logs"] = data;
    } else {
        data = [];
    }

    setTimeout(() => {
        modal.modal('hide');
        render();
        updateAverageDisplay(data.length - 1);
    }, 500);
}


function updateAverageDisplay(len) {
    console.log(`Calculating averages for log: ${window.current_file || 'N/A'}`);

    const container = document.getElementById("averages-container");
    const message = document.getElementById("report-message");
    const dynamicAvgValueEl = document.getElementById("dynamic-avg-value");
    const avgAllValueEl = document.getElementById("avgAll-value");
    const peakValueEl = document.getElementById("peak-value");

    const allBCColumns = data.columns ? data.columns.filter(c => c.toLowerCase().includes('bc')) : [];
    if (!data?.length || allBCColumns.length === 0) {
        if(container) container.style.display = 'none';
        if(message) message.style.display = 'block';
        message.innerHTML = `<h4>No Black Carbon data available to calculate averages.</h4>`;
        return;
    }

    // --- Column and Unit Determination ---
    const preferredOrder = window.is_ebcMeter ?
        ["BCugm3_unfiltered", "BCugm3_unfiltered_880nm", "BCugm3_880nm", "BCngm3_880nm", "BCngm3"] :
        ["BCngm3", "BCugm3", "BCngm3_880nm", "BCugm3_880nm"];
    const sourceColumn = preferredOrder.find(col => allBCColumns.includes(col)) || allBCColumns[0];

    if (!sourceColumn) {
        if(container) container.style.display = 'none';
        return;
    }
    const unit = sourceColumn.toLowerCase().includes("ugm3") ? "µg/m<sup>3</sup>" : "ng/m<sup>3</sup>";

    if(container) container.style.display = 'grid';
    if(message) message.style.display = 'none';

    // --- Apply Median Filter if applicable ---
    let activeKernelSize = 0;
    if (sourceColumn === yColumn) {
        activeKernelSize = medianFilterKernel1;
    } else if (sourceColumn === yColumn2) {
        activeKernelSize = medianFilterKernel2;
    } else if (sourceColumn === yColumn3) {
        activeKernelSize = medianFilterKernel3;
    }

    let dataForCalculations = data.map(d => ({ ...d }));

    if (activeKernelSize >= 2) {
        const valuesToFilter = data.map(d => +d[sourceColumn]);
        const filteredValues = applyMedianFilter(valuesToFilter, activeKernelSize);
        dataForCalculations.forEach((d, i) => {
            d[sourceColumn] = filteredValues[i];
        });
    }

    // ALL SUBSEQUENT CALCULATIONS USE 'dataForCalculations'
    
    // --- Dynamic Average Calculation ---
    const targetDurationSeconds = window.is_ebcMeter ? 300 : 3600;
    const timeWindowMinutes = targetDurationSeconds / 60;
    document.getElementById("dynamic-avg-label").textContent = `Average (Last ~${timeWindowMinutes} Min)`;
    let numSamplesToAverage = 0;
    if (dataForCalculations.length > 1) {
        const lastPointTime = dataForCalculations[dataForCalculations.length - 1].bcmTime;
        const secondLastPointTime = dataForCalculations[dataForCalculations.length - 2].bcmTime;
        if (lastPointTime instanceof Date && secondLastPointTime instanceof Date && !isNaN(lastPointTime) && !isNaN(secondLastPointTime)) {
            let timeDiffSeconds = (lastPointTime.getTime() - secondLastPointTime.getTime()) / 1000;
            if (timeDiffSeconds <= 0 && window.configSampleTime > 0) timeDiffSeconds = window.configSampleTime;
            if (timeDiffSeconds > 0) numSamplesToAverage = Math.round(targetDurationSeconds / timeDiffSeconds);
        }
    }
    numSamplesToAverage = Math.min(numSamplesToAverage, dataForCalculations.length);
    if (numSamplesToAverage > 1) {
        const samplesForAvg = dataForCalculations.slice(-numSamplesToAverage);
        const values = samplesForAvg.map(d => +d[sourceColumn]).filter(val => !isNaN(val));
        if (values.length > 1) {
            const dynamicAvg = Math.round(d3.mean(values));
            dynamicAvgValueEl.innerHTML = (dynamicAvg >= 0) ? `${dynamicAvg} ${unit}` : `<small class="text-muted">Below Zero</small>`;
        } else {
             dynamicAvgValueEl.innerHTML = `<small class="text-muted">N/A</small>`;
        }
    } else {
        dynamicAvgValueEl.innerHTML = `<small class="text-muted">Calculating...</small>`;
    }
    
    // --- Total Average Calculation ---
    const allValues = dataForCalculations.map(d => +d[sourceColumn]).filter(val => !isNaN(val));
    const avgAll = allValues.length > 0 ? Math.round(d3.mean(allValues)) : 0;
    avgAllValueEl.innerHTML = (avgAll >= 0) ? `${avgAll} ${unit}` : `<small class="text-muted">Below Zero</small>`;

    // --- Simplified Peak Calculation & Display ---
    const peakDataPoint = d3.greatest(dataForCalculations, d => +d[sourceColumn]);

    if (peakDataPoint) {
        const highestVal = +peakDataPoint[sourceColumn];
        if (!isNaN(highestVal)) {
            const bcmTimeRaw = peakDataPoint.bcmTimeRaw;
            let highestDate = '', highestTime = '';

            if (bcmTimeRaw) {
                const timeParts = bcmTimeRaw.split(' ');
                if (timeParts.length >= 2) {
                    const dateParts = timeParts[0].split('-');
                    if (dateParts.length >= 2) highestDate = dateParts[0] + '.' + dateParts[1];
                    const timeComponents = timeParts[1].split(':');
                    if (timeComponents.length >= 2) highestTime = timeComponents[0] + ':' + timeComponents[1];
                }
            }
            peakValueEl.innerHTML = `${Math.round(highestVal)} ${unit} <small>${highestDate} ${highestTime}</small>`;
        } else {
            peakValueEl.innerHTML = '-';
        }
    } else {
        peakValueEl.innerHTML = '-';
    }
}

const findBCColumn = () => {
  if (!data || !Array.isArray(data) || !data.length || !data.columns) return null;

  const preferredColumns = window.is_ebcMeter
    ? ["BCugm3_unfiltered_880nm", "BCugm3_unfiltered","BCugm3"]
    : ["BCngm3", "BCugm3_unfiltered"];

  const foundColumn = preferredColumns.find(col => data.columns.includes(col));

  if (foundColumn) {
    return foundColumn;
  }

  return data.columns.find(col => col.toLowerCase().includes('bc')) || null;
};

function toggleYMenu2() {
  isHidden = !isHidden;
  localStorage.setItem('y2AxisHidden', isHidden);
  d3.select('.y-axis2').style("opacity", Number(!isHidden));
  d3.select('.line-chart2').style("opacity", Number(!isHidden));
  const button = document.getElementById("hide-y-menu2");
  if (button) button.innerHTML = isHidden ? 'Show Second Graph' : 'Hide Second Graph';
  if (yMin2Doc && yMax2Doc) {
    yMin2Doc.style.opacity = isHidden ? 0 : 1;
    yMax2Doc.style.opacity = isHidden ? 0 : 1;
  }
  render();
}

function toggleYMenu3() {
    isHidden3 = !isHidden3;
    localStorage.setItem('y3AxisHidden', isHidden3);
    d3.select('.y-axis3').style("opacity", Number(!isHidden3));
    d3.select('.line-chart3').style("opacity", Number(!isHidden3));
    const button = document.getElementById("hide-y-menu3");
    if (button) button.innerHTML = isHidden3 ? 'Show Third Graph' : 'Hide Third Graph';
    if (yMin3Doc && yMax3Doc) {
        yMin3Doc.style.opacity = isHidden3 ? 0 : 1;
        yMax3Doc.style.opacity = isHidden3 ? 0 : 1;
    }
    render();
}


function setYAxis() {
  const filteredDataForExtent = data.map(d => ({ ...d }));

  if (yColumn && medianFilterKernel1 > 0) {
    const values = filteredDataForExtent.map(d => d[yColumn]);
    filteredDataForExtent.forEach((d, i) => d[yColumn] = applyMedianFilter(values, medianFilterKernel1)[i]);
  }
  if (yColumn2 && medianFilterKernel2 > 0) {
    const values = filteredDataForExtent.map(d => d[yColumn2]);
    filteredDataForExtent.forEach((d, i) => d[yColumn2] = applyMedianFilter(values, medianFilterKernel2)[i]);
  }
  if (yColumn3 && medianFilterKernel3 > 0) {
      const values = filteredDataForExtent.map(d => d[yColumn3]);
      filteredDataForExtent.forEach((d, i) => d[yColumn3] = applyMedianFilter(values, medianFilterKernel3)[i]);
  }

  let [yDataMin, yDataMax] = d3.extent(filteredDataForExtent, yValueScale);
  let [yDataMin2, yDataMax2] = d3.extent(filteredDataForExtent, yValueScale2);
  let [yDataMin3, yDataMax3] = d3.extent(filteredDataForExtent, yValueScale3);

  if (window.is_ebcMeter && yColumn && yColumn.includes('BC')) {
    const defaultMin = -200, defaultMax = 200;
    yDataMin = Math.min(yDataMin ?? defaultMin, defaultMin);
    yDataMax = Math.max(yDataMax ?? defaultMax, defaultMax);
  }

  yRange = [
    yMin === '' ? (yDataMin ?? -100) : Number(yMin),
    yMax === '' ? (yDataMax ?? 100) : Number(yMax)
  ];
  yRange2 = [
    yMin2Inputted === '' ? (yDataMin2 ?? -100) : Number(yMin2Inputted),
    yMax2Inputted === '' ? (yDataMax2 ?? 100) : Number(yMax2Inputted)
  ];
  yRange3 = [
      yMin3Inputted === '' ? (yDataMin3 ?? -100) : Number(yMin3Inputted),
      yMax3Inputted === '' ? (yDataMax3 ?? 100) : Number(yMax3Inputted)
  ];

  if (yRange[0] > yRange[1]) [yRange[0], yRange[1]] = [yRange[1], yRange[0]];
  if (yRange2[0] > yRange2[1]) [yRange2[0], yRange2[1]] = [yRange2[1], yRange2[0]];
  if (yRange3[0] > yRange3[1]) [yRange3[0], yRange3[1]] = [yRange3[1], yRange3[0]];
}
function updateScales() {
  const now = new Date(), past = new Date(now.getTime() - 3600 * 1000);
  xScale.domain([past, now]).range([0, innerWidth]).nice();
  yScale.domain([0, 100]).range([innerHeight, 0]).nice();
  yScale2.domain([0, 100]).range([innerHeight, 0]).nice();
  yScale3.domain([0, 100]).range([innerHeight, 0]).nice();
}

function drawGrid() {
  svg.selectAll('.no-data-message, .grid-line, .grid-text, rect[stroke="lightgrey"]').remove();
  const g = svg.select('.container');

  g.append("rect").attr("x", 0).attr("y", 0).attr("width", innerWidth).attr("height", innerHeight).attr("fill", "none").attr("stroke", "lightgrey");
  const centerY = innerHeight / 2, middleX = innerWidth / 2;

  g.append("line").attr("class", "grid-line").attr("x1", 0).attr("y1", centerY).attr("x2", innerWidth).attr("y2", centerY).attr("stroke", "lightgrey");
  g.append("text").attr("class", "grid-text").attr("x", -40).attr("y", centerY).attr("dy", "0.32em").attr("text-anchor", "end").text("0");

  g.append("line").attr("class", "grid-line").attr("x1", middleX).attr("y1", 0).attr("x2", middleX).attr("y2", innerHeight).attr("stroke", "lightgrey").attr("stroke-width", 1);
  g.append("text").attr("class", "no-data-message").attr("x", middleX).attr("y", innerHeight + 25).attr("text-anchor", "middle").style("font-size", "12px").text("Nothing to show yet");
const duration = window.is_ebcMeter ? "5" : "15";
const warmupMessage = `Device warming up ~${duration} minutes before showing samples...`;

g.append("text")
    .attr("class", "no-data-message")
    .attr("x", middleX)
    .attr("y", innerHeight + 40)
    .attr("text-anchor", "middle")
    .style("font-size", "12px")
    .text(warmupMessage);
}

function createAlignedGrid(g, gEnter) {
  const numTicks = 9, alignedTicks = calculateAlignedTicks(yScale.domain(), yScale2.domain(), numTicks);
  g.selectAll('.grid-line-y, .grid-line-y2').remove();
  const gridContainer = g.select('.grid-container').empty() ? gEnter.append('g').attr('class', 'grid-container') : g.select('.grid-container');
  const gridLines = gridContainer.selectAll('.grid-line-horizontal').data(alignedTicks);
  gridLines.enter().append('line').attr('class', 'grid-line-horizontal').merge(gridLines).attr('x1', 0).attr('x2', innerWidth).attr('y1', d => yScale(d.y1)).attr('y2', d => yScale(d.y1)).attr('stroke', 'lightgrey').attr('stroke-width', 0.5).attr('stroke-dasharray', '2,2');
  gridLines.exit().remove();
}

const calculateAlignedTicks = (domain1, domain2, numTicks) => {
  const positions = [];
  for (let i = 0; i <= numTicks; i++) positions.push(i / numTicks);
  return positions.map(pos => ({
    position: pos,
    y1: domain1[0] + (domain1[1] - domain1[0]) * pos,
    y2: domain2[0] + (domain2[1] - domain2[0]) * pos
  }));
};

function setupTooltip() {
  const tooltip = svg.selectAll(".d3-tooltip").data([null]).join("g").attr("class", "d3-tooltip").style("display", "none");
  tooltip.selectAll("*").remove();

  const tooltipContainer = tooltip.append("g").attr("class", "tooltip-container");
  tooltipContainer.append("rect")
    .attr("class", "tooltip-bg")
    .attr("rx", 8)
    .attr("ry", 8)
    .attr("fill", "rgba(44, 62, 80, 0.95)")
    .attr("stroke", "rgba(255, 255, 255, 0.3)")
    .attr("stroke-width", 1.5)
    .style("filter", "drop-shadow(0 6px 16px rgba(0, 0, 0, 0.4))");

  tooltipContainer.append("text")
    .attr("class", "tooltip-text")
    .attr("font-family", "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif")
    .attr("font-size", 13)
    .attr("fill", "white")
    .attr("text-anchor", "middle");
}



function plotChart(skipTransition = false) {
    // 1. Initial Setup and Data Check
    svg.selectAll(".container, .d3-tooltip, .no-data-message").remove();
    if (!Array.isArray(data) || !data.length) {
        updateScales();
        const g = svg.selectAll('.container').data([null]).join("g").attr('class', 'container').attr("transform", `translate(${margin.left}, ${margin.top})`);
        drawGrid();
        return;
    }

    setYAxis();

    // 2. Preserve Zoom & Set Scales
    if (!initialXDomain || skipTransition) {
        initialXDomain = d3.extent(data, xValue);
        xScale.domain(initialXDomain).range([0, innerWidth]).nice();
    }
    initialYDomain = yRange;
    initialY2Domain = yRange2;
    initialY3Domain = yRange3;
    yScale.domain(initialYDomain).range([innerHeight, 0]).nice();
    yScale2.domain(initialY2Domain).range([innerHeight, 0]).nice();
    yScale3.domain(initialY3Domain).range([innerHeight, 0]).nice();

    const originalXScale = xScale.copy();
    const originalYScale = yScale.copy();
    const originalYScale2 = yScale2.copy();
    const originalYScale3 = yScale3.copy();

    // 3. Filter Data and Define Line Generators
    const filteredData = data.map(d => ({...d}));
    if (yColumn && medianFilterKernel1 > 0) {
        const values = filteredData.map(d => d[yColumn]);
        filteredData.forEach((d, i) => d[yColumn] = applyMedianFilter(values, medianFilterKernel1)[i]);
    }
    if (yColumn2 && medianFilterKernel2 > 0) {
        const values = filteredData.map(d => d[yColumn2]);
        filteredData.forEach((d, i) => d[yColumn2] = applyMedianFilter(values, medianFilterKernel2)[i]);
    }
    if (yColumn3 && medianFilterKernel3 > 0) {
        const values = filteredData.map(d => d[yColumn3]);
        filteredData.forEach((d, i) => d[yColumn3] = applyMedianFilter(values, medianFilterKernel3)[i]);
    }

    yValue = d => d[yColumn];
    yValue2 = d => d[yColumn2];
    yValue3 = d => d[yColumn3];

    const lineGenerator = d3.line().x(d => xScale(xValue(d))).y(d => yScale(yValue(d))).defined(d => d[yColumn] != null);
    const lineGenerator2 = d3.line().x(d => xScale(xValue(d))).y(d => yScale2(yValue2(d))).defined(d => d[yColumn2] != null);
    const lineGenerator3 = d3.line().x(d => xScale(xValue(d))).y(d => yScale3(yValue3(d))).defined(d => d[yColumn3] != null);

    // 4. Create SVG Groups and Static Elements
    const g = svg.selectAll('.container').data([null]).join("g").attr('class', 'container').attr("transform", `translate(${margin.left}, ${margin.top})`);
    g.selectAll(".clipPath").data([null]).join("clipPath").attr("id", "rectClipPath").append("rect").attr("width", innerWidth).attr("height", innerHeight);
    
    const xAxisG = g.selectAll('.x-axis').data([null]).join('g').attr('class', 'x-axis');
    const yAxisG = g.selectAll('.y-axis').data([null]).join('g').attr('class', 'y-axis');
    const yAxisG2 = g.selectAll('.y-axis2').data([null]).join('g').attr('class', 'y-axis2');
    const yAxisG3 = g.selectAll('.y-axis3').data([null]).join('g').attr('class', 'y-axis3');

    g.selectAll('.x-axis-label').data([null]).join("text").attr('class', 'x-axis-label').attr("y", innerHeight + 50).attr("x", innerWidth / 2).attr("text-anchor", "middle").text(xLabel);
    g.selectAll('.y-axis-label').data([null]).join("text").attr('class', 'y-axis-label').attr("y", -70).attr("x", -innerHeight / 2).attr("text-anchor", "middle").attr("transform", `rotate(-90)`).text(yLabel);
    g.selectAll('.y-axis-label2').data([null]).join("text").attr('class', 'y-axis-label2').attr("y", innerWidth + 70).attr("x", -innerHeight / 2).attr("text-anchor", "middle").attr("transform", `rotate(-90)`).text(yLabel2);
    g.selectAll('.y-axis-label3').data([null]).join("text").attr('class', 'y-axis-label3').attr("y", innerWidth + 130).attr("x", -innerHeight / 2).attr("text-anchor", "middle").attr("transform", `rotate(-90)`).text(yLabel3);

    // This function will draw/redraw axes, grid, and data lines
    function redraw() {
        const y1Ticks = yScale.ticks(9); 
        g.selectAll('.grid-line-horizontal').remove();
        g.insert('g', ':first-child').attr('class', 'grid').selectAll('.grid-line-horizontal').data(y1Ticks).join('line')
            .attr('class', 'grid-line-horizontal').attr('x1', 0).attr('x2', innerWidth).attr('y1', d => yScale(d)).attr('y2', d => yScale(d))
            .attr('stroke', d => (Math.abs(d) < 1e-9 ? 'darkgrey' : '#e0e0e0')).attr('stroke-width', d => (Math.abs(d) < 1e-9 ? 1 : 0.5));

        yAxisG.call(d3.axisLeft(yScale).tickValues(y1Ticks).tickSize(0).tickPadding(8));
        yAxisG2.attr("transform", `translate(${innerWidth}, 0)`).call(d3.axisRight(yScale2).ticks(9).tickSize(0).tickPadding(8));
        yAxisG3.attr("transform", `translate(${innerWidth + 70}, 0)`).call(d3.axisRight(yScale3).ticks(9).tickSize(0).tickPadding(8));
        
        const timeFormat = d3.timeFormat("%H:%M:%S");
        xAxisG.attr("transform", `translate(0, ${innerHeight})`).call(d3.axisBottom(xScale).tickSize(-innerHeight).tickPadding(15).tickFormat(timeFormat));
        g.selectAll(".domain").remove();
        
        g.select('.line-chart').datum(filteredData).attr('d', lineGenerator);
        g.select('.line-chart2').datum(isHidden ? [] : filteredData).attr('d', lineGenerator2);
        g.select('.line-chart3').datum(isHidden3 ? [] : filteredData).attr('d', lineGenerator3);
    }

    // 5. Create Path Elements and Perform Initial Draw
    g.selectAll('.line-chart').data([null]).join("path").attr('class', 'line-chart').attr('fill', 'none').attr('stroke', '#1f77b4').attr('stroke-width', 2).attr("clip-path", "url(#rectClipPath)");
    g.selectAll('.line-chart2').data([null]).join("path").attr('class', 'line-chart2').attr('fill', 'none').attr('stroke', '#ff7f0e').attr('stroke-width', 2).attr("clip-path", "url(#rectClipPath)");
    g.selectAll('.line-chart3').data([null]).join("path").attr('class', 'line-chart3').attr('fill', 'none').attr('stroke', '#2ca02c').attr('stroke-width', 2).attr("clip-path", "url(#rectClipPath)");

    redraw(); // Call redraw to draw everything for the first time

    // 6. Setup Tooltip and Zoom
    g.selectAll(".hover-line").data([null]).join("line").attr("class", "hover-line").attr("stroke", "lightgrey").attr("stroke-dasharray", "4,2").attr("stroke-width", 1).attr("y1", 0).attr("y2", innerHeight).style("display", "none");
    setupTooltip();

    const zoomed = (event) => {
        const transform = event.transform;
        xScale.domain(transform.rescaleX(originalXScale).domain());
        yScale.domain(transform.rescaleY(originalYScale).domain());
        yScale2.domain(transform.rescaleY(originalYScale2).domain());
        yScale3.domain(transform.rescaleY(originalYScale3).domain());
        redraw();
    }

    const zoomBehavior = d3.zoom().scaleExtent([0.5, 20]).translateExtent([[0, 0], [innerWidth, innerHeight]]).on("zoom", zoomed);
    const zoomRect = g.selectAll(".zoom-rect").data([null]);
    zoomRect.enter().append("rect").attr("class", "zoom-rect").attr("width", innerWidth).attr("height", innerHeight)
        .style("fill", "none").style("pointer-events", "all").merge(zoomRect).call(zoomBehavior)
        .on("pointerenter pointermove", pointermoved).on("pointerleave", pointerleft);
}
const formatDateTooltip = date => d3.timeFormat("%d-%m-%Y %H:%M:%S")(date);
const formatValueTooltip = value => d3.format(".2f")(value);

function sizeTooltip(textSelection, containerSelection) {
  const textNode = textSelection.node();
  if (!textNode) return;
  const bbox = textNode.getBBox(), padding = 12;
  const width = bbox.width + (padding * 2), height = bbox.height + (padding * 2);
  textSelection.attr("transform", `translate(0, ${padding + Math.abs(bbox.y)})`);
  containerSelection.select(".tooltip-bg").attr("x", -width / 2).attr("y", 0).attr("width", width).attr("height", height);
}

function pointermoved(event) {
    if (!data || !Array.isArray(data) || !data.length) {
        d3.select(".d3-tooltip").style("display", "none");
        d3.select(".hover-line").style("display", "none");
        return;
    }

    const [absolutePointerX, absolutePointerY] = d3.pointer(event, svg.node());
    const chartRelativeX = absolutePointerX - margin.left;
    const hoveredTime = xScale.invert(chartRelativeX);
    const i = d3.bisector(d => d.bcmTime).center(data, hoveredTime);
    const d = data[i];
    if (!d) return;

    const filteredData = data.map(item => ({...item}));
    if (yColumn && medianFilterKernel1 >= 2) {
        const values = filteredData.map(item => item[yColumn]);
        const filteredValues = applyMedianFilter(values, medianFilterKernel1);
        filteredData.forEach((item, idx) => item[yColumn] = filteredValues[idx]);
    }
    if (yColumn2 && medianFilterKernel2 >= 2) {
        const values = filteredData.map(item => item[yColumn2]);
        const filteredValues = applyMedianFilter(values, medianFilterKernel2);
        filteredData.forEach((item, idx) => item[yColumn2] = filteredValues[idx]);
    }
    if (yColumn3 && medianFilterKernel3 >= 2) {
        const values = filteredData.map(item => item[yColumn3]);
        const filteredValues = applyMedianFilter(values, medianFilterKernel3);
        filteredData.forEach((item, idx) => item[yColumn3] = filteredValues[idx]);
    }


    const filteredD = filteredData[i], tooltip = d3.select(".d3-tooltip");
    tooltip.style("display", null);
    d3.select(".hover-line").attr("x1", chartRelativeX).attr("x2", chartRelativeX).style("display", null);

    const tooltipLines = [`${formatDateTooltip(d.bcmTime)}`, `${yLabel}: ${formatValueTooltip(filteredD[yColumn])}`];
    if (!isHidden && yColumn2) tooltipLines.push(`${yLabel2}: ${formatValueTooltip(filteredD[yColumn2])}`);
    if (!isHidden3 && yColumn3) tooltipLines.push(`${yLabel3}: ${formatValueTooltip(filteredD[yColumn3])}`);

    const tooltipText = tooltip.select(".tooltip-text").call(text => text.selectAll("tspan").data(tooltipLines).join("tspan").attr("x", 0).attr("y", (_, i) => `${i * 1.3}em`).attr("font-weight", (_, i) => i === 0 ? "600" : "400").attr("font-size", (_, i) => i === 0 ? "11px" : "12px").attr("fill", (_, i) => i === 0 ? "rgba(236, 240, 241, 0.9)" : "white").text(val => val));
    const tooltipContainer = tooltip.select(".tooltip-container");
    sizeTooltip(tooltipText, tooltipContainer);

    const bbox = tooltipText.node().getBBox(), tooltipWidth = bbox.width + 24, tooltipHeight = bbox.height + 24;
    let finalTooltipX = absolutePointerX, finalTooltipY = absolutePointerY - tooltipHeight - 10;

    if (finalTooltipX - (tooltipWidth / 2) < margin.left) finalTooltipX = margin.left + (tooltipWidth / 2);
    if (finalTooltipX + (tooltipWidth / 2) > width - margin.right) finalTooltipX = width - margin.right - (tooltipWidth / 2);
    if (finalTooltipY < margin.top) finalTooltipY = absolutePointerY + 20;

    tooltip.attr("transform", `translate(${finalTooltipX}, ${finalTooltipY})`);
}

const pointerleft = () => {
  d3.select(".d3-tooltip").style("display", "none");
  d3.select(".hover-line").style("display", "none");
};
function updateScaleModalValues() {
    if (data.length > 0) {
        const y1Domain = yScale.domain();
        const y2Domain = yScale2.domain();
        const y3Domain = yScale3.domain();
        const format = d3.format(".2f");

        document.getElementById('current-y1-min').textContent = format(y1Domain[0]);
        document.getElementById('current-y1-max').textContent = format(y1Domain[1]);

        const y2Rows = document.querySelectorAll('.y2-axis-row');
        y2Rows.forEach(row => row.style.display = isHidden ? 'none' : 'table-row');
        if (!isHidden) {
            document.getElementById('current-y2-min').textContent = format(y2Domain[0]);
            document.getElementById('current-y2-max').textContent = format(y2Domain[1]);
        }

        const y3Rows = document.querySelectorAll('.y3-axis-row');
        y3Rows.forEach(row => row.style.display = isHidden3 ? 'none' : 'table-row');
        if (!isHidden3) {
            document.getElementById('current-y3-min').textContent = format(y3Domain[0]);
            document.getElementById('current-y3-max').textContent = format(y3Domain[1]);
        }
    }
}


function render() {
    isHidden = localStorage.getItem('y2AxisHidden') === 'true';
    isHidden3 = localStorage.getItem('y3AxisHidden') === 'true';

    const hideButton = document.getElementById("hide-y-menu2");
    if (hideButton) hideButton.innerHTML = isHidden ? 'Show Second Graph' : 'Hide Second Graph';
    const hideButton3 = document.getElementById("hide-y-menu3");
    if (hideButton3) hideButton3.innerHTML = isHidden3 ? 'Show Third Graph' : 'Hide Third Graph';


    const y2ModalRows = document.querySelectorAll('#scaleModal .y2-axis-row');
    y2ModalRows.forEach(row => row.style.display = isHidden ? 'none' : 'table-row');
    const y3ModalRows = document.querySelectorAll('#scaleModal .y3-axis-row');
    y3ModalRows.forEach(row => row.style.display = isHidden3 ? 'none' : 'table-row');


    d3.select('.y-axis2').style("opacity", Number(!isHidden));
    d3.select('.line-chart2').style("opacity", Number(!isHidden));
    d3.select('.y-axis3').style("opacity", Number(!isHidden3));
    d3.select('.line-chart3').style("opacity", Number(!isHidden3));

    if (data.columns?.length) {
        const allAvailableColumns = filterColumns(data.columns);
        // FIX: Allow all non-excluded columns to be selected in dropdowns.
        const displayColumns = allAvailableColumns;

        if (yMenuDom) selectUpdate(displayColumns, "#y-menu", yColumn);
        if (yMenuDom2) selectUpdate(displayColumns, "#y-menu2", yColumn2);
        if (yMenuDom3) selectUpdate(displayColumns, "#y-menu3", yColumn3);

        // FIX: Improved auto-selection for a more useful default view.
        if (!yColumn || !displayColumns.includes(yColumn)) {
            const y1Order = window.is_ebcMeter
                ? ["BCugm3_880nm", "BCugm3", "BCngm3_880nm", "BCngm3"]
                : ["BCngm3_880nm", "BCngm3", "BCugm3_880nm", "BCugm3"];
            yColumn = y1Order.find(col => displayColumns.includes(col))
                || displayColumns.find(col => col.toLowerCase().startsWith('bc'))
                || displayColumns[0] || null;
        }

        if (!yColumn2 || !displayColumns.includes(yColumn2) || yColumn2 === yColumn) {
             const y2Order = ["BCngm3_520nm", "Temperature", "relativeLoad", "AAE"];
             yColumn2 = y2Order.find(col => displayColumns.includes(col) && col !== yColumn)
                || displayColumns.find(col => col !== yColumn) || '';
        }

        if (!yColumn3 || !displayColumns.includes(yColumn3) || yColumn3 === yColumn || yColumn3 === yColumn2) {
            const y3Order = ["BCngm3_370nm", "AAE", "relativeLoad", "Temperature", "bcmATN_880nm"];
            yColumn3 = y3Order.find(col => displayColumns.includes(col) && col !== yColumn && col !== yColumn2)
                || displayColumns.find(col => col !== yColumn && col !== yColumn2) || '';
        }

        if (yMenuDom) yMenuDom.value = yColumn;
        if (yMenuDom2) yMenuDom2.value = yColumn2;
        if (yMenuDom3) yMenuDom3.value = yColumn3;
    }

    if (!Array.isArray(data) || !data.length) {
        plotChart();
        return;
    }

    yValueScale = d => +d[yColumn];
    yValueScale2 = d => yColumn2 && d[yColumn2] !== undefined ? +d[yColumn2] : null;
    yValueScale3 = d => yColumn3 && d[yColumn3] !== undefined ? +d[yColumn3] : null;

    yValue = d => d[yColumn], yValue2 = d => d[yColumn2], yValue3 = d => d[yColumn3];

    yLabel = COLUMN_ALIASES[yColumn] || yColumn;
    yLabel2 = yColumn2 ? (COLUMN_ALIASES[yColumn2] || yColumn2) : '';
    yLabel3 = yColumn3 ? (COLUMN_ALIASES[yColumn3] || yColumn3) : '';

    const label1 = document.querySelector('label[for="medianFilter1"]');
    const label2 = document.querySelector('label[for="medianFilter2"]');
    const label3 = document.querySelector('label[for="medianFilter3"]');
    const span1 = document.getElementById('medianFilterValue1');
    const span2 = document.getElementById('medianFilterValue2');
    const span3 = document.getElementById('medianFilterValue3');

    if (label1 && span1 && yLabel) {
        label1.innerHTML = `Denoise ${yLabel}: <span id="medianFilterValue1">${span1.textContent}</span>`;
    }
    if (label2 && span2 && yLabel2) {
        label2.innerHTML = `Denoise ${yLabel2}: <span id="medianFilterValue2">${span2.textContent}</span>`;
    }
    if (label3 && span3 && yLabel3) {
        label3.innerHTML = `Denoise ${yLabel3}: <span id="medianFilterValue3">${span3.textContent}</span>`;
    }
    plotChart(false);
    updateAverageDisplay(data.length - 1);
}


function autoscaleAxis(axis = 'both') {
  if (axis === 'y1' || axis === 'both') {
    if (y1MinIsAuto) yMin = '';
    if (y1MaxIsAuto) yMax = '';
  }
  if (axis === 'y2' || axis === 'both') {
    if (y2MinIsAuto) yMin2Inputted = '';
    if (y2MaxIsAuto) yMax2Inputted = '';
  }
    if (axis === 'y3' || axis === 'both') {
        if (y3MinIsAuto) yMin3Inputted = '';
        if (y3MaxIsAuto) yMax3Inputted = '';
    }
}

const yOptionClicked = value => {
  yColumn = value;
  autoscaleAxis('y1');
  initialYDomain = null;
  render();
};

const yOptionClicked2 = value => {
  yColumn2 = value;
  autoscaleAxis('y2');
  initialY2Domain = null;
  render();
};

const yOptionClicked3 = value => {
    yColumn3 = value;
    autoscaleAxis('y3');
    initialY3Domain = null;
    render();
};


function dataFile(file, isCombineLogsSelected = false, callback = null) {
    const messageEl = document.getElementById("report-message");
    const containerEl = document.getElementById("averages-container");
    const isPeriodicUpdate = file === logPath + getMostRecentLogFile();

    if (!isCombineLogsSelected && !isPeriodicUpdate && messageEl) {
        if(containerEl) containerEl.style.display = 'none';
        messageEl.style.display = 'block';
        messageEl.innerHTML = "<h5>Loading data...</h5>";
    }

    const currentIsHidden = isHidden;
    const currentIsHidden3 = isHidden3;
    d3.dsv(';', file).then(rawData => {
        const validRawData = rawData.filter(d => d.bcmTime);
        if (!validRawData.length) {
            console.warn(`No valid data rows found in ${file}.`);
            data = [];
            if(messageEl) messageEl.innerHTML = "";
            render();
            if (callback) callback();
            return;
        }
        if (!rawData.columns?.length) {
            if (validRawData.length > 0) rawData.columns = Object.keys(validRawData[0]);
            else {
                console.error("No valid headers found in file and no data rows to infer from:", file);
                data = [];
                if(messageEl) messageEl.innerHTML = "";
                render();
                if (callback) callback();
                return;
            }
        }

        autoscaleAxis('both');
        initialXDomain = null;
        initialYDomain = null;
        initialY2Domain = null;
        initialY3Domain = null;

        const headers = rawData.columns;
        updateAliasesBasedOnUnits(headers);
        const filteredHeaders = filterColumns(headers);
        data.columns = filteredHeaders, combineLogs.columns = filteredHeaders;
        if (yMenuDom) selectUpdate(filteredHeaders, "#y-menu", yColumn);
        if (yMenuDom2) selectUpdate(filteredHeaders, "#y-menu2", yColumn2);
        if (yMenuDom3) selectUpdate(filteredHeaders, "#y-menu3", yColumn3);
        let newData = [], movingIndex6 = 0, movingIndex12 = 0;
        validRawData.forEach((d, i) => {
            d.bcmTimeRaw = d.bcmDate + ' ' + d.bcmTime;
            d.bcmTime = parseTime(d.bcmDate + ' ' + d.bcmTime);
            headers.forEach(column => {
                if (column !== 'bcmDate' && column !== 'bcmTime' && column !== 'bcmTimeRaw') d[column] = isNaN(+d[column]) ? d[column] : +d[column];
            });
            newData.push(d);
        });
        let processedData = newData;
        processedData.columns = filteredHeaders;
        const bcColumn = window.is_ebcMeter ? (headers.includes("BCugm3_unfiltered") ? "BCugm3_unfiltered" : (headers.includes("BCugm3") ? "BCugm3" : null)) : (headers.includes("BCngm3_unfiltered") ? "BCngm3_unfiltered" : (headers.includes("BCngm3") ? "BCngm3" : null));
        if (bcColumn) {
            processedData.forEach((d, i) => {
                const bcValue = +d[bcColumn];
                if (!isNaN(bcValue)) {
                    if (i >= 2 && i <= processedData.length - 3) {
                        const window6 = processedData.slice(i - 2, i + 4);
                        const validWindow6 = window6.map(item => +item[bcColumn]).filter(val => !isNaN(val));
                        d.BC_rolling_avg_of_6 = validWindow6.length > 0 ? d3.mean(validWindow6) : null;
                    } else d.BC_rolling_avg_of_6 = null;
                    if (i >= 5 && i <= processedData.length - 6) {
                        const window12 = processedData.slice(i - 5, i + 7);
                        const validWindow12 = window12.map(item => +item[bcColumn]).filter(val => !isNaN(val));
                        d.BC_rolling_avg_of_12 = validWindow12.length > 0 ? d3.mean(validWindow12) : null;
                    } else d.BC_rolling_avg_of_12 = null;
                } else d.BC_rolling_avg_of_6 = null, d.BC_rolling_avg_of_12 = null;
            });
            if (!processedData.columns.includes('BC_rolling_avg_of_6')) processedData.columns.push('BC_rolling_avg_of_6');
            if (!processedData.columns.includes('BC_rolling_avg_of_12')) processedData.columns.push('BC_rolling_avg_of_12');
        }
        if (!isCombineLogsSelected) {
            data = processedData;
            if (window.current_file) dataObj[window.current_file] = data;
            let len = data.length - 1;
            if (len >= 0) {
                updateAverageDisplay(len);
                if (len > 0 && headers.includes('bcmRef') && headers.includes('bcmSen')) {
                    let bcmRef = data[len].bcmRef, bcmSen = data[len].bcmSen, btn = document.getElementById("report-button");
                    const statusValueEl = document.getElementById('filterStatusValue');

                    if (bcmSen == 0 && bcmRef == 0) {
                        btn.className = "btn btn-sm btn-secondary";
                        if (statusValueEl) statusValueEl.textContent = "N/A";
                    } else {
                        const filterStatus = bcmSen / bcmRef;
                        const percentage = Math.round(filterStatus * 100);
                        if (statusValueEl) statusValueEl.textContent = percentage;

                        btn.className = "btn btn-sm " + (!window.is_ebcMeter ? (filterStatus > 0.8 ? "btn-success" : filterStatus > 0.7 ? "btn-warning" : filterStatus > 0.55 ? "btn-danger" : filterStatus > 0.45 ? "btn-secondary" : "btn-dark") : (filterStatus <= 0.1 ? "btn-dark" : filterStatus <= 0.2 ? "btn-secondary" : filterStatus <= 0.25 ? "btn-danger" : filterStatus <= 0.4 ? "btn-warning" : "btn-success"));
                    }
                }
            }
            isHidden = currentIsHidden;
            isHidden3 = currentIsHidden3;
            localStorage.setItem('y2AxisHidden', isHidden.toString());
            localStorage.setItem('y3AxisHidden', isHidden3.toString());
            if (messageEl && !messageEl.innerHTML.includes("Averages:")) messageEl.innerHTML = "";
            render();
        } else {
            if (!window.skipBackgroundLoading) {
                const fileName = file.split("/").pop();
                dataObj[fileName] = processedData;
                combineLogs = [...combineLogs, ...processedData];
                if (window.current_file === "combine_logs") {
                    data = combineLogs;
                    if (data.length > 0) updateAverageDisplay(data.length - 1);
                    if (messageEl && !messageEl.innerHTML.includes("Averages:")) messageEl.innerHTML = "";
                    render();
                }
            }
            if (callback) callback();
        }
    }).catch(error => {
        console.error(`Error during d3.dsv parsing for ${file}:`, error);
        data = [];
        if (messageEl) {
            if(containerEl) containerEl.style.display = 'none';
            messageEl.style.display = 'block';
            messageEl.innerHTML = "<h5>Error: Could not load data file.</h5>";
        }
        render();
        if (isCombineLogsSelected && callback) callback();
    });
}
function loadInitialData() {
  console.log("loadInitialData called.");
  if (!data.columns || !combineLogs.columns) initializeColumnData();
  const mostRecentFile = getMostRecentLogFile();
  if (mostRecentFile) {
    window.current_file = mostRecentFile;
    const selectLogs = document.getElementById("logs_select");
    if (selectLogs) selectLogs.value = mostRecentFile;
    dataFile(logPath + mostRecentFile);
    updateCurrentLogsFunction();
    setTimeout(() => refreshFileList(), 3000);
  } else {
    console.log("No most recent log file found in loadInitialData.");
    data = [];
    render();
  }
}

function loadAllFilesForCombine(index) {
  if (!window.logFiles || index >= window.logFiles.length) {
    if (combineLogs.length > 0) {
      combineLogs.sort((a, b) => a.bcmTime - b.bcmTime);
      dataObj["combine_logs"] = combineLogs;
    }
    if (window.mainViewFile && window.mainViewFile !== 'combine_logs') {
      const mostRecentFile = getMostRecentLogFile();
      window.current_file = mostRecentFile;
      dataFile(logPath + mostRecentFile);
    } else if (window.current_file === 'combine_logs') {
      data = combineLogs;
      render();
    }
    return;
  }
  const file = window.logFiles[index];
  dataFile(logPath + file, true, () => loadAllFilesForCombine(index + 1));
}

function serializeData() {
  var svgElement = document.getElementById("line-chart");
  if (!svgElement) {
    console.error("SVG element with ID 'line-chart' not found for serialization.");
    return null;
  }
  var png = (new XMLSerializer()).serializeToString(svgElement);
  var svgBlob = new Blob([png], {type: "image/svg+xml;charset=utf-8"});
  var svgURL = URL.createObjectURL(svgBlob);
  return {svgURL, svgBlob};
}

const saveSVG = () => {
  const serialized = serializeData();
  if (serialized) downloadFile(serialized.svgURL, "svg");
};

function savePNG() {
  const serialized = serializeData();
  if (!serialized) return;
  var dom = document.createElement("canvas"), ct = dom.getContext("2d");
  dom.width = width, dom.height = height;
  var img = new Image();
  img.onload = function() {
    ct.drawImage(img, 0, 0);
    downloadFile(dom.toDataURL('image/png'), "png");
    URL.revokeObjectURL(serialized.svgURL);
  };
  img.onerror = function() {
    console.error("Failed to load SVG image for PNG conversion.");
    URL.revokeObjectURL(serialized.svgURL);
  }
  img.src = serialized.svgURL;
}

const saveCSV = () => window.current_file === "combine_logs" ? downloadCombinedCSV() : downloadCSVFile(logPath + window.current_file, "csv");

function downloadCombinedCSV() {
  if (!data?.length) {
    console.error("No combined data to download");
    return;
  }
  const headers = data.columns || Object.keys(data[0]).filter(key => key !== 'bcmTime');
  let csvContent = headers.join(';') + '\n';
  const dataForDownload = data.map(d => ({...d}));
  if (yColumn && medianFilterKernel1 > 0) {
    const values = dataForDownload.map(d => d[yColumn]);
    const filteredValues = applyMedianFilter(values, medianFilterKernel1);
    dataForDownload.forEach((d, i) => d[yColumn] = filteredValues[i]);
  }
  if (yColumn2 && medianFilterKernel2 > 0) {
    const values = dataForDownload.map(d => d[yColumn2]);
    const filteredValues = applyMedianFilter(values, medianFilterKernel2);
    dataForDownload.forEach((d, i) => d[yColumn2] = filteredValues[i]);
  }
  if (yColumn3 && medianFilterKernel3 > 0) {
      const values = dataForDownload.map(d => d[yColumn3]);
      const filteredValues = applyMedianFilter(values, medianFilterKernel3);
      dataForDownload.forEach((d, i) => d[yColumn3] = filteredValues[i]);
  }
  dataForDownload.forEach(row => {
    const csvRow = headers.map(header => {
      if (header === 'bcmDate') return row.bcmTimeRaw ? row.bcmTimeRaw.split(' ')[0] : '';
      else if (header === 'bcmTime') return row.bcmTimeRaw ? row.bcmTimeRaw.split(' ')[1] : '';
      else {
        const value = row[header];
        if (typeof value === 'number') return String(value).replace(/\./g, ',');
        else if (Array.isArray(value)) return JSON.stringify(value);
        return value !== undefined ? value : '';
      }
    });
    csvContent += csvRow.join(';') + '\n';
  });
  const blob = new Blob([csvContent], {type: 'text/csv;charset=utf-8;'});
  const url = URL.createObjectURL(blob);
  const today = new Date();
  const date = today.getFullYear().toString() + (today.getMonth() + 1).toString().padStart(2, '0') + today.getDate().toString().padStart(2, '0');
  const time = today.getHours().toString().padStart(2, '0') + today.getMinutes().toString().padStart(2, '0') + today.getSeconds().toString().padStart(2, '0');
  const dateTime = date + '_' + time, hostName = location.hostname;
  download.href = url;
  download.download = `${hostName}_combined_logs_filtered_${dateTime}.csv`;
  download.click();
  URL.revokeObjectURL(url);
}

function downloadCSVFile(url, ext) {
  var today = new Date();
  var date = today.getFullYear().toString() + (today.getMonth() + 1).toString().padStart(2, '0') + today.getDate().toString().padStart(2, '0');
  var time = today.getHours().toString().padStart(2, '0') + today.getMinutes().toString().padStart(2, '0') + today.getSeconds().toString().padStart(2, '0');
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

function selectUpdate(options, id, selectedOption) {
  const select = d3.select(id);
  let option = select.selectAll('option').data(options);
  option.enter().append('option').merge(option).attr('value', d => d).property("selected", d => d === selectedOption).text(d => COLUMN_ALIASES[d] || d);
  option.exit().remove();
}

function updateExcludedColumns(columnsToExclude) {
  if (Array.isArray(columnsToExclude)) {
    EXCLUDED_COLUMNS.length = 0;
    columnsToExclude.forEach(col => EXCLUDED_COLUMNS.push(col));
    if (data.columns?.length) {
      const filteredColumns = filterColumns(data.columns);
      if (yMenuDom) {
        selectUpdate(filteredColumns, "#y-menu", yColumn);
        if (!filteredColumns.includes(yColumn) && filteredColumns.length > 0) yColumn = filteredColumns[0];
      }
      if (yMenuDom2) {
        selectUpdate(filteredColumns, "#y-menu2", yColumn2);
        if (!filteredColumns.includes(yColumn2) && filteredColumns.length > 0) yColumn2 = filteredColumns.length > 1 ? filteredColumns[1] : filteredColumns[0];
      }
      if (yMenuDom3) {
          selectUpdate(filteredColumns, "#y-menu3", yColumn3);
          if (!filteredColumns.includes(yColumn3) && filteredColumns.length > 0) yColumn3 = filteredColumns.length > 2 ? filteredColumns[2] : (filteredColumns.length > 1 ? filteredColumns[1] : filteredColumns[0]);
      }
      render();
    }
  }
}

window.render = render;
window.saveSVG = saveSVG;
window.savePNG = savePNG;
window.saveCSV = saveCSV;
window.updateExcludedColumns = updateExcludedColumns;