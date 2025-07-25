<?php
header('Content-Type: application/json');

$old_time = exec('date');
$old_timestamp = exec('date +%s');

if (!isset($_POST['timestamp']) || !is_numeric($_POST['timestamp'])) {
  echo json_encode([
    'success' => false, 
    'error' => 'Invalid timestamp', 
    'old_time' => $old_time,
    'show_modal' => false
  ]);
  exit;
}

$timestamp = (int)$_POST['timestamp'];
$show_modal = isset($_POST['show_modal']) ? (bool)$_POST['show_modal'] : false;

$set_time_command = "sudo date -s @$timestamp 2>&1";
$result = exec($set_time_command, $output, $return_code);

if ($return_code === 0) {
  exec("sudo hwclock --systohc");
}

$new_time = exec('date');
$new_timestamp = exec('date +%s');
$timezone_info = exec('date +%Z');

// Make sure to properly encode show_modal for JavaScript
$response = [
  'success' => ($return_code === 0),
  'old_time' => $old_time,
  'new_time' => $new_time,
  'old_timestamp' => (int)$old_timestamp,
  'new_timestamp' => (int)$new_timestamp,
  'timezone_info' => $timezone_info,
  'difference' => (int)$timestamp - (int)$old_timestamp,
  'show_modal' => (bool)$show_modal,
  'error' => ($return_code !== 0) ? implode("\n", $output) : null
];

echo json_encode($response);