from __future__ import annotations

import colorsys
import hashlib
import io
import json
import math
import os
import queue
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

import libusb_package
import numpy as np
import usb.core
import usb.util
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from usb.backend import libusb1


VID = 0x87AD
PID = 0x70DB
DEFAULT_WIDTH = 800
DEFAULT_HEIGHT = 480
DEFAULT_FPS = 10
DEVICE_NAME = "USBDISPLAY"
FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
RGB565_PMS = {32}
PM_TO_FBL_OVERRIDES = {
    5: 50,
    7: 64,
    9: 224,
    10: 224,
    11: 224,
    12: 224,
    13: 224,
    14: 64,
    15: 224,
    16: 224,
    17: 224,
    32: 100,
    50: 50,
    63: 114,
    64: 114,
    65: 192,
    66: 192,
    68: 192,
    69: 192,
}
PM_SUB_TO_FBL = {
    (1, 48): 114,
    (1, 49): 192,
}
FBL_PROFILES = {
    36: (240, 240),
    37: (240, 240),
    50: (320, 240),
    51: (320, 240),
    52: (320, 240),
    53: (320, 240),
    54: (360, 360),
    58: (320, 240),
    64: (640, 480),
    72: (480, 480),
    100: (320, 320),
    101: (320, 320),
    102: (320, 320),
    114: (1600, 720),
    128: (1280, 480),
    129: (480, 480),
    192: (1920, 462),
    224: (854, 480),
}
FBL_224_BY_PM = {
    10: (960, 540),
    12: (800, 480),
    13: (960, 320),
    15: (640, 172),
    16: (960, 540),
    17: (960, 320),
}
FBL_192_BY_PM = {
    68: (1280, 480),
    69: (1920, 440),
}
KNOWN_BULK_PMS = {
    1, 5, 7, 9, 10, 11, 12, 13, 14, 15, 16, 17, 32, 50, 63, 64, 65, 66, 68, 69
}

backend = libusb1.get_backend(find_library=libusb_package.find_library)

state_lock = threading.Lock()
current_state: dict[str, Any] = {
    "connected": False,
    "status": "idle",
    "message": "Waiting for Spotify state...",
    "track": None,
    "updatedAt": int(time.time() * 1000),
}
state_queue: "queue.Queue[dict[str, Any]]" = queue.Queue()
stop_event = threading.Event()
art_cache: dict[str, Image.Image] = {}

font_paths = [
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\seguisb.ttf",
    r"C:\Windows\Fonts\arial.ttf",
]


def log(message: str) -> None:
    try:
        print(f"[lcd] {message}", flush=True)
    except OSError:
        pass


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        str(FONT_DIR / ("NotoSansCJKtc-Bold.otf" if bold else "NotoSansCJKtc-Regular.otf")),
        r"C:\Windows\Fonts\NotoSansTC-VF.ttf",
        r"C:\Windows\Fonts\NotoSansHK-VF.ttf",
        r"C:\Windows\Fonts\msjhbd.ttc" if bold else r"C:\Windows\Fonts\msjh.ttc",
        r"C:\Windows\Fonts\msjhbd.ttc" if bold else r"C:\Windows\Fonts\msjhui.ttc",
        r"C:\Windows\Fonts\mingliub.ttc" if bold else r"C:\Windows\Fonts\mingliu.ttc",
        r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\seguisb.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
    ]

    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue

    return ImageFont.load_default()


def set_state(new_state: dict[str, Any]) -> None:
    with state_lock:
        current_state.clear()
        current_state.update(new_state)


def get_state() -> dict[str, Any]:
    with state_lock:
        return dict(current_state)


def lcd_fps_from_state(state: dict[str, Any]) -> int:
    settings = state.get("settings") if isinstance(state.get("settings"), dict) else {}
    try:
        fps = int(settings.get("lcdFps") or DEFAULT_FPS)
    except (TypeError, ValueError):
        fps = DEFAULT_FPS
    return min(60, max(10, fps))


def read_stdin() -> None:
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue

        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue

        if payload.get("type") == "state" and isinstance(payload.get("state"), dict):
            state_queue.put(payload["state"])


def hash_palette(track: dict[str, Any] | None) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    seed = f"{track.get('title', '')}|{track.get('artist', '')}|{track.get('album', '')}" if track else "idle"
    digest = hashlib.sha1(seed.encode("utf-8")).digest()

    hue = digest[0] / 255.0
    hue2 = ((digest[1] / 255.0) + 0.12) % 1.0
    hue3 = ((digest[2] / 255.0) + 0.24) % 1.0

    def hsv(h: float, s: float, v: float) -> tuple[int, int, int]:
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return (int(r * 255), int(g * 255), int(b * 255))

    return hsv(hue, 0.56, 0.24), hsv(hue2, 0.7, 0.42), hsv(hue3, 0.75, 0.7)


def apply_tint(image: Image.Image, color: tuple[int, int, int], alpha: int = 140) -> Image.Image:
    overlay = Image.new("RGBA", image.size, color + (alpha,))
    return Image.alpha_composite(image.convert("RGBA"), overlay)


def fetch_album_art(url: str) -> Image.Image | None:
    if not url:
        return None

    cached = art_cache.get(url)
    if cached is not None:
        return cached.copy()

    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = response.read()
    except Exception:
        return None

    try:
        image = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return None

    art_cache[url] = image
    return image.copy()


def cover_crop(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    src_w, src_h = image.size
    scale = max(target_w / src_w, target_h / src_h)
    new_size = (max(1, int(src_w * scale)), max(1, int(src_h * scale)))
    resized = image.resize(new_size, Image.Resampling.LANCZOS)
    left = max(0, (resized.width - target_w) // 2)
    top = max(0, (resized.height - target_h) // 2)
    return resized.crop((left, top, left + target_w, top + target_h))


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    if not text:
        return [""]

    if " " in text:
        words = text.split()
    else:
        words = list(text)

    lines: list[str] = []
    current = ""

    for word in words:
        candidate = word if not current else (current + (" " if " " in text else "") + word)
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines[:4]


def fit_single_line(
    draw: ImageDraw.ImageDraw,
    text: str,
    start_size: int,
    bold: bool,
    max_width: int,
    min_size: int = 20,
) -> tuple[str, ImageFont.ImageFont]:
    if not text:
        return " ", load_font(start_size, bold=bold)

    for size in range(start_size, min_size - 1, -2):
        font = load_font(size, bold=bold)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return text, font

    font = load_font(min_size, bold=bold)
    candidate = text
    while candidate:
        final = candidate + "…"
        bbox = draw.textbbox((0, 0), final, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return final, font
        candidate = candidate[:-1]

    return "…", font


def current_progress_ms(track: dict[str, Any] | None, updated_at: int) -> float:
    if not track:
        return 0.0

    progress = float(track.get("progressMs") or 0)
    if track.get("isPlaying"):
        progress += max(0.0, (time.time() * 1000.0) - float(updated_at))
    return progress


def active_lyric_index(lines: list[dict[str, Any]], progress_ms: float) -> tuple[int, float]:
    if not lines:
        return 0, 0.0

    active = 0
    for index, line in enumerate(lines):
        if progress_ms >= float(line.get("startMs", 0)):
            active = index
        else:
            break

    next_start = float(lines[active + 1]["startMs"]) if active + 1 < len(lines) else float(lines[active]["startMs"]) + 3000.0
    start = float(lines[active].get("startMs", 0))
    span = max(1.0, next_start - start)
    interp = min(1.0, max(0.0, (progress_ms - start) / span))
    return active, interp


def ease_out_cubic(value: float) -> float:
    value = min(1.0, max(0.0, value))
    return 1.0 - pow(1.0 - value, 3)


def bulk_profile_from_pm(pm: int, sub: int) -> tuple[int, int, bool]:
    if (pm, sub) in PM_SUB_TO_FBL:
        fbl = PM_SUB_TO_FBL[(pm, sub)]
    else:
        fbl = PM_TO_FBL_OVERRIDES.get(pm, pm)

    if fbl == 224:
        width, height = FBL_224_BY_PM.get(pm, FBL_PROFILES[224])
    elif fbl == 192:
        width, height = FBL_192_BY_PM.get(pm, FBL_PROFILES[192])
    else:
        width, height = FBL_PROFILES.get(fbl, FBL_PROFILES[72] if pm not in KNOWN_BULK_PMS else (DEFAULT_WIDTH, DEFAULT_HEIGHT))

    use_jpeg = pm not in RGB565_PMS
    return width, height, use_jpeg


def choose_lyric_sizes(width: int, height: int) -> tuple[int, int]:
    if width >= 700 or height >= 420:
        return 44, 34
    if width >= 420 or height >= 320:
        return 34, 26
    return 24, 18


def build_background(size: tuple[int, int], track: dict[str, Any] | None, t: float) -> Image.Image:
    image = None
    if track:
        image = fetch_album_art(str(track.get("albumArtUrl") or ""))

    if image is None:
        base_color, blob_a, blob_b = hash_palette(track)
        fallback = Image.new("RGBA", size, base_color + (255,))
        overlay = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        w, h = size
        draw.ellipse((-int(w * 0.35), -int(h * 0.5), int(w * 1.2), int(h * 0.8)), fill=blob_a + (90,))
        draw.ellipse((int(w * 0.05), int(h * 0.05), int(w * 1.15), int(h * 1.15)), fill=blob_b + (72,))
        overlay = overlay.filter(ImageFilter.GaussianBlur(90))
        return Image.alpha_composite(fallback, overlay)

    frame = cover_crop(image, size).convert("RGBA")
    frame = frame.filter(ImageFilter.GaussianBlur(24))
    tint = Image.new("RGBA", size, (10, 10, 10, 145))
    frame = Image.alpha_composite(frame, tint)

    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    glow = ImageDraw.Draw(overlay)
    w, h = size
    glow.rectangle((0, 0, w, int(h * 0.18)), fill=(255, 255, 255, 8))
    glow.rectangle((0, int(h * 0.82), w, h), fill=(0, 0, 0, 24))
    overlay = overlay.filter(ImageFilter.GaussianBlur(36))
    return Image.alpha_composite(frame, overlay)


def draw_header(frame: Image.Image, track: dict[str, Any] | None, palette: tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]) -> None:
    draw = ImageDraw.Draw(frame)
    small_font = load_font(13, bold=True)
    title_font = load_font(22, bold=True)
    artist_font = load_font(14, bold=False)

    draw.text((28, 24), "SPOTIFY LYRIC SCREEN", font=small_font, fill=(255, 255, 255, 160))

    if track:
        title = str(track.get("title") or "Unknown Track")
        artist = str(track.get("artist") or "")
        draw.text((28, 42), title, font=title_font, fill=(255, 255, 255, 245))
        draw.text((28, 72), artist or " ", font=artist_font, fill=(255, 255, 255, 170))
    else:
        draw.text((28, 42), "Waiting for Spotify", font=title_font, fill=(255, 255, 255, 235))
        draw.text((28, 72), "No playback state yet", font=artist_font, fill=(255, 255, 255, 160))

    draw.ellipse((414, 38, 432, 56), fill=palette[2] + (255,))


def draw_cover(frame: Image.Image, track: dict[str, Any] | None) -> None:
    if not track:
        return

    url = str(track.get("albumArtUrl") or "")
    image = fetch_album_art(url)
    if image is None:
        return

    cover = cover_crop(image, (112, 112)).resize((112, 112), Image.Resampling.LANCZOS)
    mask = Image.new("L", cover.size, 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, cover.width - 1, cover.height - 1), radius=20, fill=255)

    x, y = 42, 36
    shadow = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle((x + 4, y + 6, x + 116, y + 118), radius=22, fill=(0, 0, 0, 90))
    frame.paste(shadow, (0, 0), shadow)
    frame.paste(cover.convert("RGBA"), (x, y), mask)


def draw_lyrics_spotify(draw: ImageDraw.ImageDraw, frame: Image.Image, state: dict[str, Any], progress_ms: float) -> None:
    track = state.get("track") or {}
    lyrics = track.get("lyrics") or {}
    items = lyrics.get("syncedLyrics") or []
    plain = lyrics.get("plainLyrics") or state.get("message") or "No lyrics found."
    width, height = frame.size
    max_width = max(120, width - 40)
    center_x = width // 2
    y_positions = [
        int(height * 0.24),
        int(height * 0.53),
        int(height * 0.82),
    ]

    if items:
        active_index, _ = active_lyric_index(items, progress_ms)
        visible = [active_index - 1, active_index, active_index + 1]
        active_size, inactive_size = choose_lyric_sizes(width, height)

        for slot, index in enumerate(visible):
            if index < 0 or index >= len(items):
                continue

            line = str(items[index].get("text") or " ")
            size = active_size if index == active_index else inactive_size
            font = load_font(size, bold=False)
            wrapped = wrap_text(draw, line, font, max_width)[:2]
            line_box = draw.textbbox((0, 0), "Ag", font=font)
            line_height = (line_box[3] - line_box[1]) + 6
            block_height = len(wrapped) * line_height - 6
            center_y = y_positions[slot]
            top_y = center_y - block_height / 2

            for line_index, part in enumerate(wrapped):
                y = top_y + line_index * line_height
                draw.text((center_x, y), part, font=font, fill=(255, 255, 255, 255), anchor="ma")
    else:
        lines = wrap_text(draw, plain, load_font(30, bold=False), max_width)
        font_size = choose_lyric_sizes(width, height)[0]
        min_size = max(20, font_size - 24)
        for size in range(font_size, min_size - 1, -2):
            test_font = load_font(size, bold=False)
            if all((draw.textbbox((0, 0), part, font=test_font)[2] - draw.textbbox((0, 0), part, font=test_font)[0]) <= max_width for part in lines[:3]):
                font_size = size
                break
        font = load_font(font_size, bold=False)
        for slot, part in enumerate(lines[:3]):
            draw.text((center_x, y_positions[slot]), part, font=font, fill=(255, 255, 255, 255), anchor="ma")


def render_frame(state: dict[str, Any]) -> Image.Image:
    track = state.get("track")
    updated_at = int(state.get("updatedAt") or int(time.time() * 1000))
    progress_ms = current_progress_ms(track, updated_at)
    width = int(state.get("lcdWidth") or DEFAULT_WIDTH)
    height = int(state.get("lcdHeight") or DEFAULT_HEIGHT)

    frame = build_background((width, height), track, time.time())
    draw = ImageDraw.Draw(frame)
    draw_lyrics_spotify(draw, frame, state, progress_ms)
    return frame


def image_to_rgb565_be(image: Image.Image) -> bytes:
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    r = rgb[:, :, 0].astype(np.uint16)
    g = rgb[:, :, 1].astype(np.uint16)
    b = rgb[:, :, 2].astype(np.uint16)
    rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return rgb565.astype(">u2").tobytes()


class LcdDevice:
    def __init__(self) -> None:
        self.dev: usb.core.Device | None = None
        self.ep_out = None
        self.ep_in = None
        self.interface_number: int | None = None
        self.packet_size = 512
        self.use_jpeg = True
        self.width = DEFAULT_WIDTH
        self.height = DEFAULT_HEIGHT
        self.pm = 0
        self.sub = 0

    def connect(self) -> bool:
        self.dev = usb.core.find(idVendor=VID, idProduct=PID, backend=backend)
        if self.dev is None:
            return False

        try:
            self.dev.set_configuration()
            cfg = self.dev.get_active_configuration()
        except usb.core.USBError as exc:
            log(f"USB access denied or busy: {exc}")
            self.disconnect()
            return False
        except Exception as exc:
            log(f"USB init failed: {exc}")
            self.disconnect()
            return False

        for interface in cfg:
            endpoint_out = usb.util.find_descriptor(
                interface,
                custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT,
            )
            endpoint_in = usb.util.find_descriptor(
                interface,
                custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN,
            )
            if endpoint_out is not None:
                self.ep_out = endpoint_out
                self.ep_in = endpoint_in
                self.interface_number = interface.bInterfaceNumber
                self.packet_size = max(512, int(getattr(endpoint_out, "wMaxPacketSize", 512)))
                try:
                    usb.util.claim_interface(self.dev, self.interface_number)
                except Exception:
                    pass
                log(f"Connected to {DEVICE_NAME} on interface {self.interface_number}, endpoint 0x{endpoint_out.bEndpointAddress:02x}.")
                self.handshake()
                return True

        self.dev = None
        return False

    def handshake(self) -> None:
        if self.dev is None or self.ep_out is None or self.ep_in is None:
            return

        request = bytearray(64)
        request[0:4] = b"\x12\x34\x56\x78"
        request[56] = 1
        self.ep_out.write(request, timeout=2000)

        response = bytes(self.ep_in.read(1024, timeout=2000))
        log(f"Handshake response: {response[:64].hex()}")
        if len(response) >= 37:
            self.pm = int(response[24])
            self.sub = int(response[36])
            self.width, self.height, self.use_jpeg = bulk_profile_from_pm(self.pm, self.sub)
            log(
                f"Detected panel mode PM={self.pm} SUB={self.sub} -> "
                f"{self.width}x{self.height} ({'JPEG' if self.use_jpeg else 'RGB565'})"
            )
            if self.pm not in KNOWN_BULK_PMS and (self.pm, self.sub) not in PM_SUB_TO_FBL:
                log("Unknown bulk PM/SUB, using 480x480-compatible fallback profile.")
        else:
            self.use_jpeg = True

        if self.use_jpeg and response[4:12].startswith(b"SSCRM-"):
            log("Bulk handshake OK: JPEG frame mode enabled.")
        else:
            log("Bulk handshake completed.")

    def disconnect(self) -> None:
        if self.dev is not None and self.interface_number is not None:
            try:
                usb.util.release_interface(self.dev, self.interface_number)
            except Exception:
                pass
        if self.dev is not None:
            usb.util.dispose_resources(self.dev)
        self.dev = None
        self.ep_out = None
        self.ep_in = None
        self.interface_number = None

    def build_frame_payload(self, frame: Image.Image) -> bytes:
        image = frame.convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=90, subsampling=0, optimize=False)
        return buffer.getvalue()

    def send_frame(self, frame: Image.Image) -> None:
        if self.dev is None or self.ep_out is None:
            raise RuntimeError("Device not connected")

        try:
            payload = self.build_frame_payload(frame) if self.use_jpeg else image_to_rgb565_be(frame)
            header = bytearray(64)
            header[0:4] = b"\x12\x34\x56\x78"
            header[4:8] = (2 if self.use_jpeg else 3).to_bytes(4, "little")
            header[8:12] = self.width.to_bytes(4, "little")
            header[12:16] = self.height.to_bytes(4, "little")
            header[56:60] = (2).to_bytes(4, "little")
            header[60:64] = len(payload).to_bytes(4, "little")
            packet = bytes(header) + payload

            chunk_size = 16 * 1024
            for offset in range(0, len(packet), chunk_size):
                self.ep_out.write(packet[offset : offset + chunk_size], timeout=5000)
            if len(packet) % 512 == 0:
                self.ep_out.write(b"", timeout=2000)
        except usb.core.USBError:
            self.disconnect()
            raise


def ensure_device(device: LcdDevice, last_attempt: float) -> float:
    now = time.time()
    if device.dev is not None:
        return last_attempt

    if now - last_attempt < 2.0:
        return last_attempt

    last_attempt = now
    if not device.connect():
        log(f"Device {VID:04x}:{PID:04x} not found. Retrying...")
    return last_attempt


def main() -> int:
    log("LCD bridge starting.")
    device = LcdDevice()

    threading.Thread(target=read_stdin, daemon=True).start()

    last_attempt = 0.0
    last_frame_at = 0.0

    while not stop_event.is_set():
        while not state_queue.empty():
            try:
                new_state = state_queue.get_nowait()
            except queue.Empty:
                break
            set_state(new_state)

        last_attempt = ensure_device(device, last_attempt)
        state = get_state()
        state["lcdWidth"] = device.width
        state["lcdHeight"] = device.height
        frame_interval = 1.0 / lcd_fps_from_state(state)
        try:
            frame = render_frame(state)
            if device.dev is not None:
                device.send_frame(frame)
        except Exception as exc:
            log(f"Frame send failed: {exc}")
            device.disconnect()

        elapsed = time.time() - last_frame_at
        if elapsed < frame_interval:
            time.sleep(frame_interval - elapsed)
        last_frame_at = time.time()

    device.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
