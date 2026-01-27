"""
GPU Accelerated Screen Capture (Windows DXGI)
==============================================
Desktop Duplication API를 사용한 GPU 가속 캡처
CPU 대비 5-10배 빠른 화면 캡처

Requirements:
    pip install dxcam  # 또는 d3dshot
"""

import time
import threading
from dataclasses import dataclass
from typing import Optional, Tuple, Callable
import numpy as np

# GPU Capture Libraries
DXCAM_AVAILABLE = False
D3DSHOT_AVAILABLE = False

try:
    import dxcam
    DXCAM_AVAILABLE = True
    print("[GPU] dxcam available")
except ImportError:
    pass

if not DXCAM_AVAILABLE:
    try:
        import d3dshot
        D3DSHOT_AVAILABLE = True
        print("[GPU] d3dshot available")
    except ImportError:
        pass


@dataclass
class GPUCaptureConfig:
    """GPU 캡처 설정"""
    target_fps: int = 60
    region: Optional[Tuple[int, int, int, int]] = None  # (left, top, right, bottom)
    output_color: str = "RGB"  # RGB or BGR
    monitor_index: int = 0


class DXCamCapture:
    """dxcam 기반 GPU 캡처 (최신, 가장 빠름)"""
    
    def __init__(self, config: GPUCaptureConfig = None):
        if not DXCAM_AVAILABLE:
            raise RuntimeError("dxcam not installed. Run: pip install dxcam")
        
        self.config = config or GPUCaptureConfig()
        self.camera = None
        self.running = False
        self._init_camera()
    
    def _init_camera(self):
        """카메라 초기화"""
        try:
            self.camera = dxcam.create(
                output_idx=self.config.monitor_index,
                output_color=self.config.output_color
            )
            print(f"[GPU] DXCam initialized: {self.camera.width}x{self.camera.height}")
        except Exception as e:
            print(f"[GPU] DXCam init error: {e}")
            self.camera = None
    
    def capture(self) -> Optional[np.ndarray]:
        """단일 프레임 캡처"""
        if not self.camera:
            return None
        
        try:
            frame = self.camera.grab(region=self.config.region)
            return frame
        except Exception as e:
            print(f"[GPU] Capture error: {e}")
            return None
    
    def start_streaming(self, callback: Callable[[np.ndarray], None]):
        """연속 캡처 스트리밍 시작"""
        if not self.camera:
            return
        
        self.running = True
        self.camera.start(
            target_fps=self.config.target_fps,
            video_mode=True
        )
        
        def stream_loop():
            while self.running:
                frame = self.camera.get_latest_frame()
                if frame is not None:
                    callback(frame)
        
        self._stream_thread = threading.Thread(target=stream_loop, daemon=True)
        self._stream_thread.start()
    
    def stop_streaming(self):
        """스트리밍 중지"""
        self.running = False
        if self.camera:
            self.camera.stop()
    
    def get_resolution(self) -> Tuple[int, int]:
        """현재 해상도"""
        if self.camera:
            return self.camera.width, self.camera.height
        return 0, 0
    
    def set_region(self, left: int, top: int, right: int, bottom: int):
        """캡처 영역 설정"""
        self.config.region = (left, top, right, bottom)
    
    def release(self):
        """리소스 해제"""
        self.stop_streaming()
        if self.camera:
            del self.camera
            self.camera = None


class D3DShotCapture:
    """d3dshot 기반 GPU 캡처 (대안)"""
    
    def __init__(self, config: GPUCaptureConfig = None):
        if not D3DSHOT_AVAILABLE:
            raise RuntimeError("d3dshot not installed. Run: pip install d3dshot")
        
        self.config = config or GPUCaptureConfig()
        self.d3d = None
        self._init_d3d()
    
    def _init_d3d(self):
        """D3DShot 초기화"""
        try:
            self.d3d = d3dshot.create(
                capture_output="numpy",
                frame_buffer_size=60
            )
            displays = self.d3d.displays
            if displays:
                print(f"[GPU] D3DShot initialized: {len(displays)} displays")
        except Exception as e:
            print(f"[GPU] D3DShot init error: {e}")
            self.d3d = None
    
    def capture(self) -> Optional[np.ndarray]:
        """단일 프레임 캡처"""
        if not self.d3d:
            return None
        
        try:
            frame = self.d3d.screenshot(region=self.config.region)
            if frame is not None:
                # BGR to RGB
                if self.config.output_color == "RGB":
                    frame = frame[:, :, ::-1]
            return frame
        except Exception as e:
            print(f"[GPU] Capture error: {e}")
            return None
    
    def start_streaming(self, callback: Callable[[np.ndarray], None]):
        """연속 캡처"""
        if not self.d3d:
            return
        
        self.d3d.capture(
            target_fps=self.config.target_fps,
            region=self.config.region
        )
        
        self.running = True
        
        def stream_loop():
            while self.running:
                frame = self.d3d.get_latest_frame()
                if frame is not None:
                    if self.config.output_color == "RGB":
                        frame = frame[:, :, ::-1]
                    callback(frame)
                time.sleep(1.0 / self.config.target_fps)
        
        self._stream_thread = threading.Thread(target=stream_loop, daemon=True)
        self._stream_thread.start()
    
    def stop_streaming(self):
        """스트리밍 중지"""
        self.running = False
        if self.d3d:
            self.d3d.stop()
    
    def release(self):
        """리소스 해제"""
        self.stop_streaming()
        self.d3d = None


class GPUCapture:
    """통합 GPU 캡처 인터페이스"""
    
    def __init__(self, config: GPUCaptureConfig = None):
        self.config = config or GPUCaptureConfig()
        self.backend = None
        self.backend_name = None
        
        # 사용 가능한 백엔드 선택
        if DXCAM_AVAILABLE:
            try:
                self.backend = DXCamCapture(self.config)
                self.backend_name = "dxcam"
                print("[GPU] Using dxcam backend")
            except Exception as e:
                print(f"[GPU] dxcam failed: {e}")
        
        if self.backend is None and D3DSHOT_AVAILABLE:
            try:
                self.backend = D3DShotCapture(self.config)
                self.backend_name = "d3dshot"
                print("[GPU] Using d3dshot backend")
            except Exception as e:
                print(f"[GPU] d3dshot failed: {e}")
        
        if self.backend is None:
            print("[GPU] No GPU capture backend available, using CPU fallback")
    
    @property
    def available(self) -> bool:
        """GPU 캡처 사용 가능 여부"""
        return self.backend is not None
    
    def capture(self) -> Optional[np.ndarray]:
        """프레임 캡처"""
        if self.backend:
            return self.backend.capture()
        return None
    
    def capture_jpeg(self, quality: int = 75) -> Optional[bytes]:
        """JPEG으로 캡처 및 인코딩"""
        frame = self.capture()
        if frame is None:
            return None
        
        from PIL import Image
        import io
        
        img = Image.fromarray(frame)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=quality, optimize=True)
        return buf.getvalue()
    
    def start_streaming(self, callback: Callable[[np.ndarray], None]):
        """스트리밍 시작"""
        if self.backend:
            self.backend.start_streaming(callback)
    
    def stop_streaming(self):
        """스트리밍 중지"""
        if self.backend:
            self.backend.stop_streaming()
    
    def get_resolution(self) -> Tuple[int, int]:
        """해상도"""
        if self.backend and hasattr(self.backend, 'get_resolution'):
            return self.backend.get_resolution()
        return (1920, 1080)
    
    def release(self):
        """리소스 해제"""
        if self.backend:
            self.backend.release()


# Benchmark utility
def benchmark_capture(duration: float = 5.0):
    """캡처 성능 벤치마크"""
    import mss
    
    print(f"\n{'='*50}")
    print("GPU vs CPU Capture Benchmark")
    print(f"{'='*50}\n")
    
    results = {}
    
    # CPU Capture (mss)
    print("[CPU] Testing mss capture...")
    sct = mss.mss()
    monitor = sct.monitors[1]
    
    start = time.time()
    frames = 0
    while time.time() - start < duration:
        sct.grab(monitor)
        frames += 1
    
    cpu_fps = frames / duration
    results['cpu_mss'] = cpu_fps
    print(f"[CPU] mss: {cpu_fps:.1f} FPS")
    
    # GPU Capture
    if DXCAM_AVAILABLE or D3DSHOT_AVAILABLE:
        print("[GPU] Testing GPU capture...")
        gpu = GPUCapture()
        
        if gpu.available:
            start = time.time()
            frames = 0
            while time.time() - start < duration:
                frame = gpu.capture()
                if frame is not None:
                    frames += 1
            
            gpu_fps = frames / duration
            results['gpu'] = gpu_fps
            print(f"[GPU] {gpu.backend_name}: {gpu_fps:.1f} FPS")
            
            speedup = gpu_fps / cpu_fps if cpu_fps > 0 else 0
            print(f"\n[Result] GPU is {speedup:.1f}x faster than CPU")
            
            gpu.release()
    else:
        print("[GPU] No GPU backend available")
    
    return results


def is_gpu_available() -> bool:
    """GPU 캡처 사용 가능 여부"""
    return DXCAM_AVAILABLE or D3DSHOT_AVAILABLE


if __name__ == "__main__":
    benchmark_capture()
