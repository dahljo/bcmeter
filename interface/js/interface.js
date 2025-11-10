// interface.js
document.addEventListener('DOMContentLoaded', () => {
  let isDirty = false;
  let hasShownWarningModal = false;
  let lastErrorTimestamp = 0;
  let configSampleTime = 300;
  const tabsConfig = [{
    tabId: 'session-tab',
    configType: 'session'
  }, {
    tabId: 'device-tab',
    configType: 'device'
  }, {
    tabId: 'administration-tab',
    configType: 'administration'
  }, {
    tabId: 'email-tab',
    configType: 'email'
  }];
  initInterface();
  fetchStatus();

  let statusIntervalId = setInterval(fetchStatus, 5000);

  function updateStatusInterval() {
    const statusInterval = Math.max(5000, Math.min(configSampleTime * 1000, 60000));
    if (statusIntervalId) {
      clearInterval(statusIntervalId);
    }
    statusIntervalId = setInterval(fetchStatus, statusInterval);
  }

  function initInterface() {
    setupDeviceControlListeners();
    setupTabSwitching();
    setupWifiControls();
    setupModalEvents();
    loadSampleTimeConfig();
  }

  function loadSampleTimeConfig() {
    fetch(`${getBaseUrl()}/load-config`)
      .then(response => response.json())
      .then(data => {
        if (data.sample_time && data.sample_time.value) {
          configSampleTime = Number(data.sample_time.value);
          window.configSampleTime = configSampleTime;
          updateStatusInterval();
          const configEvent = new CustomEvent('bcmeter-config-loaded', {
            detail: {
              sampleTime: configSampleTime
            }
          });
          document.dispatchEvent(configEvent);
        }
      })
      .catch(error => console.error('Failed to load sample time configuration:', error));
  }

  async function getLogDuration(filename) {
    try {
      const response = await fetch(`../../logs/${filename}`);
      const text = await response.text();
      const lines = text.trim().split('\n').filter(line => line.trim());

      if (lines.length < 2) return '';

      const firstDataLine = lines[1];
      const lastDataLine = lines[lines.length - 1];

      const firstCols = firstDataLine.split(';');
      const lastCols = lastDataLine.split(';');

      if (firstCols.length < 2 || lastCols.length < 2) return '';

      const startDate = firstCols[0] + ' ' + firstCols[1];
      const endDate = lastCols[0] + ' ' + lastCols[1];

      const start = new Date(startDate.replace(/(\d{2})-(\d{2})-(\d{2})/, '20$3-$2-$1'));
      const end = new Date(endDate.replace(/(\d{2})-(\d{2})-(\d{2})/, '20$3-$2-$1'));

      if (isNaN(start.getTime()) || isNaN(end.getTime())) return '';

      const diffMs = end - start;
      const hours = Math.floor(diffMs / (1000 * 60 * 60));
      const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));

      if (hours > 0) {
        return ` (${hours}h ${minutes}m)`;
      } else if (minutes > 0) {
        return ` (${minutes}m)`;
      } else {
        return ' (<1m)';
      }
    } catch (error) {
      return '';
    }
  }

  function setupDeviceControlListeners() {
    $('#bcMeter_reboot').click(confirmReboot);
    $('#bcMeter_stop').click(confirmStop);
    $('#bcMeter_debug').click(confirmDebugMode);
    $('#force_wifi').click(resetWifi);
    $('#bcMeter_calibration').click(confirmCalibration);
    $('#bcMeter_update, #bcMeter_update2').click(confirmUpdate);
    $('#saveGraph').click(confirmSaveGraph);
    $('#startNewLog').click(confirmStartNewLog);
    const optionsButton = document.querySelector('[data-target="#pills-devicecontrol"]');
    if (optionsButton) {
      optionsButton.addEventListener('click', function() {
        const target = document.querySelector(this.getAttribute('data-target'));
        const isCurrentlyHidden = target.style.display === "none" || target.style.display === "";
        target.style.display = isCurrentlyHidden ? "block" : "none";
        if (isCurrentlyHidden) {
          setTimeout(() => {
            target.scrollIntoView({ behavior: 'smooth', block: 'end' });
          }, 0);
        }
      });
    }
    $(".toggle-password").click(function() {
      $(this).find('i').toggleClass('fa-eye fa-eye-slash');
      const input = $("#pass_log_id");
      input.attr("type", input.attr("type") === "password" ? "text" : "password");
    });
    $(".js-edit-password").click(function() {
      $('.wifi-pwd-field-exist').hide();
      $('.wifi-pwd-field').show();
    });
$('#saveWifiSettings').click(function(e) {
    e.preventDefault();
    const ssid = $('#js-wifi-dropdown').val();
    let finalSsid = ssid === 'custom-network-selection' ? $('#custom_ssid').val() : ssid;
    const password = $('#pass_log_id').val();

    const postData = {
        conn_submit: true,
        wifi_ssid: finalSsid,
        custom_wifi_name: (ssid === 'custom-network-selection') ? finalSsid : '',
        wifi_pwd: password
    };

    $.ajax({
        type: 'POST',
        url: 'index.php',
        data: postData,
        success: async function() {
            try {
                const statusResponse = await fetch('/tmp/BCMETER_WEB_STATUS');
                const statusData = await statusResponse.json();
                let hostname = statusData.hostname || 'bcMeter';
                if (!hostname.endsWith('.local')) {
                  hostname += '.local';
                }

                const progressModal = bootbox.dialog({
                  title: 'Connecting to WiFi…',
                  message: `
                      <div class="text-center">
                          <p>The device is now attempting to connect to the WiFi network.<br>
                          This may take up to 60 seconds.</p>
                          <div class="progress mt-3" style="height: 20px;">
                              <div class="progress-bar progress-bar-striped progress-bar-animated bg-info" role="progressbar" style="width: 0%"></div>
                          </div>
                          <p class="mt-3 small text-muted">
                              After connection, you can access the device at:<br>
                              <a href="http://${hostname}" target="_blank">http://${hostname}</a>
                          </p>
                      </div>`,
                  closeButton: false
                });


                const progressBar = progressModal.find('.progress-bar');
                const totalTime = 75000, step = 300;
                let elapsed = 0;
                const interval = setInterval(() => {
                    elapsed += step;
                    const percent = Math.min(100, (elapsed / totalTime) * 100);
                    progressBar.css('width', percent + '%');
                    if (percent >= 100) {
                        clearInterval(interval);
                        progressModal.modal('hide');
                        bootbox.alert(`WiFi connection attempt finished.<br>Try reconnecting to <a href="http://${hostname}" target="_blank">${hostname}</a>.`);
                        setTimeout(fetchStatus, 5000);
                    }
                }, step);
            } catch (err) {
                console.error('Failed to fetch hostname:', err);
                bootbox.alert("WiFi settings saved. The device will now attempt to connect.");
            }
        },
        error: function() {
            bootbox.alert("An error occurred while saving WiFi settings.");
        }
    });
});

  }

  function setupTabSwitching() {
    $('#configTabs a').on('click', function(e) {
      e.preventDefault();
      handleTabSwitch($(this));
    });
    tabsConfig.forEach(tab => {
      const saveButton = document.getElementById(`save${tab.configType.charAt(0).toUpperCase() + tab.configType.slice(1)}Settings`);
      if (saveButton) {
        saveButton.addEventListener("click", function(event) {
          event.preventDefault();
          saveConfigurationBasedOnTab(tab.tabId);
          $('#device-parameters').modal('hide');
        });
      }
    });
    document.addEventListener("keydown", function(event) {
      if (event.key === "Enter" || event.keyCode === 13) {
        let activeTabId = null;

        tabsConfig.forEach(tab => {
          if ($(`#${tab.tabId}`).hasClass('active')) {
            activeTabId = tab.tabId;
          }
        });

        if (activeTabId) {
          saveConfigurationBasedOnTab(activeTabId);
        }

        $('#device-parameters').modal('hide');
      }
    });
  }

  function setupWifiControls() {
    const wifiDropdown = document.getElementById('js-wifi-dropdown');
    const customNetworkInput = document.getElementById('custom-network-input');

    if (wifiDropdown && customNetworkInput) {
      wifiDropdown.addEventListener('change', function() {
        customNetworkInput.style.display = this.value === 'custom-network-selection' ? 'block' : 'none';

        if (this.value !== "custom-network-selection") {
          updatePasswordFieldVisibility(this.value);
        }
      });
      if (wifiDropdown.value === 'custom-network-selection') {
        customNetworkInput.style.display = 'block';
      }
      $('#refreshWifi').click(fetchWifiNetworks);
      fetchWifiNetworks();
    }
  }

function setupModalEvents() {
    $('#pills-devicecontrol').on('hidden.bs.collapse', function() {
      $('#statusDiv').empty();
    });
    window.addEventListener('load', function() {
      hasShownWarningModal = false;
    });
    const deleteWifiModal = document.getElementById('deleteWifiModal');
    if (deleteWifiModal) {
      deleteWifiModal.addEventListener('hidden.bs.modal', function() {
        const form = deleteWifiModal.querySelector('form');
        if (form) {
          form.reset();
        }
      });
    }

    $('#device-parameters').on('shown.bs.modal', function () {
        const activeTabPane = $(this).find('.tab-pane.active');
        const tbody = activeTabPane.find('tbody');

        // Only load data if the table body is currently empty
        if (tbody.is(':empty')) {
            const activeTabLink = $(this).find('#configTabs a.active');
            if (activeTabLink.length) {
                activateAndLoadConfig(activeTabLink);
            }
        }
    });
}

function fetchStatus() {
  fetch('/tmp/BCMETER_WEB_STATUS')
    .then(response => response.ok ? response.text() : Promise.reject('Network error'))
    .then(data => {
      try {
        const jsonData = JSON.parse(data);
        window.in_hotspot = jsonData.in_hotspot;

        updateStatus(
          jsonData.bcMeter_status,
          jsonData.hostname,
          jsonData.log_creation_time,
          jsonData.calibration_time,
          jsonData.filter_status,
          jsonData.in_hotspot
        );
      } catch (error) {
        console.error('JSON parsing error:', error);
        updateStatus(-1, "Device", null, null, null, false);
        window.in_hotspot = false;
      }
    })
    .catch(error => {
      console.error('Fetch error:', error);
      updateStatus(-1, "Device", null, null, null, false);
      window.in_hotspot = false;
    });

  fetch('../logs/log_current.csv?t=' + new Date().getTime())
    .then(response => {
      if (!response.ok) throw new Error('Network response was not ok');
      return response.text();
    })
    .then(text => {
      const lines = text.trim().split('\n');

      if (lines.length < 3) {
        throw new Error('Log file is empty or has insufficient data');
      }

      // Find the header line (skip blank lines)
      let headerLine = '';
      for (let line of lines) {
        if (line.trim() !== '') {
          headerLine = line;
          break;
        }
      }

      if (headerLine === '') {
        throw new Error('No header line found in log');
      }

      const headers = headerLine.split(';').map(h => h.trim());
      const lastLine = lines[lines.length - 1].split(';');

      const sensorIndex = headers.indexOf('bcmSen_880nm') !== -1
        ? headers.indexOf('bcmSen_880nm')
        : headers.indexOf('bcmSen');

      const refIndex = headers.indexOf('bcmRef_880nm') !== -1
        ? headers.indexOf('bcmRef_880nm')
        : headers.indexOf('bcmRef');

      if (sensorIndex === -1 || refIndex === -1) {
        console.error('Available headers:', headers);
        throw new Error('Required columns "bcmSen_880nm" or "bcmRef_880nm" not found');
      }

      const sensorVal = parseFloat(lastLine[sensorIndex]);
      const refVal = parseFloat(lastLine[refIndex]);

      if (isNaN(sensorVal) || isNaN(refVal) || refVal === 0) {
        console.error('Invalid data row:', lastLine);
        throw new Error('Invalid sensor/reference data in log');
      }

      const loading = 100 - Math.min(100, (sensorVal / refVal) * 100);

const filterButton = document.getElementById('filterStatusValue');
if (filterButton) {
  filterButton.textContent = 'Filter Loading: ' + loading.toFixed(1) + '%';

  let colorClass = 'btn-success'; 
  if (loading > 80) {
    colorClass = 'btn-dark';
  } else if (loading > 60) {
    colorClass = 'btn-danger';
  } else if (loading > 40) {
    colorClass = 'btn-warning';
  } else if (loading > 20) {
    colorClass = 'btn-secondary';
  }

  filterButton.className = 'btn btn-sm ' + colorClass;
}


    })
    .catch(error => {
      console.error('Error fetching filter status:', error);

      const filterButton = document.getElementById('filterStatusValue');
      if (filterButton) {
        filterButton.textContent = 'N/A';
        filterButton.className = 'btn btn-sm btn-secondary';
      }
    });
}


function updateStatus(status, deviceName, creationTimeString, calibrationTime, filterStatus, in_hotspot) {
  window.deviceName = deviceName;
  if (status != -1 && (!calibrationTime || (filterStatus !== null && filterStatus < 2)) &&
    (!window.is_ebcMeter || (window.is_ebcMeter && filterStatus === 0))) {
    showWarningModal(calibrationTime, filterStatus);
  }
  console.log(status, deviceName, creationTimeString, calibrationTime, filterStatus, in_hotspot)
  const statusDiv = document.getElementById('statusDiv');
  statusDiv.className = 'status-div';

  let formattedCreationTime = formatTimeString(creationTimeString);
  let formattedCalibrationTime = formatTimeString(calibrationTime);
  let statusText = getStatusText(status, deviceName, formattedCreationTime);
  const calibrationTimeDiv = document.getElementById('calibrationTime');
  const filterStatusDiv = document.getElementById('filterStatusDiv');

  if (calibrationTimeDiv) {
    calibrationTimeDiv.textContent = formattedCalibrationTime ?
      `Last calibration: ${formattedCalibrationTime}` : 'No calibration data';
  }

  if (filterStatusDiv) {
    filterStatusDiv.textContent = filterStatus !== null ?
      `Filter status: ${filterStatus}/5` : 'No filter status';
  }
  statusDiv.textContent = statusText;
  setStatusColors(statusDiv, status);
  updateHotspotWarning(in_hotspot);

  // Start auto-refresh when script is running (status 2 or 3)
  if ((status === '2' || status === '3') && typeof window.updateCurrentLogsFunction === 'function') {
    window.updateCurrentLogsFunction();
  }
}

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
      '5': `${deviceName} stopped by user`,
      '6': `${deviceName} stopped because of an error. See bcMeter.log in System Logs Tab.`
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
      '5': 'bg-warning',
      '6': 'bg-danger'
    };
    statusDiv.classList.add(statusColors[status] || '', 'text-white');
  }

  function updateHotspotWarning(in_hotspot) {
    const hotspotWarningDiv = document.getElementById('hotspotwarning');
    if (hotspotWarningDiv) {
      if (in_hotspot === true) {} else {
        hotspotWarningDiv.style.display = 'none';
      }
    }
  }

  function showError(message) {
    const now = Date.now();
    if (now - lastErrorTimestamp > 10000) {
      lastErrorTimestamp = now;
      console.error(message);
    }
  }

  function showWarningModal(calibrationTime, filterStatus) {
    if (document.getElementById('warningModal') || hasShownWarningModal) {
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
                ${!calibrationTime ? '<p>The device was not calibrated recently. Please calibrate it with new filter.</p>' : ''}
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

    document.body.insertAdjacentHTML('beforeend', modalHtml);
    $('#warningModal').modal('show');
    hasShownWarningModal = true;
  }

  function checkUndervoltageStatus() {
    $.ajax({
      url: 'includes/status.php',
      type: 'POST',
      data: {
        status: 'undervolt'
      },
      success: function(response) {
        if (response.trim() !== '') {
          $('#undervoltage-status').html(response);
        }
      },
      error: function() {
        $('#undervoltage-status').html('');
      }
    });
  }

  function ignoreWarning() {
    const warningDiv = document.getElementById('undervoltage-status');
    if (warningDiv) {
      warningDiv.style.display = 'none';
    }
  }

  function handleTabSwitch(newTab) {
    if (isDirty) {
      const confirmSwitch = confirm('You have unsaved changes. Do you want to save them before switching?'); //
      if (confirmSwitch) {
        let activeTabId = null;

        tabsConfig.forEach(tab => { //
          if ($(`#${tab.tabId}`).hasClass('active')) { //
            activeTabId = tab.tabId; //
          }
        });

        if (activeTabId) {
          saveConfiguration(getFormIdFromConfigType(tabsConfig.find(tab => tab.tabId === activeTabId).configType))
            .then(() => {
                isDirty = false; // Reset only after save is confirmed
                activateAndLoadConfig(newTab);
            })
            .catch(error => {
                console.error('Error saving configuration:', error);
                // Decide what to do on error: keep isDirty true, or proceed
                activateAndLoadConfig(newTab); // Proceed anyway, or handle error
            });
        } else {
            activateAndLoadConfig(newTab); // No active tab, proceed
        }
      } else {
        isDirty = false; // User chose NOT to save, so discard changes
        activateAndLoadConfig(newTab);
      }
    } else {
      activateAndLoadConfig(newTab);
    }
  }
  function monitorChanges(formId) {
    const form = document.getElementById(formId);
    if (form) {
      form.querySelectorAll('input, select, textarea').forEach(input => {
        input.addEventListener('change', () => {
          isDirty = true;
        });
      });
    }
  }

  function activateAndLoadConfig(tabElement) {
    const configType = tabElement.attr('aria-controls');
    loadConfig(configType);

    const formId = getFormIdFromConfigType(configType);
    monitorChanges(formId);
  }

  function getFormIdFromConfigType(configType) {
    const formIds = {
      'session': 'session-parameters-form',
      'device': 'device-parameters-form',
      'administration': 'administration-parameters-form',
      'email': 'email-parameters-form'
    };
    return formIds[configType] || '';
  }

  function getBaseUrl() {
    return window.location.protocol + '//' + window.location.hostname + ':5000';
  }

function loadConfig(configType) {
    const formId = getFormIdFromConfigType(configType);
    const tbody = document.querySelector(`#${formId} tbody`);

    if (!tbody) {
        console.error(`Could not find tbody for formId: ${formId}`);
        return;
    }

    // Show loading indicator
    tbody.innerHTML = '<tr><td colspan="2" class="text-center"><em>Loading...</em></td></tr>';

    fetch(`${getBaseUrl()}/load-config`)
        .then(response => response.json())
        .then(data => {
            tbody.innerHTML = ''; // Clear loading indicator

            Object.entries(data).forEach(([key, config]) => {
                if (config.parameter === configType) {
                    const description = config.description;
                    let valueField = '';

                    if (config.type === 'boolean') {
                        const checkedAttr = config.value ? 'checked' : '';
                        valueField = `<input name="${key}" type="checkbox" ${checkedAttr} data-toggle="toggle" data-onstyle="info" data-offstyle="light">`;
                    } else if (config.type === 'number' || config.type === 'float') {
                        valueField = `<input type="number" class="form-control" name="${key}" value="${config.value}">`;
                    } else if (config.type === 'string') {
                        valueField = `<input type="text" class="form-control" name="${key}" value="${config.value}">`;
                    } else if (config.type === 'array') {
                        valueField = `<input type="text" class="form-control array" name="${key}" value="${JSON.stringify(config.value)}">`;
                    }

                    const row = `<tr data-toggle="tooltip" data-placement="top" title="${description}">
                                <td>${description}</td>
                                <td>${valueField}</td>
                            </tr>`;
                    tbody.innerHTML += row;
                }
            });

            $('[data-toggle="toggle"]').bootstrapToggle();
            monitorChanges(formId);
        })
        .catch(error => {
            console.error('Failed to load configuration:', error);
            tbody.innerHTML = '<tr><td colspan="2" class="text-center text-danger"><em>Failed to load configuration.</em></td></tr>';
        });
}

 function saveConfiguration(configType) {
    return new Promise((resolve, reject) => { // Wrap in a Promise
      const formId = getFormIdFromConfigType(configType); //
      const form = document.getElementById(formId); //
      const updatedConfig = {}; //

      form.querySelectorAll('input[type="checkbox"], input[type="number"], input[type="text"]').forEach(input => { //
        const key = input.name; //
        let value = input.value; //

        if (input.type === 'checkbox') { //
          value = input.checked; //
        } else if (input.classList.contains('array')) { //
          try { //
            value = JSON.parse(input.value); //
          } catch (e) { //
            console.error('Failed to parse array input:', e); //
          }
        }

        if (input.type === 'number') { //
          value = value.replace(/,/g, '.'); //
        }

        const description = input.closest('tr').getAttribute('title')?.trim() || ''; //

        if (key) { //
          updatedConfig[key] = { //
            value: value, //
            description: description, //
            type: determineType(input), //
            parameter: configType //
          };
        }
      });

      function determineType(input) { //
        if (input.type === 'checkbox') { //
          return 'boolean'; //
        } else if (input.type === 'number') { //
          return 'number'; //
        } else if (input.classList.contains('array')) { //
          return 'array'; //
        } else if (input.type === 'text') { //
          return 'string'; //
        } else {
          return typeof value; //
        }
      }

      fetch(`${getBaseUrl()}/load-config`) //
        .then(response => response.json()) //
        .then(existingConfig => { //
          const mergedConfig = { ...existingConfig }; //

          Object.keys(updatedConfig).forEach(key => { //
            mergedConfig[key] = updatedConfig[key]; //
          });

          fetch(`${getBaseUrl()}/save-config`, { //
              method: 'POST', //
              headers: { //
                'Content-Type': 'application/json' //
              },
              body: JSON.stringify(mergedConfig) //
            })
            .then(response => { //
              if (!response.ok) { //
                throw new Error('Failed to save configuration'); //
              }
              console.log('Configuration saved successfully'); //
              isDirty = false; // Reset isDirty flag upon successful save
              resolve(); // Resolve the Promise
            })
            .catch(error => {
              console.error('Failed to save configuration:', error); //
              reject(error); // Reject the Promise on error
            });
        })
        .catch(error => {
          console.error('Failed to load configuration:', error); //
          reject(error); // Reject the Promise on error
        });
    }); // End of Promise
  }

  function saveConfigurationBasedOnTab(tabId) {
    const tabToConfigMap = { //
      'session-tab': 'session', //
      'device-tab': 'device', //
      'administration-tab': 'administration', //
      'email-tab': 'email'
    };

    const configType = tabToConfigMap[tabId]; //
    if (configType) { //
      saveConfiguration(configType); //
    }
  }

  function fetchWifiNetworks() {
    $('.loading-available-networks').show();

    $.getJSON('includes/wlan_list.php', function(networks) {
      window.availableNetworks = networks;
      const dropdown = $('#js-wifi-dropdown');

      dropdown.find('option:not(:first):not([value="custom-network-selection"])').remove();

      networks.forEach(network => {
        if (network !== window.currentWifiSsid) {
          dropdown.append($('<option></option>').val(network).text(network));
        }
      });

      updatePasswordFieldVisibility(window.currentWifiSsid);

      $('.loading-available-networks').hide();
    });
  }

  function updatePasswordFieldVisibility(selectedNetwork) {
    const isInRange = window.availableNetworks?.includes(selectedNetwork);
    const hasStoredPassword = window.currentWifiSsid === selectedNetwork;

    if (!isInRange || !hasStoredPassword) {
      $('.wifi-pwd-field-exist').hide();
      $('.wifi-pwd-field').show();
    } else {
      $('.wifi-pwd-field-exist').show();
      $('.wifi-pwd-field').hide();
    }
  }

  function confirmReboot(e) {
    e.preventDefault();
    bootbox.dialog({
      title: 'Reboot bcMeter?',
      message: "<p>Do you want to reboot the device?</p>",
      size: 'small',
      buttons: {
        cancel: {
          label: "No",
          className: 'btn-success'
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
  }

  function confirmStop(e) {
    e.preventDefault();
    bootbox.dialog({
      title: 'Stop logging',
      message: "<p>This will stop the current measurement. Sure?</p>",
      size: 'small',
      buttons: {
        cancel: {
          label: "No",
          className: 'btn-success'
        },
        ok: {
          label: "Yes",
          className: 'btn-danger',
          callback: function() {
            $.ajax({
              type: 'post',
              data: 'exec_stop',
              success: function(response) {}
            });
          }
        }
      }
    });
  }

  function confirmDebugMode(e) {
    e.preventDefault();
    bootbox.dialog({
      title: 'Enter debug mode?',
      message: "<p>Do you want to switch to debug mode? Device will be unresponsive for 10-20 seconds</p>",
      size: 'small',
      buttons: {
        cancel: {
          label: "No",
          className: 'btn-success'
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
  }

  function resetWifi(e) {
    e.preventDefault();
    bootbox.dialog({
      title: 'Reset Wifi?',
      message: "<p>This will trigger a manual reload of the WiFi credentials and cut your current connection. </p>",
      size: 'small',
      buttons: {
        cancel: {
          label: "No",
          className: 'btn-success'
        },
        ok: {
          label: "Yes",
          className: 'btn-danger',
          callback: function() {
            $.ajax({
              type: 'post',
              data: {
                force_wifi: true
              },
              success: function(response) {}
            });
          }
        }
      }
    });
  }

  function confirmCalibration(e) {
    e.preventDefault();
    bootbox.dialog({
      title: 'Calibrate bcMeter?',
      message: "<p>Calibrate only with new filterpaper. Avoid direct sunlight. Continue? </p>",
      size: 'medium',
      buttons: {
        cancel: {
          label: "No",
          className: 'btn-success'
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
  }

  function confirmUpdate(e) {
    e.preventDefault();
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
          fetch('/bcMeter_config.json')
            .then(response => {
              if (!response.ok) {
                throw new Error('Network response was not ok');
              }
              return response.blob();
            })
            .then(blob => {
              const downloadUrl = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = downloadUrl;
              a.download = 'bcMeter_config.json';
              document.body.appendChild(a);
              a.click();
              a.remove();
              URL.revokeObjectURL(downloadUrl);

              showUpdateDialog();
            })
            .catch(error => {
              console.error('There was a problem with the fetch operation:', error);
              alert("Failed to download the configuration file.");
            });
        } else {
          showUpdateDialog();
        }
      }
    });
  }

  function showUpdateDialog() {
    bootbox.dialog({
      title: 'Update bcMeter?',
      message: "<p>The most recent files will be downloaded. If possible, your parameters will be kept but please save them and check after the update if they are the same.</p>",
      size: 'medium',
      buttons: {
        cancel: {
          label: "No",
          className: 'btn-success'
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

  function confirmSaveGraph(e) {
    e.preventDefault();
    bootbox.dialog({
      title: 'Save graph as',
      message: "<p>Choose the type of file you want to save the current measurements as</p>",
      size: 'large',
      buttons: {
        1: {
          label: "CSV (MS Office/Google Docs)",
          className: 'btn-info',
          callback: function() {
            window.saveCSV();
          }
        },
        2: {
          label: "PNG (Web/Mail)",
          className: 'btn-info',
          callback: function() {
            window.savePNG();
          }
        },
        3: {
          label: "SVG (DTP)",
          className: 'btn-info',
          callback: function() {
            window.saveSVG();
          }
        }
      }
    });
  }


function confirmStartNewLog(e) {
    e.preventDefault();

    if ($(e.target).data('processing')) return;
    $(e.target).data('processing', true);

    const isEbcMeter = typeof window.is_ebcMeter !== 'undefined' && window.is_ebcMeter === true;
    const messageText = "<p>This will start a new log. It takes a few moments for the new chart to appear.</p>";
    
    bootbox.dialog({
        title: 'Start New Log?',
        message: messageText,
        size: 'small',
        buttons: {
            cancel: {
                label: "No",
                className: 'btn-secondary',
                callback: function() {
                    $(e.target).data('processing', false);
                }
            },
            ok: {
                label: "Yes, Start New Log",
                className: 'btn-danger',
                callback: function() {
                    // Restored original messages with the progress bar HTML structure
                    const processingModalMessage = isEbcMeter ?
                        '<div class="text-center">' +
                        '<p>It takes about 5-10 minutes for the first samples to appear.</p>' +
                        '<p>Please note that measurements will be most accurate once the device has reached a stable running temperature.</p>' +
                        '<p>For most accurate emission control, you may wait until the temperature curve flattens.</p>' +
                        '<div class="progress mt-3" style="height: 20px;">' +
                        '<div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: 0%"></div>' +
                        '</div></div>' :
                        '<div class="text-center">' +
                        '<p>It takes a few minutes for the first samples to appear.</p>' +
                        '<p>Please note that samples might be inaccurate until the device has reached running temperature.</p>' +
                        '<div class="progress mt-3" style="height: 20px;">' +
                        '<div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: 0%"></div>' +
                        '</div></div>';

                    const processingModal = bootbox.dialog({
                        title: 'Initializing New Log...',
                        message: processingModalMessage,
                        closeButton: false
                    });

                    $.ajax({
                        type: 'post',
                        url: 'index.php',
                        data: { exec_new_log: true },
                        timeout: 40000,
                        success: function() {
                            const totalWaitTime = 15000; 
                            const intervalTime = 150;
                            let elapsedTime = 0;
                            const progressBar = processingModal.find('.progress-bar');

                            const progressInterval = setInterval(function() {
                                elapsedTime += intervalTime;
                                const percentComplete = Math.min(Math.round((elapsedTime / totalWaitTime) * 100), 100);
                                progressBar.css('width', percentComplete + '%');

                                if (percentComplete >= 100) {
                                    clearInterval(progressInterval);
                                    window.location.reload();
                                }
                            }, intervalTime);
                        },
                        error: function() {
                            processingModal.modal('hide');
                            bootbox.alert('There was an error starting the new log.');
                            $(e.target).data('processing', false);
                        }
                    });
                }
            }
        }
    });
}
  function fetchAndProcessLogFile(logType, elementId) {
    fetch(`../../maintenance_logs/${logType}.log`)
      .then(response => {
        if (response.status === 404) {
          document.getElementById(elementId).innerHTML = 'Log file not found (404).';
          throw new Error('404 Not Found');
        }
        if (!response.ok) {
          document.getElementById(elementId).innerHTML = 'Error fetching log file.';
          throw new Error('Fetch error');
        }
        return response.text();
      })
      .then(data => {
        const lines = data.split('\n');
        let prevMessage = '';
        let prevTimestamp = '';
        let contentCount = 0;
        let output = '';
        lines.forEach(line => {
          const matches = line.match(/(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}),\d{3}\s+-\s+(DEBUG|ERROR): (.+)/);
          if (matches) {
            const timestamp = matches[1];
            const level = matches[2];
            const message = matches[3];
            const currentMessage = message;
            if (currentMessage === prevMessage) {
              contentCount++;
            } else {
              if (contentCount > 1) {
                output += `${prevTimestamp} ${level}: ${prevMessage} (Repeated ${contentCount} times)<br>`;
              } else if (prevMessage !== '') {
                output += `${prevTimestamp} ${level}: ${prevMessage}<br>`;
              }
              prevMessage = currentMessage;
              prevTimestamp = timestamp;
              contentCount = 1;
            }
          }
        });
        if (contentCount > 1) {
          output += `${prevTimestamp} DEBUG: ${prevMessage} (Repeated ${contentCount} times)<br>`;
        } else if (prevMessage !== '') {
          output += `${prevTimestamp} DEBUG: ${prevMessage}<br>`;
        }
        document.getElementById(elementId).innerHTML = output;
      })
      .catch(error => console.error(error));
  }

function addDeleteButtonsToLogs() {
  document.querySelectorAll('#large-files table tbody, #small-files table tbody').forEach(tableBody => {
    const rows = Array.from(tableBody.querySelectorAll('tr'));
    rows.forEach((row, index) => {
      const downloadLink = row.querySelector('td:last-child a');
      if (!downloadLink) return;
      const existingDeleteBtn = row.querySelector('.btn-danger');
      if (existingDeleteBtn) return;
      
      const fileName = downloadLink.getAttribute('href').split('/').pop();
      const dateText = row.querySelector('td:first-child').textContent;
      const deleteBtn = document.createElement('button');
      deleteBtn.type = 'button';
      deleteBtn.className = 'btn btn-danger ml-2';
      deleteBtn.innerText = 'Delete';
      
      const isNewestLog = rows.every(otherRow => {
        const otherDateText = otherRow.querySelector('td:first-child').textContent;
        return dateText >= otherDateText;
      });
      
      if (isNewestLog) {
        deleteBtn.disabled = true;
        deleteBtn.title = "Cannot delete the most recent log file";
        deleteBtn.classList.add('disabled');
      } else {
        deleteBtn.onclick = () => showDeleteConfirmation(fileName);
      }
      
      row.querySelector('td:last-child').appendChild(deleteBtn);
    });
  });
}

  function showDeleteConfirmation(fileName) {
    const modal = document.getElementById('deleteLogModal') || createDeleteModal();
    document.getElementById('delete-log-filename').textContent = fileName;
    document.getElementById('delete-log-filepath').value = fileName;
    $('#deleteLogModal').modal('show');
  }

  function createDeleteModal() {
    const modalHtml = `
    <div class="modal fade" id="deleteLogModal" tabindex="-1" role="dialog">
      <div class="modal-dialog" role="document">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Confirm Delete</h5>
            <button type="button" class="close" data-dismiss="modal" aria-label="Close">
              <span aria-hidden="true">&times;</span>
            </button>
          </div>
          <div class="modal-body">
            <p>Are you sure you want to delete the log file?</p>
            <p><strong id="delete-log-filename"></strong></p>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-dismiss="modal">Cancel</button>
            <form action="includes/status.php" method="GET">
              <input type="hidden" name="status" value="delete_log">
              <input type="hidden" id="delete-log-filepath" name="file">
              <button type="submit" class="btn btn-danger">Delete</button>
            </form>
          </div>
        </div>
      </div>
    </div>
  `;
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    return document.getElementById('deleteLogModal');
  }

  document.querySelector('button[data-target="#downloadOld"]').addEventListener('click', () => {
    setTimeout(addDeleteButtonsToLogs, 500);
  });

  document.querySelectorAll('#logTabs a[data-toggle="tab"]').forEach(tab => {
    tab.addEventListener('shown.bs.tab', addDeleteButtonsToLogs);
  });

  document.querySelector('#small-files-tab').addEventListener('shown.bs.tab', addDeleteButtonsToLogs);

  document.querySelector('button[data-target="#downloadOld"]').addEventListener('click', () => {
    setTimeout(addDeleteButtonsToLogs, 500);
  });

  function startLogFetching() {
    const logs = [{
      type: 'bcMeter',
      elementId: 'logBcMeter'
    }, {
      type: 'ap_control_loop',
      elementId: 'logApControlLoop'
    }];

   

    logs.forEach(log => {
      fetchAndProcessLogFile(log.type, log.elementId);
      setInterval(() => fetchAndProcessLogFile(log.type, log.elementId), 5000);
    });
  }

  $('#systemlogs').on('shown.bs.modal', startLogFetching);
  checkUndervoltageStatus();
  setInterval(checkUndervoltageStatus, 120000);

  window.getLogDuration = getLogDuration;
});

function syncDeviceTime() {
  const browserTime = new Date();
  const browserTimestamp = Math.floor(browserTime.getTime() / 1000);
  const formattedBrowserTime = browserTime.toLocaleString();
  if (document.getElementById("datetime_local")) {
    document.getElementById("datetime_local").innerHTML = "Current time based on your Browser: <br/>" + formattedBrowserTime;
  }
  console.log("Time Check")
  $.ajax({
    url: "includes/get_device_time.php",
    type: "get",
    cache: false,
    timeout: 3000,
    success: function(result) {
      const deviceTimestamp = parseInt(result.trim(), 10);
      const deviceTime = new Date(deviceTimestamp * 1000);
      const formattedDeviceTime = deviceTime.toLocaleString();
      const timeDifference = Math.abs(browserTimestamp - deviceTimestamp);
      updateTimeDisplays(formattedDeviceTime);
      if (window.in_hotspot && timeDifference >= 10) {
        console.log("Time difference detected:", timeDifference, "seconds. Synchronizing...");

        if (document.getElementById("datetime_note")) {
          document.getElementById("datetime_note").innerHTML = "Time difference detected. Synchronizing...";
        }
        performTimeSync(browserTimestamp, browserTime, deviceTime, timeDifference);
      } else {
        if (document.getElementById("datetime_note")) {
          document.getElementById("datetime_note").innerHTML = "Device time is correct (difference is less than 10 seconds).";
        }
        console.log("Time is synced");
      }
      if (document.getElementById('hotspotwarning')) {
        document.getElementById('hotspotwarning').classList.remove('alert-danger');
        document.getElementById('hotspotwarning').classList.add('alert');
      }
    },
    error: function(xhr, status, error) {
      handleSyncError();
    }
  });
}

function updateTimeDisplays(formattedDeviceTime) {
  if (document.getElementById("datetime_device")) {
    document.getElementById("datetime_device").innerHTML = "Current time set on your bcMeter: " + formattedDeviceTime;
  }

  if (document.getElementById("devicetime")) {
    document.getElementById("devicetime").innerHTML = "Time on bcMeter: " + formattedDeviceTime;
  }
}

function handleSyncError() {
  const deviceURL = (window.deviceName !== "" && window.deviceName !== undefined) ? "http://" + window.deviceName : "";
  if (document.getElementById("datetime_device")) {
    document.getElementById("datetime_device").innerHTML = "No connection to bcMeter<br /> Wait a minute to click <a href=\"" + deviceURL + "\">here </a> after WiFi Setup";
  }
  ["datetime_local", "set_time", "datetime_note", "devicetime"].forEach(id => {
    if (document.getElementById(id)) {
      document.getElementById(id).innerHTML = "";
    }
  });
  if (document.getElementById('hotspotwarning')) {
    document.getElementById('hotspotwarning').classList.remove('alert');
    document.getElementById('hotspotwarning').classList.add('alert-danger');
  }
  if (window.in_hotspot) {
    syncTimeManually();
  }
}

function performTimeSync(browserTimestamp, browserTime, deviceTime, timeDifference) {
  const formattedBrowserTime = browserTime.toLocaleString();
  const formattedDeviceTime = deviceTime.toLocaleString();

  $.ajax({
    url: "includes/set_device_time.php",
    type: "post",
    data: {
      timestamp: browserTimestamp,
      show_modal: 1
    },
    success: function(response) {
      if (document.getElementById("datetime_note")) {
        document.getElementById("datetime_note").innerHTML = "Time successfully synchronized!";
      }
      if (document.getElementById("datetime_device")) {
        document.getElementById("datetime_device").innerHTML = "Current time set on your bcMeter: " + formattedBrowserTime;
      }
      showTimeSyncSuccessModal(formattedBrowserTime, formattedDeviceTime, timeDifference);
    },
    error: function() {
      if (document.getElementById("datetime_note")) {
        document.getElementById("datetime_note").innerHTML = "Failed to synchronize time.";
      }
    }
  });
}

function quickSyncCheck() {
  const browserTimestamp = Math.floor(new Date().getTime() / 1000);

  $.ajax({
    url: "includes/time_check.php",
    type: "post",
    data: {
      browser_time: browserTimestamp
    },
    success: function(response) {
      if (response.needs_sync) {
        syncTimeManually();
      }
    },
    error: function() {
      syncTimeManually();
    }
  });
}

function syncTimeManually() {
  const browserTime = new Date();
  const browserTimestamp = Math.floor(browserTime.getTime() / 1000);
  const formattedBrowserTime = browserTime.toLocaleString();

  $.ajax({
    url: "includes/set_device_time.php",
    type: "post",
    data: {
      timestamp: browserTimestamp,
      show_modal: localStorage.getItem('timeModalShown') ? 0 : 1
    },
    success: function(response) {
      if (document.getElementById("datetime_note")) {
        document.getElementById("datetime_note").innerHTML = "Time successfully synchronized!";
      }

      if (document.getElementById("datetime_device")) {
        document.getElementById("datetime_device").innerHTML = "Current time set on your bcMeter: " + formattedBrowserTime;
      }
      if (response.show_modal) {
        showTimeSyncSuccessModal(formattedBrowserTime, "Unknown (unavailable in hotspot mode)", null);
        localStorage.setItem('timeModalShown', '1');
      }
    },
    error: function() {
      if (document.getElementById("datetime_note")) {
        document.getElementById("datetime_note").innerHTML = "Failed to synchronize time.";
      }
    }
  });
}

function showTimeSyncSuccessModal(browserTime, deviceTime, timeDifference) {
  if (localStorage.getItem('timeModalShown') === '1' && !sessionStorage.getItem('forceSyncModal')) {
    return;
  }
  sessionStorage.setItem('forceSyncModal', '');
  localStorage.setItem('timeModalShown', '1');
  if (!document.getElementById('timeSyncModal')) {
    const modalHTML = `
    <div class="modal fade" id="timeSyncModal" tabindex="-1" role="dialog" aria-labelledby="timeSyncModalLabel" aria-hidden="true">
        <div class="modal-dialog" role="document">
            <div class="modal-content">
                <div class="modal-header bg-success text-white">
                    <h5 class="modal-title" id="timeSyncModalLabel">Time Synchronization Successful</h5>
                    <button type="button" class="close" data-dismiss="modal" aria-label="Close">
                        <span aria-hidden="true">&times;</span>
                    </button>
                </div>
                <div class="modal-body">
                    <div class="time-sync-details">
                        <p><strong>Browser Time:</strong> <span id="browserTimeValue"></span></p>
                        <p><strong>Device Time (before sync):</strong> <span id="deviceTimeValue"></span></p>
                        <p id="timeDifferenceRow"><strong>Time Difference:</strong> <span id="timeDifferenceValue"></span></p>
                        <p class="text-success font-weight-bold">Device time has been synchronized with your browser time.</p>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-dismiss="modal">Close</button>
                </div>
            </div>
        </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', modalHTML);
  }
  setTimeout(() => {
    const browserTimeEl = document.getElementById('browserTimeValue');
    const deviceTimeEl = document.getElementById('deviceTimeValue');
    const timeDifferenceRow = document.getElementById('timeDifferenceRow');
    const timeDifferenceEl = document.getElementById('timeDifferenceValue');

    if (browserTimeEl) browserTimeEl.textContent = browserTime;
    if (deviceTimeEl) deviceTimeEl.textContent = deviceTime;

    if (timeDifferenceRow && timeDifferenceEl) {
      if (timeDifference !== null) {
        timeDifferenceEl.textContent = timeDifference + ' seconds';
        timeDifferenceRow.style.display = 'block';
      } else {
        timeDifferenceRow.style.display = 'none';
      }
    }
    $('#timeSyncModal').modal('show');
  }, 50);
}

function showTimeAlert(difference) {
  const minutes = Math.floor(difference / 60);
  const timeMessage = minutes > 0 ?
    `Device time is off by ${minutes} minutes and ${difference % 60} seconds.` :
    `Device time is off by ${difference} seconds.`;

  if (!document.getElementById('timeAlertModal')) {
    const modalHTML = `
        <div class="modal fade" id="timeAlertModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header bg-warning">
                        <h5 class="modal-title">Time Difference Detected</h5>
                        <button type="button" class="close" data-dismiss="modal">&times;</button>
                    </div>
                    <div class="modal-body">
                        <p>${timeMessage}</p>
                        <p>Inaccurate time may affect measurement timestamps and data logging.</p>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-dismiss="modal">Ignore</button>
                        <button type="button" class="btn btn-primary" onclick="syncTimeManually(); $('#timeAlertModal').modal('hide');">Sync Now</button>
                    </div>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHTML);
  } else {
    document.querySelector('#timeAlertModal .modal-body p:first-child').textContent = timeMessage;
  }

  $('#timeAlertModal').modal('show');
}

document.addEventListener('DOMContentLoaded', () => {
  $(document).on('click', '[data-toggle="modal"]', function(e) {
    const trigger = $(this);
    const parentModal = trigger.closest('.modal.show');

    if (parentModal.length) {
        e.preventDefault();
        const targetModalId = trigger.data('target');
        parentModal.one('hidden.bs.modal', () => $(targetModalId).modal('show'));
        parentModal.modal('hide');
    }
});
  setTimeout(syncDeviceTime, 2000);
  setInterval(syncDeviceTime, 600000);
});