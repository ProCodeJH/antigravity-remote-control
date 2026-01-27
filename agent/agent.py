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
    """BitBlt 기반 고성능 스크린 캡처"""
    
    def __init__(self):
        self.sct = mss.mss()
        self.frame_id = 0
        
    def capture_frame(self) -> dict:
        """화면 캡처 및 JPEG 인코딩"""
        try:
            # 모니터 캡처
            monitor = self.sct.monitors[CONFIG.monitor]
            screenshot = self.sct.grab(monitor)
            
            # PIL Image로 변환
            img = Image.frombytes('RGB', screenshot.size, screenshot.bgra, 'raw', 'BGRX')
            
            # 해상도 조정 (필요시)
            if img.size != (CONFIG.screen_width, CONFIG.screen_height):
                img = img.resize((CONFIG.screen_width, CONFIG.screen_height), Image.LANCZOS)
            
            # JPEG 인코딩
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=CONFIG.jpeg_quality, optimize=True)
            jpeg_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            self.frame_id += 1
            
            return {
                "type": "frame",
                "frameId": self.frame_id,
                "timestamp": int(time.time() * 1000),
                "width": CONFIG.screen_width,
                "height": CONFIG.screen_height,
                "quality": CONFIG.jpeg_quality,
                "data": jpeg_data
            }
        except Exception as e:
            print(f"[ERROR] Screen capture failed: {e}")
            return None

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
# Main Agent
# ============================================================================
class RemoteAgent:
    """통합 원격 제어 에이전트"""
    
    def __init__(self):
        self.capture = ScreenCapture()
        self.injector = InputInjector()
        self.monitor = SystemMonitor()
        self.bridge = AntigravityBridge()
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        
    async def connect(self):
        """릴레이 서버에 연결"""
        print(f"[AGENT] Connecting to {CONFIG.relay_url}...")
        
        while True:
            try:
                self.ws = await websockets.connect(CONFIG.relay_url)
                print("[AGENT] WebSocket connected!")
                
                # 인증
                await self.ws.send(json.dumps({
                    "type": "auth",
                    "sessionId": CONFIG.session_id,
                    "clientType": "agent"
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
                
    async def send_frames(self):
        """프레임 스트리밍 루프"""
        interval = 1.0 / CONFIG.capture_fps
        
        while self.running:
            try:
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
                    
                elif msg_type == "peer_connected":
                    print(f"[AGENT] Mobile client connected!")
                    
                elif msg_type == "peer_disconnected":
                    print(f"[AGENT] Mobile client disconnected")
                    
            except websockets.ConnectionClosed:
                print("[AGENT] Connection closed")
                break
            except Exception as e:
                print(f"[ERROR] Message receive error: {e}")
                
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
