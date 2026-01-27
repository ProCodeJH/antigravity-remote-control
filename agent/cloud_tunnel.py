"""
ULTRA Cloud Tunnel Engine
=========================
NAT/방화벽 우회 클라우드 터널링
전 세계 어디서든 PC 접속

Options:
- ngrok (추천)
- Cloudflare Tunnel
- localtunnel
"""

import asyncio
import subprocess
import json
import time
import os
from dataclasses import dataclass
from typing import Optional, Callable
from pathlib import Path
import threading


@dataclass
class TunnelConfig:
    """터널 설정"""
    port: int = 8080
    region: str = "auto"
    auth_token: str = ""
    subdomain: str = ""


class NgrokTunnel:
    """ngrok 터널"""
    
    def __init__(self, config: TunnelConfig = None):
        self.config = config or TunnelConfig()
        self.process = None
        self.public_url = None
        self.running = False
    
    def start(self) -> Optional[str]:
        """터널 시작"""
        try:
            # ngrok 설치 확인
            result = subprocess.run(
                ["ngrok", "version"],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                print("[TUNNEL] ngrok not found. Install from https://ngrok.com")
                return None
            
            # Auth token 설정
            if self.config.auth_token:
                subprocess.run(
                    ["ngrok", "config", "add-authtoken", self.config.auth_token],
                    capture_output=True
                )
            
            # 터널 시작
            cmd = ["ngrok", "http", str(self.config.port)]
            
            if self.config.region != "auto":
                cmd.extend(["--region", self.config.region])
            
            if self.config.subdomain:
                cmd.extend(["--subdomain", self.config.subdomain])
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            self.running = True
            
            # URL 가져오기 (ngrok API)
            time.sleep(2)
            self.public_url = self._get_public_url()
            
            if self.public_url:
                print(f"[TUNNEL] ngrok started: {self.public_url}")
            
            return self.public_url
        
        except FileNotFoundError:
            print("[TUNNEL] ngrok not installed")
            return None
        except Exception as e:
            print(f"[TUNNEL] Error: {e}")
            return None
    
    def _get_public_url(self) -> Optional[str]:
        """ngrok API에서 public URL 가져오기"""
        import urllib.request
        
        try:
            with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels") as response:
                data = json.loads(response.read())
                tunnels = data.get("tunnels", [])
                
                for tunnel in tunnels:
                    if tunnel.get("proto") == "https":
                        return tunnel.get("public_url")
                
                if tunnels:
                    return tunnels[0].get("public_url")
        except:
            pass
        
        return None
    
    def stop(self):
        """터널 중지"""
        if self.process:
            self.process.terminate()
            self.process = None
        self.running = False
        self.public_url = None
        print("[TUNNEL] ngrok stopped")


class CloudflareTunnel:
    """Cloudflare Tunnel (cloudflared)"""
    
    def __init__(self, config: TunnelConfig = None):
        self.config = config or TunnelConfig()
        self.process = None
        self.public_url = None
        self.running = False
    
    def start(self) -> Optional[str]:
        """터널 시작"""
        try:
            # Quick tunnel (인증 필요 없음)
            cmd = [
                "cloudflared", "tunnel",
                "--url", f"http://localhost:{self.config.port}"
            ]
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            
            self.running = True
            
            # URL 파싱
            def read_output():
                for line in self.process.stdout:
                    if "trycloudflare.com" in line:
                        import re
                        match = re.search(r'https://[^\s]+trycloudflare\.com', line)
                        if match:
                            self.public_url = match.group(0)
                            print(f"[TUNNEL] Cloudflare: {self.public_url}")
            
            threading.Thread(target=read_output, daemon=True).start()
            
            time.sleep(5)
            return self.public_url
        
        except FileNotFoundError:
            print("[TUNNEL] cloudflared not installed")
            return None
        except Exception as e:
            print(f"[TUNNEL] Error: {e}")
            return None
    
    def stop(self):
        """터널 중지"""
        if self.process:
            self.process.terminate()
            self.process = None
        self.running = False
        self.public_url = None
        print("[TUNNEL] Cloudflare stopped")


class UltraTunnel:
    """ULTRA 통합 터널"""
    
    PROVIDERS = {
        "ngrok": NgrokTunnel,
        "cloudflare": CloudflareTunnel,
    }
    
    def __init__(self, provider: str = "ngrok", config: TunnelConfig = None):
        self.config = config or TunnelConfig()
        self.provider_name = provider
        
        tunnel_class = self.PROVIDERS.get(provider)
        if tunnel_class:
            self.tunnel = tunnel_class(self.config)
        else:
            print(f"[TUNNEL] Unknown provider: {provider}")
            self.tunnel = None
    
    def start(self) -> Optional[str]:
        """터널 시작"""
        if self.tunnel:
            url = self.tunnel.start()
            if url:
                # WebSocket URL 변환
                ws_url = url.replace("https://", "wss://").replace("http://", "ws://")
                ws_url = f"{ws_url}/ws/relay"
                print(f"[TUNNEL] WebSocket URL: {ws_url}")
                return {"http": url, "ws": ws_url}
        return None
    
    def stop(self):
        """터널 중지"""
        if self.tunnel:
            self.tunnel.stop()
    
    @property
    def public_url(self) -> Optional[str]:
        return self.tunnel.public_url if self.tunnel else None
    
    @property
    def running(self) -> bool:
        return self.tunnel.running if self.tunnel else False


class TunnelManager:
    """터널 관리자"""
    
    CONFIG_FILE = Path.home() / ".antigravity" / "tunnel.json"
    
    def __init__(self):
        self.tunnel: Optional[UltraTunnel] = None
        self.load_config()
    
    def load_config(self) -> dict:
        """설정 로드"""
        if self.CONFIG_FILE.exists():
            with open(self.CONFIG_FILE, 'r') as f:
                return json.load(f)
        return {}
    
    def save_config(self, config: dict):
        """설정 저장"""
        self.CONFIG_FILE.parent.mkdir(exist_ok=True)
        with open(self.CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
    
    def start(self, provider: str = None, port: int = 8080) -> dict:
        """터널 시작"""
        config = TunnelConfig(port=port)
        
        saved = self.load_config()
        if provider:
            config.auth_token = saved.get(f"{provider}_token", "")
        
        # 자동 선택
        if not provider:
            for p in ["ngrok", "cloudflare"]:
                try:
                    self.tunnel = UltraTunnel(p, config)
                    result = self.tunnel.start()
                    if result:
                        return {"success": True, "provider": p, **result}
                except:
                    pass
            return {"success": False, "error": "No tunnel provider available"}
        
        self.tunnel = UltraTunnel(provider, config)
        result = self.tunnel.start()
        
        if result:
            return {"success": True, "provider": provider, **result}
        return {"success": False, "error": f"{provider} tunnel failed"}
    
    def stop(self):
        """터널 중지"""
        if self.tunnel:
            self.tunnel.stop()
    
    def get_status(self) -> dict:
        """상태 확인"""
        if self.tunnel and self.tunnel.running:
            return {
                "running": True,
                "provider": self.tunnel.provider_name,
                "url": self.tunnel.public_url
            }
        return {"running": False}


if __name__ == "__main__":
    manager = TunnelManager()
    
    print("Starting tunnel...")
    result = manager.start(port=8080)
    print(f"Result: {result}")
    
    if result.get("success"):
        print("\nPress Enter to stop...")
        input()
        manager.stop()
