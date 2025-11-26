<?php
session_start();
if (!isset($_SESSION['valid_session'])) {
    echo "<script>setTimeout(function(){window.location.replace('/interface/index.php');}, 4000);</script>";
    exit();
}

session_write_close();
header('X-Accel-Buffering: no');

while (ob_get_level() > 0) {
    ob_end_flush();
}
ini_set('output_buffering', 'off');
ini_set('zlib.output_compression', 0);
ini_set('implicit_flush', 1);
ob_implicit_flush(1);

$baseDir = file_exists('/home/bcmeter') ? '/home/bcmeter' : (file_exists('/home/bcMeter') ? '/home/bcMeter' : '/home/pi');


if (isset($_GET['status']) && $_GET['status'] === 'syslog') {
    $timestamp = date('Ymd_His');
    $hostname = gethostname();
    $zipFilePath = '/tmp/syslog_and_maintenance_logs_' . $hostname . '_' . $timestamp . '.zip';
    $additionalSyslog = file_exists('/var/log/syslog.1') ? '/var/log/syslog.1' : '';
    
    $zipCommand = "sudo zip -j $zipFilePath /var/log/syslog $baseDir/maintenance_logs/* $additionalSyslog";
    shell_exec($zipCommand);

    if (file_exists($zipFilePath)) {
        while (ob_get_level()) ob_end_clean(); 
        header('Content-Description: File Transfer');
        header('Content-Type: application/zip');
        header('Content-Disposition: attachment; filename=' . basename($zipFilePath));
        header('Content-Transfer-Encoding: binary');
        header('Expires: 0');
        header('Cache-Control: must-revalidate');
        header('Pragma: public');
        header('Content-Length: ' . filesize($zipFilePath));
        readfile($zipFilePath);
        unlink($zipFilePath);
        exit();
    }
}


function checkUpdate($path) {
    $local = '0.9.20';
    $remote = '0.9.19';
    if ($content = @file_get_contents($path)) {
        preg_match('/bcMeter_version\s*=\s*"([0-9.]+)"/', $content, $m);
        if ($m) $local = $m[1];
    }
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

function checkUndervoltage() {
    $styles = [
        'red' => "<span class='text-danger font-weight-bold'>",
        'black' => "<span class='text-dark'>",
        'reset' => "</span>"
    ];
    $today = date('M d');
    $timeFilter = date('Y-m-d H:i:s', strtotime('-10 minutes'));
    $output = shell_exec("sudo tac /var/log/syslog | awk '/Linux version/ {exit} {print}' | grep -a 'Undervoltage' | awk -v time='$timeFilter' '$0 >= time'");
    $lines = array_filter(explode("\n", trim($output)));
    if (count($lines) <= 4) return "";
    $response = "<div class='text-center'>{$styles['red']}<strong>WARNING</strong>: Frequent undervoltage detected - Please use a 5.25V, 3A power supply and a short cable.{$styles['reset']}<br><br>";
    foreach ($lines as $line) {
        $style = (strpos($line, $today) !== false) ? 'red' : 'black';
        $response .= "{$styles[$style]}{$line}{$styles['reset']}<br>";
    }
    $response .= "<br /><button class='btn btn-danger mt-3' onclick='ignoreWarning()'>Ignore undervoltage warning</button></div><br />";
    return $response;
}

function getPID() {
    global $baseDir;
    $version = '';
    $localfile = $baseDir . '/bcMeter.py';
    for($i = 1; $i <= 50; $i++) {
        $line = trim(exec("head -$i $localfile| tail -1"));
        if (strpos($line, 'bcMeter_version') === 0) {
            $version = explode('"', $line)[1];
            break;
        }
    }
    echo "The version is $version";
    $version_parts = explode('.', $version);
    $VERSION = implode('.', array_slice($version_parts, 0, 3));
    $grep = shell_exec('ps -eo pid,lstart,cmd | grep bcMeter.py | grep -Fv grep | grep -Fv www-data | grep -Fv sudo | grep -Fiv screen | grep python3');
    $numbers = preg_replace('/^\s+| python3 \/home\/pi\/bcMeter.py/', "", $grep);
    $numbers = explode(" ", $numbers);
    $PID = $numbers[0] ?? '';
    $STARTED = !empty($numbers[1]) ? implode(" ", array_slice($numbers, 1)) : '';
    if (empty($grep)) {
        echo "<pre style='text-align:center;'>bcMeter stopped.<br/></pre>";
    } else {
        echo "<pre style='text-align:center;'>Running with PID $PID since $STARTED <br /> v$VERSION </pre>";
    }
    return $PID;
}

function sendOutput($output) {
    echo $output;
    flush();
}

function executeCommand($cmd) {
    $proc = popen($cmd . ' 2>&1', 'r');
    echo '<pre>';
    flush();
    while (!feof($proc)) {
        echo fread($proc, 1024);
        flush();
    }
    echo '</pre>';
    flush();
    pclose($proc);
}

function delete_single_log($filename) {
    if (!preg_match('/^\d{2}-\d{2}-\d{2}_\d{6}\.csv$/', $filename)) return "Invalid filename format";
    $filepath = realpath("../../logs/" . basename($filename));
    if (!$filepath || strpos($filepath, realpath("../../logs")) !== 0) return "Invalid file path";
    if (!file_exists($filepath)) return "File not found";
    if (unlink($filepath)) return true;
    return "Permission denied";
}

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['status']) && $_POST['status'] === 'undervolt') {
    echo checkUndervoltage();
    exit();
}

$connected = @fsockopen('www.google.com', 80) ? true : false;
shell_exec('sudo systemctl daemon-reload');
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>bcMeter Status</title>
    <link rel="stylesheet" type="text/css" href="css/bootstrap.min.css">
    <style>
        html, body {
            font-family: sans-serif;
            margin: 0;
            padding: 0;
        }
    </style>
</head>
<body>
    <a href="../index.php">
        <img src="../bcMeter-logo.png" style="width: 300px; display:block; margin: 0 auto;"/>
        <div style="text-align:center">Back to interface</div>
    </a>

    <script src="../../js/jquery-3.6.0.min.js"></script>
    <script src="../../js/bootstrap.min.js"></script>
    <script src="../../js/bootbox.min.js"></script>

    <h3 style="text-align: center">
    <?php
    $status = $_GET['status'] ?? '';

    switch($status) {

        case 'change_hostname':
            if (isset($_GET['new_hostname'])) {
                $new_hostname = $_GET['new_hostname'];
                $success = true;
                $errors = [];
                if (!preg_match('/^[a-zA-Z0-9-]{1,63}$/', $new_hostname)) die("Invalid hostname format");
                $setHostname = 'sudo raspi-config nonint do_hostname '. escapeshellarg($new_hostname);
                exec($setHostname, $output, $returnCode);
                if ($returnCode !== 0) {
                    $success = false;
                    $errors[] = "Failed to set hostname (exit code: $returnCode)";
                }
                $hostapd_conf = '/etc/hostapd/hostapd.conf';
                $sedCommand = sprintf("sudo sed -i.backup 's/^ssid=.*/ssid=%s/' %s", escapeshellarg($new_hostname), escapeshellarg($hostapd_conf));
                exec($sedCommand, $output, $sedReturn);
                if ($sedReturn === 0) {
                    $grepCommand = sprintf("sudo grep -q '^ssid=%s$' %s", escapeshellarg($new_hostname), escapeshellarg($hostapd_conf));
                    exec($grepCommand, $output, $grepReturn);
                    if ($grepReturn === 0) {
                        echo "<div class='success'>✓ Hostname will change to '$new_hostname' and WiFi SSID will be updated on next reboot.</div>";
                        error_log("Successfully updated hostname and SSID to $new_hostname");
                    } else {
                        $errors[] = "WiFi SSID update verification failed";
                        exec("sudo mv ${hostapd_conf}.backup $hostapd_conf");
                    }
                } else {
                    $errors[] = "Failed to update WiFi SSID in hostapd config";
                }
                if (!empty($errors)) {
                    echo "<div class='error'>× Some operations failed:</div><ul>";
                    foreach ($errors as $error) {
                        echo "<li>$error</li>";
                        error_log("Hostname change error: $error");
                    }
                    echo "</ul>";
                }
            }
            echo "</pre><script>setTimeout(function(){window.location.replace('/interface/index.php');}, 5000);</script>";
            break;

        case 'debug':
            echo "Debug mode activated";
            break;

        case 'deleteOld':
            $files = glob('../../logs/*.csv');
            array_multisort(array_map('filemtime', $files), SORT_NUMERIC, SORT_DESC, $files);
            $recentFiles = array_slice($files, 0, 2);
            foreach (array_diff($files, $recentFiles) as $file) unlink($file);
            $maint_files = glob('../../maintenance_logs/*.csv');
            array_multisort(array_map('filemtime', $maint_files), SORT_NUMERIC, SORT_DESC, $maint_files);
            $recent_maint_files = array_slice($maint_files, 0, 3);
            $install_files = array_filter($maint_files, function($file) { return strpos($file, 'install') !== false; });
            $files_to_keep = array_unique(array_merge($recent_maint_files, $install_files));
            foreach (array_diff($maint_files, $files_to_keep) as $file) unlink($file);
            echo "<pre style='text-align:center'><h2>Successfully deleted old logs</h2>Returning to Interface in a few seconds or click <a href='/interface/index.php'>here</a></pre>";
            echo "<script>setTimeout(function(){window.location.replace('/interface/index.php');}, 4000);</script>";
            break;

        case 'reboot':
            $wifiFile = $baseDir . '/bcMeter_wifi.json';
            $data = json_decode(file_get_contents($wifiFile), true);
            $wifi_pwd = $data["wifi_pwd"] ?? '';
            $wifi_ssid = $data["wifi_ssid"] ?? '';
            $bcMeter_hotspot_address = "http://192.168.18.8";
            $bcMeter_hostname = gethostname();
            $bcMeter_wifi_address = "http://$bcMeter_hostname.local";
            if (empty($wifi_pwd)) {
                echo "<pre style='text-align:center'><h2>Rebooting to hotspot mode</h2>";
                echo "Connect to WiFi called bcMeter when it shows up in a minute or two before you connect to <a href='$bcMeter_hotspot_address'>$bcMeter_hotspot_address</a>.";
            } else {
                echo "<pre style='text-align:center'><h2>Rebooting and logging into WiFi $wifi_ssid</h2>";
                echo "You can access your bcMeter then at <br /> <a href='$bcMeter_wifi_address'>$bcMeter_wifi_address</a> <br /> I will try to automatically redirect in about a minute.";
                echo "</pre><script>setTimeout(function(){window.location.replace('$bcMeter_wifi_address');}, 70000);</script>";
            }
            exec('sudo reboot now');
            break;

        case 'shutdown':
            echo "bcMeter will now shutdown<br />You may disconnect the power source in about 20 seconds.<br /><br /><pre>";
            exec('sudo shutdown now');
            echo "</pre><script>setTimeout(function(){window.location.replace('/interface/index.php');}, 10000);</script>";
            break;

        case 'debug':
            echo "debug log<br /><br /><pre>";
            $cmd = 'sudo python3 ' . $baseDir . '/bcMeter.py debug';
            while (@ ob_end_flush());
            $proc = popen($cmd, 'r');
            echo '<pre>';
            echo '</pre><br /> <h3>copy and paste this to <a href="mailto:jd@bcmeter.org">jd@bcmeter.org</a><br /> <br /><a href="index.php">Go back to interface</a>';
            break;

        case 'update':
            if (!isset($_SESSION['update_in_progress'])) {
                $_SESSION['update_in_progress'] = true;
                if ($connected) {
                    echo "bcMeter will now update, this may take a few minutes. <br /><br /><pre>";
                    $cmd = "screen -dmS bcMeterUpdate bash -c 'cd $baseDir && sudo wget -N https://raw.githubusercontent.com/bcmeter/bcmeter/main/install.sh -P $baseDir && sudo bash $baseDir/install.sh update'";
                    $proc = popen($cmd, 'r');
                    sendOutput('<pre>');
                    while (!feof($proc)) {
                        $output = fread($proc, 4096);
                        sendOutput($output);
                    }
                    pclose($proc);
                    $logContent = file_get_contents($baseDir . '/maintenance_logs/bcMeter_install.log');
                    sendOutput($logContent);
                    echo "</pre><script>setTimeout(function(){window.location.replace('/interface/index.php');}, 30000);</script>";
                } else {
                    echo "<pre style='text-align:center'>bcMeter seems not to be online! Change WiFi and try again</pre>";
                }
                echo "Wait for automatic redirect... <script>setTimeout(function(){window.location.replace('/interface/index.php');}, 10000);</script>";
                unset($_SESSION['update_in_progress']);
            }
            break;

       
        case 'calibration':
            echo 'Starting calibration... Takes a minute<br>';
            flush();
            $cmd1 = 'sudo systemctl stop bcMeter';
            executeCommand($cmd1);
            flush();
            sleep(2);
            $cmd2 = "sudo python3 -u $baseDir/bcMeter.py cal";
            executeCommand($cmd2);
            flush();
            echo "Calibration complete. You may return to interface. ";
            flush();
            break;

        case 'delete_all_small_logs':
            $deleted = 0;
            $files = glob('../../logs/*.csv');
            usort($files, function($a, $b) { return filemtime($b) - filemtime($a); });
            if (count($files) > 0) $mostRecentFile = array_shift($files);
            foreach ($files as $file) {
                if (filesize($file) < 2048 && preg_match('/^\d{2}-\d{2}-\d{2}_\d{6}\.csv$/', basename($file))) {
                    if (unlink($file)) $deleted++;
                }
            }
            echo "<div class='alert alert-success'>Deleted $deleted small log files. The most recent log was preserved.</div>";
            echo "<script>setTimeout(function(){window.location.replace('/interface/index.php');}, 2000);</script>";
            break;

        case 'delete_log':
            $file = isset($_GET['file']) ? $_GET['file'] : '';
            $allFiles = glob('../../logs/*.csv');
            usort($allFiles, function($a, $b) { return filemtime($b) - filemtime($a); });
            $mostRecentFile = count($allFiles) > 0 ? basename($allFiles[0]) : '';
            if ($file === $mostRecentFile) {
                echo '<div class="alert alert-warning">Cannot delete the most recent log file as it may be the current sampling session.</div>';
            } else {
                $result = delete_single_log($file);
                if ($result === true) {
                    echo '<div class="alert alert-success">Log file deleted successfully.</div>';
                } else {
                    echo '<div class="alert alert-danger">Error deleting log file: ' . $result . '</div>';
                }
            }
            echo "<script>setTimeout(function(){window.location.replace('/interface/index.php');}, 2000);</script>";
            break;

        default:
            getPID();
    }
    ?>
    </h3>
</body>
</html>
