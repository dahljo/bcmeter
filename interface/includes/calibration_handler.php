<?php
header('Content-Type: application/json');

$baseDir = file_exists('/home/bcmeter') ? '/home/bcmeter' : (file_exists('/home/bcMeter') ? '/home/bcMeter' : '/home/pi');
$logFile = $baseDir . '/maintenance_logs/bcMeter.log';
$startTimeFile = '/tmp/bcmeter_calibration_start.time';
$php_path = '/usr/bin/php';

$response = [
    'status' => 'waiting',
    'message' => 'Waiting for log...'
];

if (isset($_POST['action']) && $_POST['action'] === 'start') {
    if (file_exists($startTimeFile)) {
        unlink($startTimeFile);
    }
    touch($startTimeFile);

    $command = "sudo /usr/bin/nohup $php_path $baseDir/interface/includes/run_calibration.php > /dev/null 2>&1 &";
    exec($command);

    echo json_encode(['status' => 'started']);
    exit;

} elseif (isset($_GET['action']) && $_GET['action'] === 'status') {

    if (!file_exists($startTimeFile)) {
        echo json_encode(['status' => 'error', 'message' => 'Calibration not initiated.']);
        exit;
    }

    $startTime = filemtime($startTimeFile);

    if ((time() - $startTime) < 8) {
        echo json_encode(['status' => 'running', 'message' => 'Initializing calibration sequence...']);
        exit;
    }

    $status = 'running';
    $lastLine = 'Waiting for log output...';

    if (file_exists($logFile)) {
        $lines = array_slice(file($logFile, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES), -50);

        if (!empty($lines)) {
            foreach ($lines as $line) {
                if (preg_match('/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3} - /', $line, $matches)) {
                    $logTime = strtotime($matches[1]);

                    if ($logTime < $startTime) {
                        continue;
                    }

                    $cleanMsg = trim(preg_replace('/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} - (INFO: |DEBUG: |ERROR: )?/', '', $line));
                    $lastLine = $cleanMsg;

                    if (strpos($line, 'Calibration completed at') !== false || strpos($line, 'Calibration done') !== false) {
                        $status = 'complete';
                    }

                    if (strpos($line, 'ERROR:') !== false) {
                        if (strpos($line, 'No ADC found on I2C bus') === false) {
                            $status = 'error';
                            $lastLine = "Error: " . $cleanMsg;
                        }
                    }
                }
            }
        }
    }

    echo json_encode(['status' => $status, 'message' => $lastLine]);
    exit;
}
?>