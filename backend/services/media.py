"""Video codec detection and browser-playable previews.

Browsers (Chrome/Edge on Windows in particular) only play a few codecs: H.264, VP8/VP9 and AV1.
Phones often record HEVC, and OpenCV/older tools write MPEG-4 Part 2; those files analyse fine
but cannot be played in the Review Queue. When ffmpeg is available we create an H.264 preview.
"""
import logging
import os
import shutil
import subprocess
from typing import Optional

try:
    import cv2
except Exception:  # pragma: no cover - reported via /api/system/status
    cv2 = None

log = logging.getLogger("bas.media")

FFMPEG = shutil.which(os.environ.get("BAS_FFMPEG", "ffmpeg"))
FFPROBE = shutil.which(os.path.join(os.path.dirname(FFMPEG), "ffprobe")) if FFMPEG else shutil.which("ffprobe")

BROWSER_CODECS = {"h264", "vp8", "vp9", "av1"}
BROWSER_CONTAINERS = {".mp4", ".webm", ".mov"}

_FOURCC_CODECS = {
    "avc1": "h264", "h264": "h264", "x264": "h264", "avc3": "h264",
    "hvc1": "hevc", "hev1": "hevc", "hevc": "hevc",
    "vp80": "vp8", "vp08": "vp8", "vp90": "vp9", "vp09": "vp9", "av01": "av1",
    "mp4v": "mpeg4", "xvid": "mpeg4", "divx": "mpeg4", "dx50": "mpeg4", "fmp4": "mpeg4",
    "mjpg": "mjpeg",
}

PREVIEW_TIMEOUT_SECONDS = 1800


def ffmpeg_available() -> bool:
    return FFMPEG is not None


def probe_codec(path: str) -> Optional[str]:
    """Video codec name (ffprobe naming, e.g. 'h264', 'hevc', 'mpeg4'), or None if unknown."""
    if FFPROBE:
        try:
            out = subprocess.run(
                [FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name",
                 "-of", "default=nw=1:nk=1", path],
                capture_output=True, text=True, timeout=30,
            )
            name = out.stdout.strip().splitlines()[0].lower() if out.stdout.strip() else ""
            if name:
                return name
        except Exception as e:
            log.warning("ffprobe failed for %s: %s", path, e)
    if cv2 is not None:
        cap = cv2.VideoCapture(path)
        try:
            code = int(cap.get(cv2.CAP_PROP_FOURCC) or 0)
        finally:
            cap.release()
        fourcc = "".join(chr((code >> 8 * i) & 0xFF) for i in range(4)).strip("\x00 ").lower()
        return _FOURCC_CODECS.get(fourcc, fourcc or None)
    return None


def browser_playable(path: str, codec: Optional[str]) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in BROWSER_CONTAINERS and (codec or "") in BROWSER_CODECS


def preview_path_for(path: str) -> str:
    stem, _ = os.path.splitext(path)
    return f"{stem}.preview.mp4"


def make_preview(src: str, dst: str) -> None:
    """Transcode to H.264/yuv420p MP4 with the index at the front (fast seeking). Raises on failure."""
    if not FFMPEG:
        raise RuntimeError("ffmpeg is not installed")
    tmp = dst + ".part.mp4"
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-i", src, "-map", "0:v:0", "-an",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", tmp]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=PREVIEW_TIMEOUT_SECONDS)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
