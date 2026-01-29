"""
Antigravity Remote Control - File Transfer Module
==================================================
PC ↔ 모바일 파일 전송 지원

Features:
    - PC → Mobile: 선택한 파일을 모바일로 전송 (다운로드)
    - Mobile → PC: 모바일에서 업로드한 파일을 PC에 저장
    - 청크 단위 전송 (대용량 파일 지원)
    - 진행률 표시
"""

import os
import uuid
import json
import base64
import asyncio
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict

# ============================================================================
# Configuration
# ============================================================================
@dataclass
class FileTransferConfig:
    chunk_size: int = 64 * 1024  # 64KB per chunk
    download_dir: str = str(Path.home() / "Downloads" / "antigravity")
    max_file_size: int = 100 * 1024 * 1024  # 100MB limit
    allowed_extensions: list = field(default_factory=lambda: [
        '.txt', '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.mp4', '.mp3',
        '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.zip', '.rar'
    ])

TRANSFER_CONFIG = FileTransferConfig()

# ============================================================================
# File Transfer Manager
# ============================================================================
class FileTransferManager:
    """파일 전송 관리자"""
    
    def __init__(self):
        self.active_uploads: Dict[str, dict] = {}  # fileId -> upload info
        self.active_downloads: Dict[str, dict] = {}  # fileId -> download info
        
        # 다운로드 폴더 생성
        os.makedirs(TRANSFER_CONFIG.download_dir, exist_ok=True)
    
    # ========================================================================
    # PC → Mobile (Send File)
    # ========================================================================
    async def send_file(self, ws, file_path: str) -> dict:
        """PC에서 모바일로 파일 전송"""
        path = Path(file_path)
        
        # 유효성 검사
        if not path.exists():
            return {"success": False, "error": "파일을 찾을 수 없습니다"}
        
        if not path.is_file():
            return {"success": False, "error": "폴더는 전송할 수 없습니다"}
        
        file_size = path.stat().st_size
        if file_size > TRANSFER_CONFIG.max_file_size:
            return {"success": False, "error": f"파일이 너무 큽니다 (최대 {TRANSFER_CONFIG.max_file_size // (1024*1024)}MB)"}
        
        file_id = str(uuid.uuid4())
        
        try:
            # 전송 시작 알림
            await ws.send(json.dumps({
                "type": "file_start",
                "fileId": file_id,
                "name": path.name,
                "size": file_size,
                "mimeType": self._get_mime_type(path.suffix)
            }))
            
            # 청크 단위 전송
            with open(path, 'rb') as f:
                offset = 0
                chunk_index = 0
                total_chunks = (file_size + TRANSFER_CONFIG.chunk_size - 1) // TRANSFER_CONFIG.chunk_size
                
                while True:
                    chunk = f.read(TRANSFER_CONFIG.chunk_size)
                    if not chunk:
                        break
                    
                    await ws.send(json.dumps({
                        "type": "file_chunk",
                        "fileId": file_id,
                        "index": chunk_index,
                        "totalChunks": total_chunks,
                        "offset": offset,
                        "data": base64.b64encode(chunk).decode('utf-8')
                    }))
                    
                    offset += len(chunk)
                    chunk_index += 1
                    
                    # 약간의 딜레이로 네트워크 부하 분산
                    await asyncio.sleep(0.01)
            
            # 전송 완료
            await ws.send(json.dumps({
                "type": "file_complete",
                "fileId": file_id,
                "name": path.name,
                "size": file_size
            }))
            
            print(f"[FILE] Sent: {path.name} ({file_size} bytes)")
            return {"success": True, "fileId": file_id, "size": file_size}
            
        except Exception as e:
            await ws.send(json.dumps({
                "type": "file_error",
                "fileId": file_id,
                "error": str(e)
            }))
            return {"success": False, "error": str(e)}
    
    # ========================================================================
    # Mobile → PC (Receive File)
    # ========================================================================
    def start_receive(self, data: dict) -> dict:
        """파일 수신 시작"""
        file_id = data.get("fileId")
        file_name = data.get("name", "unknown")
        file_size = data.get("size", 0)
        
        # 확장자 검사
        ext = Path(file_name).suffix.lower()
        if ext and ext not in TRANSFER_CONFIG.allowed_extensions:
            return {"success": False, "error": f"허용되지 않는 파일 형식: {ext}"}
        
        # 저장 경로 설정 (중복 방지)
        save_path = Path(TRANSFER_CONFIG.download_dir) / file_name
        if save_path.exists():
            base = save_path.stem
            ext = save_path.suffix
            counter = 1
            while save_path.exists():
                save_path = Path(TRANSFER_CONFIG.download_dir) / f"{base}_{counter}{ext}"
                counter += 1
        
        self.active_uploads[file_id] = {
            "name": file_name,
            "size": file_size,
            "path": str(save_path),
            "received": 0,
            "chunks": {}
        }
        
        print(f"[FILE] Receiving: {file_name} ({file_size} bytes)")
        return {"success": True, "fileId": file_id}
    
    def receive_chunk(self, data: dict) -> dict:
        """파일 청크 수신"""
        file_id = data.get("fileId")
        chunk_index = data.get("index", 0)
        chunk_data = data.get("data", "")
        
        if file_id not in self.active_uploads:
            return {"success": False, "error": "알 수 없는 파일 ID"}
        
        upload = self.active_uploads[file_id]
        
        try:
            decoded = base64.b64decode(chunk_data)
            upload["chunks"][chunk_index] = decoded
            upload["received"] += len(decoded)
            
            # 진행률 계산
            progress = (upload["received"] / upload["size"] * 100) if upload["size"] > 0 else 0
            
            return {"success": True, "progress": progress}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def complete_receive(self, data: dict) -> dict:
        """파일 수신 완료"""
        file_id = data.get("fileId")
        
        if file_id not in self.active_uploads:
            return {"success": False, "error": "알 수 없는 파일 ID"}
        
        upload = self.active_uploads[file_id]
        
        try:
            # 청크 조립 및 파일 저장
            with open(upload["path"], 'wb') as f:
                for i in sorted(upload["chunks"].keys()):
                    f.write(upload["chunks"][i])
            
            print(f"[FILE] Saved: {upload['path']}")
            
            # 정리
            del self.active_uploads[file_id]
            
            return {
                "success": True,
                "path": upload["path"],
                "size": upload["received"]
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ========================================================================
    # Utilities
    # ========================================================================
    def _get_mime_type(self, ext: str) -> str:
        """확장자로 MIME 타입 반환"""
        mime_map = {
            '.txt': 'text/plain',
            '.pdf': 'application/pdf',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.mp4': 'video/mp4',
            '.mp3': 'audio/mpeg',
            '.zip': 'application/zip',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        }
        return mime_map.get(ext.lower(), 'application/octet-stream')
    
    def list_downloads(self) -> list:
        """다운로드 폴더 파일 목록"""
        download_path = Path(TRANSFER_CONFIG.download_dir)
        files = []
        
        for f in download_path.iterdir():
            if f.is_file():
                files.append({
                    "name": f.name,
                    "size": f.stat().st_size,
                    "path": str(f)
                })
        
        return files
