"""
ULTRA Voice Control Engine
==========================
음성 명령으로 PC 제어
"Open Chrome", "Click Accept", "Scroll down" 등

Requirements:
    pip install SpeechRecognition
    Optional: pip install pvporcupine (wake word)
"""

import json
import re
from dataclasses import dataclass
from typing import Optional, Callable, Dict, List
from enum import Enum


class VoiceCommand(Enum):
    """음성 명령 타입"""
    OPEN_APP = "open"
    CLOSE_APP = "close"
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    PRESS = "press"
    MACRO = "macro"
    SCREENSHOT = "screenshot"
    SWITCH_MONITOR = "monitor"
    UNKNOWN = "unknown"


@dataclass
class ParsedCommand:
    """파싱된 음성 명령"""
    command_type: VoiceCommand
    target: str
    parameters: Dict
    raw_text: str
    confidence: float


class VoiceCommandParser:
    """음성 명령 파서"""
    
    # 명령 패턴
    PATTERNS = {
        # 앱 실행
        VoiceCommand.OPEN_APP: [
            r"(?:open|start|launch|run)\s+(.+)",
            r"(.+)\s+(?:열어|실행|시작)",
        ],
        # 앱 종료
        VoiceCommand.CLOSE_APP: [
            r"(?:close|exit|quit|kill)\s+(.+)",
            r"(.+)\s+(?:닫아|종료|끄기)",
        ],
        # 클릭
        VoiceCommand.CLICK: [
            r"(?:click|press|tap)\s+(?:on\s+)?(.+)",
            r"(.+)\s+(?:클릭|누르기|눌러)",
        ],
        # 타이핑
        VoiceCommand.TYPE: [
            r"(?:type|write|input)\s+(.+)",
            r"(.+)\s+(?:입력|타이핑|쓰기)",
        ],
        # 스크롤
        VoiceCommand.SCROLL: [
            r"scroll\s+(up|down|left|right)(?:\s+(\d+))?",
            r"(?:위|아래|왼쪽|오른쪽)(?:으)?로\s*스크롤",
        ],
        # 키 입력
        VoiceCommand.PRESS: [
            r"(?:press|hit)\s+(.+)",
            r"(.+)\s+키\s*(?:누르기|입력)",
        ],
        # 매크로
        VoiceCommand.MACRO: [
            r"(?:run|execute)\s+macro\s+(.+)",
            r"(.+)\s+매크로\s*실행",
        ],
        # 스크린샷
        VoiceCommand.SCREENSHOT: [
            r"(?:take\s+)?(?:a\s+)?screenshot",
            r"스크린샷|화면\s*캡처",
        ],
        # 모니터 전환
        VoiceCommand.SWITCH_MONITOR: [
            r"(?:switch\s+(?:to\s+)?)?monitor\s+(\d+)",
            r"모니터\s*(\d+)(?:번)?(?:으로)?",
        ],
    }
    
    # 앱 이름 매핑
    APP_ALIASES = {
        "chrome": "chrome.exe",
        "크롬": "chrome.exe",
        "browser": "chrome.exe",
        "firefox": "firefox.exe",
        "파이어폭스": "firefox.exe",
        "edge": "msedge.exe",
        "엣지": "msedge.exe",
        "notepad": "notepad.exe",
        "메모장": "notepad.exe",
        "explorer": "explorer.exe",
        "탐색기": "explorer.exe",
        "terminal": "wt.exe",
        "터미널": "wt.exe",
        "cmd": "cmd.exe",
        "vscode": "code.exe",
        "코드": "code.exe",
        "discord": "discord.exe",
        "디스코드": "discord.exe",
        "spotify": "spotify.exe",
        "스포티파이": "spotify.exe",
    }
    
    # 스크롤 방향 매핑
    SCROLL_DIRECTIONS = {
        "up": (0, 500),
        "down": (0, -500),
        "left": (-500, 0),
        "right": (500, 0),
        "위": (0, 500),
        "아래": (0, -500),
        "왼쪽": (-500, 0),
        "오른쪽": (500, 0),
    }
    
    # 키 이름 매핑
    KEY_ALIASES = {
        "enter": "return",
        "엔터": "return",
        "escape": "escape",
        "esc": "escape",
        "이스케이프": "escape",
        "space": "space",
        "스페이스": "space",
        "tab": "tab",
        "탭": "tab",
        "backspace": "backspace",
        "백스페이스": "backspace",
        "delete": "delete",
        "삭제": "delete",
        "home": "home",
        "홈": "home",
        "end": "end",
        "엔드": "end",
        "page up": "pageup",
        "page down": "pagedown",
        "control": "ctrl",
        "컨트롤": "ctrl",
        "alt": "alt",
        "알트": "alt",
        "shift": "shift",
        "쉬프트": "shift",
    }
    
    def parse(self, text: str, confidence: float = 1.0) -> ParsedCommand:
        """음성 텍스트를 명령으로 파싱"""
        text = text.lower().strip()
        
        for cmd_type, patterns in self.PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return self._build_command(cmd_type, match, text, confidence)
        
        return ParsedCommand(
            command_type=VoiceCommand.UNKNOWN,
            target=text,
            parameters={},
            raw_text=text,
            confidence=confidence
        )
    
    def _build_command(self, cmd_type: VoiceCommand, match, raw_text: str, confidence: float) -> ParsedCommand:
        """명령 객체 생성"""
        groups = match.groups()
        target = groups[0] if groups else ""
        params = {}
        
        if cmd_type == VoiceCommand.OPEN_APP:
            target = self.APP_ALIASES.get(target.lower(), target)
        
        elif cmd_type == VoiceCommand.SCROLL:
            direction = groups[0] if groups else "down"
            amount = int(groups[1]) if len(groups) > 1 and groups[1] else 500
            dx, dy = self.SCROLL_DIRECTIONS.get(direction, (0, -500))
            params = {"dx": dx * (amount / 500), "dy": dy * (amount / 500)}
        
        elif cmd_type == VoiceCommand.PRESS:
            target = self.KEY_ALIASES.get(target.lower(), target)
        
        elif cmd_type == VoiceCommand.SWITCH_MONITOR:
            params = {"monitor": int(groups[0]) if groups else 1}
        
        return ParsedCommand(
            command_type=cmd_type,
            target=target,
            parameters=params,
            raw_text=raw_text,
            confidence=confidence
        )


class VoiceCommandExecutor:
    """음성 명령 실행기"""
    
    def __init__(self, input_injector, ocr_detector=None, macro_engine=None):
        self.injector = input_injector
        self.ocr = ocr_detector
        self.macros = macro_engine
        self.parser = VoiceCommandParser()
    
    def execute(self, text: str, confidence: float = 1.0) -> dict:
        """음성 텍스트 실행"""
        cmd = self.parser.parse(text, confidence)
        
        if cmd.confidence < 0.7:
            return {"success": False, "error": "Low confidence", "command": cmd.raw_text}
        
        try:
            result = self._execute_command(cmd)
            return {"success": True, "command": cmd.command_type.value, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e), "command": cmd.raw_text}
    
    def _execute_command(self, cmd: ParsedCommand) -> str:
        """명령 실행"""
        import subprocess
        import pyautogui
        
        if cmd.command_type == VoiceCommand.OPEN_APP:
            subprocess.Popen(cmd.target, shell=True)
            return f"Opened {cmd.target}"
        
        elif cmd.command_type == VoiceCommand.CLOSE_APP:
            subprocess.run(f'taskkill /im {cmd.target} /f', shell=True)
            return f"Closed {cmd.target}"
        
        elif cmd.command_type == VoiceCommand.CLICK:
            # OCR로 버튼 찾아서 클릭
            if self.ocr:
                button = self.ocr.find_button_by_text(cmd.target)
                if button:
                    pyautogui.click(button.x, button.y)
                    return f"Clicked {cmd.target} at ({button.x}, {button.y})"
            return f"Button '{cmd.target}' not found"
        
        elif cmd.command_type == VoiceCommand.TYPE:
            pyautogui.typewrite(cmd.target, interval=0.02)
            return f"Typed: {cmd.target}"
        
        elif cmd.command_type == VoiceCommand.SCROLL:
            dx = cmd.parameters.get("dx", 0)
            dy = cmd.parameters.get("dy", -500)
            pyautogui.scroll(int(dy))
            return f"Scrolled ({dx}, {dy})"
        
        elif cmd.command_type == VoiceCommand.PRESS:
            pyautogui.press(cmd.target)
            return f"Pressed {cmd.target}"
        
        elif cmd.command_type == VoiceCommand.MACRO:
            if self.macros:
                self.macros.run(cmd.target)
                return f"Executed macro: {cmd.target}"
            return "Macro engine not available"
        
        elif cmd.command_type == VoiceCommand.SCREENSHOT:
            screenshot = pyautogui.screenshot()
            path = f"screenshot_{int(time.time())}.png"
            screenshot.save(path)
            return f"Screenshot saved: {path}"
        
        elif cmd.command_type == VoiceCommand.SWITCH_MONITOR:
            monitor = cmd.parameters.get("monitor", 1)
            return f"Switched to monitor {monitor}"
        
        return "Unknown command"


class VoiceRecognizer:
    """음성 인식기 (선택적)"""
    
    def __init__(self, callback: Callable[[str, float], None]):
        self.callback = callback
        self.running = False
        self.recognizer = None
        
        try:
            import speech_recognition as sr
            self.recognizer = sr.Recognizer()
            self.microphone = sr.Microphone()
            print("[VOICE] Speech recognition available")
        except ImportError:
            print("[VOICE] SpeechRecognition not available")
    
    def start_listening(self):
        """음성 인식 시작"""
        if not self.recognizer:
            return
        
        import speech_recognition as sr
        
        self.running = True
        
        def listen_loop():
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source)
                
                while self.running:
                    try:
                        audio = self.recognizer.listen(source, timeout=5)
                        text = self.recognizer.recognize_google(audio)
                        self.callback(text, 0.9)
                    except sr.WaitTimeoutError:
                        pass
                    except sr.UnknownValueError:
                        pass
                    except Exception as e:
                        print(f"[VOICE] Error: {e}")
        
        import threading
        self.thread = threading.Thread(target=listen_loop, daemon=True)
        self.thread.start()
    
    def stop_listening(self):
        """음성 인식 중지"""
        self.running = False


# Time import for screenshot naming
import time


if __name__ == "__main__":
    # 테스트
    parser = VoiceCommandParser()
    
    test_commands = [
        "open chrome",
        "click accept",
        "scroll down",
        "type hello world",
        "press enter",
        "크롬 열어",
        "확인 클릭",
        "아래로 스크롤",
    ]
    
    for cmd in test_commands:
        result = parser.parse(cmd)
        print(f"{cmd} -> {result.command_type.value}: {result.target}")
