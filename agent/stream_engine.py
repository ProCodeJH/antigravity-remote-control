"""
Real-time Screen Streaming Engine v3
High-performance frame capture and WebSocket streaming
Target: 10-15 FPS, <200ms latency
"""

import asyncio
import base64
import io
import time
from dataclasses import dataclass
from typing import Optional, Callable, Set
from PIL import Image
import mss
import mss.tools


@dataclass
class StreamConfig:
    """Streaming configuration"""
    target_fps: int = 12
    max_width: int = 960
    jpeg_quality: int = 75
    min_frame_interval: float = 0.066  # ~15 FPS max
    adaptive_quality: bool = True
    motion_detection: bool = True


class StreamEngine:
    """High-performance real-time screen streaming engine"""
    
    def __init__(self, config: Optional[StreamConfig] = None):
        self.config = config or StreamConfig()
        self.sct = mss.mss()
        self.is_streaming = False
        self.subscribers: Set[Callable] = set()
        self.current_region: Optional[dict] = None
        self.last_frame: Optional[bytes] = None
        self.last_frame_time: float = 0
        self.frame_count: int = 0
        self.avg_latency: float = 0
        self._stream_task: Optional[asyncio.Task] = None
        
        # Adaptive quality state
        self._quality_level = self.config.jpeg_quality
        self._consecutive_slow_frames = 0
        
    def set_capture_region(self, x: int, y: int, width: int, height: int):
        """Set the screen region to capture"""
        self.current_region = {
            "left": x,
            "top": y,
            "width": width,
            "height": height
        }
        
    def set_window_region(self, hwnd: int, chat_only: bool = True):
        """Set capture region from window handle
        
        Args:
            hwnd: Window handle
            chat_only: If True, capture only the right 40% (chat panel area)
        """
        import win32gui
        try:
            rect = win32gui.GetWindowRect(hwnd)
            full_width = rect[2] - rect[0]
            full_height = rect[3] - rect[1]
            
            if chat_only:
                # Capture only right 40% (Antigravity chat panel)
                chat_width_ratio = 0.40
                chat_left = rect[0] + int(full_width * (1 - chat_width_ratio))
                
                self.current_region = {
                    "left": chat_left,
                    "top": rect[1] + 30,  # Skip title bar
                    "width": int(full_width * chat_width_ratio),
                    "height": full_height - 30
                }
                print(f"[StreamEngine] Capturing chat panel only (right {int(chat_width_ratio*100)}%)")
            else:
                # Capture full window
                self.current_region = {
                    "left": rect[0],
                    "top": rect[1],
                    "width": full_width,
                    "height": full_height
                }
                print(f"[StreamEngine] Capturing full window")
            
            return True
        except Exception as e:
            print(f"[StreamEngine] Failed to get window rect: {e}")
            return False
    
    def capture_frame(self) -> Optional[str]:
        """Capture a single frame and return as base64 JPEG"""
        try:
            start_time = time.time()
            
            # Determine capture region
            if self.current_region:
                region = self.current_region
            else:
                # Default to primary monitor
                monitor = self.sct.monitors[1]
                region = {
                    "left": monitor["left"],
                    "top": monitor["top"],
                    "width": monitor["width"],
                    "height": monitor["height"]
                }
            
            # Capture screen
            screenshot = self.sct.grab(region)
            
            # Convert to PIL Image
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            
            # Resize if needed
            if img.width > self.config.max_width:
                ratio = self.config.max_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((self.config.max_width, new_height), Image.LANCZOS)
            
            # Encode to JPEG
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=self._quality_level, optimize=True)
            frame_data = buffer.getvalue()
            
            # Calculate latency
            latency = (time.time() - start_time) * 1000
            self._update_latency(latency)
            
            # Adaptive quality adjustment
            if self.config.adaptive_quality:
                self._adjust_quality(latency, len(frame_data))
            
            # Encode to base64
            return base64.b64encode(frame_data).decode('utf-8')
            
        except Exception as e:
            print(f"[StreamEngine] Capture error: {e}")
            return None
    
    def _update_latency(self, latency: float):
        """Update average latency using exponential moving average"""
        alpha = 0.3
        self.avg_latency = alpha * latency + (1 - alpha) * self.avg_latency
    
    def _adjust_quality(self, latency: float, frame_size: int):
        """Adaptively adjust quality based on performance"""
        target_latency = 50  # ms
        max_frame_size = 100 * 1024  # 100KB
        
        if latency > target_latency * 2 or frame_size > max_frame_size:
            self._consecutive_slow_frames += 1
            if self._consecutive_slow_frames > 3:
                self._quality_level = max(40, self._quality_level - 5)
                self._consecutive_slow_frames = 0
        else:
            self._consecutive_slow_frames = 0
            if latency < target_latency and frame_size < max_frame_size * 0.5:
                self._quality_level = min(85, self._quality_level + 2)
    
    def subscribe(self, callback: Callable):
        """Subscribe to frame updates"""
        self.subscribers.add(callback)
        
    def unsubscribe(self, callback: Callable):
        """Unsubscribe from frame updates"""
        self.subscribers.discard(callback)
    
    async def start_streaming(self):
        """Start the streaming loop"""
        if self.is_streaming:
            return
            
        self.is_streaming = True
        self.frame_count = 0
        print(f"[StreamEngine] Starting stream at {self.config.target_fps} FPS target")
        
        frame_interval = 1.0 / self.config.target_fps
        
        while self.is_streaming:
            loop_start = time.time()
            
            # Capture frame
            frame = self.capture_frame()
            
            if frame and self.subscribers:
                self.frame_count += 1
                
                # Send to all subscribers
                frame_data = {
                    "type": "frame",
                    "data": frame,
                    "frame_id": self.frame_count,
                    "latency": round(self.avg_latency, 1),
                    "quality": self._quality_level
                }
                
                # Notify subscribers asynchronously
                for callback in list(self.subscribers):
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            asyncio.create_task(callback(frame_data))
                        else:
                            callback(frame_data)
                    except Exception as e:
                        print(f"[StreamEngine] Subscriber error: {e}")
            
            # Maintain frame rate
            elapsed = time.time() - loop_start
            sleep_time = max(0, frame_interval - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
    
    def stop_streaming(self):
        """Stop the streaming loop"""
        self.is_streaming = False
        print(f"[StreamEngine] Stopped. Total frames: {self.frame_count}")
    
    def get_stats(self) -> dict:
        """Get streaming statistics"""
        return {
            "is_streaming": self.is_streaming,
            "frame_count": self.frame_count,
            "avg_latency_ms": round(self.avg_latency, 1),
            "current_quality": self._quality_level,
            "target_fps": self.config.target_fps,
            "subscribers": len(self.subscribers)
        }
    
    def capture_single(self) -> Optional[str]:
        """Capture a single high-quality frame (for screenshots)"""
        # Temporarily boost quality
        original_quality = self._quality_level
        self._quality_level = 90
        frame = self.capture_frame()
        self._quality_level = original_quality
        return frame


# Global instance
_stream_engine: Optional[StreamEngine] = None

def get_stream_engine() -> StreamEngine:
    """Get or create the global stream engine instance"""
    global _stream_engine
    if _stream_engine is None:
        _stream_engine = StreamEngine()
    return _stream_engine
