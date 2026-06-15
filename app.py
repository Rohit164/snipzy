import os
import sys
import shutil
import uuid
import threading
from flask import Flask, request, render_template, jsonify, send_from_directory, url_for

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from main import PromptVideoCleaner, check_ffmpeg, RESOLUTION_MAP

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"mp4", "mov", "avi", "mkv", "webm"}

# job_id -> status dict
jobs = {}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def run_job(job_id, input_path, target_text, quality, output_path, ocr_every):
    jobs[job_id]["status"] = "processing"
    temp_dir = f"temp_{job_id}"
    DIR_FRAMES = f"{temp_dir}/frames"
    DIR_MASKS  = f"{temp_dir}/masks"
    DIR_CLEAN  = f"{temp_dir}/clean"

    def progress_cb(phase, pct, current, total):
        if phase == "scanning":
            jobs[job_id]["progress"] = f"Scanning frames for text... {pct}%"
        elif phase == "inpainting":
            jobs[job_id]["progress"] = f"Inpainting frames... {pct}%"
        jobs[job_id]["percent"] = pct

    try:
        cleaner = PromptVideoCleaner(ocr_scale=0.75)
        jobs[job_id]["progress"] = "Scanning frames for text... 0%"
        jobs[job_id]["percent"] = 0
        total, fps = cleaner.extract_and_mask(input_path, target_text, DIR_FRAMES, DIR_MASKS,
                                               ocr_every=ocr_every, progress_cb=progress_cb)

        jobs[job_id]["progress"] = "Inpainting frames... 0%"
        jobs[job_id]["percent"] = 0
        cleaner.inpaint_frames(DIR_FRAMES, DIR_MASKS, DIR_CLEAN, total, progress_cb=progress_cb)

        jobs[job_id]["progress"] = "Compiling video..."
        jobs[job_id]["percent"] = 99
        cleaner.compile_and_transcode(DIR_CLEAN, input_path, output_path, quality, fps)

        jobs[job_id]["status"] = "done"
        jobs[job_id]["percent"] = 100
        jobs[job_id]["output"] = os.path.basename(output_path)
    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        if os.path.exists(input_path):
            os.remove(input_path)


@app.route("/")
def index():
    return render_template("index.html", qualities=list(RESOLUTION_MAP.keys()))


@app.route("/upload", methods=["POST"])
def upload():
    if "video" not in request.files:
        return jsonify({"error": "No video file provided"}), 400

    file = request.files["video"]
    target_text = request.form.get("text", "").strip()
    quality = request.form.get("quality", "720p")
    ocr_every = int(request.form.get("ocr_every", 10))

    if not file or not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type"}), 400
    if not target_text:
        return jsonify({"error": "Please enter text to remove"}), 400

    job_id = str(uuid.uuid4())[:8]
    ext = file.filename.rsplit(".", 1)[1].lower()
    input_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_input.{ext}")
    output_path = os.path.join(OUTPUT_FOLDER, f"{job_id}_cleaned.mp4")

    file.save(input_path)
    jobs[job_id] = {"status": "queued", "progress": "Starting...", "percent": 0, "output": None, "error": None}

    threading.Thread(target=run_job,
                     args=(job_id, input_path, target_text, quality, output_path, ocr_every),
                     daemon=True).start()

    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/download/<filename>")
def download(filename):
    return send_from_directory(OUTPUT_FOLDER, filename, as_attachment=True)


if __name__ == "__main__":
    check_ffmpeg()
    # HF Spaces requires port 7860; locally falls back to 5000
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=False)
