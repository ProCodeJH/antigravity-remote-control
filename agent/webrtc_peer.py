"""
WebRTC P2P Connection Module
============================
릴레이 서버 우회하여 Mobile ↔ Agent 직접 연결
지연시간 70% 감소 예상

의존성: pip install aiortc
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, Any
import logging

# aiortc imports
try:
    from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
    from aiortc import VideoStreamTrack, RTCDataChannel
    from aiortc.contrib.media import MediaStreamTrack
    from av import VideoFrame
    import numpy as np
    from PIL import Image
    WEBRTC_AVAILABLE = True
except ImportError:
    WEBRTC_AVAILABLE = False
    print("[WebRTC] aiortc not installed. Run: pip install aiortc")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webrtc")


@dataclass
class WebRTCConfig:
    """WebRTC 설정"""
    stun_servers: list = field(default_factory=lambda: [
        "stun:stun.l.google.com:19302",
        "stun:stun1.l.google.com:19302"
    ])
    turn_servers: list = field(default_factory=list)  # TURN 서버 (NAT 실패 시)
    video_codec: str = "VP8"
    max_bitrate: int = 2_000_000  # 2 Mbps
    

class ScreenVideoTrack(MediaStreamTrack if WEBRTC_AVAILABLE else object):
    """화면 캡처를 WebRTC 비디오 트랙으로 변환"""
    
    kind = "video"
    
    def __init__(self, capture_func: Callable[[], np.ndarray], fps: int = 30):
        if WEBRTC_AVAILABLE:
            super().__init__()
        self.capture_func = capture_func
        self.fps = fps
        self.frame_count = 0
        self._start_time = time.time()
    
    async def recv(self):
        """다음 비디오 프레임 생성"""
        if not WEBRTC_AVAILABLE:
            raise RuntimeError("aiortc not available")
        
        # FPS 유지
        pts = self.frame_count
        self.frame_count += 1
        
        # 화면 캡처
        try:
            frame_array = self.capture_func()
            if frame_array is None:
                # 빈 프레임 반환
                frame_array = np.zeros((720, 1280, 3), dtype=np.uint8)
        except Exception as e:
            logger.error(f"Capture error: {e}")
            frame_array = np.zeros((720, 1280, 3), dtype=np.uint8)
        
        # VideoFrame으로 변환
        frame = VideoFrame.from_ndarray(frame_array, format="rgb24")
        frame.pts = pts
        frame.time_base = fractions.Fraction(1, self.fps)
        
        # FPS 유지를 위한 대기
        elapsed = time.time() - self._start_time
        expected = self.frame_count / self.fps
        if elapsed < expected:
            await asyncio.sleep(expected - elapsed)
        
        return frame


class WebRTCPeer:
    """WebRTC P2P 연결 관리"""
    
    def __init__(self, config: WebRTCConfig = None):
        if not WEBRTC_AVAILABLE:
            raise RuntimeError("aiortc not installed. Run: pip install aiortc")
        
        self.config = config or WebRTCConfig()
        self.pc: Optional[RTCPeerConnection] = None
        self.data_channel: Optional[RTCDataChannel] = None
        self.video_track: Optional[ScreenVideoTrack] = None
        
        # 콜백
        self.on_message: Optional[Callable[[str], None]] = None
        self.on_connected: Optional[Callable[[], None]] = None
        self.on_disconnected: Optional[Callable[[], None]] = None
        
        # 상태
        self.connected = False
        self._pending_candidates = []
    
    async def create_peer_connection(self):
        """RTCPeerConnection 생성"""
        ice_servers = []
        
        # STUN 서버
        for stun in self.config.stun_servers:
            ice_servers.append({"urls": stun})
        
        # TURN 서버
        for turn in self.config.turn_servers:
            ice_servers.append(turn)
        
        self.pc = RTCPeerConnection(configuration={"iceServers": ice_servers})
        
        # ICE 이벤트 핸들러
        @self.pc.on("icecandidate")
        async def on_icecandidate(candidate):
            if candidate:
                logger.info(f"ICE candidate: {candidate.candidate}")
        
        @self.pc.on("connectionstatechange")
        async def on_connectionstatechange():
            state = self.pc.connectionState
            logger.info(f"Connection state: {state}")
            
            if state == "connected":
                self.connected = True
                if self.on_connected:
                    self.on_connected()
            elif state in ["disconnected", "failed", "closed"]:
                self.connected = False
                if self.on_disconnected:
                    self.on_disconnected()
        
        @self.pc.on("datachannel")
        async def on_datachannel(channel):
            self.data_channel = channel
            self._setup_data_channel()
        
        return self.pc
    
    def _setup_data_channel(self):
        """데이터 채널 이벤트 설정"""
        if not self.data_channel:
            return
        
        @self.data_channel.on("message")
        async def on_message(message):
            if self.on_message:
                self.on_message(message)
        
        @self.data_channel.on("open")
        async def on_open():
            logger.info("Data channel opened")
        
        @self.data_channel.on("close")
        async def on_close():
            logger.info("Data channel closed")
    
    async def create_offer(self, capture_func: Callable = None) -> dict:
        """SDP Offer 생성 (Agent 측)"""
        if not self.pc:
            await self.create_peer_connection()
        
        # 데이터 채널 생성 (입력 수신용)
        self.data_channel = self.pc.createDataChannel("input", ordered=True)
        self._setup_data_channel()
        
        # 비디오 트랙 추가 (화면 스트리밍)
        if capture_func:
            self.video_track = ScreenVideoTrack(capture_func)
            self.pc.addTrack(self.video_track)
        
        # Offer 생성
        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)
        
        return {
            "type": "offer",
            "sdp": self.pc.localDescription.sdp
        }
    
    async def create_answer(self, offer: dict) -> dict:
        """SDP Answer 생성 (Mobile 측)"""
        if not self.pc:
            await self.create_peer_connection()
        
        # Remote description 설정
        await self.pc.setRemoteDescription(
            RTCSessionDescription(sdp=offer["sdp"], type=offer["type"])
        )
        
        # Answer 생성
        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)
        
        return {
            "type": "answer",
            "sdp": self.pc.localDescription.sdp
        }
    
    async def set_remote_description(self, desc: dict):
        """Remote SDP 설정"""
        await self.pc.setRemoteDescription(
            RTCSessionDescription(sdp=desc["sdp"], type=desc["type"])
        )
        
        # 대기 중인 ICE candidates 처리
        for candidate in self._pending_candidates:
            await self.add_ice_candidate(candidate)
        self._pending_candidates.clear()
    
    async def add_ice_candidate(self, candidate: dict):
        """ICE Candidate 추가"""
        if not self.pc.remoteDescription:
            self._pending_candidates.append(candidate)
            return
        
        try:
            ice_candidate = RTCIceCandidate(
                sdpMid=candidate.get("sdpMid"),
                sdpMLineIndex=candidate.get("sdpMLineIndex"),
                candidate=candidate.get("candidate")
            )
            await self.pc.addIceCandidate(ice_candidate)
        except Exception as e:
            logger.error(f"Add ICE candidate error: {e}")
    
    def send_message(self, message: str):
        """데이터 채널로 메시지 전송"""
        if self.data_channel and self.data_channel.readyState == "open":
            self.data_channel.send(message)
    
    async def close(self):
        """연결 종료"""
        if self.pc:
            await self.pc.close()
            self.pc = None
        self.connected = False


class WebRTCSignaling:
    """WebSocket 기반 시그널링 (SDP/ICE 교환)"""
    
    def __init__(self, ws_send: Callable, peer: WebRTCPeer):
        self.ws_send = ws_send
        self.peer = peer
    
    async def handle_signal(self, data: dict):
        """시그널링 메시지 처리"""
        signal_type = data.get("signalType")
        
        if signal_type == "offer":
            # Offer 수신 → Answer 생성 및 전송
            answer = await self.peer.create_answer(data)
            await self.ws_send(json.dumps({
                "type": "webrtc_signal",
                "signalType": "answer",
                **answer
            }))
        
        elif signal_type == "answer":
            # Answer 수신
            await self.peer.set_remote_description(data)
        
        elif signal_type == "ice_candidate":
            # ICE Candidate 수신
            await self.peer.add_ice_candidate(data)
    
    async def initiate_connection(self, capture_func: Callable = None):
        """연결 시작 (Offer 생성 및 전송)"""
        offer = await self.peer.create_offer(capture_func)
        await self.ws_send(json.dumps({
            "type": "webrtc_signal",
            "signalType": "offer",
            **offer
        }))


# Fractions import for VideoFrame timing
import fractions


def is_webrtc_available() -> bool:
    """WebRTC 사용 가능 여부"""
    return WEBRTC_AVAILABLE
