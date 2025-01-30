from flask import Flask, jsonify, request
import os
import datetime
import logging
from flask_cors import CORS

app = Flask(__name__)

CORS(app)

# Set MAX_CONTENT_LENGTH to limit the max file size to 1GB (1GB = 1024 * 1024 * 1024 bytes)
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1GB

# Path utama untuk menyimpan file
BASE_UPLOAD_FOLDER = os.path.join(os.path.expanduser("~"), "Documents", "HauntAI_Uploads")

# Pastikan folder utama ada
os.makedirs(BASE_UPLOAD_FOLDER, exist_ok=True)

# Konfigurasi logging
logging.basicConfig(level=logging.INFO)

# Status upload dan analisis
upload_status = {"uploaded": False, "analyzed": False}

@app.route('/')
def home():
    return 'Hello, Flask!'

@app.route('/upload', methods=['POST'])
def upload_file():
    global upload_status
    if 'files' not in request.files:
        return jsonify({"error": "No file part"}), 400

    files = request.files.getlist('files')
    if not files:
        return jsonify({"error": "No files received"}), 400

    # Buat folder unik berdasarkan timestamp
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    unique_folder = os.path.join(BASE_UPLOAD_FOLDER, timestamp)
    os.makedirs(unique_folder, exist_ok=True)
    logging.info(f"Saving files to: {unique_folder}")

    accepted_files = []
    for file in files:
        filename = os.path.basename(file.filename)  # Ambil nama file tanpa path
        filepath = os.path.join(unique_folder, filename)

        try:
            # Save the file to the disk
            file.save(filepath)
            logging.info(f"File saved: {filepath}")
            accepted_files.append(filepath)
        except Exception as e:
            logging.error(f"Error saving file {filename}: {e}")
            return jsonify({"error": f"Failed to save file {filename}"}), 500

    # Set status upload menjadi True
    upload_status["uploaded"] = True
    upload_status["analyzed"] = False

    return jsonify({
        "message": "File(s) uploaded and saved successfully",
        "saved_files": accepted_files,
        "upload_status": upload_status
    })

@app.route('/analyze', methods=['POST'])
def analyze_files():
    global upload_status
    if not upload_status["uploaded"]:
        return jsonify({"error": "No files uploaded to analyze"}), 400

    # Simulasi proses analisis
    logging.info("Analyzing files...")

    # Setelah selesai analisis, ubah status
    upload_status["analyzed"] = True
    upload_status["uploaded"] = False

    return jsonify({
        "message": "Files analyzed successfully",
        "upload_status": upload_status
    })

@app.route('/status', methods=['GET'])
def get_status():
    return jsonify(upload_status)

@app.errorhandler(413)
def handle_large_request(error):
    logging.error(f"Request terlalu besar: {request.content_length} bytes")
    return jsonify({"error": f"File terlalu besar, maksimum 1GB. Ukuran yang dikirim: {request.content_length / (1024 * 1024):.2f}MB"}), 413

if __name__ == '__main__':
    logging.info(f"Starting Flask app... Uploads will be saved in: {BASE_UPLOAD_FOLDER}")
    app.run(debug=True, host='0.0.0.0', port=5000)
