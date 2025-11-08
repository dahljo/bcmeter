<?php
//interface version 0.95 2025-04-04
// Start the PHP session
session_start();
$_SESSION['valid_session'] = 1;
header('X-Accel-Buffering: no');
header("Access-Control-Allow-Origin: *");

if (isset($_GET['action']) && $_GET['action'] === 'get_log_files') {
    header('Content-Type: application/json');
    $logsPath = '../logs/';
    $files = scandir($logsPath);
    $logFiles = array_filter($files, function($file) use ($logsPath) {
      return !is_dir($logsPath . $file) &&
             $file !== '.' &&
             $file !== '..' &&
             pathinfo($file, PATHINFO_EXTENSION) === 'csv' &&
             preg_match('/^\d{2}-\d{2}-\d{2}_\d{6}\.csv$/', $file);
    });
    echo json_encode(array_values($logFiles));
    exit;
}


function getMacAddress($interface = 'wlan0') {
    $sysPath = "/sys/class/net/$interface/address";
    if (file_exists($sysPath)) {
        $macAddr = trim(file_get_contents($sysPath));
        if ($macAddr) {
            return str_replace(':', '', $macAddr);
        }
    }
    $output = [];
    $exitCode = 0;
    exec("timeout 2 /sbin/ifconfig $interface 2>/dev/null | grep -o -E '([0-9a-f]{2}:){5}[0-9a-f]{2}'", $output, $exitCode);
    if ($exitCode === 0 && !empty($output[0])) {
        return str_replace(':', '', $output[0]);
    }
    return '000000000000';
}

$macAddr = getMacAddress();

$baseDir = file_exists('/home/bcmeter') ? '/home/bcmeter' : (file_exists('/home/bcMeter') ? '/home/bcMeter' : '/home/pi');


function getBcMeterConfigValue($bcMeter_variable, $default = null) {
    global $baseDir;
    $jsonFilePath = $baseDir . '/bcMeter_config.json';
    if (!file_exists($jsonFilePath)) {
        error_log("Config file not found: $jsonFilePath");
        return $default;
    }
    $jsonData = @file_get_contents($jsonFilePath);
    if ($jsonData === false) {
        error_log("Error reading config file: $jsonFilePath");
        return $default;
    }
    $configData = json_decode($jsonData, true);
    if (json_last_error() !== JSON_ERROR_NONE) {
        error_log("JSON parsing error in config file: " . json_last_error_msg());
        return $default;
    }
    if (isset($configData[$bcMeter_variable]['value'])) {
        return $configData[$bcMeter_variable]['value'];
    }
    return $default;
}

// Get configuration values
$is_ebcMeter = getBcMeterConfigValue('is_ebcMeter');
$is_hotspot = getBcMeterConfigValue('run_hotspot');
$show_undervoltage_warning = getBcMeterConfigValue('show_undervoltage_warning');

// Get bcMeter version
$version = '';
$localfile = $baseDir . '/bcMeter.py';

if (file_exists($localfile)) {
    $file = fopen($localfile, 'r');
    if ($file) {
        $lineCount = 0;
        while (($line = fgets($file)) !== false && $lineCount < 50) {
            $lineCount++;
            $line = trim($line);
            if (strpos($line, 'bcMeter_version') === 0) {
                $parts = explode('"', $line);
                if (isset($parts[1])) {
                    $version = $parts[1];
                    break;
                }
            }
        }
        fclose($file);
    }
}

$version_parts = explode('.', $version);
$VERSION = implode('.', array_slice($version_parts, 0, 3));

if (isset($_POST['conn_submit'])) {
    $wifiFile = $baseDir . '/bcMeter_wifi.json';
    $wifi_ssid = null;
    
    if (trim($_POST['wifi_ssid']) === 'custom-network-selection') {
        $wifi_ssid = trim($_POST['custom_wifi_name']);
    } else {
        $wifi_ssid = trim($_POST['wifi_ssid']);
    }

    $wifi_pwd = trim($_POST['wifi_pwd']);
    if (empty($wifi_pwd)) {
        if (file_exists($wifiFile)) {
            $existing_data = json_decode(file_get_contents($wifiFile), TRUE);
            if (isset($existing_data["wifi_pwd"])) {
                $wifi_pwd = $existing_data["wifi_pwd"];
            }
        }
    }
    
    $data = array("wifi_ssid" => $wifi_ssid, "wifi_pwd" => $wifi_pwd);
    file_put_contents($wifiFile, json_encode($data, JSON_PRETTY_PRINT));
    
    // Attempt to trigger a reconnection
    exec('systemctl show --property MainPID --value bcMeter_ap_control_loop.service', $output);
    $pid = isset($output[0]) ? $output[0] : 0;
    if ($pid > 0) {
        posix_kill($pid, 10); // Send SIGUSR1 signal
    }
    
    exit();
}


if (isset($_POST['reset_wifi_json'])) {
    $wifiFile = $baseDir . '/bcMeter_wifi.json';
    $data = array("wifi_ssid" => "", "wifi_pwd" => "");
    file_put_contents($wifiFile, json_encode($data, JSON_PRETTY_PRINT));
}


function checkUpdate() {
    global $VERSION;
    $local = $VERSION ?: '0.9.20';  // default for old versions
    $remote = '0.9.19'; // default if not found online
    if ($content = @file_get_contents('https://raw.githubusercontent.com/dahljo/bcmeter/main/bcMeter.py')) {
        preg_match('/bcMeter_version\s*=\s*"([0-9.]+)"/', $content, $m);
        if ($m) $remote = $m[1];
    }
    $l = explode('.', $local);
    $r = explode('.', $remote);
    $update = false;
    if ($r[0] > $l[0]) $update = true;
    elseif ($r[0] == $l[0]) {
        if ($r[1] > $l[1]) $update = true;
        elseif ($r[1] == $l[1] && $r[2] > $l[2]) $update = true;
    }
    return [
        'update' => $update,
        'current' => $local,
        'available' => $remote
    ];
}


$grep = shell_exec('ps -eo pid,lstart,cmd | grep bcMeter.py | grep -Fv grep | grep -Fv www-data | grep -Fv sudo | grep -Fiv screen | grep python3');
$check = checkUpdate();

if (isset($_POST['exec_new_log'])) {
    exec('sudo systemctl restart bcMeter > /dev/null 2>&1 &');
    exit(); 
}

foreach ($_POST as $action => $value) {
    switch ($action) {
        case 'deleteOld': showConfirmDialog('delete-old-logs'); break;
        case 'syslog': showConfirmDialog('download-syslog'); break;
        case 'shutdown': showConfirmDialog('shutdown-device'); break;
        case 'force_wifi': exec('sudo systemctl restart bcMeter_ap_control_loop > /dev/null 2>&1 &'); break;
        case 'exec_stop': exec('sudo systemctl stop bcMeter > /dev/null 2>&1 &'); break;
        case 'exec_debug': exec("sudo kill -SIGINT $PID > /dev/null 2>&1 &"); break;
    }
}
function showConfirmDialog($action) {
    $dialogs = [
        'delete-old-logs' => [
            'title' => 'Delete old logs from device?',
            'message' => 'This cannot be undone.',
            'url' => 'includes/status.php?status=deleteOld'
        ],
        'download-syslog' => [
            'title' => 'Download Syslog?',
            'message' => 'Do you want to download the syslog for debugging?',
            'url' => 'includes/status.php?status=syslog'
        ],
        'shutdown-device' => [
            'title' => 'Turn off bcMeter?',
            'message' => 'Do you want to shutdown the device?',
            'url' => 'includes/status.php?status=shutdown'
        ]
    ];

    if (isset($dialogs[$action])) {
        echo '<script>var bootboxAction = "' . $action . '";</script>';
    }
}

if ($check['update']) {
    echo "<div style='text-align:center';'><strong>bcMeter Software Update available!</strong></div>";
}


function filterLogsByPattern($files) {
    $pattern = '/^\d{2}-\d{2}-\d{2}_\d{6}\.csv$/';
    return array_filter($files, function($file) use ($pattern) {
        return preg_match($pattern, $file);
    });
}

function getMostRecentLogFile($files) {
    if (empty($files)) return null;
    usort($files, function($a, $b) {
        $dateTimeA = str_replace('.csv', '', $a);
        $dateTimeB = str_replace('.csv', '', $b);
        return strcmp($dateTimeB, $dateTimeA);
    });

    return $files[0];
}

$folder_path = '../logs';
$allLogFiles = array_diff(scandir($folder_path), ['.', '..']);
$filteredLogFiles = filterLogsByPattern($allLogFiles);
$mostRecentLogFile = getMostRecentLogFile($filteredLogFiles);

$logString = "<select id='logs_select' class='form-control'>";

if ($mostRecentLogFile) {
    $logString .= "<option value='{$mostRecentLogFile}' selected>{$mostRecentLogFile}</option>";
}

foreach ($filteredLogFiles as $file) {
    if ($file !== $mostRecentLogFile) {
        $logString .= "<option value='{$file}'>{$file}</option>";
    }
}

$logString .= "<option value='combine_logs'>Combine Logs</option></select>";

// Pass filteredLogFiles directly to window.logFiles for d3plotting.js to use
echo "<script>
    window.logFiles = " . json_encode(array_values($filteredLogFiles)) . ";
    var mostRecentLogFile = " . json_encode($mostRecentLogFile) . ";
</script>";
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>bcMeter Interface</title>
    <link rel="stylesheet" type="text/css" href="css/bootstrap.min.css">
    <link rel="stylesheet" type="text/css" href="css/bootstrap4-toggle.min.css">
    <link href="css/all.min.css" rel="stylesheet">
    <link rel="stylesheet" href="css/bootstrap-slider.min.css">
    <link rel="stylesheet" href="css/bcmeter.css">
</head>
<body>
    <a href="" id="download" style="display: none;"></a>

    <div class="top-nav">
        <div class="nav-buttons">
            <a href="http://<?php echo $_SERVER['HTTP_HOST']; ?>">
                <img src="bcMeter-logo.png" style="width: 150px; vertical-align: middle;"/>
            </a>
            <button class="btn btn-primary" id="dashboard-btn">Dashboard</button>
            <button class="btn btn-secondary" data-toggle="modal" data-target="#downloadOld">Session logs</button>
            <button class="btn btn-secondary" data-toggle="modal" data-target="#device-parameters">Configuration</button>
            <button class="btn btn-secondary" data-toggle="modal" data-target="#systemModal">System</button>
        </div>
        <div class="status-div" id="statusDiv"></div>
    </div>

    <div class="page-container">
        <div id="dashboard-view">
                        <?php if ($is_ebcMeter === true): ?>
                <p class="text-center text-muted font-weight-bold mt-2">direct emission control</p>
            <?php endif; ?>

            <div id="averages-container">
                <div class="stat-card">
                    <h6 id="dynamic-avg-label">Average</h6>
                    <p id="dynamic-avg-value">-</p>
                </div>
                <div class="stat-card">
                    <h6>Total Average</h6>
                    <p id="avgAll-value">-</p>
                </div>

                    <div class="stat-card">
                        <h6>Peak Value</h6>
                        <p id="peak-value">-</p>
                        <button id="resetPeakBtn" class="btn btn-sm btn-outline-secondary mt-2" style="display: none;">Reset Peak</button>
                    </div>
                                </div>


            <div id="report-message" style="text-align: center; display: none;"></div>

             <?php if ($show_undervoltage_warning === true): ?>
                <div id='undervoltage-status' class='alert alert-warning'></div>
            <?php endif; ?>

       
            <div id="svg-container">
                <div class="tooltip" style="position: absolute;"></div>
                <svg id="line-chart"></svg>
            </div>


<div class="control-box">
                <div>
                    <h5>Plot Controls</h5>
                    <div class="text-center">
                        <button class="btn btn-light" id="resetZoom">Reset Zoom</button>
                        <button type="button" class="btn btn-light ml-1" data-toggle="modal" data-target="#scaleModal">Axis scaling</button>
                    </div>
                </div>
                    <br /> <br/>

                <div class="control-grid">
                    <label>View Log:</label>
                    <span id="logs"><?php echo $logString; ?></span>

                    <label for="y-menu">Y1-Axis:</label>
                    <select id="y-menu" class="form-control"></select>

                    <label for="medianFilter1">Denoise Y1:</label>
                    <div class="d-flex align-items-center">
                        <input id="medianFilter1" type="text" style="width: 100%;" data-slider-min="2" data-slider-max="10" data-slider-step="1" data-slider-value="2"/>
                        <span id="medianFilterValue1" class="ml-2 badge badge-secondary"></span>
                    </div>

                    <label></label> <button class="btn btn-light" id="hide-y-menu2">Hide Second Graph</button>

                    <label for="y-menu2">Y2-Axis:</label>
                    <select id="y-menu2" class="form-control"></select>

                    <label for="medianFilter2">Denoise Y2:</label>
                     <div class="d-flex align-items-center">
                        <input id="medianFilter2" type="text" style="width: 100%;" data-slider-min="2" data-slider-max="10" data-slider-step="1" data-slider-value="2"/>
                        <span id="medianFilterValue2" class="ml-2 badge badge-secondary"></span>
                    </div>

                    <label></label> <button class="btn btn-light" id="hide-y-menu3">Hide Third Graph</button>

                    <label for="y-menu3">Y3-Axis:</label>
                    <select id="y-menu3" class="form-control"></select>

                    <label for="medianFilter3">Denoise Y3:</label>
                     <div class="d-flex align-items-center">
                        <input id="medianFilter3" type="text" style="width: 100%;" data-slider-min="2" data-slider-max="10" data-slider-step="1" data-slider-value="2"/>
                        <span id="medianFilterValue3" class="ml-2 badge badge-secondary"></span>
                    </div>
                </div>
            </div>




           <div class="control-box text-center">
                  <h5>Session Control</h5>
                  <button type="button" id="startNewLog" class="btn btn-success">Start New Log</button>
                  <form method="post" class="d-inline">
                    <input type="submit" id="bcMeter_stop" name="bcMeter_stop" value="Stop Logging" class="btn btn-warning" />
                  </form>
                  <button type="button" id="saveGraph" class="btn btn-info">Download Current View</button>
                  <p>
                    Filter loading:
                    <button id="filterStatusValue" type="button" class="btn btn-sm btn-dark" disabled>0 %</button>
              </p>
             </div>

        </div>
    </div>


<div class="modal fade" id="systemModal" tabindex="-1" role="dialog">
    <div class="modal-dialog modal-lg" role="document">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">System & Maintenance</h5>
                <button type="button" class="close" data-dismiss="modal"><span>&times;</span></button>
            </div>
            <div class="modal-body">

                <div class="card mb-3">
                    <div class="card-header">Device Management</div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-6">
                                <h6 class="text-center">Routine Maintenance</h6>
                                <hr>
                                <form method="post" class="d-block mb-2">
                                    <input type="submit" id="bcMeter_calibration" name="bcMeter_calibration" value="Calibrate Device" class="btn btn-primary btn-block" />
                                </form>
                                
                                <button type="button" class="btn btn-primary btn-block mb-2" data-toggle="modal" data-target="#wifisetup">WiFi Setup</button>
                                
                                <form method="post" class="d-block mb-2">
                                    <input type="submit" id="bcMeter_update" name="bcMeter_update" value="Check for Updates" class="btn btn-primary btn-block" />
                                </form>
                                <button type="button" class="btn btn-secondary btn-block" data-toggle="modal" data-target="#systemlogs">View System Logs</button>
                                <a href="includes/status.php?status=syslog" class="btn btn-info btn-block mt-2" role="button">Download logs for debug</a>
                            </div>

                            <div class="col-md-6">
                                <h6 class="text-center">System Operations</h6>
                                <hr>
                                <form method="post" class="d-block mb-2">
                                    <input type="submit" name="bcMeter_reboot" id="bcMeter_reboot" value="Reboot Device" class="btn btn-warning btn-block" />
                                </form>
                                <form method="post" class="d-block mb-2">
                                    <input type="submit" name="shutdown" value="Shutdown Device" class="btn btn-danger btn-block" />
                                </form>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="card mb-3">
                    <div class="card-header">System Status</div>
                    <div class="card-body">
                        <p class="mb-1"><strong>Device ID:</strong> <?php echo 'bcMeter_0x' . $macAddr; ?></p>
                        <p class="mb-1"><strong>Software Version:</strong> <?php echo $VERSION; ?></p>
                        <div id="calibrationTime" class="mb-1"></div>

                    </div>
                </div>
                <div class="card mb-3">
                  <div class="card-header">Time Synchronization</div>
                  <div class="card-body">
                    <p><strong>Browser Time:</strong> <span id="systemBrowserTime">Loading...</span></p>
                    <p><strong>Device Time:</strong> <span id="systemDeviceTime">Loading...</span></p>
                    <button class="btn btn-sm btn-primary" id="refreshTimes">Refresh Times</button>
                  </div>
                </div>

                <div class="card mb-3">
                  <div class="card-header">Device Identity</div>
                  <div class="card-body">
                    <p><strong>Current Device Name:</strong> <span id="currentDeviceName"><?php echo gethostname(); ?></span></p>
                    <button class="btn btn-sm btn-secondary" id="renameDeviceBtn">Rename Device</button>
                  </div>
                </div>

            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-dismiss="modal">Close</button>
            </div>
        </div>
    </div>
</div>





    <div class="modal fade" id="downloadOld" tabindex="-1" role="dialog">
        <div class="modal-dialog modal-lg" role="document">
            <div class="modal-content">
                <div class="modal-header"><h5 class="modal-title">All Data Logs</h5><button type="button" class="close" data-dismiss="modal"><span>&times;</span></button></div>
                <div class="modal-body">
                     <ul class="nav nav-tabs" id="logTabs" role="tablist">
                        <li class="nav-item"><a class="nav-link active" id="large-files-tab" data-toggle="tab" href="#large-files" role="tab">Logs (>2KB)</a></li>
                        <li class="nav-item"><a class="nav-link" id="small-files-tab" data-toggle="tab" href="#small-files" role="tab">Logs (<2KB)</a></li>
                    </ul>
                    <div class="tab-content mt-2">
                        <div class="tab-pane fade show active" id="large-files" role="tabpanel">
                            <table class='table table-sm'><thead><tr><th>Log Start Time</th><th>File Size</th><th></th></tr></thead><tbody>
                            <?php
                            $hostname = $_SERVER['HTTP_HOST'];
                            $dir = "../logs";
                            $files = scandir($dir);
                            foreach ($files as $file) :
                                if (pathinfo($file, PATHINFO_EXTENSION) === 'csv' && $file != 'log_current.csv') :
                                    $file_size_kb = filesize($dir . '/' . $file) / 1024;
                                    if ($file_size_kb >= 2) {
                                        $date_time = explode("_", substr($file, 0, -4))[1];
                                        $date_time_day = explode("_", substr($file, 0, -4))[0];
                                        $date_time = $date_time_day . " " . substr($date_time, 0, 2) . ":" . substr($date_time, 2, 2) . ":" . substr($date_time, 4, 2);
                                        echo "<tr><td>{$date_time}</td><td>".number_format($file_size_kb, 2)." KB</td><td><a href='{$dir}/{$file}' download='{$hostname}_{$file}' class='btn btn-sm btn-primary'>Download</a></td></tr>";
                                    }
                                endif;
                            endforeach;
                            ?>
                            </tbody></table>
                        </div>
                        <div class="tab-pane fade" id="small-files" role="tabpanel">
                             <table class='table table-sm'><thead><tr><th>Log Start Time</th><th>File Size</th><th></th></tr></thead><tbody>
                             <?php
                             foreach ($files as $file) :
                                if (pathinfo($file, PATHINFO_EXTENSION) === 'csv' && $file != 'log_current.csv') :
                                    $file_size_kb = filesize($dir . '/' . $file) / 1024;
                                    if ($file_size_kb < 2) {
                                        $date_time = explode("_", substr($file, 0, -4))[1];
                                        $date_time_day = explode("_", substr($file, 0, -4))[0];
                                        $date_time = $date_time_day . " " . substr($date_time, 0, 2) . ":" . substr($date_time, 2, 2) . ":" . substr($date_time, 4, 2);
                                        echo "<tr><td>{$date_time}</td><td>".number_format($file_size_kb, 2)." KB</td><td><a href='{$dir}/{$file}' download='{$hostname}_{$file}' class='btn btn-sm btn-primary'>Download</a></td></tr>";
                                    }
                                endif;
                            endforeach;
                            ?>
                             </tbody></table>
                        </div>
                    </div>
                </div>
                 <div class="modal-footer"><button type="button" class="btn btn-secondary" data-dismiss="modal">Close</button></div>
            </div>
        </div>
    </div>

    <div class="modal fade" id="device-parameters" tabindex="-1" role="dialog">
        <div class="modal-dialog modal-xl" role="document">
            <div class="modal-content">
                <div class="modal-header"><h5 class="modal-title">Configuration</h5><button type="button" class="close" data-dismiss="modal"><span>&times;</span></button></div>
                <div class="modal-body">
                    <?php
                        $tabs = [ "session" => "Session", "device" => "Device", "administration" => "Administration", "email" => "Email" ];
                    ?>
                    <ul class="nav nav-tabs" id="configTabs" role="tablist">
                        <?php foreach ($tabs as $type => $title): ?>
                            <li class="nav-item">
                                <a class="nav-link <?php if ($type === 'session') echo 'active'; ?>" 
                                   id="<?= $type ?>-tab" 
                                   data-toggle="tab" 
                                   href="#<?= $type ?>" 
                                   role="tab" 
                                   aria-controls="<?= $type ?>"> <?= $title ?>
                                </a>
                            </li>
                        <?php endforeach; ?>
                    </ul>
                    <div class="tab-content mt-2">
                        <?php foreach ($tabs as $type => $title): ?>
                            <div class="tab-pane <?php if ($type === 'session') echo 'active'; ?>" id="<?= $type ?>" role="tabpanel">
                                <form id="<?= $type ?>-parameters-form">
                                    <table class="table table-bordered table-sm"><thead><tr><th style="width: 80%;">Description</th><th>Value</th></tr></thead><tbody></tbody></table>
                                    <button type="button" class="btn btn-primary" id="save<?= ucfirst($type) ?>Settings">Save <?= $title ?> Settings</button>
                                </form>
                            </div>
                        <?php endforeach; ?>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <div class="modal fade" id="scaleModal" tabindex="-1" role="dialog">
        <div class="modal-dialog" role="document">
            <div class="modal-content">
                <div class="modal-header"><h5 class="modal-title">Change Plot Scale</h5><button type="button" class="close" data-dismiss="modal" aria-label="Close"><span aria-hidden="true">&times;</span></button></div>
                <div class="modal-body">
                    <p>Use the checkboxes to toggle between autoscaling and a manual override for each axis boundary.</p><hr>
                    <div class="table-responsive">
                        <table class="table table-bordered text-center" id="scale-control-table">
                            <thead><tr><th>Axis</th><th>Boundary</th><th>Current</th><th>Auto</th><th>Override</th></tr></thead>
                            <tbody>
                                <tr>
                                    <th scope="row" rowspan="2" class="align-middle">Y1</th><td>Min</td><td id="current-y1-min">-</td>
                                    <td><input type="checkbox" id="y1-min-auto" class="auto-scale-toggle"></td><td><input type="number" id="y-menu-min" class="form-control"></td>
                                </tr>
                                <tr>
                                    <td>Max</td><td id="current-y1-max">-</td><td><input type="checkbox" id="y1-max-auto" class="auto-scale-toggle"></td><td><input type="number" id="y-menu-max" class="form-control"></td>
                                </tr>
                                <tr class="y2-axis-row">
                                    <th scope="row" rowspan="2" class="align-middle">Y2</th><td>Min</td><td id="current-y2-min">-</td>
                                    <td><input type="checkbox" id="y2-min-auto" class="auto-scale-toggle"></td><td><input type="number" id="y-menu2-min" class="form-control"></td>
                                </tr>
                                <tr class="y2-axis-row">
                                    <td>Max</td><td id="current-y2-max">-</td><td><input type="checkbox" id="y2-max-auto" class="auto-scale-toggle"></td><td><input type="number" id="y-menu2-max" class="form-control"></td>
                                </tr>
                                <tr class="y3-axis-row">
                                    <th scope="row" rowspan="2" class="align-middle">Y3</th><td>Min</td><td id="current-y3-min">-</td>
                                    <td><input type="checkbox" id="y3-min-auto" class="auto-scale-toggle"></td><td><input type="number" id="y-menu3-min" class="form-control"></td>
                                </tr>
                                <tr class="y3-axis-row">
                                    <td>Max</td><td id="current-y3-max">-</td><td><input type="checkbox" id="y3-max-auto" class="auto-scale-toggle"></td><td><input type="number" id="y-menu3-max" class="form-control"></td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
                <div class="modal-footer"><button type="button" class="btn btn-secondary" data-dismiss="modal">Close</button><button type="button" class="btn btn-primary" id="applyScaleChanges">Apply Changes</button></div>
            </div>
        </div>
    </div>
    


<div class="modal fade" id="wifisetup" tabindex="-1" role="dialog" aria-labelledby="wifiSetupLabel" aria-hidden="true">
    <div class="modal-dialog" role="document">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title" id="wifiSetupLabel">WiFi Setup</h5>
                <button type="button" class="close" data-dismiss="modal" aria-label="Close">
                    <span aria-hidden="true">&times;</span>
                </button>
            </div>
            <div class="modal-body">
                <form id="wifi-form">
                    <div class="form-group">
                        <label for="js-wifi-dropdown">Select Network</label>
                        <div class="input-group">
                            <select class="form-control" id="js-wifi-dropdown">
                                <option>Loading networks...</option>
                                </select>
                            <div class="input-group-append">
                                <button class="btn btn-outline-secondary" type="button" id="refreshWifi" title="Refresh List">
                                    <i class="fas fa-sync-alt"></i>
                                </button>
                            </div>
                        </div>
                        <div class="loading-available-networks" style="display: none;">
                            <small class="form-text text-muted">Scanning for networks...</small>
                        </div>
                    </div>
                    <div class="form-group" id="custom-network-input" style="display: none;">
                        <label for="custom_ssid">Network Name (SSID)</label>
                        <input type="text" class="form-control" id="custom_ssid" name="custom_ssid" placeholder="Enter custom network name">
                    </div>
                    <div class="form-group wifi-pwd-field-exist" style="display: none;">
                        <label>Password</label>
                        <div class="input-group">
                            <input type="text" class="form-control" value="••••••••" disabled>
                            <div class="input-group-append">
                                <button class="btn btn-outline-secondary js-edit-password" type="button">Edit</button>
                            </div>
                        </div>
                        <small class="form-text text-muted">A password for this network is already saved. Click 'Edit' to change it.</small>
                    </div>
                    <div class="form-group wifi-pwd-field">
                         <label for="pass_log_id">Password</label>
                         <div class="input-group">
                            <input type="password" id="pass_log_id" name="pass_log" class="form-control">
                            <div class="input-group-append">
                               <span class="input-group-text toggle-password" style="cursor: pointer;"><i class="fa fa-eye-slash"></i></span>
                            </div>
                         </div>
                    </div>
                </form>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-danger" data-toggle="modal" data-target="#deleteWifiModal">Delete Settings</button>
                <button type="button" class="btn btn-secondary" data-dismiss="modal">Close</button>
                <button type="button" class="btn btn-primary" id="saveWifiSettings">Save & Connect</button>
            </div>
        </div>
    </div>
</div>



     <div class="modal fade" id="systemlogs" tabindex="-1" role="dialog" aria-labelledby="systemlogsLabel" aria-hidden="true">
    <div class="modal-dialog modal-xl" role="document">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title" id="systemlogsLabel">System Logs</h5>
                <button type="button" class="close" data-dismiss="modal" aria-label="Close">
                    <span aria-hidden="true">&times;</span>
                </button>
            </div>
            <div class="modal-body">
                <div class="accordion" id="logAccordion">
                    <div class="card">
                        <div class="card-header" id="headingBcMeter">
                            <h5 class="mb-0">
                                <button class="btn btn-link" type="button" data-toggle="collapse" data-target="#collapseBcMeter" aria-expanded="true" aria-controls="collapseBcMeter">
                                    bcMeter.log
                                </button>
                            </h5>
                        </div>
                        <div id="collapseBcMeter" class="collapse show" aria-labelledby="headingBcMeter" data-parent="#logAccordion">
                            <div class="card-body log-box" id="logBcMeter">
                                Loading log...
                            </div>
                        </div>
                    </div>
                    <div class="card">
                        <div class="card-header" id="headingApControl">
                            <h5 class="mb-0">
                                <button class="btn btn-link collapsed" type="button" data-toggle="collapse" data-target="#collapseApControl" aria-expanded="false" aria-controls="collapseApControl">
                                    ap_control_loop.log
                                </button>
                            </h5>
                        </div>
                        <div id="collapseApControl" class="collapse" aria-labelledby="headingApControl" data-parent="#logAccordion">
                            <div class="card-body log-box" id="logApControlLoop">
                                Loading log...
                            </div>
                        </div>
                    </div>


                </div>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-dismiss="modal">Close</button>
            </div>
        </div>
    </div>
</div>


<div class="modal fade" id="deleteWifiModal" tabindex="-1" role="dialog" aria-labelledby="deleteWifiModalLabel" aria-hidden="true">
    <div class="modal-dialog" role="document">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title" id="deleteWifiModalLabel">Confirm WiFi Deletion</h5>
                <button type="button" class="close" data-dismiss="modal" aria-label="Close">
                    <span aria-hidden="true">&times;</span>
                </button>
            </div>
            <div class="modal-body">
                <p><strong>Are you sure you want to delete all saved WiFi credentials?</strong></p>
                <p class="text-muted">After deletion, it may take up to 5 minutes for the device's hotspot to become available for reconnection.</p>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-dismiss="modal">Cancel</button>
                <form method="POST" action="index.php" style="display: inline;">
                    <button type="submit" name="reset_wifi_json" class="btn btn-danger">Delete Credentials</button>
                </form>
            </div>
        </div>
    </div>
</div>




    <script src="js/jquery-3.6.0.min.js"></script>
    <script src="js/bootstrap.min.js"></script>
    <script src="js/bootbox.min.js"></script>
    <script src="js/bootstrap4-toggle.min.js"></script>
    <script src="js/d3.v7.min.js"></script>
    <script src="js/bootstrap-slider.min.js"></script>
    <script>
        var is_hotspot = <?php echo json_encode($is_hotspot); ?>;
        var is_ebcMeter = <?php echo json_encode($is_ebcMeter); ?>;
    </script>
    <script src="js/d3plotting.js"></script>
    <script src="js/interface.js"></script>
    <script>
        // JS to handle confirmation dialogs
        $(document).ready(function() {
            var dialogConfigs = {
                'delete-old-logs': { title: 'Delete old logs?', message: '<p>This cannot be undone.</p>', url: 'includes/status.php?status=deleteOld' },
                'download-syslog': { title: 'Download Syslog?', message: '<p>Do you want to download the syslog for debugging?</p>', url: 'includes/status.php?status=syslog' },
                'shutdown-device': { title: 'Turn off bcMeter?', message: '<p>Do you want to shutdown the device?</p>', url: 'includes/status.php?status=shutdown' }
            };
            if (typeof bootboxAction !== 'undefined' && bootboxAction in dialogConfigs) {
                var dialog = dialogConfigs[bootboxAction];
                bootbox.dialog({
                    title: dialog.title, message: dialog.message, size: 'small',
                    buttons: {
                        cancel: { label: "No", className: 'btn-success' },
                        ok: { label: "Yes", className: 'btn-danger', callback: function() { window.location.href = dialog.url; } }
                    }
                });
            }
            // Logic to handle download button bootbox
            $('#saveGraph').on('click', function(e) {
                e.preventDefault();
                bootbox.dialog({
                    title: 'Save graph as', message: "<p>Choose a file type to download the current view.</p>", size: 'large',
                    buttons: {
                        csv: { label: "CSV", className: 'btn-info', callback: function() { window.saveCSV(); }},
                        png: { label: "PNG", className: 'btn-info', callback: function() { window.savePNG(); }},
                        svg: { label: "SVG", className: 'btn-info', callback: function() { window.saveSVG(); }}
                    }
                });
            });


        });

      function updateSystemTimes() {
        const browserTime = new Date().toLocaleString();
        $("#systemBrowserTime").text(browserTime);
        $.get("includes/get_device_time.php", function(result) {
          const ts = parseInt(result.trim(), 10);
          if (!isNaN(ts)) {
            $("#systemDeviceTime").text(new Date(ts * 1000).toLocaleString());
          } else {
            $("#systemDeviceTime").text("Unavailable");
          }
        }).fail(() => $("#systemDeviceTime").text("Unavailable"));
      }

      $("#refreshTimes").click(updateSystemTimes);
      $("#systemModal").on("shown.bs.modal", updateSystemTimes);

      $("#renameDeviceBtn").click(() => {
        bootbox.prompt({
          title: "Rename Device",
          message: "Enter a new hostname for this bcMeter device:",
          callback: name => {
            if (name && name.trim() !== "") {
              $.post("includes/rename_device.php", { hostname: name.trim() })
                .done(() => {
                  bootbox.alert("Device renamed successfully. Reboot to apply changes.");
                  $("#currentDeviceName").text(name.trim());
                })
                .fail(() => bootbox.alert("Failed to rename device."));
            }
          }
        });
      });

</script>

</body>
</html>