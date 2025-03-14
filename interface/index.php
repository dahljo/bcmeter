<?php
//interface version 0.95 2025-03-14
// Start the PHP session
session_start();
$_SESSION['valid_session'] = 1;
header('X-Accel-Buffering: no');

// Configuration and device detection
$macAddr = exec("/sbin/ifconfig wlan0 | grep 'ether' | awk '{print $2}'");
$macAddr = str_replace(':', '', $macAddr);

$baseDir = file_exists('/home/bcMeter') ? '/home/bcMeter' : '/home/pi';

// Load configuration from JSON
function getBcMeterConfigValue($bcMeter_variable) {
    global $baseDir;
    $jsonFilePath = $baseDir . '/bcMeter_config.json';
    
    if (file_exists($jsonFilePath)) {
        $jsonData = file_get_contents($jsonFilePath);
        $configData = json_decode($jsonData, true);
        
        return $configData[$bcMeter_variable]['value'] ?? null;
    }
    
    return null;
}

// Get configuration values
$is_ebcMeter = getBcMeterConfigValue('is_ebcMeter');
$is_hotspot = getBcMeterConfigValue('run_hotspot');
$compair_upload = getBcMeterConfigValue('compair_upload');
$show_undervoltage_warning = getBcMeterConfigValue('show_undervoltage_warning');

// Get bcMeter version
$version = '';
$localfile = $baseDir . '/bcMeter.py';

for ($i = 1; $i <= 50; $i++) {
    $line = trim(exec("head -$i $localfile | tail -1"));
    if (strpos($line, 'bcMeter_version') === 0) {
        $version = explode('"', $line)[1];
        break;
    }
}

$version_parts = explode('.', $version);
$VERSION = implode('.', array_slice($version_parts, 0, 3));

/**
 * Check for bcMeter updates
 */
function checkUpdate() {
    global $VERSION;
    $local = $VERSION ?: '0.9.20';  // default for old versions
    $remote = '0.9.19'; // default if not found online
    
    // Get remote version
    if ($content = @file_get_contents('https://raw.githubusercontent.com/dahljo/bcmeter/main/bcMeter.py')) {
        preg_match('/bcMeter_version\s*=\s*"([0-9.]+)"/', $content, $m);
        if ($m) $remote = $m[1];
    }
    
    // Split versions
    $l = explode('.', $local);
    $r = explode('.', $remote);
    
    // Compare versions
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

// Check for running bcMeter process and updates
$grep = shell_exec('ps -eo pid,lstart,cmd | grep bcMeter.py | grep -Fv grep | grep -Fv www-data | grep -Fv sudo | grep -Fiv screen | grep python3');
$check = checkUpdate();

// Execute post requests
if (isset($_POST["deleteOld"])) {
    showConfirmDialog('delete-old-logs');
}

if (isset($_POST["set_time"])) {
    $set_timestamp_to = $_POST['set_time'];
    header("Location: includes/status.php?status=timestamp&timestamp=$set_timestamp_to");
    exit;
}

if (isset($_POST["syslog"])) {
    showConfirmDialog('download-syslog');
}

if (isset($_POST["shutdown"])) {
    showConfirmDialog('shutdown-device');
}

if (isset($_POST["force_wifi"])) {
    shell_exec("sudo systemctl restart bcMeter_ap_control_loop");
}

if (isset($_POST["exec_stop"])) {
    shell_exec("sudo systemctl stop bcMeter");
}

if (isset($_POST["exec_debug"])) {
    shell_exec("sudo kill -SIGINT $PID");
}

if (isset($_POST["exec_new_log"])) {
    shell_exec("sudo systemctl restart bcMeter");
}

/**
 * Show confirmation dialog with JavaScript
 */
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
        $dialog = $dialogs[$action];
        echo <<< JAVASCRIPT
<script>
bootbox.dialog({
    title: '{$dialog['title']}',
    message: "<p>{$dialog['message']}</p>",
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
                window.location.href = '{$dialog['url']}';
            }
        }
    }
});
</script>
JAVASCRIPT;
    }
}

// Show update notification if available
if ($check['update']) {
    echo "<div style='text-align:center';'><strong>bcMeter Software Update available!</strong></div>";
}

// Get the list of log files
$folder_path = '../logs';
$logFiles = scandir($folder_path);
$logString = "<select id='logs_select'>";
foreach ($logFiles as $key => $value) {
    if ($key > 1) {
        $logString .= "<option value='{$value}'>{$value}</option>"; 
    }
}
$logString .= "<option value='combine_logs'>Combine Logs</option></select>";
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>bcMeter Interface</title>
    <link rel="stylesheet" type="text/css" href="css/bootstrap.min.css">
    <link rel="stylesheet" type="text/css" href="css/bootstrap4-toggle.min.css">
    <link rel="stylesheet" type="text/css" href="css/bcmeter.css">
    <link href="css/all.min.css" rel="stylesheet">
</head>
<body>
    <a href="" id="download" style="display: none;"></a>
    <br />
    <a href="http://<?php echo $_SERVER['HTTP_HOST']; ?>">
        <img src="bcMeter-logo.png" style="width: 250px; display:block; margin: 0 auto;"/>
    </a>
    
    <?php if ($is_ebcMeter === true): ?>
        <p style='text-align:center;font-weight:bold;'>emission measurement prototype</p>
    <?php endif; ?>
    
    <div class="status-div" id="statusDiv"></div>
    
    <div class="container">
        <div class="row">
            <div class="col-sm-12">
                <div style='display:none; margin: 20px 0;' id='hotspotwarning' class='alert'>
                    <div style='text-align:center;'><strong>You're currently offline</strong></div>
                    <div style="display: block;margin: 0 auto;">
                        <p style="text-align: center;" id="datetime_note"></p>
                        <pre style='text-align:center;' id='datetime_device'></pre>
                        <pre style='text-align:center;' id='datetime_local'></pre>
                    </div>
                    <div style="text-align: center";>
                        <form method="POST">
                            <input type="hidden" id="set_time" name="set_time" value="">
                            <input type="submit" value="Set clock on bcMeter to your time" class="btn btn-primary">
                        </form>
                    </div>
                </div>
            </div>
        </div>
        
        <div id="report-value" style="text-align: center; display: block;margin: 20px 0;"></div>
        
        <?php if ($show_undervoltage_warning === true): ?>
            <div id='undervoltage-status' class='status'></div>
        <?php endif; ?>
        
        <!-- Drop-down menu container -->
        <div class="menu" style="display: block; text-align: center;">
            Selected View:
            <span id="logs"><?php echo $logString; ?></span>
            <span class="y-menu">
                <select id="y-menu"></select>
            </span>
            <span class="y-menu2">
                <select id="y-menu2"></select>
            </span>
            <span class="btn btn-light" id="hide-y-menu2">Hide</span>
            <span class="btn" id="resetZoom">Reset Zoom</span>
        </div>
        
        <!-- Chart container -->
        <div id="svg-container">
            <input type="number" id="y-menu-min" placeholder="min">
            <input type="number" id="y-menu-max" placeholder="max">
            <input type="number" id="y-menu2-min" placeholder="min">
            <input type="number" id="y-menu2-max" placeholder="max">
            <div class="tooltip" style="position: absolute;"></div>
            <svg id="line-chart" width="1100" height="480" style="margin: 0px auto 10px"></svg>
        </div>
        
        <!-- Control buttons -->
        <form style="display: block; text-align:center;" method="post">
            <input type="submit" id="startNewLog" name="newlog" value="Start" class="btn btn-info" />
            <input type="submit" id="bcMeter_stop" name="bcMeter_stop" value="Stop" class="btn btn-secondary" />
            <input type="submit" id="saveGraph" name="saveGraph" value="Download" class="btn btn-info bootbox-accept" />
            <button type="button" class="btn btn-info" data-toggle="pill" data-target="#pills-devicecontrol" role="tab">Administration</button>
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
                        <p>Filter loading: <span id="filterStatusValue"></span>%</p>
                        <p>5 colors are possible: Green, red, orange, grey and black. Red means: be prepared to change. <br /> When grey, it should be changed. <br />Data will still be gathered. When black, the paper cannot load any more black carbon.</p>
                        You may calibrate the device with fresh filter paper to get the most reliable results. 
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-dismiss="modal">Close</button>
                    </div>
                </div>
            </div>
        </div>
        
        <br />
        
        <!-- Administration Panel -->
        <div class="tab-pane fade" id="pills-devicecontrol" role="tabpanel" aria-labelledby="pills-devicecontrol-tab" style="display: none;">
            <form style="text-align:center;" method="post">
                <div class="btn-group" role="group">
                    <button type="button" class="btn btn-primary" data-toggle="modal" data-target="#wifisetup">WiFi Settings</button>
                    <button type="button" class="btn btn-secondary" data-toggle="modal" data-target="#device-parameters">Settings</button>
                    <button type="button" class="btn btn-info" data-toggle="modal" data-target="#downloadOld">All logs</button>
                    <input type="submit" name="deleteOld" value="Delete old logs" class="btn btn-info" />
                    <input type="submit" id="bcMeter_calibration" name="bcMeter_calibration" value="Calibration" class="btn btn-info" />
                    <button type="button" class="btn btn-info" data-toggle="modal" data-target="#systemlogs">System Logs</button>
                    <input type="hidden" name="randcheck" />
                    <input type="submit" id="bcMeter_update" name="bcMeter_update" value="Update bcMeter" class="btn btn-info" />
                    <button type="button" class="btn btn-info" data-toggle="modal" data-target="#edithostname">Change Hostname</button> 
                    <input type="submit" name="bcMeter_reboot" id="bcMeter_reboot" value="Reboot" class="btn btn-info" />
                    <input type="submit" name="shutdown" value="Shutdown" class="btn btn-danger" />
                </div>
                
                <?php
                    // Display device information
                    $hostname = $_SERVER['HTTP_HOST'];
                    $macAddr = 'bcMeter_0x' . $macAddr;
                    echo "<br />thingID: $macAddr<br />Version: $VERSION <br /><br />";
                    
                    // Get uptime information
                    $uptime = shell_exec('uptime');
                    echo "<div id='uptimeDisplay'>Server Uptime: $uptime</div><br /><br />";
                    
                    echo "<div id='calibrationTime'></div><div id='filterStatusDiv'></div>";
                ?>
                
                <script>
                    function updateUptime() {
                        var xhttp = new XMLHttpRequest();
                        xhttp.onreadystatechange = function() {
                            if (this.readyState == 4 && this.status == 200) {
                                document.getElementById("uptimeDisplay").innerHTML = "Server Uptime: " + this.responseText;
                            }
                        };
                        xhttp.open("GET", "<?php echo $_SERVER['PHP_SELF']; ?>?get_uptime=1", true);
                        xhttp.send();
                    }
                    
                    setInterval(updateUptime, 300000); // Update every 5 minutes
                </script>
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
                            <!-- Tabs navigation -->
                            <ul class="nav nav-tabs" id="logTabs" role="tablist">
                                <li class="nav-item">
                                    <a class="nav-link active" id="large-files-tab" data-toggle="tab" href="#large-files" role="tab" aria-controls="large-files" aria-selected="true">Logs over 2KB</a>
                                </li>
                                <li class="nav-item">
                                    <a class="nav-link" id="small-files-tab" data-toggle="tab" href="#small-files" role="tab" aria-controls="small-files" aria-selected="false">Logs with very few samples</a>
                                </li>
                            </ul>
                            
                            <!-- Tab content -->
                            <div class="tab-content">
                                <!-- Tab for large files -->
                                <div class="tab-pane fade show active" id="large-files" role="tabpanel" aria-labelledby="large-files-tab">
                                    <table class='container'>
                                        <thead>
                                            <tr>
                                                <th>Download log from</th>
                                                <th>File Size</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            <?php
                                            $hostname = $_SERVER['HTTP_HOST'];
                                            // List all .csv files in logs directory
                                            $dir = "../logs";
                                            $files = scandir($dir);
                                            
                                            foreach ($files as $file) :
                                                if (pathinfo($file, PATHINFO_EXTENSION) === 'csv' && $file != 'log_current.csv') :
                                                    // Get file size
                                                    $file_size = filesize($dir . '/' . $file);
                                                    $file_size_kb = $file_size / 1024;
                                                    
                                                    if ($file_size_kb >= 2) {
                                                        // Extract the date and time from the filename
                                                        $date_time = explode("_", substr($file, 0, -4))[1];
                                                        $date_time_day = explode("_", substr($file, 0, -4))[0];
                                                        $date_time = $date_time_day . " " . substr($date_time, 0, 2) . ":" . substr($date_time, 2, 2) . ":" . substr($date_time, 4, 2);
                                            ?>
                                                        <tr>
                                                            <td><?= $date_time ?></td>
                                                            <td><?= number_format($file_size_kb, 2) ?> KB</td>
                                                            <td>
                                                                <a href='<?= $dir . "/" . $file ?>' download='<?= $hostname . '_' . $file; ?>'>
                                                                    <button type="button" class='btn btn-primary'>Download</button>
                                                                </a>
                                                            </td>
                                                        </tr>
                                            <?php
                                                    }
                                                endif;
                                            endforeach;
                                            ?>
                                        </tbody>
                                    </table>
                                </div>
                                
                                <!-- Tab for small files -->
                                <div class="tab-pane fade" id="small-files" role="tabpanel" aria-labelledby="small-files-tab">
                                    <table class='container'>
                                        <thead>
                                            <tr>
                                                <th>Download log from</th>
                                                <th>File Size</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            <?php
                                            foreach ($files as $file) :
                                                if (pathinfo($file, PATHINFO_EXTENSION) === 'csv' && $file != 'log_current.csv') :
                                                    // Get file size
                                                    $file_size = filesize($dir . '/' . $file);
                                                    $file_size_kb = $file_size / 1024;
                                                    
                                                    if ($file_size_kb < 2) {
                                                        // Extract the date and time from the filename
                                                        $date_time = explode("_", substr($file, 0, -4))[1];
                                                        $date_time_day = explode("_", substr($file, 0, -4))[0];
                                                        $date_time = $date_time_day . " " . substr($date_time, 0, 2) . ":" . substr($date_time, 2, 2) . ":" . substr($date_time, 4, 2);
                                            ?>
                                                        <tr style="font-style: italic;" title="very few samples">
                                                            <td><?= $date_time ?></td>
                                                            <td><?= number_format($file_size_kb, 2) ?> KB</td>
                                                            <td>
                                                                <a href='<?= $dir . "/" . $file ?>' download='<?= $hostname . '_' . $file; ?>'>
                                                                    <button type="button" class='btn btn-primary'>Download</button>
                                                                </a>
                                                            </td>
                                                        </tr>
                                            <?php
                                                    }
                                                endif;
                                            endforeach;
                                            ?>
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-dismiss="modal">Cancel</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Edit Hostname Modal -->
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

        <!-- System Logs Modal -->
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
                            <?php if ($compair_upload === true): ?>
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
                            <?php endif; ?>
                        </div>
                        
                        <br />
                        
                        <form method="post" action="">
                            <input type="submit" name="syslog" value="Download logs" class="btn btn-info" style="display: block;width: 50%;margin: 0 auto;" />
                        </form>
                        <br />
                        <p style="display:block; margin: 0 auto;">In case of problems, please download the logs and send it to jd@bcmeter.org!</p>
                    </div>
                </div>
            </div>
        </div>
                
        <?php
        // Define tab titles and parameter types
        $tabs = [
            "session" => "Session Parameters",
            "device" => "Device Parameters",
            "administration" => "Administration Parameters",
            "email" => "Email Parameters",
            "compair" => "COMPAIR Parameters"
        ];
        ?>
                
        <!-- Device Parameters Modal -->
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
                                <?php foreach ($tabs as $type => $title): ?>
                                    <li class="nav-item">
                                        <a class="nav-link <?php if ($type === 'session') echo 'active'; ?>" id="<?= $type ?>-tab" data-toggle="tab" href="#<?= $type ?>" role="tab" aria-controls="<?= $type ?>" aria-selected="<?= $type === 'session' ? 'true' : 'false' ?>"><?= $title ?></a>
                                    </li>
                                <?php endforeach; ?>
                            </ul>
                            <!-- Tab panes -->
                            <div class="tab-content">
                                <?php foreach ($tabs as $type => $title): ?>
                                    <div class="tab-pane <?php if ($type === 'session') echo 'active'; ?>" id="<?= $type ?>" role="tabpanel" aria-labelledby="<?= $type ?>-tab">
                                        <!-- <?= $title ?> parameters form -->
                                        <form id="<?= $type ?>-parameters-form">
                                            <table class="table table-bordered">
                                                <thead>
                                                    <tr>
                                                        <th scope="col" style="width: 90%;" data-toggle="tooltip" data-placement="top" title="Variable Name">Description</th>
                                                        <th scope="col" style="width: 10%;">Value</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    <!-- Dynamic <?= $title ?> Configuration Rows Will Be Inserted Here by JavaScript -->
                                                </tbody>
                                            </table>
                                            <button type="button" class="btn btn-primary" id="save<?= ucfirst($type) ?>Settings">Save <?= $title ?> Settings</button>
                                        </form>
                                    </div>
                                <?php endforeach; ?>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
                
        <!-- WiFi Setup Modal -->
        <div class="modal fade" id="wifisetup" tabindex="-1" role="dialog" aria-labelledby="exampleModalCenterTitle2" aria-hidden="true">
            <div class="modal-dialog modal-dialog-centered modal-lg" role="document">
                <div class="modal-content">
                    <div class="modal-header">
                        <h2 class="modal-title" id="exampleModalLongTitle" style="text-align: center;">Select your Network</h2>
                        <button type="button" class="close" data-dismiss="modal" aria-label="Close">
                            <span aria-hidden="true">&times;</span>
                        </button>
                    </div>
                    <div class="modal-body p-4">
                        <?php
                        // WiFi setup logic
                        //languages
                        if(isset($_GET['lang']) && in_array($_GET['lang'],['nl', 'en', 'si', 'es', 'de', 'fr'])) {
                            $lang = $_GET['lang'];
                            $_SESSION['lang'] = $lang;
                        } else {
                            $lang = isset($_SESSION['lang']) ? $_SESSION['lang'] : 'en';
                        }
                        require_once("lang/lang.".$lang.".php");
                        
                        //mac address and checksum
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
                        $wifiFile=$baseDir.'/bcMeter_wifi.json';
                        
                        $currentWifiSsid=null;
                        $currentWifiPwd=null;
                        $sendBackground=true;
                        $credsUpdated=false;
                        
                        // save wifi credentials to json file
                        if (isset($_POST['conn_submit'])) {
                            $wifi_ssid=null;
                            if(trim($_POST['wifi_ssid'])==='custom-network-selection'){     //Own custom network, not in the network list
                                $wifi_ssid = trim($_POST['custom_wifi_name']);
                            } else {
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
                            $wifiFile=$baseDir . '/bcMeter_wifi.json';
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
                            // get the pid for the bcMeter_ap_control_loop service
                            exec('systemctl show --property MainPID --value bcMeter_ap_control_loop.service', $output);
                            $pid=$output[0];
                            
                            if($pid==0){
                                echo("<div class='error'>". $language["service_not_running"]." Check logs and reconnect manually by button below.</div>");
                            } else {
                                // send SIGUSR1 signal to the bcMeter_ap_control_loop service
                                $interruptSent=true;
                            }
                        }
                        ?>
                        
                        <script>
                        var currentWifiSsid = "<?php echo $currentWifiSsid; ?>";
                        </script>
                        
                        <h4 class="mb-4">Select your Network</h4>
                      
                        <form name="conn_form" method="POST" action="index.php">
                            <!-- Network Selection -->
                            <div class="mb-4">
                                <label class="mb-2">WiFi Network</label>
                                <div class="d-flex gap-2">
                                    <select name="wifi_ssid" id="js-wifi-dropdown" class="form-control">
                                        <?php if ($currentWifiSsid === null) { ?>
                                            <option selected><?php echo $language["wifi_network_loading_short"]; ?></option>
                                        <?php } else { ?>
                                            <option selected><?php echo $currentWifiSsid; ?></option>
                                        <?php } ?>
                                        <option value="custom-network-selection"><?php echo $language["add_custom_network"]; ?></option>
                                    </select>
                                    <button type="button" id="refreshWifi" class="btn btn-outline-secondary">
                                        Rescan
                                    </button>
                                </div>
                                <!-- Add the custom network input field (initially hidden) -->
                                <div id="custom-network-input" class="mt-2" style="display: none;">
                                    <input type="text" name="custom_wifi_name" class="form-control" placeholder="Enter network name">
                                </div>
                            </div>
                
                            <!-- Password Field -->
                            <div class="mb-4">
                                <div class="input-group">
                                    <input type="password" id="pass_log_id" name="wifi_pwd" class="form-control" placeholder="Password">
                                    <button type="button" class="btn btn-outline-secondary toggle-password px-3">
                                        <i class="far fa-eye"></i>
                                    </button>
                                </div>
                            </div>
                
                            <!-- Action Buttons -->
                            <div>
                                <form id="connectionForm">
                                    <button type="submit" name="conn_submit" class="btn btn-primary">Save & Connect</button>
                                </form>
                
                                <div id="progressContainer" class="mt-4" style="display: none;">
                                    <div class="alert alert-info">
                                        Attempting to connect to WiFi network...
                                    </div>
                                    <div class="progress">
                                        <div class="progress-bar progress-bar-striped progress-bar-animated" 
                                             role="progressbar" 
                                             aria-valuenow="0" 
                                             aria-valuemin="0" 
                                             aria-valuemax="100">
                                            0%
                                        </div>
                                    </div>
                                </div>
                
                                <button type="submit" name="cancel" class="btn btn-secondary" data-dismiss="modal">Cancel</button>
                                <button type="button" class="btn btn-danger" data-toggle="modal" data-target="#deleteWifiModal">Delete Wifi</button>
                                <button type="submit" name="force_wifi" class="btn btn-info">Reconnect</button>
                            </div>
                        </form>
                    </div>
                </div>
            </div>
        </div>
                
        <!-- Delete WiFi Modal -->
        <div class="modal fade" id="deleteWifiModal" tabindex="-1" role="dialog" aria-labelledby="deleteWifiModalLabel" aria-hidden="true">
            <div class="modal-dialog" role="document">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title" id="deleteWifiModalLabel">Confirm Delete</h5>
                        <button type="button" class="close" data-dismiss="modal" aria-label="Close">
                            <span aria-hidden="true">&times;</span>
                        </button>
                    </div>
                    <div class="modal-body">
                        This will delete the saved WiFi credentials and switch the bcMeter to run as Hotspot. Continue?
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-dismiss="modal">No</button>
                        <form method="POST" style="display: inline;">
                            <button type="submit" name="reset_wifi_json" class="btn btn-danger">Yes</button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- JavaScript Libraries -->
    <script src="js/d3.min.js"></script>
    <script src="js/jquery-3.6.0.min.js"></script>
    <script src="js/bootstrap.min.js"></script>
    <script src="js/bootbox.min.js"></script>
    <script src="js/bootstrap4-toggle.min.js"></script>
    <script>
        // Pass PHP variables to JavaScript
        var is_hotspot = <?php echo json_encode($is_hotspot); ?>;
        var logFiles = <?php echo json_encode($logFiles); ?>;
    </script>
    
    <!-- Our Custom JavaScript -->
    <script src="js/d3plotting.js"></script>
    <script src="js/interface.js"></script>
</body>
</html>