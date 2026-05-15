<?php
header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['error' => 'Method not allowed']);
    exit;
}

if (empty($_POST['hostname'])) {
    http_response_code(400);
    echo json_encode(['error' => 'Missing hostname']);
    exit;
}

$newHostname = trim($_POST['hostname']);
if (!preg_match('/^[a-zA-Z0-9-]{1,63}$/', $newHostname)) {
    http_response_code(400);
    echo json_encode(['error' => 'Invalid hostname format']);
    exit;
}

$errors = [];

exec('sudo raspi-config nonint do_hostname ' . escapeshellarg($newHostname), $output, $returnCode);

if ($returnCode !== 0) {
    $errors[] = "Failed to set system hostname (Exit code: $returnCode)";
    http_response_code(500);
}

exec("sudo sed -i 's/127.0.1.1.*/127.0.1.1 " . escapeshellarg($newHostname) . "/' /etc/hosts");

if (empty($errors)) {
    echo json_encode(['success' => true, 'hostname' => $newHostname]);
} else {
    echo json_encode(['success' => false, 'error' => implode(', ', $errors)]);
}
?>