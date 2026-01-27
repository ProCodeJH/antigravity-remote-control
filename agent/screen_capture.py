"""
Antigravity Remote Controller - Screen Capture
실시간 화면 캡처 및 스트리밍 모듈
"""

import mss
import mss.tools
from PIL import Image
import io
import base64
import time
from typing import Optional, Tuple, Dict
import win32gui


class ScreenCapture:
    """고속 화면 캡처 클래스"""
    
    def __init__(self):
        self.sct = mss.mss()
        self.last_capture: Optional[bytes] = None
        self.capture_quality = 85  # JPEG 품질 (0-100) - 높임
        self.max_width = 1200  # 최대 너비 - 더 선명하게
    
    def capture_full_screen(self, monitor_num: int = 1) -> bytes:
        """전체 화면 캡처"""
        monitor = self.sct.monitors[monitor_num]
        sct_img = self.sct.grab(monitor)
        return self._process_image(sct_img)
    
    def capture_window(self, hwnd: int) -> Optional[bytes]:
        """특정 창만 캡처"""
        try:
            rect = win32gui.GetWindowRect(hwnd)
            monitor = {
                "left": rect[0],
                "top": rect[1],
                "width": rect[2] - rect[0],
                "height": rect[3] - rect[1]
            }
            
            if monitor["width"] <= 0 or monitor["height"] <= 0:
                return None
            
            sct_img = self.sct.grab(monitor)
            return self._process_image(sct_img)
        except Exception as e:
            print(f"Failed to capture window: {e}")
            return None
    
    def capture_region(self, left: int, top: int, width: int, height: int) -> bytes:
        """특정 영역 캡처"""
        monitor = {
            "left": left,
            "top": top,
            "width": width,
            "height": height
        }
        sct_img = self.sct.grab(monitor)
        return self._process_image(sct_img)
    
    def _process_image(self, sct_img) -> bytes:
        """이미지 처리: 리사이즈 및 JPEG 압축"""
        # PIL Image로 변환
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        
        # 리사이즈 (비율 유지)
        if img.width > self.max_width:
            ratio = self.max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((self.max_width, new_height), Image.LANCZOS)
        
        # JPEG로 압축
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=self.capture_quality, optimize=True)
        jpeg_bytes = buffer.getvalue()
        
        self.last_capture = jpeg_bytes
        return jpeg_bytes
    
    def capture_to_base64(self, hwnd: Optional[int] = None) -> Optional[str]:
        """Base64 인코딩된 이미지 반환"""
        if hwnd:
            image_bytes = self.capture_window(hwnd)
        else:
            image_bytes = self.capture_full_screen()
        
        if image_bytes:
            return base64.b64encode(image_bytes).decode('utf-8')
        return None
    
    def set_quality(self, quality: int):
        """JPEG 품질 설정 (0-100)"""
        self.capture_quality = max(0, min(100, quality))
    
    def set_max_width(self, width: int):
        """최대 너비 설정"""
        self.max_width = max(100, width)
    
    def get_stats(self) -> Dict:
        """캡처 통계 반환"""
        return {
            "quality": self.capture_quality,
            "max_width": self.max_width,
            "last_size": len(self.last_capture) if self.last_capture else 0
        }


# 싱글톤 인스턴스
capture = ScreenCapture()
