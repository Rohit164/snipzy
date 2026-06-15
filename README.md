# ✂ snipzy

> remove text, watermarks, and usernames from any video — no GPU required

snipzy scans your video frame by frame, finds the text you want gone using OCR, masks it out, and inpaints over it so the background looks natural. then it stitches everything back into a clean output video with the original audio intact.

---

## how it works

```
input video
    │
    ▼
frame extraction  ──►  OCR scan (every N frames)
    │                        │
    │                   text matched?
    │                        │
    ▼                        ▼
mask generation  ◄──── bounding box
    │
    ▼
inpainting (OpenCV TELEA)
    │
    ▼
ffmpeg transcode + audio mux
    │
    ▼
clean output video
```

- **OCR engine** — uses RapidOCR by default (ONNX-based, fast on CPU). falls back to PaddleOCR or EasyOCR automatically if not installed
- **inpainting** — OpenCV TELEA algorithm fills masked regions using surrounding pixel context
- **smart skipping** — frames with no detected text skip inpainting entirely, saving significant time
- **frame sampling** — OCR runs every N frames (configurable), reusing boxes in between for speed

---

## stack

- `opencv-python` — frame extraction, masking, inpainting
- `rapidocr-onnxruntime` — fast CPU OCR
- `ffmpeg` — video/audio transcoding
- `flask` — web interface
- `numpy` — mask operations

---

## setup

**requirements**
- Python 3.8+
- ffmpeg on your system PATH → [download](https://ffmpeg.org/download.html)

```bash
git clone https://github.com/yourusername/snipzy.git
cd snipzy
pip install -r requirements.txt
```

---

## usage

### web interface (recommended)

```bash
python app.py
```

then open `http://localhost:5000` in your browser — or on your phone if you're on the same wifi network using your machine's local IP.

upload a video, type the text to remove, pick quality, hit `>>`.

### command line

```bash
python main.py --input input.mp4 --text "@username" --quality 720p --output cleaned.mp4
```

| flag | default | description |
|---|---|---|
| `--input` | `input.mp4` | path to source video |
| `--text` | `@clips` | text/watermark to detect and remove |
| `--quality` | `720p` | output resolution: `144p` `240p` `360p` `480p` `720p` `1080p` |
| `--output` | `final_cleaned_video.mp4` | output filename |
| `--ocr-every` | `5` | run OCR every N frames — higher is faster |
| `--ocr-scale` | `0.75` | downscale factor before OCR — lower is faster, may miss small text |
| `--keep-temp` | off | keep temp frame files after processing |
| `--debug` | off | print every OCR detection to diagnose missed text |

### debug mode

if the text isn't being removed, run with `--debug` to see exactly what the OCR is reading:

```bash
python main.py --input input.mp4 --text "@username" --debug --ocr-every 30
```

this prints every detected string and confidence score so you can tune the match.

---

## performance tips

snipzy is designed to work without a GPU. on a typical laptop:

- use `--ocr-every 10` or higher for static watermarks (they don't move between frames)
- use `--ocr-scale 0.5` for a further speed boost if the watermark is large/clear
- lower output quality (`480p`) if you just need a quick clean copy

install `rapidocr-onnxruntime` for the best CPU performance — it's 3–5x faster than EasyOCR:

```bash
python -m pip install rapidocr-onnxruntime
```

---

## project structure

```
snipzy/
├── main.py          # core pipeline — OCR, masking, inpainting, transcode
├── app.py           # flask web server with job queue
├── ui.py            # optional desktop UI (tkinter)
├── templates/
│   └── index.html   # web frontend
├── requirements.txt
└── README.md
```

---

## notes

- temp files are written to `temp/` and cleaned up automatically after each job
- the web server processes one job at a time per thread — for production use, swap `threading` for a proper task queue like Celery
- for higher quality inpainting on complex backgrounds, the `inpaint_frames()` method in `main.py` can be swapped with a [ProPainter](https://github.com/sczhou/ProPainter) inference call

---

## license

MIT
