"""
OCR Button Detector
===================
EasyOCR 기반 화면 버튼/텍스트 감지 및 클릭 좌표 추출
"""

import io
from dataclasses import dataclass
from typing import List, Tuple, Optional
from PIL import Image

# Lazy load EasyOCR for performance
_reader = None

def get_reader():
    global _reader
    if _reader is None:
        try:
            import easyocr
            _reader = easyocr.Reader(['en', 'ko'], gpu=False, verbose=False)
            print("[OCR] EasyOCR initialized")
        except ImportError:
            print("[OCR] EasyOCR not installed. Run: pip install easyocr")
            return None
    return _reader


@dataclass
class DetectedButton:
    """감지된 버튼/텍스트 정보"""
    text: str
    x: int  # 중심 X
    y: int  # 중심 Y
    width: int
    height: int
    confidence: float
    bbox: Tuple[int, int, int, int]  # left, top, right, bottom
    
    def to_dict(self):
        return {
            "text": self.text,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "confidence": self.confidence,
            "bbox": list(self.bbox)
        }


class ButtonDetector:
    """화면에서 클릭 가능한 버튼/텍스트 감지"""
    
    def __init__(self):
        self.last_results = []
        self.cache_valid = False
        self.last_image_hash = None
        
        # 버튼으로 인식할 키워드
        self.button_keywords = [
            'ok', 'cancel', 'yes', 'no', 'accept', 'reject', 'close', 'open',
            'save', 'delete', 'submit', 'confirm', 'next', 'back', 'done',
            'continue', 'skip', 'apply', 'settings', 'help', 'exit', 'quit',
            '확인', '취소', '예', '아니오', '닫기', '열기', '저장', '삭제'
        ]
    
    def detect_from_image(self, image: Image.Image) -> List[DetectedButton]:
        """이미지에서 텍스트/버튼 감지"""
        reader = get_reader()
        if reader is None:
            return []
        
        try:
            # PIL Image를 numpy array로 변환
            import numpy as np
            img_array = np.array(image)
            
            # OCR 실행
            results = reader.readtext(img_array)
            
            buttons = []
            for (bbox, text, confidence) in results:
                if confidence < 0.3:
                    continue
                    
                # Bounding box 좌표 추출
                (tl, tr, br, bl) = bbox
                left = int(min(tl[0], bl[0]))
                top = int(min(tl[1], tr[1]))
                right = int(max(tr[0], br[0]))
                bottom = int(max(bl[1], br[1]))
                
                width = right - left
                height = bottom - top
                center_x = left + width // 2
                center_y = top + height // 2
                
                button = DetectedButton(
                    text=text,
                    x=center_x,
                    y=center_y,
                    width=width,
                    height=height,
                    confidence=confidence,
                    bbox=(left, top, right, bottom)
                )
                buttons.append(button)
            
            self.last_results = buttons
            return buttons
            
        except Exception as e:
            print(f"[OCR] Detection error: {e}")
            return []
    
    def detect_from_bytes(self, jpeg_bytes: bytes) -> List[DetectedButton]:
        """JPEG 바이트에서 텍스트/버튼 감지"""
        try:
            image = Image.open(io.BytesIO(jpeg_bytes))
            return self.detect_from_image(image)
        except Exception as e:
            print(f"[OCR] Image load error: {e}")
            return []
    
    def find_button_by_text(self, target_text: str, case_sensitive: bool = False) -> Optional[DetectedButton]:
        """특정 텍스트를 가진 버튼 찾기"""
        target = target_text if case_sensitive else target_text.lower()
        
        for button in self.last_results:
            text = button.text if case_sensitive else button.text.lower()
            if target in text or text in target:
                return button
        return None
    
    def get_clickable_buttons(self) -> List[DetectedButton]:
        """클릭 가능한 버튼만 필터링"""
        clickable = []
        for button in self.last_results:
            text_lower = button.text.lower()
            # 버튼 키워드 또는 짧은 텍스트(버튼일 가능성 높음)
            if any(kw in text_lower for kw in self.button_keywords) or len(button.text) <= 15:
                clickable.append(button)
        return clickable
    
    def get_all_buttons(self) -> List[dict]:
        """모든 감지된 버튼 반환 (JSON 직렬화 가능)"""
        return [b.to_dict() for b in self.last_results]


# Global detector instance
detector = ButtonDetector()


def detect_buttons(jpeg_bytes: bytes) -> List[dict]:
    """버튼 감지 (외부 호출용)"""
    buttons = detector.detect_from_bytes(jpeg_bytes)
    return [b.to_dict() for b in buttons]


def find_and_click(target_text: str) -> Optional[Tuple[int, int]]:
    """텍스트로 버튼 찾아서 클릭 좌표 반환"""
    button = detector.find_button_by_text(target_text)
    if button:
        return (button.x, button.y)
    return None
