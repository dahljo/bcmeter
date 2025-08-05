try:
    from flask import Flask, jsonify, request
except ImportError:
    print("flask not installed")
from flask_cors import CORS
import os
import json

base_dir = '/home/bcmeter' if os.path.isdir('/home/bcmeter') else '/home/bcMeter' if os.path.isdir('/home/bcMeter') else '/home/pi'

app = Flask(__name__)
# Enable CORS for all domains on all routes
CORS(app)

config_file_path = base_dir + '/bcMeter_config.json'

@app.route('/load-config', methods=['GET'])
def load_config():
    if os.path.exists(config_file_path):
        with open(config_file_path, 'r') as config_file:
            config = json.load(config_file)
            return jsonify(config), 200
    else:
        return jsonify({"error": "Configuration file not found."}), 404

@app.route('/save-config', methods=['POST'])
def save_config():
    config_data = request.json
    with open(config_file_path, 'w') as config_file:
        json.dump(config_data, config_file, indent=4)
        return jsonify({"message": "Configuration saved successfully."}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
