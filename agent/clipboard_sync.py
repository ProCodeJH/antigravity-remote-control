"""
ULTRA Clipboard Sync Engine
============================
PC ↔ Mobile 클립보드 실시간 동기화

Requirements:
    pip install pyperclip pillow
"""

import time
import threading
import base64
import io
from dataclasses import dataclass
from typing import Optional, Callable, Union
from enum import Enum

try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except ImportError:
    PYPERCLIP_AVAILABLE = False

from PIL import Image


class ClipboardType(Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"


@dataclass
class ClipboardData:
    """클립보드 데이터"""
    content_type: ClipboardType
    data: Union[str, bytes]
    timestamp: int
    
    def to_dict(self) -> dict:
        if self.content_type == ClipboardType.TEXT:
            return {
                "type": "clipboard",
                "contentType": self.content_type.value,
                "data": self.data,
                "timestamp": self.timestamp
            }
        elif self.content_type == ClipboardType.IMAGE:
            return {
                "type": "clipboard",
                "contentType": self.content_type.value,
                "data": base64.b64encode(self.data).decode('utf-8'),
                "timestamp": self.timestamp
            }
        return {}
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ClipboardData':
        content_type = ClipboardType(data.get("contentType", "text"))
        content = data.get("data", "")
        
        if content_type == ClipboardType.IMAGE:
            content = base64.b64decode(content)
        
        return cls(
            content_type=content_type,
            data=content,
            timestamp=data.get("timestamp", int(time.time() * 1000))
        )


class ClipboardMonitor:
    """클립보드 변경 감지"""
    
    def __init__(self, callback: Callable[[ClipboardData], None]):
        self.callback = callback
        self.running = False
        self.last_text = ""
        self.last_hash = ""
    
    def start(self):
        """모니터링 시작"""
        if not PYPERCLIP_AVAILABLE:
            print("[CLIPBOARD] pyperclip not available")
            return
        
        self.running = True
        
        def monitor_loop():
            while self.running:
                try:
                    # 텍스트 변경 감지
                    text = pyperclip.paste()
                    if text and text != self.last_text:
                        self.last_text = text
                        
                        clip_data = ClipboardData(
                            content_type=ClipboardType.TEXT,
                            data=text,
                            timestamp=int(time.time() * 1000)
                        )
                        self.callback(clip_data)
                    
                    time.sleep(0.5)  # 500ms 간격
                except Exception as e:
                    time.sleep(1)
        
        self.thread = threading.Thread(target=monitor_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        """모니터링 중지"""
        self.running = False


class ClipboardSync:
    """ULTRA 클립보드 동기화"""
    
    def __init__(self, send_callback: Callable[[dict], None]):
        self.send = send_callback
        self.monitor = ClipboardMonitor(self._on_change)
    
    def _on_change(self, data: ClipboardData):
        """클립보드 변경 시"""
        self.send(data.to_dict())
    
    def start(self):
        """동기화 시작"""
        self.monitor.start()
        print("[CLIPBOARD] Sync started")
    
    def stop(self):
        """동기화 중지"""
        self.monitor.stop()
    
    def set_clipboard(self, data: ClipboardData):
        """클립보드 설정 (Mobile → PC)"""
        if data.content_type == ClipboardType.TEXT:
            if PYPERCLIP_AVAILABLE:
                pyperclip.copy(data.data)
                print(f"[CLIPBOARD] Set text: {data.data[:50]}...")
        elif data.content_type == ClipboardType.IMAGE:
            # 이미지를 클립보드에 복사
            try:
                import win32clipboard
                from io import BytesIO
                
                img = Image.open(BytesIO(data.data))
                output = BytesIO()
                img.convert("RGB").save(output, "BMP")
                bmp_data = output.getvalue()[14:]  # BMP 헤더 제거
                
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32clipboard.CF_DIB, bmp_data)
                win32clipboard.CloseClipboard()
                
                print("[CLIPBOARD] Set image")
            except ImportError:
                print("[CLIPBOARD] win32clipboard not available for images")
