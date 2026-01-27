"""
Antigravity Remote Control - PC Agent
=====================================
스크린 캡처, 입력 인젝션, Antigravity API 브릿지 담당

Requirements:
    pip install websockets pyautogui mss pillow psutil aiohttp
"""

import asyncio
import json
import base64
import io
import time
import sys
import os
from dataclasses import dataclass
from typing import Optional

import websockets
import pyautogui
import mss
from PIL import Image
import psutil
import aiohttp

# ============================================================================
# Configuration
# ============================================================================
@dataclass
class Config:
    relay_url: str = "ws://localhost:8080/ws/relay"
    antigravity_url: str = "http://localhost:8765"
    session_id: str = "test-session"
    screen_width: int = 1920
    screen_height: int = 1080
    capture_fps: int = 15
    jpeg_quality: int = 60
    monitor: int = 1  # Primary monitor

CONFIG = Config()

# ============================================================================
# Screen Capture Engine
# ============================================================================
class ScreenCapture:
    """GPU 가속 + BitBlt 기반 고성능 스크린 캡처 (바이너리 전송 + 적응형 화질)"""
    
    def __init__(self):
        self.sct = mss.mss()
        self.frame_id = 0
        self.monitors = self.sct.monitors
        
        # Adaptive quality settings
        self.current_quality = CONFIG.jpeg_quality
        self.current_fps = CONFIG.capture_fps
        self.min_quality = 20
        self.max_quality = 85
        self.latency_history = []
        self.last_adjust_time = time.time()
        
        # GPU 가속 캡처 초기화
        self.gpu_capture = None
        self.use_gpu = False
        try:
            from gpu_capture import GPUCapture, is_gpu_available
            if is_gpu_available():
                self.gpu_capture = GPUCapture()
                self.use_gpu = self.gpu_capture.available
                if self.use_gpu:
                    print(f"[CAPTURE] GPU acceleration enabled ({self.gpu_capture.backend_name})")
        except ImportError:
            print("[CAPTURE] GPU capture not available, using CPU")
        
    def get_monitor_list(self) -> list:
        """사용 가능한 모니터 목록 반환"""
        return [
            {
                "id": i,
                "width": m["width"],
                "height": m["height"],
                "left": m["left"],
                "top": m["top"]
            }
            for i, m in enumerate(self.monitors) if i > 0  # Skip "all monitors" entry
        ]
    
    def set_monitor(self, monitor_id: int):
        """캡처할 모니터 변경"""
        if 0 < monitor_id < len(self.monitors):
            global CONFIG
            CONFIG.monitor = monitor_id
            print(f"[CAPTURE] Switched to monitor {monitor_id}")
            return True
        return False
    
    def adjust_quality(self, latency_ms: int):
        """네트워크 지연에 따라 화질 자동 조절"""
        self.latency_history.append(latency_ms)
        if len(self.latency_history) > 30:  # Keep last 30 samples
            self.latency_history.pop(0)
        
        # Adjust every 2 seconds
        if time.time() - self.last_adjust_time < 2:
            return
        
        self.last_adjust_time = time.time()
        avg_latency = sum(self.latency_history) / len(self.latency_history)
        
        if avg_latency > 200:  # High latency - reduce quality
            self.current_quality = max(self.min_quality, self.current_quality - 10)
            self.current_fps = max(5, self.current_fps - 2)
        elif avg_latency < 50:  # Low latency - increase quality
            self.current_quality = min(self.max_quality, self.current_quality + 5)
            self.current_fps = min(30, self.current_fps + 1)
        
        print(f"[ADAPTIVE] Quality: {self.current_quality}%, FPS: {self.current_fps}, Avg Latency: {avg_latency:.0f}ms")
        
    def capture_frame(self) -> dict:
        """화면 캡처 및 JPEG 인코딩 (JSON 호환)"""
        try:
            # 모니터 캡처
            monitor = self.sct.monitors[CONFIG.monitor]
            screenshot = self.sct.grab(monitor)
            
            # PIL Image로 변환
            img = Image.frombytes('RGB', screenshot.size, screenshot.bgra, 'raw', 'BGRX')
            
            # 해상도 조정 (필요시)
            if img.size != (CONFIG.screen_width, CONFIG.screen_height):
                img = img.resize((CONFIG.screen_width, CONFIG.screen_height), Image.LANCZOS)
            
            # JPEG 인코딩 (적응형 화질 사용)
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=self.current_quality, optimize=True)
            jpeg_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            self.frame_id += 1
            
            return {
                "type": "frame",
                "frameId": self.frame_id,
                "timestamp": int(time.time() * 1000),
                "width": CONFIG.screen_width,
                "height": CONFIG.screen_height,
                "quality": self.current_quality,
                "data": jpeg_data
            }
        except Exception as e:
            print(f"[ERROR] Screen capture failed: {e}")
            return None
    
    def capture_binary_frame(self) -> tuple:
        """화면 캡처 및 바이너리 JPEG 반환 (GPU 가속 + 33% 더 효율적)"""
        try:
            import struct
            
            # GPU 가속 캡처 시도
            if self.use_gpu and self.gpu_capture:
                frame = self.gpu_capture.capture()
                if frame is not None:
                    img = Image.fromarray(frame)
                    
                    # 해상도 조정 (필요시)
                    if img.size != (CONFIG.screen_width, CONFIG.screen_height):
                        img = img.resize((CONFIG.screen_width, CONFIG.screen_height), Image.LANCZOS)
                    
                    # JPEG 인코딩
                    buffer = io.BytesIO()
                    img.save(buffer, format='JPEG', quality=self.current_quality, optimize=True)
                    
                    self.frame_id += 1
                    timestamp = int(time.time() * 1000)
                    header = struct.pack('>I Q', self.frame_id, timestamp)
                    
                    return header + buffer.getvalue(), self.frame_id, timestamp
            
            # CPU 폴백: mss 사용
            monitor = self.sct.monitors[CONFIG.monitor]
            screenshot = self.sct.grab(monitor)
            
            # PIL Image로 변환
            img = Image.frombytes('RGB', screenshot.size, screenshot.bgra, 'raw', 'BGRX')
            
            # 해상도 조정 (필요시)
            if img.size != (CONFIG.screen_width, CONFIG.screen_height):
                img = img.resize((CONFIG.screen_width, CONFIG.screen_height), Image.LANCZOS)
            
            # JPEG 인코딩 (적응형 화질, 바이너리)
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=self.current_quality, optimize=True)
            
            self.frame_id += 1
            
            # 메타데이터 헤더 (12 bytes) + JPEG 바이너리
            # Header: frameId (4 bytes) + timestamp (8 bytes)
            timestamp = int(time.time() * 1000)
            header = struct.pack('>I Q', self.frame_id, timestamp)
            
            return header + buffer.getvalue(), self.frame_id, timestamp
        except Exception as e:
            print(f"[ERROR] Binary capture failed: {e}")
            return None, 0, 0
    
    def capture_diff_frame(self, force_keyframe: bool = False) -> bytes:
        """차분 프레임 캡처 (GPU 가속 + 변경된 블록만 전송, 대역폭 80% 절감)"""
        try:
            from diff_encoder import get_encoder
            import numpy as np
            
            # GPU 가속 캡처 시도
            frame = None
            if self.use_gpu and self.gpu_capture:
                frame = self.gpu_capture.capture()
            
            # CPU 폴백
            if frame is None:
                monitor = self.sct.monitors[CONFIG.monitor]
                screenshot = self.sct.grab(monitor)
                frame = np.array(screenshot)[:, :, :3]  # BGRA -> BGR
                frame = frame[:, :, ::-1]  # BGR -> RGB
            
            # 차분 인코딩
            encoder = get_encoder(self.current_quality)
            diff_frame = encoder.encode(frame, force_keyframe)
            
            # 바이너리 직렬화
            return diff_frame.to_binary()
        except ImportError as e:
            print(f"[WARN] Diff encoder not available: {e}")
            # 폴백: 일반 바이너리 프레임
            data, _, _ = self.capture_binary_frame()
            return data
        except Exception as e:
            print(f"[ERROR] Diff capture failed: {e}")
            return None
    
    def get_frame_interval(self) -> float:
        """현재 FPS에 따른 프레임 간격 반환"""
        return 1.0 / self.current_fps

# ============================================================================
# Input Injector
# ============================================================================
class InputInjector:
    """마우스/키보드 입력 인젝션"""
    
    def __init__(self):
        pyautogui.FAILSAFE = False
        pyautogui.PAUSE = 0.01
        
    def handle_input(self, event: dict):
        """입력 이벤트 처리"""
        try:
            event_type = event.get("type")
            
            if event_type == "click":
                x = int(event["x"] * CONFIG.screen_width)
                y = int(event["y"] * CONFIG.screen_height)
                button = event.get("button", "left")
                pyautogui.click(x, y, button=button)
                print(f"[INPUT] Click: ({x}, {y}) {button}")
                
            elif event_type == "move":
                x = int(event["x"] * CONFIG.screen_width)
                y = int(event["y"] * CONFIG.screen_height)
                pyautogui.moveTo(x, y)
                
            elif event_type == "key":
                key = event["key"]
                modifiers = event.get("modifiers", {})
                
                # 모디파이어 처리
                keys_to_press = []
                if modifiers.get("ctrl"):
                    keys_to_press.append("ctrl")
                if modifiers.get("alt"):
                    keys_to_press.append("alt")
                if modifiers.get("shift"):
                    keys_to_press.append("shift")
                if modifiers.get("win"):
                    keys_to_press.append("win")
                keys_to_press.append(key)
                
                pyautogui.hotkey(*keys_to_press)
                print(f"[INPUT] Key: {'+'.join(keys_to_press)}")
                
            elif event_type == "scroll":
                delta_y = event.get("deltaY", 0)
                # 스크롤 방향 변환 (deltaY: 음수=위, 양수=아래)
                clicks = int(delta_y / -120)  # 표준 휠 단위
                pyautogui.scroll(clicks)
                print(f"[INPUT] Scroll: {clicks}")
                
            elif event_type == "drag":
                start_x = int(event["startX"] * CONFIG.screen_width)
                start_y = int(event["startY"] * CONFIG.screen_height)
                end_x = int(event["endX"] * CONFIG.screen_width)
                end_y = int(event["endY"] * CONFIG.screen_height)
                pyautogui.moveTo(start_x, start_y)
                pyautogui.drag(end_x - start_x, end_y - start_y, duration=0.3)
                print(f"[INPUT] Drag: ({start_x},{start_y}) -> ({end_x},{end_y})")
                
        except Exception as e:
            print(f"[ERROR] Input injection failed: {e}")

# ============================================================================
# System Monitor
# ============================================================================
class SystemMonitor:
    """시스템 상태 모니터링"""
    
    def get_status(self) -> dict:
        try:
            cpu_percent = psutil.cpu_percent(interval=None)
            memory = psutil.virtual_memory()
            
            # 배터리 정보 (노트북)
            battery = psutil.sensors_battery()
            battery_info = {
                "percent": battery.percent if battery else 100,
                "charging": battery.power_plugged if battery else True,
                "remaining": battery.secsleft if battery and battery.secsleft > 0 else None
            }
            
            # 네트워크 정보
            net_io = psutil.net_io_counters()
            
            return {
                "type": "status",
                "timestamp": int(time.time() * 1000),
                "system": {
                    "cpu": {"usage": cpu_percent},
                    "memory": {
                        "used": memory.used // (1024**2),
                        "total": memory.total // (1024**2),
                        "percent": memory.percent
                    },
                    "battery": battery_info,
                    "network": {
                        "bytesSent": net_io.bytes_sent,
                        "bytesRecv": net_io.bytes_recv
                    }
                }
            }
        except Exception as e:
            print(f"[ERROR] System monitoring failed: {e}")
            return {"type": "status", "error": str(e)}

# ============================================================================
# Antigravity Bridge
# ============================================================================
class AntigravityBridge:
    """Antigravity API 연동"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def start(self):
        self.session = aiohttp.ClientSession()
        
    async def stop(self):
        if self.session:
            await self.session.close()
            
    async def execute_command(self, command: str, cmd_type: str = "text") -> dict:
        """Antigravity에 명령 전달"""
        try:
            async with self.session.post(
                f"{CONFIG.antigravity_url}/api/execute",
                json={"command": command, "type": cmd_type}
            ) as resp:
                return await resp.json()
        except Exception as e:
            return {"success": False, "error": str(e)}
            
    async def get_antigravity_status(self) -> dict:
        """Antigravity 상태 조회"""
        try:
            async with self.session.get(
                f"{CONFIG.antigravity_url}/api/status"
            ) as resp:
                return await resp.json()
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}

# ============================================================================
# File Transfer Handler
# ============================================================================
class FileTransfer:
    """파일 전송 수신 및 저장"""
    
    def __init__(self):
        self.pending_files = {}  # fileId -> {name, size, chunks, received}
        self.save_dir = os.path.join(os.path.expanduser("~"), "Downloads", "RemoteFiles")
        os.makedirs(self.save_dir, exist_ok=True)
        
    def start_transfer(self, file_id: str, file_name: str, file_size: int, total_chunks: int) -> dict:
        """파일 전송 시작"""
        self.pending_files[file_id] = {
            "name": file_name,
            "size": file_size,
            "total_chunks": total_chunks,
            "chunks": {},
            "received": 0
        }
        print(f"[FILE] Starting transfer: {file_name} ({file_size} bytes, {total_chunks} chunks)")
        return {"success": True, "fileId": file_id}
    
    def receive_chunk(self, file_id: str, chunk_index: int, data: bytes) -> dict:
        """청크 수신"""
        if file_id not in self.pending_files:
            return {"success": False, "error": "Unknown file ID"}
        
        file_info = self.pending_files[file_id]
        file_info["chunks"][chunk_index] = data
        file_info["received"] += 1
        
        progress = (file_info["received"] / file_info["total_chunks"]) * 100
        print(f"[FILE] {file_info['name']}: {progress:.1f}% ({file_info['received']}/{file_info['total_chunks']})")
        
        return {
            "success": True,
            "progress": progress,
            "received": file_info["received"],
            "total": file_info["total_chunks"]
        }
    
    def complete_transfer(self, file_id: str) -> dict:
        """파일 전송 완료 및 저장"""
        if file_id not in self.pending_files:
            return {"success": False, "error": "Unknown file ID"}
        
        file_info = self.pending_files[file_id]
        
        # 모든 청크 수신 확인
        if file_info["received"] < file_info["total_chunks"]:
            missing = file_info["total_chunks"] - file_info["received"]
            return {"success": False, "error": f"Missing {missing} chunks"}
        
        # 청크를 순서대로 조합
        try:
            file_data = b""
            for i in range(file_info["total_chunks"]):
                file_data += file_info["chunks"][i]
            
            # 파일 저장
            save_path = os.path.join(self.save_dir, file_info["name"])
            
            # 동일 파일명 처리
            if os.path.exists(save_path):
                name, ext = os.path.splitext(file_info["name"])
                save_path = os.path.join(self.save_dir, f"{name}_{int(time.time())}{ext}")
            
            with open(save_path, "wb") as f:
                f.write(file_data)
            
            del self.pending_files[file_id]
            print(f"[FILE] Saved: {save_path}")
            
            return {
                "success": True,
                "path": save_path,
                "size": len(file_data)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def cancel_transfer(self, file_id: str) -> dict:
        """파일 전송 취소"""
        if file_id in self.pending_files:
            del self.pending_files[file_id]
            print(f"[FILE] Cancelled: {file_id}")
            return {"success": True}
        return {"success": False, "error": "Unknown file ID"}

# ============================================================================
# Main Agent
# ============================================================================
class RemoteAgent:
    """통합 원격 제어 에이전트"""
    
    def __init__(self):
        self.capture = ScreenCapture()
        self.injector = InputInjector()
        self.monitor = SystemMonitor()
        self.bridge = AntigravityBridge()
        self.file_transfer = FileTransfer()
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        self.device_id = None
        
        # OCR Button Detection
        try:
            from ocr_detector import ButtonDetector
            self.ocr = ButtonDetector()
            self.ocr_enabled = True
            print("[AGENT] OCR button detection enabled")
        except ImportError:
            self.ocr = None
            self.ocr_enabled = False
            print("[AGENT] OCR not available (install easyocr)")
        
    async def connect(self):
        """릴레이 서버에 연결"""
        print(f"[AGENT] Connecting to {CONFIG.relay_url}...")
        
        # Generate unique device ID
        import platform
        import uuid
        import socket as sock
        
        self.device_id = str(uuid.uuid4())[:16]
        hostname = sock.gethostname()
        
        while True:
            try:
                self.ws = await websockets.connect(CONFIG.relay_url)
                print("[AGENT] WebSocket connected!")
                
                # 디바이스 정보와 함께 인증
                await self.ws.send(json.dumps({
                    "type": "auth",
                    "sessionId": CONFIG.session_id,
                    "clientType": "agent",
                    "deviceInfo": {
                        "deviceId": self.device_id,
                        "name": f"{hostname}",
                        "hostname": hostname,
                        "ip": self._get_local_ip(),
                        "os": f"{platform.system()} {platform.release()}",
                        "antigravityStatus": "active",
                        "capabilities": ["screen", "input", "command", "file", "ocr"]
                    }
                }))
                
                # 인증 응답 대기
                response = await self.ws.recv()
                data = json.loads(response)
                
                if data.get("type") == "auth_success":
                    print(f"[AGENT] Authenticated: {data}")
                    return True
                else:
                    print(f"[AGENT] Auth failed: {data}")
                    return False
                    
            except Exception as e:
                print(f"[AGENT] Connection failed: {e}, retrying in 3s...")
                await asyncio.sleep(3)
    
    def _get_local_ip(self):
        """로컬 IP 주소 획득"""
        import socket as sock
        try:
            s = sock.socket(sock.AF_INET, sock.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
                
    async def send_frames(self):
        """프레임 스트리밍 루프 (차분 압축 + 바이너리 전송 + 적응형 FPS)"""
        use_diff = True   # 차분 압축 모드 (대역폭 80% 절감)
        use_binary = True  # 바이너리 모드 활성화
        
        while self.running:
            try:
                interval = self.capture.get_frame_interval()
                
                if use_diff:
                    # 차분 프레임 전송 (변경된 영역만, 80% 대역폭 절감)
                    diff_data = self.capture.capture_diff_frame()
                    if diff_data and self.ws:
                        # 차분 프레임임을 알리는 프리픽스 추가 (0x01)
                        await self.ws.send(b'\x01' + diff_data)
                elif use_binary:
                    # 바이너리 프레임 전송 (33% 더 효율적)
                    binary_data, frame_id, timestamp = self.capture.capture_binary_frame()
                    if binary_data and self.ws:
                        # 일반 바이너리 프레임 프리픽스 (0x00)
                        await self.ws.send(b'\x00' + binary_data)
                else:
                    # JSON 프레임 전송 (호환 모드)
                    frame = self.capture.capture_frame()
                    if frame and self.ws:
                        await self.ws.send(json.dumps(frame))
                        
                await asyncio.sleep(interval)
            except Exception as e:
                print(f"[ERROR] Frame send error: {e}")
                break
                
    async def send_status(self):
        """상태 전송 루프"""
        while self.running:
            try:
                status = self.monitor.get_status()
                
                # Antigravity 상태 추가
                ag_status = await self.bridge.get_antigravity_status()
                status["antigravity"] = ag_status
                
                if self.ws:
                    await self.ws.send(json.dumps(status))
                    
                await asyncio.sleep(1)  # 1초마다
            except Exception as e:
                print(f"[ERROR] Status send error: {e}")
                break
    
    async def send_heartbeat(self):
        """디바이스 하트비트 전송 (멀티 네트워크 디스커버리용)"""
        while self.running:
            try:
                # 썸네일 생성 (작은 이미지)
                frame = self.capture.capture_frame()
                thumbnail = None
                if frame and frame.get("data"):
                    # 썸네일은 더 작은 사이즈로
                    thumbnail = frame["data"][:500]  # 일부만 전송
                
                # Antigravity 상태
                ag_status = await self.bridge.get_antigravity_status()
                
                heartbeat = {
                    "type": "heartbeat",
                    "deviceId": self.device_id,
                    "timestamp": int(time.time() * 1000),
                    "antigravityStatus": ag_status.get("status", "unknown"),
                    "systemInfo": self.monitor.get_status().get("system"),
                    "thumbnail": thumbnail
                }
                
                if self.ws:
                    await self.ws.send(json.dumps(heartbeat))
                    
                await asyncio.sleep(10)  # 10초마다 하트비트
            except Exception as e:
                print(f"[ERROR] Heartbeat error: {e}")
                await asyncio.sleep(5)
                
    async def receive_messages(self):
        """메시지 수신 루프"""
        while self.running:
            try:
                message = await self.ws.recv()
                data = json.loads(message)
                
                msg_type = data.get("type")
                
                if msg_type in ["click", "move", "key", "scroll", "drag"]:
                    # 입력 이벤트
                    self.injector.handle_input(data)
                    
                elif msg_type == "command":
                    # Antigravity 명령
                    result = await self.bridge.execute_command(
                        data.get("text", ""),
                        data.get("cmdType", "text")
                    )
                    # 결과 전송
                    await self.ws.send(json.dumps({
                        "type": "commandResult",
                        "requestId": data.get("requestId"),
                        **result
                    }))
                
                elif msg_type == "get_monitors":
                    # 모니터 목록 조회
                    monitors = self.capture.get_monitor_list()
                    await self.ws.send(json.dumps({
                        "type": "monitors",
                        "list": monitors,
                        "current": CONFIG.monitor
                    }))
                    
                elif msg_type == "switch_monitor":
                    # 모니터 전환
                    monitor_id = data.get("monitorId", 1)
                    success = self.capture.set_monitor(monitor_id)
                    await self.ws.send(json.dumps({
                        "type": "monitor_switched",
                        "success": success,
                        "monitorId": monitor_id
                    }))
                
                elif msg_type == "latency_report":
                    # 클라이언트에서 보낸 latency 피드백
                    latency = data.get("latency", 100)
                    self.capture.adjust_quality(latency)
                
                # ============ File Transfer Handlers ============
                elif msg_type == "file_start":
                    # 파일 전송 시작
                    result = self.file_transfer.start_transfer(
                        data.get("fileId"),
                        data.get("fileName"),
                        data.get("fileSize"),
                        data.get("totalChunks")
                    )
                    await self.ws.send(json.dumps({
                        "type": "file_start_ack",
                        **result
                    }))
                
                elif msg_type == "file_chunk":
                    # 파일 청크 수신
                    chunk_data = base64.b64decode(data.get("data", ""))
                    result = self.file_transfer.receive_chunk(
                        data.get("fileId"),
                        data.get("chunkIndex"),
                        chunk_data
                    )
                    await self.ws.send(json.dumps({
                        "type": "file_progress",
                        "fileId": data.get("fileId"),
                        **result
                    }))
                
                elif msg_type == "file_complete":
                    # 파일 전송 완료
                    result = self.file_transfer.complete_transfer(data.get("fileId"))
                    await self.ws.send(json.dumps({
                        "type": "file_complete_ack",
                        "fileId": data.get("fileId"),
                        **result
                    }))
                
                elif msg_type == "file_cancel":
                    # 파일 전송 취소
                    result = self.file_transfer.cancel_transfer(data.get("fileId"))
                    await self.ws.send(json.dumps({
                        "type": "file_cancel_ack",
                        **result
                    }))
                    
                elif msg_type == "peer_connected":
                    print(f"[AGENT] Mobile client connected!")
                
                elif msg_type == "mobile_connected":
                    print(f"[AGENT] Mobile connected to this device!")
                    
                elif msg_type == "peer_disconnected":
                    print(f"[AGENT] Mobile client disconnected")
                
                # ============ OCR Button Detection Handlers ============
                elif msg_type == "detect_buttons":
                    # 현재 화면에서 버튼 감지
                    if self.ocr_enabled:
                        frame = self.capture.capture_frame()
                        if frame and frame.get("data"):
                            import base64
                            jpeg_bytes = base64.b64decode(frame["data"])
                            buttons = self.ocr.detect_from_bytes(jpeg_bytes)
                            await self.ws.send(json.dumps({
                                "type": "detected_buttons",
                                "buttons": [b.to_dict() for b in buttons],
                                "timestamp": int(time.time() * 1000)
                            }))
                    else:
                        await self.ws.send(json.dumps({
                            "type": "error",
                            "message": "OCR not available"
                        }))
                
                elif msg_type == "click_by_text":
                    # 텍스트로 버튼 찾아서 클릭
                    target_text = data.get("text", "")
                    if self.ocr_enabled and target_text:
                        # 먼저 현재 화면에서 버튼 다시 감지
                        frame = self.capture.capture_frame()
                        if frame and frame.get("data"):
                            jpeg_bytes = base64.b64decode(frame["data"])
                            self.ocr.detect_from_bytes(jpeg_bytes)
                        
                        button = self.ocr.find_button_by_text(target_text)
                        if button:
                            # 실제 픽셀 좌표로 직접 클릭 (pyautogui)
                            try:
                                pyautogui.click(button.x, button.y)
                                await self.ws.send(json.dumps({
                                    "type": "click_result",
                                    "success": True,
                                    "text": target_text,
                                    "x": button.x,
                                    "y": button.y
                                }))
                                print(f"[OCR] Clicked '{target_text}' at ({button.x}, {button.y})")
                            except Exception as e:
                                await self.ws.send(json.dumps({
                                    "type": "click_result",
                                    "success": False,
                                    "error": str(e)
                                }))
                        else:
                            await self.ws.send(json.dumps({
                                "type": "click_result",
                                "success": False,
                                "error": f"Button '{target_text}' not found"
                            }))
                    else:
                        await self.ws.send(json.dumps({
                            "type": "error",
                            "message": "OCR not available or text not specified"
                        }))
                
                # ============ WebRTC P2P Handlers ============
                elif msg_type == "request_webrtc":
                    # Mobile에서 WebRTC 연결 요청
                    await self.initiate_webrtc()
                
                elif msg_type == "webrtc_signal":
                    # WebRTC 시그널링 메시지 처리
                    await self.handle_webrtc_signal(data)
                
                # ============ ULTRA Feature Handlers ============
                elif msg_type == "voice_command":
                    # 음성 명령 처리
                    await self.handle_voice_command(data)
                
                elif msg_type == "get_macros":
                    # 매크로 목록 조회
                    await self.handle_get_macros()
                
                elif msg_type == "run_macro":
                    # 매크로 실행
                    await self.handle_run_macro(data.get("name", ""))
                
                elif msg_type == "clipboard_sync":
                    # 클립보드 동기화 시작/중지
                    await self.handle_clipboard_sync(data.get("action", "stop"))
                
                elif msg_type == "clipboard_set":
                    # 클립보드 설정 (Mobile → PC)
                    await self.handle_clipboard_set(data)
                
                elif msg_type == "audio_stream":
                    # 오디오 스트리밍 시작/중지
                    await self.handle_audio_stream(data.get("action", "stop"))
                
                elif msg_type == "gesture":
                    # 제스처 처리
                    await self.handle_gesture(data.get("gesture", ""))
                    
            except websockets.ConnectionClosed:
                print("[AGENT] Connection closed")
                break
            except Exception as e:
                print(f"[ERROR] Message receive error: {e}")
                
    async def initiate_webrtc(self):
        """WebRTC 연결 시작 (Offer 생성 및 전송)"""
        try:
            from webrtc_peer import WebRTCPeer, WebRTCSignaling, is_webrtc_available
            
            if not is_webrtc_available():
                print("[WEBRTC] aiortc not available, skipping P2P")
                await self.ws.send(json.dumps({
                    "type": "error",
                    "message": "WebRTC not available on agent"
                }))
                return
            
            print("[WEBRTC] Initiating P2P connection...")
            
            # WebRTC Peer 생성
            self.webrtc_peer = WebRTCPeer()
            
            # 화면 캡처 함수
            def get_screen_frame():
                import numpy as np
                monitor = self.capture.sct.monitors[CONFIG.monitor]
                screenshot = self.capture.sct.grab(monitor)
                frame = np.array(screenshot)[:, :, :3]  # BGRA -> BGR
                return frame[:, :, ::-1]  # BGR -> RGB
            
            # Offer 생성
            self.webrtc_signaling = WebRTCSignaling(
                lambda msg: asyncio.create_task(self.ws.send(msg)),
                self.webrtc_peer
            )
            
            await self.webrtc_signaling.initiate_connection(get_screen_frame)
            print("[WEBRTC] Offer sent")
            
        except ImportError:
            print("[WEBRTC] webrtc_peer module not found")
        except Exception as e:
            print(f"[WEBRTC] Init error: {e}")
    
    async def handle_webrtc_signal(self, data: dict):
        """WebRTC 시그널링 메시지 처리"""
        try:
            if hasattr(self, 'webrtc_signaling') and self.webrtc_signaling:
                await self.webrtc_signaling.handle_signal(data)
            else:
                # Signaling 없으면 초기화 후 처리
                await self.initiate_webrtc()
                if hasattr(self, 'webrtc_signaling'):
                    await self.webrtc_signaling.handle_signal(data)
        except Exception as e:
            print(f"[WEBRTC] Signal error: {e}")
    
    # ============ ULTRA Feature Methods ============
    
    async def handle_voice_command(self, data: dict):
        """음성 명령 처리"""
        try:
            from voice_control import VoiceCommandExecutor
            
            text = data.get("text", "")
            confidence = data.get("confidence", 0.0)
            
            if not hasattr(self, 'voice_executor'):
                self.voice_executor = VoiceCommandExecutor(self.injector, self.ocr)
            
            result = self.voice_executor.execute(text, confidence)
            
            await self.ws.send(json.dumps({
                "type": "voice_result",
                **result
            }))
            print(f"[VOICE] Command: {text} -> {result.get('result', result.get('error'))}")
        except ImportError:
            await self.ws.send(json.dumps({
                "type": "error",
                "message": "Voice control not available"
            }))
        except Exception as e:
            print(f"[VOICE] Error: {e}")
    
    async def handle_get_macros(self):
        """매크로 목록 조회"""
        try:
            from macro_engine import MacroEngine
            
            if not hasattr(self, 'macro_engine'):
                self.macro_engine = MacroEngine()
            
            macros = self.macro_engine.list_macros()
            await self.ws.send(json.dumps({
                "type": "macro_list",
                "macros": macros
            }))
        except ImportError:
            await self.ws.send(json.dumps({
                "type": "macro_list",
                "macros": []
            }))
    
    async def handle_run_macro(self, name: str):
        """매크로 실행"""
        try:
            from macro_engine import MacroEngine
            
            if not hasattr(self, 'macro_engine'):
                self.macro_engine = MacroEngine()
            
            result = self.macro_engine.run(name)
            await self.ws.send(json.dumps({
                "type": "macro_result",
                "name": name,
                **result
            }))
            print(f"[MACRO] {name}: {'Success' if result.get('success') else 'Failed'}")
        except Exception as e:
            await self.ws.send(json.dumps({
                "type": "macro_result",
                "name": name,
                "success": False,
                "error": str(e)
            }))
    
    async def handle_clipboard_sync(self, action: str):
        """클립보드 동기화"""
        try:
            from clipboard_sync import ClipboardSync
            
            if action == "start":
                async def send_clipboard(data):
                    if self.ws:
                        await self.ws.send(json.dumps(data))
                
                if not hasattr(self, 'clipboard_sync'):
                    self.clipboard_sync = ClipboardSync(
                        lambda d: asyncio.create_task(send_clipboard(d))
                    )
                self.clipboard_sync.start()
                print("[CLIPBOARD] Sync started")
            else:
                if hasattr(self, 'clipboard_sync'):
                    self.clipboard_sync.stop()
                print("[CLIPBOARD] Sync stopped")
        except ImportError:
            print("[CLIPBOARD] Module not available")
    
    async def handle_clipboard_set(self, data: dict):
        """클립보드 설정 (Mobile → PC)"""
        try:
            from clipboard_sync import ClipboardData, ClipboardType
            
            clip_data = ClipboardData.from_dict(data)
            
            if not hasattr(self, 'clipboard_sync'):
                from clipboard_sync import ClipboardSync
                self.clipboard_sync = ClipboardSync(lambda d: None)
            
            self.clipboard_sync.set_clipboard(clip_data)
        except ImportError:
            print("[CLIPBOARD] Module not available")
    
    async def handle_audio_stream(self, action: str):
        """오디오 스트리밍"""
        try:
            from audio_stream import UltraAudioStream
            
            if action == "start":
                async def send_audio(data):
                    if self.ws:
                        import base64
                        await self.ws.send(json.dumps({
                            "type": "audio_data",
                            "data": base64.b64encode(data).decode()
                        }))
                
                if not hasattr(self, 'audio_stream'):
                    self.audio_stream = UltraAudioStream(
                        lambda d: asyncio.create_task(send_audio(d))
                    )
                self.audio_stream.start()
                print("[AUDIO] Streaming started")
            else:
                if hasattr(self, 'audio_stream'):
                    self.audio_stream.stop()
                print("[AUDIO] Streaming stopped")
        except ImportError:
            print("[AUDIO] Module not available")
    
    async def handle_gesture(self, gesture: str):
        """제스처 처리"""
        try:
            from gesture_engine import UltraGestureEngine, GestureType, GestureEvent
            
            if not hasattr(self, 'gesture_engine'):
                self.gesture_engine = UltraGestureEngine()
            
            # 제스처 타입에 따른 액션 실행
            gesture_actions = {
                "swipe_left": ("hotkey", "alt+tab"),
                "swipe_right": ("hotkey", "alt+shift+tab"),
                "swipe_up": ("hotkey", "win+tab"),
                "swipe_down": ("hotkey", "win+d"),
            }
            
            action = gesture_actions.get(gesture)
            if action:
                action_type, params = action
                if action_type == "hotkey":
                    keys = params.split("+")
                    pyautogui.hotkey(*keys)
                    print(f"[GESTURE] {gesture} -> {params}")
                
                await self.ws.send(json.dumps({
                    "type": "gesture_result",
                    "gesture": gesture,
                    "action": params,
                    "success": True
                }))
            else:
                await self.ws.send(json.dumps({
                    "type": "gesture_result",
                    "gesture": gesture,
                    "success": False,
                    "error": "Unknown gesture"
                }))
        except Exception as e:
            print(f"[GESTURE] Error: {e}")
                
    async def run(self):
        """에이전트 실행"""
        await self.bridge.start()
        
        while True:
            if await self.connect():
                self.running = True
                
                # 병렬 태스크 실행
                tasks = [
                    asyncio.create_task(self.send_frames()),
                    asyncio.create_task(self.send_status()),
                    asyncio.create_task(self.send_heartbeat()),
                    asyncio.create_task(self.receive_messages())
                ]
                
                try:
                    await asyncio.gather(*tasks)
                except Exception as e:
                    print(f"[AGENT] Task error: {e}")
                finally:
                    self.running = False
                    for task in tasks:
                        task.cancel()
                        
            print("[AGENT] Reconnecting in 5s...")
            await asyncio.sleep(5)

# ============================================================================
# Entry Point
# ============================================================================
def main():
    # CLI 인자 처리
    if len(sys.argv) > 1:
        CONFIG.relay_url = sys.argv[1]
    if len(sys.argv) > 2:
        CONFIG.session_id = sys.argv[2]
        
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║     🖥️  Antigravity Remote Control - PC Agent               ║
╠══════════════════════════════════════════════════════════════╣
║  Relay URL:   {CONFIG.relay_url:<45} ║
║  Session ID:  {CONFIG.session_id:<45} ║
║  Resolution:  {CONFIG.screen_width}x{CONFIG.screen_height}                                  ║
║  FPS:         {CONFIG.capture_fps}                                            ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    agent = RemoteAgent()
    asyncio.run(agent.run())

if __name__ == "__main__":
    main()
