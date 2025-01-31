from flask import Flask, jsonify, request
import os
import datetime
import logging
from flask_cors import CORS
from werkzeug.utils import secure_filename
from concurrent.futures import ThreadPoolExecutor
import shutil
import time

app = Flask(__name__)
CORS(app)

BASE_UPLOAD_FOLDER = os.path.join(os.path.expanduser("~"), "Documents", "HauntAI_Uploads")
TEMP_UPLOAD_FOLDER = os.path.join(BASE_UPLOAD_FOLDER, "temp")
MAX_CONTENT_LENGTH = 1024 * 1024 * 1024  # 1GB
CHUNK_SIZE = 1024 * 1024 * 10  # 10MB chunks

os.makedirs(BASE_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMP_UPLOAD_FOLDER, exist_ok=True)

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

upload_status = {
    "uploaded": False,
    "analyzed": False,
    "current_session": None,
    "files_processed": 0
}

executor = ThreadPoolExecutor(max_workers=4)

def save_chunk(chunk_data, chunk_path):
    start_time = time.time()
    with open(chunk_path, 'wb') as f:
        f.write(chunk_data)
    duration = time.time() - start_time
    logger.info(f"[CHUNK] Saved {len(chunk_data)/1024/1024:.2f}MB in {duration:.2f}s")

@app.route('/upload-chunk', methods=['POST'])
def upload_chunk():
    if 'file' not in request.files:
        logger.error("No file chunk in request")
        return jsonify({"error": "No file chunk in request"}), 400
    
    file_chunk = request.files['file']
    session_id = request.form.get('sessionId')
    start_position = int(request.form.get('start'))
    filename = request.form.get('filename')
    total_size = int(request.form.get('total_size'))
    
    logger.info(f"[UPLOAD] Receiving chunk for {filename}: {start_position}/{total_size} bytes")
    
    temp_folder = os.path.join(TEMP_UPLOAD_FOLDER, session_id, secure_filename(filename))
    os.makedirs(temp_folder, exist_ok=True)
    
    chunk_path = os.path.join(temp_folder, f"chunk_{start_position}")
    try:
        start_time = time.time()
        save_chunk(file_chunk.read(), chunk_path)
        duration = time.time() - start_time
        
        progress = (start_position + file_chunk.content_length) / total_size * 100
        logger.info(f"[PROGRESS] {filename}: {progress:.1f}% ({duration:.2f}s)")
        
        return jsonify({
            "message": "Chunk uploaded successfully",
            "status": {
                "filename": filename,
                "position": start_position,
                "total_size": total_size
            }
        }), 200
    except Exception as e:
        logger.error(f"[ERROR] Saving chunk failed: {e}")
        return jsonify({"error": str(e)}), 500

def merge_file_chunks(source_folder, destination_path):
    start_time = time.time()
    filename = os.path.basename(destination_path)
    logger.info(f"[MERGE] Starting merge for {filename}")
    
    chunk_files = sorted(
        os.listdir(source_folder), 
        key=lambda x: int(x.split('_')[1])
    )
    
    with open(destination_path, 'wb') as outfile:
        buffer_size = 8 * 1024 * 1024  # 8MB buffer
        for chunk_name in chunk_files:
            chunk_path = os.path.join(source_folder, chunk_name)
            with open(chunk_path, 'rb') as chunk:
                shutil.copyfileobj(chunk, outfile, buffer_size)
    
    duration = time.time() - start_time
    size_mb = os.path.getsize(destination_path) / 1024 / 1024
    logger.info(f"[MERGE] Completed {filename}: {size_mb:.2f}MB in {duration:.2f}s")

@app.route('/finalize-upload', methods=['POST'])
def finalize_upload():
    try:
        start_time = time.time()
        data = request.json
        session_id = data['sessionId']
        
        logger.info(f"[FINALIZE] Starting session {session_id}")
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        final_folder = os.path.join(BASE_UPLOAD_FOLDER, timestamp)
        os.makedirs(final_folder, exist_ok=True)
        
        session_temp_folder = os.path.join(TEMP_UPLOAD_FOLDER, session_id)
        saved_files = []
        futures = []

        # Process files in parallel
        for file_temp_folder in os.listdir(session_temp_folder):
            source_folder = os.path.join(session_temp_folder, file_temp_folder)
            destination_path = os.path.join(final_folder, file_temp_folder)
            futures.append(
                executor.submit(merge_file_chunks, source_folder, destination_path)
            )
            saved_files.append(destination_path)

        # Wait for all merges to complete
        for future in futures:
            future.result()

        # Clean up temp files
        shutil.rmtree(session_temp_folder)
        duration = time.time() - start_time
        logger.info(f"[FINALIZE] Completed in {duration:.2f}s. Files saved: {len(saved_files)}")
        
        upload_status["uploaded"] = True
        upload_status["analyzed"] = False
        
        return jsonify({
            "message": "Files uploaded successfully",
            "saved_files": saved_files,
            "folder": final_folder,
            "upload_status": upload_status
        }), 200
        
    except Exception as e:
        logger.error(f"[ERROR] Finalize failed: {e}")
        upload_status["uploaded"] = False
        return jsonify({
            "error": str(e),
            "upload_status": upload_status
        }), 500

@app.route('/status', methods=['GET'])
def get_status():
    return jsonify(upload_status)

if __name__ == '__main__':
    logger.info(f"[START] Server running. Upload folder: {BASE_UPLOAD_FOLDER}")
    app.run(debug=True, host='0.0.0.0', port=5000)
