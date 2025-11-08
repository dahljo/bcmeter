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

$newHostname = preg_replace('/[^a-zA-Z0-9\-]/', '', trim($_POST['hostname']));
if ($newHostname === '') {
    http_response_code(400);
    echo json_encode(['error' => 'Invalid hostname']);
    exit;
}

exec("sudo hostnamectl set-hostname " . escapeshellarg($newHostname) . " > /dev/null 2>&1", $output, $returnCode);

if ($returnCode === 0) {
    file_put_contents('/etc/hostname', $newHostname . PHP_EOL);
    exec("sudo sed -i 's/127.0.1.1.*/127.0.1.1 $newHostname/' /etc/hosts");
    echo json_encode(['success' => true, 'hostname' => $newHostname]);
} else {
    http_response_code(500);
    echo json_encode(['error' => 'Failed to set hostname']);
}
