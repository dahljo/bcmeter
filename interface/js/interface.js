/**
 * bcMeter Interface JavaScript
 * UI, modals, and system interactions for the bcMeter interface
 */

document.addEventListener('DOMContentLoaded', () => {
  // Global variables
  let isDirty = false;
  let hasShownWarningModal = false;
  let lastErrorTimestamp = 0;
  
  // Tab configuration
  const tabsConfig = [
    { tabId: 'session-tab', configType: 'session' },
    { tabId: 'device-tab', configType: 'device' },
    { tabId: 'administration-tab', configType: 'administration' },
    { tabId: 'email-tab', configType: 'email' },
    { tabId: 'compair-tab', configType: 'compair' }
  ];

  // Initialize the interface
  initInterface();
  fetchStatus();
  setInterval(fetchStatus, 5000);
  fetchTimeData();
  setInterval(fetchTimeData, 1000);

  /**
   * Initialize the interface
   */
  function initInterface() {
    // Initialize event listeners
    setupDeviceControlListeners();
    setupTabSwitching();
    setupWifiControls();
    setupModalEvents();
    
    // Initialize the initial tab
    const initialTab = $('#configTabs a.active');
    if (initialTab.length) {
      activateAndLoadConfig(initialTab);
    } else {
      activateAndLoadConfig($('#configTabs a').first());
    }
  }

  /**
   * Setup event listeners for device control buttons
   */
  function setupDeviceControlListeners() {
    // Device control buttons
    $('#bcMeter_reboot').click(confirmReboot);
    $('#bcMeter_stop').click(confirmStop);
    $('#bcMeter_debug').click(confirmDebugMode);
    $('#force_wifi').click(resetWifi);
    $('#bcMeter_calibration').click(confirmCalibration);
    $('#bcMeter_update, #bcMeter_update2').click(confirmUpdate);
    $('#saveGraph').click(confirmSaveGraph);
    $('#startNewLog').click(confirmStartNewLog);
    
    // Options button toggle
    const optionsButton = document.querySelector('[data-target="#pills-devicecontrol"]');
    if (optionsButton) {
      optionsButton.addEventListener('click', function() {
        const target = document.querySelector(this.getAttribute('data-target'));
        target.style.display = target.style.display === "none" ? "block" : "none";
      });
    }

    // Password visibility toggle
    $(".toggle-password").click(function() {
      $(this).find('i').toggleClass('fa-eye fa-eye-slash');
      const input = $("#pass_log_id");
      input.attr("type", input.attr("type") === "password" ? "text" : "password");
    });

    // Edit password button
    $(".js-edit-password").click(function() {
      $('.wifi-pwd-field-exist').hide();
      $('.wifi-pwd-field').show();
    });

    // Hide/show y-menu2
    document.getElementById("hide-y-menu2")?.addEventListener("click", function() {
      toggleYMenu2();
    });
  }

  /**
   * Setup tab switching functionality
   */
  function setupTabSwitching() {
    $('#configTabs a').on('click', function(e) {
      e.preventDefault();
      handleTabSwitch($(this));
    });

    // Handle form submissions and save actions
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

    // Handle enter key in forms
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

  /**
   * Setup WiFi control functionality
   */
  function setupWifiControls() {
    const wifiDropdown = document.getElementById('js-wifi-dropdown');
    const customNetworkInput = document.getElementById('custom-network-input');
    
    if (wifiDropdown && customNetworkInput) {
      // Show/hide custom network input based on selection
      wifiDropdown.addEventListener('change', function() {
        customNetworkInput.style.display = this.value === 'custom-network-selection' ? 'block' : 'none';
        
        if (this.value !== "custom-network-selection") {
          updatePasswordFieldVisibility(this.value);
        }
      });
      
      // If custom-network-selection is selected on page load
      if (wifiDropdown.value === 'custom-network-selection') {
        customNetworkInput.style.display = 'block';
      }
      
      // Refresh WiFi networks button
      $('#refreshWifi').click(fetchWifiNetworks);
      
      // Initial fetch of available networks
      fetchWifiNetworks();
    }
  }

  /**
   * Setup modal event handlers
   */
  function setupModalEvents() {
    // Track modal state
    $('#pills-devicecontrol').on('hidden.bs.collapse', function() {
      $('#statusDiv').empty();
    });
    
    // Reset modal state on page reload
    window.addEventListener('load', function() {
      hasShownWarningModal = false;
    });
    
    // Handle WiFi modal close
    const deleteWifiModal = document.getElementById('deleteWifiModal');
    if (deleteWifiModal) {
      deleteWifiModal.addEventListener('hidden.bs.modal', function() {
        const form = deleteWifiModal.querySelector('form');
        if (form) {
          form.reset();
        }
      });
    }
  }

  /**
   * Fetch and display device status
   */
  function fetchStatus() {
    fetch('/tmp/BCMETER_WEB_STATUS')
      .then(response => response.ok ? response.text() : Promise.reject('Network error'))
      .then(data => {
        try {
          const jsonData = JSON.parse(data);
          updateStatus(
            jsonData.bcMeter_status, 
            jsonData.hostname, 
            jsonData.log_creation_time, 
            jsonData.calibration_time, 
            jsonData.filter_status, 
            jsonData.in_hotspot
          );
        } catch (e) {
          console.error('JSON parsing error:', e);
          updateStatus(-1, "Device", null, null, null, false);
        }
      })
      .catch(error => {
        console.error('Fetch error:', error);
        updateStatus(-1, "Device", null, null, null, false);
      });
  }

  /**
   * Update the display with device status
   */
  function updateStatus(status, deviceName, creationTimeString, calibrationTime, filterStatus, in_hotspot) {
    window.deviceName = deviceName;
    
    // Show warning modal if necessary
    if ((!calibrationTime || (filterStatus !== null && filterStatus < 2)) && 
        (!window.is_ebcMeter || (window.is_ebcMeter && filterStatus === 0))) {
      showWarningModal(calibrationTime, filterStatus);
    }
    
    const statusDiv = document.getElementById('statusDiv');
    statusDiv.className = 'status-div';
    
    let formattedCreationTime = formatTimeString(creationTimeString);
    let formattedCalibrationTime = formatTimeString(calibrationTime);
    let statusText = getStatusText(status, deviceName, formattedCreationTime);
    
    // Update the calibration time and filter status displays
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
    
    // Update main status display
    statusDiv.textContent = statusText;
    setStatusColors(statusDiv, status);
    updateHotspotWarning(in_hotspot);
  }

  /**
   * Format timestamp string to readable date
   */
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

  /**
   * Get status text based on status code
   */
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

  /**
   * Set status colors based on status code
   */
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

  /**
   * Update hotspot warning display
   */
  function updateHotspotWarning(in_hotspot) {
    const hotspotWarningDiv = document.getElementById('hotspotwarning');
    if (hotspotWarningDiv) {
      if (in_hotspot === true) {
        hotspotWarningDiv.style.display = 'block';
        hotspotWarningDiv.className = 'alert alert-warning';
      } else {
        hotspotWarningDiv.style.display = 'none';
      }
    }
  }

  /**
   * Show error message with rate limiting
   */
  function showError(message) {
    const now = Date.now();
    if (now - lastErrorTimestamp > 10000) { 
      // Show error message to user
      lastErrorTimestamp = now;
      console.error(message);
    }
  }

  /**
   * Show warning modal for device maintenance
   */
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

  /**
   * Check for undervoltage status
   */
  function checkUndervoltageStatus() {
    $.ajax({
      url: 'includes/status.php',
      type: 'POST',
      data: { status: 'undervolt' },
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

  /**
   * Ignore undervoltage warning
   */
  function ignoreWarning() {
    const warningDiv = document.getElementById('undervoltage-status');
    if (warningDiv) {
      warningDiv.style.display = 'none';
    }
  }

  /**
   * Fetch and display time data
   */
  function fetchTimeData() {
    const date = new Date();
    const timestamp = Math.floor(date.getTime() / 1000);
    const currentDateTime = `${date.toLocaleString('default', { month: 'short' })} ${date.getDate()} ${date.getFullYear()} ${date.getHours()}:${date.getMinutes()}:${date.getSeconds()}`;

    $.ajax({
      url: "includes/gettime.php",
      type: "post",
      data: { datetime: "now" },
      cache: false,
      timeout: 1000,
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
        const deviceURL = (window.deviceName !== "") ? "http://" + window.deviceName : "";

        document.getElementById("datetime_device").innerHTML = "No connection to bcMeter<br /> Wait a minute to click <a href=\"" + deviceURL + "\">here </a> after WiFi Setup";
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
  }

  /**
   * Check for unsaved changes and ask for confirmation
   */
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
    isDirty = false;
    activateAndLoadConfig(newTab);
  }

  /**
   * Monitor form changes
   */
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

  /**
   * Activate tab and load config
   */
  function activateAndLoadConfig(tabElement) {
    const configType = tabElement.attr('aria-controls');
    loadConfig(configType);
    
    const formId = getFormIdFromConfigType(configType);
    monitorChanges(formId);
  }

  /**
   * Get form ID from config type
   */
  function getFormIdFromConfigType(configType) {
    const formIds = {
      'session': 'session-parameters-form',
      'device': 'device-parameters-form',
      'administration': 'administration-parameters-form',
      'email': 'email-parameters-form',
      'compair': 'compair-parameters-form'
    };
    return formIds[configType] || '';
  }

  /**
   * Get base URL with port 5000
   */
  function getBaseUrl() {
    return window.location.protocol + '//' + window.location.hostname + ':5000';
  }

  /**
   * Load configuration data
   */
  function loadConfig(configType) {
    fetch(`${getBaseUrl()}/load-config`)
      .then(response => response.json())
      .then(data => {
        const formId = getFormIdFromConfigType(configType);
        const tbody = document.querySelector(`#${formId} tbody`);
        tbody.innerHTML = '';
        
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
      .catch(error => console.error('Failed to load configuration:', error));
  }

  /**
   * Save configuration
   */
  function saveConfiguration(configType) {
    const formId = getFormIdFromConfigType(configType);
    const form = document.getElementById(formId);
    const updatedConfig = {};

    form.querySelectorAll('input[type="checkbox"], input[type="number"], input[type="text"]').forEach(input => {
      const key = input.name;
      let value = input.value;
      
      if (input.type === 'checkbox') {
        value = input.checked;
      } else if (input.classList.contains('array')) {
        try {
          value = JSON.parse(input.value);
        } catch (e) {
          console.error('Failed to parse array input:', e);
        }
      }
      
      if (input.type === 'number') {
        value = value.replace(/,/g, '.');
      }
      
      const description = input.closest('tr').getAttribute('title')?.trim() || '';

      if (key) {
        updatedConfig[key] = {
          value: value,
          description: description,
          type: determineType(input),
          parameter: configType
        };
      }
    });

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

    fetch(`${getBaseUrl()}/load-config`)
      .then(response => response.json())
      .then(existingConfig => {
        const mergedConfig = { ...existingConfig };
        
        Object.keys(updatedConfig).forEach(key => {
          mergedConfig[key] = updatedConfig[key];
        });

        fetch(`${getBaseUrl()}/save-config`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
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

  /**
   * Save configuration based on active tab
   */
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

  /**
   * Fetch available WiFi networks
   */
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

  /**
   * Update password field visibility based on network
   */
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

  // Confirmation dialog functions
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
              data: { force_wifi: true },
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
    // Ask about downloading config first
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
          // Download config first
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
          // Skip download
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
    
    // Determine if we're in ebcMeter mode
    const isEbcMeter = typeof window.is_ebcMeter !== 'undefined' && window.is_ebcMeter === true;
    
    // Different message based on device type
    const messageText = isEbcMeter ? 
      "<p>This will start a new log. It takes about 2 minutes for the new chart to appear.</p>" +
      "<p>For optimal accuracy, please wait until the temperature curve flattens, which indicates the device has reached stable running temperature. This may take several minutes.</p>" :
      "<p>This will start a new log. It takes a few minutes for the new chart to appear.</p>";
    
    bootbox.dialog({
      title: 'Start new log?',
      message: messageText,
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
            // Close the confirmation dialog
            bootbox.hideAll();
            
            // Show processing modal with message and progress bar
            const processingModalMessage = isEbcMeter ?
              '<div class="text-center">' +
              '<p>It takes about 2 minutes for the first samples to appear.</p>' +
              '<p>Please note that measurements will be most accurate once the device has reached a stable running temperature.</p>' +
              '<p>For best results, wait until the temperature curve flattens.</p>' +
              '<div class="progress mt-3">' +
              '<div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100" style="width: 0%"></div>' +
              '</div></div>' :
              '<div class="text-center">' +
              '<p>It takes a few minutes for the first samples to appear.</p>' +
              '<p>Please note that samples might be inaccurate until the device has reached running temperature.</p>' +
              '<div class="progress mt-3">' +
              '<div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100" style="width: 0%"></div>' +
              '</div></div>';
            
            var processingModal = bootbox.dialog({
              title: 'Initializing...',
              message: processingModalMessage,
              closeButton: false,
              centerVertical: true,
              size: 'small'
            });
            
            // Update progress bar over 13 seconds
            var progressBar = processingModal.find('.progress-bar');
            var progress = 0;
            var interval = setInterval(function() {
              progress += 2;
              progressBar.css('width', progress + '%');
              progressBar.attr('aria-valuenow', progress);
              
              if (progress >= 100) {
                clearInterval(interval);
                processingModal.modal('hide');
              }
            }, 260); // 13 seconds total (260ms * 50 steps = 13000ms)
            
            // Make AJAX call to initiate the backend process
            $.ajax({
              type: 'post',
              data: {
                exec_new_log: true
              },
              success: function(response) {
                // Success handler
              },
              error: function() {
                // Handle error
                clearInterval(interval);
                processingModal.modal('hide');
                bootbox.alert({
                  title: "Error",
                  message: "There was an error starting the new log. Please try again.",
                  className: 'text-danger'
                });
              }
            });
          }
        }
      }
    });
  }

  /**
   * Fetch and process log files
   */
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

  /**
   * Initialize log fetching
   */
  function startLogFetching() {
    const logs = [
      { type: 'bcMeter', elementId: 'logBcMeter' },
      { type: 'ap_control_loop', elementId: 'logApControlLoop' }
    ];
    
    // Add compair log if it exists (determined by PHP)
    if (document.getElementById('logCompairFrostUpload')) {
      logs.push({ type: 'compair_frost_upload', elementId: 'logCompairFrostUpload' });
    }

    logs.forEach(log => {
      fetchAndProcessLogFile(log.type, log.elementId);
      // Set interval for periodic fetching (every 15 seconds)
      setInterval(() => fetchAndProcessLogFile(log.type, log.elementId), 15000);
    });
  }
  
  // Initialize log fetching on appropriate modal open
  $('#systemlogs').on('shown.bs.modal', startLogFetching);
  
  // Initialize undervoltage check
  checkUndervoltageStatus();
  setInterval(checkUndervoltageStatus, 120000); // Check every 2 minutes
});