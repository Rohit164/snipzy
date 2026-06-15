import os
import sys
import shutil
import argparse
import cv2
import subprocess
import numpy as np

RESOLUTION_MAP = {
    "144p": (256, 144),
    "240p": (426, 240),
    "360p": (640, 360),
    "480p": (854, 480),
    "720p": (1280, 720),
    "1080p": (1920, 1080)
}

BITRATE_MAP = {
    "144p": "100k",
    "240p": "250k",
    "360p": "500k",
    "480p": "1M",
    "720p": "2.5M",
    "1080p": "4.5M"
}

# Scale factor for OCR — smaller = faster, but may miss small text (overridden by --ocr-scale arg)
OCR_SCALE = 0.5


def check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        print("[ERROR] ffmpeg not found on PATH. Install it from https://ffmpeg.org/download.html")
        sys.exit(1)


def load_ocr():
    """Load best available OCR engine. Priority: RapidOCR > PaddleOCR > EasyOCR."""

    # 1. RapidOCR — fastest on CPU, easiest Windows install
    try:
        from rapidocr_onnxruntime import RapidOCR
        print("[SYSTEM] Using RapidOCR (fastest CPU option)")
        ocr = RapidOCR()

        def run_ocr(frame):
            result, _ = ocr(frame)
            detections = []
            if result:
                for line in result:
                    bbox, text, prob = line
                    tl = (int(bbox[0][0]), int(bbox[0][1]))
                    br = (int(bbox[2][0]), int(bbox[2][1]))
                    detections.append((tl, br, text, float(prob)))
            return detections

        return run_ocr

    except ImportError:
        pass

    # 2. PaddleOCR
    try:
        from paddleocr import PaddleOCR
        print("[SYSTEM] Using PaddleOCR (CPU-optimized)")
        ocr = PaddleOCR(use_angle_cls=False, lang='en', use_gpu=False, show_log=False)

        def run_ocr(frame):
            result = ocr.ocr(frame, cls=False)
            detections = []
            if result and result[0]:
                for line in result[0]:
                    bbox, (text, prob) = line
                    tl = (int(bbox[0][0]), int(bbox[0][1]))
                    br = (int(bbox[2][0]), int(bbox[2][1]))
                    detections.append((tl, br, text, prob))
            return detections

        return run_ocr

    except ImportError:
        pass

    # 3. EasyOCR — slowest fallback
    try:
        import easyocr
        print("[SYSTEM] Using EasyOCR (slow on CPU — install RapidOCR for faster processing)")
        print("[TIP] Run: pip install rapidocr-onnxruntime")
        reader = easyocr.Reader(['en'], gpu=False)

        def run_ocr(frame):
            results = reader.readtext(frame)
            return [
                (tuple(map(int, bbox[0])), tuple(map(int, bbox[2])), text, prob)
                for (bbox, text, prob) in results
            ]

        return run_ocr

    except ImportError:
        print("[ERROR] No OCR engine found. Install one with: pip install rapidocr-onnxruntime")
        sys.exit(1)


class PromptVideoCleaner:
    def __init__(self, ocr_scale=0.5):
        self.ocr_scale = ocr_scale
        self.run_ocr = load_ocr()

    def _build_keywords(self, target_prompt):
        """Split target into meaningful tokens to match against OCR fragments."""
        import re
        # strip @ and split on non-alphanumeric chars, keep tokens >= 3 chars
        tokens = re.split(r'[^a-zA-Z0-9]', target_prompt.lstrip('@'))
        keywords = [t.lower() for t in tokens if len(t) >= 3]
        # also include the full prompt as a keyword
        keywords.append(target_prompt.lower().lstrip('@'))
        return keywords

    def _matches(self, text, keywords):
        t = text.lower()
        return any(kw in t for kw in keywords)

    def _detect_boxes(self, frame, target_prompt, debug=False):
        """Run OCR on a downscaled frame, return matched boxes scaled back to full size."""
        h, w = frame.shape[:2]
        scale = self.ocr_scale
        small = cv2.resize(frame, (int(w * scale), int(h * scale)))
        detections = self.run_ocr(small)
        keywords = self._build_keywords(target_prompt)
        boxes = []
        for (tl, br, text, prob) in detections:
            if debug:
                print(f"  [OCR] '{text}' (conf={prob:.2f})")
            if prob > 0.15 and self._matches(text, keywords):
                # pad the box slightly to catch clipped edges
                pad = 6
                tl_full = (max(0, int(tl[0] / scale) - pad), max(0, int(tl[1] / scale) - pad))
                br_full = (min(w, int(br[0] / scale) + pad), min(h, int(br[1] / scale) + pad))
                boxes.append((tl_full, br_full))
                if debug:
                    print(f"  [MATCH] '{text}' -> box {tl_full} {br_full}")
        return boxes

    def extract_and_mask(self, video_path, target_prompt, frames_dir, masks_dir, ocr_every=5, progress_cb=None):
        if not os.path.exists(video_path):
            print(f"[ERROR] Input file not found: {video_path}")
            sys.exit(1)

        os.makedirs(frames_dir, exist_ok=True)
        os.makedirs(masks_dir, exist_ok=True)

        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_idx = 0
        last_boxes = []
        debug = getattr(self, 'debug', False)

        print(f"[PROCESS] Scanning {total} frames for: '{target_prompt}' (OCR every {ocr_every} frames, {int(self.ocr_scale*100)}% scale)")

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % ocr_every == 0:
                last_boxes = self._detect_boxes(frame, target_prompt, debug=debug)

            h, w = frame.shape[:2]
            mask = np.zeros((h, w), dtype=np.uint8)
            for (tl, br) in last_boxes:
                cv2.rectangle(mask, tl, br, 255, -1)

            cv2.imwrite(os.path.join(frames_dir, f"frame_{frame_idx:05d}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            cv2.imwrite(os.path.join(masks_dir, f"mask_{frame_idx:05d}.png"), mask)
            frame_idx += 1

            if frame_idx % 20 == 0 or frame_idx == total:
                pct = (frame_idx / total * 100) if total > 0 else 0
                print(f"  [{frame_idx}/{total}] {pct:.1f}%", end='\r')
                if progress_cb:
                    progress_cb("scanning", int(pct), frame_idx, total)

        cap.release()
        print()
        return frame_idx, fps

    def inpaint_frames(self, frames_dir, masks_dir, clean_frames_dir, total_frames, progress_cb=None):
        os.makedirs(clean_frames_dir, exist_ok=True)
        print("[PROCESS] Inpainting frames...")
        skipped = 0

        for i in range(total_frames):
            mask = cv2.imread(os.path.join(masks_dir, f"mask_{i:05d}.png"), cv2.IMREAD_GRAYSCALE)
            frame = cv2.imread(os.path.join(frames_dir, f"frame_{i:05d}.jpg"))

            if frame is None or mask is None:
                print(f"[WARN] Skipping missing frame/mask at index {i}")
                continue

            if mask.max() == 0:
                clean_frame = frame
                skipped += 1
            else:
                clean_frame = cv2.inpaint(frame, mask, inpaintRadius=7, flags=cv2.INPAINT_TELEA)

            cv2.imwrite(os.path.join(clean_frames_dir, f"clean_{i:05d}.jpg"), clean_frame, [cv2.IMWRITE_JPEG_QUALITY, 95])

            if (i + 1) % 20 == 0 or (i + 1) == total_frames:
                pct = (i + 1) / total_frames * 100
                print(f"  [{i+1}/{total_frames}] {pct:.1f}%", end='\r')
                if progress_cb:
                    progress_cb("inpainting", int(pct), i + 1, total_frames)

        print()

    def compile_and_transcode(self, clean_frames_dir, original_video, output_path, quality, fps):
        if quality not in RESOLUTION_MAP:
            raise ValueError(f"Unsupported quality '{quality}'. Choose from: {list(RESOLUTION_MAP.keys())}")

        width, height = RESOLUTION_MAP[quality]
        bitrate = BITRATE_MAP[quality]

        print(f"[PROCESS] Compiling output at {quality} ({width}x{height})...")

        command = [
            'ffmpeg', '-y',
            '-f', 'image2',
            '-framerate', str(fps),
            '-i', os.path.join(clean_frames_dir, 'clean_%05d.jpg'),
            '-i', original_video,
            '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2',
            '-c:v', 'libx264',
            '-b:v', bitrate,
            '-c:a', 'aac',
            '-map', '0:v:0',
            '-map', '1:a:0?',
            '-pix_fmt', 'yuv420p',
            output_path
        ]

        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[SUCCESS] Video saved to: {output_path}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Snipzy — Remove text/watermarks from video using OCR + inpainting"
    )
    parser.add_argument("--input",     default="input.mp4",               help="Path to input video (default: input.mp4)")
    parser.add_argument("--text",      default="@clips",                  help="Text string to detect and remove")
    parser.add_argument("--quality",   default="720p",                    help="Output quality: 144p/240p/360p/480p/720p/1080p")
    parser.add_argument("--output",    default="final_cleaned_video.mp4", help="Output filename")
    parser.add_argument("--keep-temp", action="store_true",               help="Keep temp frame files after processing")
    parser.add_argument("--ocr-every", type=int, default=5,               help="Run OCR every N frames (default: 5, higher = faster)")
    parser.add_argument("--ocr-scale", type=float, default=0.75,          help="Downscale factor for OCR (default: 0.75, lower = faster but may miss small text)")
    parser.add_argument("--debug",     action="store_true",               help="Print all OCR detections to help diagnose missed text")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    check_ffmpeg()

    OCR_SCALE = args.ocr_scale

    DIR_FRAMES = "temp/frames"
    DIR_MASKS  = "temp/masks"
    DIR_CLEAN  = "temp/clean_frames"

    cleaner = PromptVideoCleaner(ocr_scale=args.ocr_scale)
    cleaner.debug = args.debug

    total_frames, source_fps = cleaner.extract_and_mask(args.input, args.text, DIR_FRAMES, DIR_MASKS, ocr_every=args.ocr_every)
    cleaner.inpaint_frames(DIR_FRAMES, DIR_MASKS, DIR_CLEAN, total_frames)
    cleaner.compile_and_transcode(DIR_CLEAN, args.input, args.output, args.quality, source_fps)

    if not args.keep_temp:
        shutil.rmtree("temp", ignore_errors=True)
        print("[CLEANUP] Temp files removed.")
