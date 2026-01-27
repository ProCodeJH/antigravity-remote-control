"""
ULTRA Macro Engine
==================
커스텀 매크로 정의 및 실행
YAML/JSON 기반 워크플로우 자동화

Requirements:
    pip install pyyaml pyautogui
"""

import os
import time
import subprocess
import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

import pyautogui


@dataclass
class MacroStep:
    """매크로 단계"""
    action: str
    target: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    wait_after: int = 0  # ms


@dataclass
class Macro:
    """매크로 정의"""
    name: str
    description: str = ""
    steps: List[MacroStep] = field(default_factory=list)
    hotkey: str = ""  # 단축키 (예: "ctrl+alt+1")
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Macro':
        steps = []
        for step_data in data.get("steps", []):
            steps.append(MacroStep(
                action=step_data.get("action", ""),
                target=step_data.get("target", ""),
                parameters=step_data.get("params", {}),
                wait_after=step_data.get("wait", 0)
            ))
        
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            steps=steps,
            hotkey=data.get("hotkey", "")
        )
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "hotkey": self.hotkey,
            "steps": [
                {
                    "action": s.action,
                    "target": s.target,
                    "params": s.parameters,
                    "wait": s.wait_after
                }
                for s in self.steps
            ]
        }


class MacroExecutor:
    """매크로 실행기"""
    
    ACTIONS = {
        # 앱 관련
        "open": lambda t, p: subprocess.Popen(t, shell=True),
        "close": lambda t, p: subprocess.run(f"taskkill /im {t} /f", shell=True),
        "focus": lambda t, p: MacroExecutor._focus_window(t),
        
        # 마우스
        "click": lambda t, p: pyautogui.click(p.get("x"), p.get("y")),
        "double_click": lambda t, p: pyautogui.doubleClick(p.get("x"), p.get("y")),
        "right_click": lambda t, p: pyautogui.rightClick(p.get("x"), p.get("y")),
        "move": lambda t, p: pyautogui.moveTo(p.get("x"), p.get("y")),
        "drag": lambda t, p: pyautogui.drag(p.get("dx", 0), p.get("dy", 0)),
        "scroll": lambda t, p: pyautogui.scroll(p.get("amount", -500)),
        
        # 키보드
        "type": lambda t, p: pyautogui.typewrite(t, interval=p.get("interval", 0.02)),
        "press": lambda t, p: pyautogui.press(t),
        "hotkey": lambda t, p: pyautogui.hotkey(*t.split("+")),
        
        # OCR 클릭
        "ocr_click": lambda t, p: MacroExecutor._ocr_click(t, p),
        
        # 대기
        "wait": lambda t, p: time.sleep(int(t) / 1000 if t else p.get("ms", 1000) / 1000),
        
        # 조건
        "if_window": lambda t, p: MacroExecutor._check_window(t),
        
        # 반복
        "repeat": lambda t, p: None,  # 특수 처리
        
        # 알림
        "notify": lambda t, p: print(f"[MACRO] {t}"),
    }
    
    def __init__(self, ocr_detector=None):
        self.ocr = ocr_detector
        self.variables: Dict[str, Any] = {}
        self.running = False
    
    def execute(self, macro: Macro) -> dict:
        """매크로 실행"""
        self.running = True
        results = []
        
        try:
            i = 0
            while i < len(macro.steps) and self.running:
                step = macro.steps[i]
                result = self._execute_step(step)
                results.append(result)
                
                if step.wait_after > 0:
                    time.sleep(step.wait_after / 1000)
                
                i += 1
            
            return {"success": True, "results": results}
        except Exception as e:
            return {"success": False, "error": str(e), "results": results}
        finally:
            self.running = False
    
    def _execute_step(self, step: MacroStep) -> dict:
        """단일 스텝 실행"""
        action_fn = self.ACTIONS.get(step.action)
        
        if not action_fn:
            return {"action": step.action, "error": "Unknown action"}
        
        try:
            result = action_fn(step.target, step.parameters)
            return {"action": step.action, "target": step.target, "success": True}
        except Exception as e:
            return {"action": step.action, "target": step.target, "error": str(e)}
    
    @staticmethod
    def _focus_window(title: str):
        """윈도우 포커스"""
        try:
            import win32gui
            import win32con
            
            def callback(hwnd, windows):
                if title.lower() in win32gui.GetWindowText(hwnd).lower():
                    windows.append(hwnd)
                return True
            
            windows = []
            win32gui.EnumWindows(callback, windows)
            
            if windows:
                win32gui.SetForegroundWindow(windows[0])
        except ImportError:
            pass
    
    @staticmethod
    def _ocr_click(text: str, params: dict):
        """OCR로 텍스트 찾아서 클릭"""
        # 외부에서 OCR 결과 주입 필요
        if params.get("x") and params.get("y"):
            pyautogui.click(params["x"], params["y"])
    
    @staticmethod
    def _check_window(title: str) -> bool:
        """윈도우 존재 확인"""
        try:
            import win32gui
            
            def callback(hwnd, result):
                if title.lower() in win32gui.GetWindowText(hwnd).lower():
                    result.append(True)
                return True
            
            result = []
            win32gui.EnumWindows(callback, result)
            return len(result) > 0
        except ImportError:
            return False
    
    def stop(self):
        """실행 중지"""
        self.running = False


class MacroEngine:
    """ULTRA 매크로 엔진"""
    
    def __init__(self, macros_dir: str = None):
        self.macros_dir = Path(macros_dir or "macros")
        self.macros: Dict[str, Macro] = {}
        self.executor = MacroExecutor()
        
        # 디렉토리 생성
        self.macros_dir.mkdir(exist_ok=True)
        
        # 기존 매크로 로드
        self.load_all()
    
    def load_all(self):
        """모든 매크로 파일 로드"""
        for file in self.macros_dir.glob("*.yaml"):
            self.load_macro(file)
        for file in self.macros_dir.glob("*.json"):
            self.load_macro(file)
    
    def load_macro(self, path: Path) -> Optional[Macro]:
        """매크로 파일 로드"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                if path.suffix == '.yaml' and YAML_AVAILABLE:
                    data = yaml.safe_load(f)
                else:
                    data = json.load(f)
            
            macro = Macro.from_dict(data)
            self.macros[macro.name.lower()] = macro
            print(f"[MACRO] Loaded: {macro.name}")
            return macro
        except Exception as e:
            print(f"[MACRO] Load error {path}: {e}")
            return None
    
    def save_macro(self, macro: Macro):
        """매크로 저장"""
        path = self.macros_dir / f"{macro.name.lower().replace(' ', '_')}.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(macro.to_dict(), f, indent=2, ensure_ascii=False)
        self.macros[macro.name.lower()] = macro
    
    def run(self, name: str) -> dict:
        """매크로 실행"""
        macro = self.macros.get(name.lower())
        if not macro:
            return {"success": False, "error": f"Macro '{name}' not found"}
        
        print(f"[MACRO] Running: {macro.name}")
        return self.executor.execute(macro)
    
    def list_macros(self) -> List[dict]:
        """매크로 목록"""
        return [
            {"name": m.name, "description": m.description, "hotkey": m.hotkey}
            for m in self.macros.values()
        ]
    
    def stop(self):
        """실행 중지"""
        self.executor.stop()


# 기본 매크로 템플릿
DEFAULT_MACROS = [
    {
        "name": "Morning Routine",
        "description": "아침 루틴: 브라우저, 메일, 캘린더",
        "steps": [
            {"action": "open", "target": "chrome.exe"},
            {"action": "wait", "target": "2000"},
            {"action": "hotkey", "target": "ctrl+t"},
            {"action": "type", "target": "mail.google.com"},
            {"action": "press", "target": "enter"},
            {"action": "wait", "target": "3000"},
            {"action": "hotkey", "target": "ctrl+t"},
            {"action": "type", "target": "calendar.google.com"},
            {"action": "press", "target": "enter"},
            {"action": "notify", "target": "Morning routine complete!"}
        ]
    },
    {
        "name": "Quick Screenshot",
        "description": "스크린샷 저장",
        "hotkey": "ctrl+alt+s",
        "steps": [
            {"action": "hotkey", "target": "win+shift+s"},
            {"action": "notify", "target": "Screenshot captured"}
        ]
    },
    {
        "name": "Lock Screen",
        "description": "화면 잠금",
        "hotkey": "ctrl+alt+l",
        "steps": [
            {"action": "hotkey", "target": "win+l"},
            {"action": "notify", "target": "Screen locked"}
        ]
    }
]


def create_default_macros(macros_dir: str = "macros"):
    """기본 매크로 생성"""
    path = Path(macros_dir)
    path.mkdir(exist_ok=True)
    
    for macro_data in DEFAULT_MACROS:
        file_path = path / f"{macro_data['name'].lower().replace(' ', '_')}.json"
        if not file_path.exists():
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(macro_data, f, indent=2, ensure_ascii=False)
            print(f"[MACRO] Created: {file_path}")


if __name__ == "__main__":
    # 기본 매크로 생성
    create_default_macros()
    
    # 테스트
    engine = MacroEngine()
    print("\nAvailable macros:")
    for m in engine.list_macros():
        print(f"  - {m['name']}: {m['description']}")
