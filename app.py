import sys
import os
import json
import tempfile

try:
    from flask import Flask, jsonify, request
    from flask_cors import CORS
except ImportError as e:
    print(f"Critical Import Error: {e}")
    sys.exit(1)

POSSIBLE_DIRS = ['/home/bcmeter', '/home/bcMeter', '/home/pi']
BASE_DIR = next((d for d in POSSIBLE_DIRS if os.path.isdir(d)), '/home/pi')
CONFIG_FILE_PATH = os.path.join(BASE_DIR, 'bcMeter_config.json')

app = Flask(__name__)
CORS(app)

@app.route('/load-config', methods=['GET'])
def load_config():
    if os.path.exists(CONFIG_FILE_PATH):
        try:
            with open(CONFIG_FILE_PATH, 'r') as config_file:
                config = json.load(config_file)
                return jsonify(config), 200
        except json.JSONDecodeError:
             return jsonify({"error": "Configuration file is corrupt"}), 500
    else:
        return jsonify({"error": "Configuration file not found"}), 404

@app.route('/save-config', methods=['POST'])
def save_config():
    config_data = request.get_json(force=True)

    if not config_data:
        return jsonify({"error": "No data provided"}), 400

    try:
        fd, temp_path = tempfile.mkstemp(dir=BASE_DIR, text=True)

        with os.fdopen(fd, 'w') as temp_file:
            json.dump(config_data, temp_file, indent=4)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.replace(temp_path, CONFIG_FILE_PATH)
        return jsonify({"message": "Configuration saved successfully"}), 200

    except Exception as e:
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True, use_reloader=False)