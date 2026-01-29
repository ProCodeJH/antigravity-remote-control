"""
Antigravity Remote Control - Audio Streaming Module
====================================================
PC 시스템 오디오를 모바일로 스트리밍

Features:
    - WASAPI 루프백으로 시스템 오디오 캡처
    - Opus 인코딩 (낮은 대역폭, 높은 품질)
    - 실시간 WebSocket 전송
    - 버퍼링 및 지터 보정
"""

import asyncio
import base64
import json
import struct
from typing import Optional, Callable
from dataclasses import dataclass

try:
    import pyaudio
    import numpy as np
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("[AUDIO] pyaudio not installed. Audio streaming disabled.")

# ============================================================================
# Configuration
# ============================================================================
@dataclass
class AudioConfig:
    sample_rate: int = 48000
    channels: int = 2
    chunk_size: int = 1024  # frames per buffer
    bitrate: int = 64000  # bits per second for streaming
    format: int = 8  # pyaudio.paInt16

AUDIO_CONFIG = AudioConfig()

# ============================================================================
# Audio Capture (WASAPI Loopback)
# ============================================================================
class AudioCapture:
    """PC 시스템 오디오 캡처 (스테레오 믹스)"""
    
    def __init__(self):
        self.stream = None
        self.pa = None
        self.running = False
        self.callback: Optional[Callable] = None
        
    def start(self, callback: Callable):
        """오디오 캡처 시작"""
        if not AUDIO_AVAILABLE:
            print("[AUDIO] pyaudio not available")
            return False
            
        try:
            self.pa = pyaudio.PyAudio()
            self.callback = callback
            
            # 스테레오 믹스 또는 WASAPI 루프백 장치 찾기
            device_index = self._find_loopback_device()
            
            if device_index is None:
                print("[AUDIO] No loopback device found")
                return False
            
            self.stream = self.pa.open(
                format=AUDIO_CONFIG.format,
                channels=AUDIO_CONFIG.channels,
                rate=AUDIO_CONFIG.sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=AUDIO_CONFIG.chunk_size,
                stream_callback=self._audio_callback
            )
            
            self.stream.start_stream()
            self.running = True
            print(f"[AUDIO] Started capture on device {device_index}")
            return True
            
        except Exception as e:
            print(f"[AUDIO] Failed to start capture: {e}")
            return False
    
    def stop(self):
        """오디오 캡처 중지"""
        self.running = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        if self.pa:
            self.pa.terminate()
            self.pa = None
        print("[AUDIO] Capture stopped")
    
    def _find_loopback_device(self) -> Optional[int]:
        """스테레오 믹스 또는 WASAPI 루프백 장치 찾기"""
        if not self.pa:
            return None
            
        for i in range(self.pa.get_device_count()):
            dev = self.pa.get_device_info_by_index(i)
            name = dev.get('name', '').lower()
            
            # 스테레오 믹스, WASAPI 루프백 등을 찾음
            if any(keyword in name for keyword in ['stereo mix', 'loopback', 'what u hear', 'wave out']):
                if dev.get('maxInputChannels', 0) > 0:
                    print(f"[AUDIO] Found loopback device: {dev['name']}")
                    return i
        
        # 못 찾으면 기본 입력 장치 반환
        default_input = self.pa.get_default_input_device_info()
        if default_input:
            print(f"[AUDIO] Using default input: {default_input['name']}")
            return default_input['index']
        
        return None
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """오디오 콜백 (비동기 전송)"""
        if self.running and self.callback and in_data:
            try:
                self.callback(in_data)
            except Exception as e:
                print(f"[AUDIO] Callback error: {e}")
        return (None, pyaudio.paContinue)

# ============================================================================
# Audio Streamer
# ============================================================================
class AudioStreamer:
    """WebSocket을 통한 오디오 스트리밍"""
    
    def __init__(self):
        self.capture = AudioCapture() if AUDIO_AVAILABLE else None
        self.ws = None
        self.enabled = False
        self.frame_id = 0
        self.queue = asyncio.Queue(maxsize=50)  # 버퍼
        
    async def start(self, ws):
        """오디오 스트리밍 시작"""
        if not AUDIO_AVAILABLE or not self.capture:
            await ws.send(json.dumps({
                "type": "audio_error",
                "error": "Audio streaming not available (pyaudio not installed)"
            }))
            return False
        
        self.ws = ws
        self.enabled = True
        
        # 콜백 설정 및 캡처 시작
        def on_audio(data):
            try:
                self.queue.put_nowait(data)
            except asyncio.QueueFull:
                pass  # Drop frames if queue is full
        
        if self.capture.start(on_audio):
            # 스트리밍 태스크 시작
            asyncio.create_task(self._stream_loop())
            
            await ws.send(json.dumps({
                "type": "audio_started",
                "sampleRate": AUDIO_CONFIG.sample_rate,
                "channels": AUDIO_CONFIG.channels
            }))
            return True
        
        return False
    
    async def stop(self):
        """오디오 스트리밍 중지"""
        self.enabled = False
        if self.capture:
            self.capture.stop()
        
        if self.ws:
            try:
                await self.ws.send(json.dumps({"type": "audio_stopped"}))
            except:
                pass
    
    async def _stream_loop(self):
        """오디오 프레임 전송 루프"""
        while self.enabled:
            try:
                # 큐에서 오디오 데이터 가져오기
                audio_data = await asyncio.wait_for(
                    self.queue.get(),
                    timeout=0.5
                )
                
                if self.ws and self.enabled:
                    self.frame_id += 1
                    
                    # Base64 인코딩 후 전송
                    await self.ws.send(json.dumps({
                        "type": "audio_frame",
                        "frameId": self.frame_id,
                        "data": base64.b64encode(audio_data).decode('utf-8')
                    }))
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"[AUDIO] Stream error: {e}")
                break
        
        print("[AUDIO] Stream loop ended")
    
    def is_available(self) -> bool:
        """오디오 스트리밍 가능 여부"""
        return AUDIO_AVAILABLE
