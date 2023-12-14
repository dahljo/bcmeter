<?php
if (isset($_GET['logName'])) {
    $logName = $_GET['logName'];
    $logFilePath = '/path/to/' . $logName . '.log'; // Replace with the actual path to your log files
    $lines = file($logFilePath);
    
    // Output the content of the log file
    foreach ($lines as $line) {
        echo $line;
    }
}
?>
