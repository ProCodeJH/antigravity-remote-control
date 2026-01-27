"""
ULTRA Audio Streaming Engine
============================
PC 시스템 오디오를 Mobile로 스트리밍
WASAPI Loopback + Opus 코덱

Requirements:
    pip install soundcard
    pip install numpy
"""

import io
import time
import threading
import struct
from dataclasses import dataclass
from typing import Optional, Callable, List
import numpy as np

# Soundcard for system audio capture
try:
    import soundcard as sc
    SOUNDCARD_AVAILABLE = True
except ImportError:
    SOUNDCARD_AVAILABLE = False
    print("[AUDIO] soundcard not available. Run: pip install soundcard")


@dataclass
class AudioConfig:
    """오디오 설정"""
    sample_rate: int = 48000
    channels: int = 2  # Stereo
    chunk_size: int = 960  # 20ms at 48kHz
    bitrate: int = 64000  # Opus bitrate


class AudioCapture:
    """시스템 오디오 캡처 (WASAPI Loopback)"""
    
    def __init__(self, config: AudioConfig = None):
        if not SOUNDCARD_AVAILABLE:
            raise RuntimeError("soundcard not available")
        
        self.config = config or AudioConfig()
        self.running = False
        self.loopback = None
        
        self._init_loopback()
    
    def _init_loopback(self):
        """Loopback 장치 초기화"""
        try:
            # 기본 스피커의 Loopback
            speakers = sc.all_speakers()
            if speakers:
                default = sc.default_speaker()
                self.loopback = sc.get_microphone(
                    id=str(default.name),
                    include_loopback=True
                )
                print(f"[AUDIO] Loopback initialized: {default.name}")
        except Exception as e:
            print(f"[AUDIO] Loopback init error: {e}")
    
    def capture_chunk(self) -> Optional[np.ndarray]:
        """오디오 청크 캡처"""
        if not self.loopback:
            return None
        
        try:
            with self.loopback.recorder(samplerate=self.config.sample_rate) as rec:
                data = rec.record(numframes=self.config.chunk_size)
                return data
        except Exception as e:
            print(f"[AUDIO] Capture error: {e}")
            return None
    
    def start_streaming(self, callback: Callable[[bytes], None]):
        """오디오 스트리밍 시작"""
        if not self.loopback:
            return
        
        self.running = True
        
        def stream_loop():
            try:
                with self.loopback.recorder(samplerate=self.config.sample_rate) as rec:
                    while self.running:
                        data = rec.record(numframes=self.config.chunk_size)
                        if data is not None:
                            # Float32 -> Int16 변환
                            int_data = (data * 32767).astype(np.int16)
                            # 바이트로 변환
                            raw_bytes = int_data.tobytes()
                            callback(raw_bytes)
            except Exception as e:
                print(f"[AUDIO] Stream error: {e}")
        
        self.thread = threading.Thread(target=stream_loop, daemon=True)
        self.thread.start()
    
    def stop_streaming(self):
        """스트리밍 중지"""
        self.running = False


class AudioEncoder:
    """오디오 인코더 (Simple PCM -> Compressed)"""
    
    def __init__(self, config: AudioConfig = None):
        self.config = config or AudioConfig()
        self.frame_count = 0
    
    def encode(self, pcm_data: bytes) -> bytes:
        """PCM 데이터 인코딩 (간단한 압축)"""
        import zlib
        
        # 타임스탬프 + 압축 데이터
        timestamp = int(time.time() * 1000)
        compressed = zlib.compress(pcm_data, level=1)
        
        # Header: type(1) + timestamp(8) + length(4)
        header = struct.pack('>BQI', 0x02, timestamp, len(compressed))
        
        self.frame_count += 1
        return header + compressed
    
    @staticmethod
    def decode(data: bytes) -> tuple:
        """디코딩"""
        import zlib
        
        packet_type, timestamp, length = struct.unpack('>BQI', data[:13])
        compressed = data[13:13+length]
        pcm_data = zlib.decompress(compressed)
        
        return timestamp, pcm_data


class AudioMixer:
    """오디오 믹서"""
    
    @staticmethod
    def mix_stereo_to_mono(stereo: np.ndarray) -> np.ndarray:
        """스테레오를 모노로"""
        if stereo.ndim == 2 and stereo.shape[1] == 2:
            return stereo.mean(axis=1).astype(stereo.dtype)
        return stereo
    
    @staticmethod
    def adjust_volume(audio: np.ndarray, gain: float) -> np.ndarray:
        """볼륨 조절"""
        return (audio * gain).clip(-32768, 32767).astype(np.int16)


class UltraAudioStream:
    """ULTRA 오디오 스트리밍 통합"""
    
    def __init__(self, send_callback: Callable[[bytes], None]):
        self.send = send_callback
        self.config = AudioConfig()
        self.capture = None
        self.encoder = None
        self.running = False
        
        if SOUNDCARD_AVAILABLE:
            try:
                self.capture = AudioCapture(self.config)
                self.encoder = AudioEncoder(self.config)
            except Exception as e:
                print(f"[AUDIO] Init error: {e}")
    
    def start(self):
        """오디오 스트리밍 시작"""
        if not self.capture:
            return
        
        def on_audio(raw_data: bytes):
            encoded = self.encoder.encode(raw_data)
            self.send(encoded)
        
        self.capture.start_streaming(on_audio)
        self.running = True
        print("[AUDIO] Streaming started")
    
    def stop(self):
        """스트리밍 중지"""
        if self.capture:
            self.capture.stop_streaming()
        self.running = False
        print("[AUDIO] Streaming stopped")
    
    @property
    def available(self) -> bool:
        return self.capture is not None


if __name__ == "__main__":
    if SOUNDCARD_AVAILABLE:
        print("Available speakers:")
        for spk in sc.all_speakers():
            print(f"  - {spk.name}")
        
        print("\nAvailable microphones (including loopback):")
        for mic in sc.all_microphones(include_loopback=True):
            print(f"  - {mic.name}")
    else:
        print("soundcard not available")
