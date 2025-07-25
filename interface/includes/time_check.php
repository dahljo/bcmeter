<?php
header('Content-Type: application/json');

if (!isset($_POST['browser_time']) || !is_numeric($_POST['browser_time'])) {
  echo json_encode(['needs_sync' => true]);
  exit;
}

$browserTimestamp = (int)$_POST['browser_time'];
$deviceTimestamp = (int)exec('date +%s');
$timeDifference = abs($browserTimestamp - $deviceTimestamp);

echo json_encode([
  'needs_sync' => ($timeDifference >= 10),
  'time_diff' => $timeDifference,
  'device_time' => $deviceTimestamp,
  'browser_time' => $browserTimestamp
]);
?>