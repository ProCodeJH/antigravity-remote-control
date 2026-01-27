"""
Antigravity Remote Controller - Window Controller
VS Code / Antigravity 창 제어 모듈
"""

import win32gui
import win32con
import win32process
import pyautogui
import time
from typing import List, Dict, Optional, Tuple

# PyAutoGUI 설정
pyautogui.PAUSE = 0.05  # 명령 간 딜레이
pyautogui.FAILSAFE = True  # 화면 모서리로 마우스 이동 시 중단


class WindowInfo:
    """창 정보를 담는 클래스"""
    def __init__(self, hwnd: int, title: str, rect: Tuple[int, int, int, int]):
        self.hwnd = hwnd
        self.title = title
        self.rect = rect  # (left, top, right, bottom)
        
    @property
    def width(self) -> int:
        return self.rect[2] - self.rect[0]
    
    @property
    def height(self) -> int:
        return self.rect[3] - self.rect[1]
    
    def to_dict(self) -> Dict:
        return {
            "hwnd": self.hwnd,
            "title": self.title,
            "rect": self.rect,
            "width": self.width,
            "height": self.height
        }


class WindowController:
    """VS Code / Antigravity 창을 제어하는 클래스"""
    
    # 찾을 창 제목 키워드
    TARGET_KEYWORDS = [
        "Antigravity",
        "Visual Studio Code", 
        "VS Code",
        "Code -",
        "Cursor",
        "Windsurf"
    ]
    
    def __init__(self):
        self.current_window: Optional[WindowInfo] = None
        self.windows: List[WindowInfo] = []
        
    def find_all_target_windows(self) -> List[WindowInfo]:
        """타겟 창들을 모두 찾습니다"""
        self.windows = []
        
        def enum_callback(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title and any(kw.lower() in title.lower() for kw in self.TARGET_KEYWORDS):
                    try:
                        rect = win32gui.GetWindowRect(hwnd)
                        self.windows.append(WindowInfo(hwnd, title, rect))
                    except Exception:
                        pass
            return True
        
        win32gui.EnumWindows(enum_callback, None)
        return self.windows
    
    def get_windows_list(self) -> List[Dict]:
        """현재 열린 타겟 창 목록을 반환"""
        self.find_all_target_windows()
        return [w.to_dict() for w in self.windows]
    
    def activate_window(self, hwnd: int) -> bool:
        """특정 창을 활성화 - Windows 보안 제한 우회"""
        try:
            import ctypes
            from ctypes import wintypes
            
            # Get current foreground window
            current_hwnd = win32gui.GetForegroundWindow()
            current_thread_id = ctypes.windll.user32.GetWindowThreadProcessId(current_hwnd, None)
            target_thread_id = ctypes.windll.user32.GetWindowThreadProcessId(hwnd, None)
            
            # 최소화 상태면 복원
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.05)
            
            # Method 1: Alt key trick (releases SetForegroundWindow lock)
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)  # Alt down
            ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)  # Alt up
            time.sleep(0.02)
            
            # Method 2: Attach thread input if different threads
            if current_thread_id != target_thread_id:
                ctypes.windll.user32.AttachThreadInput(current_thread_id, target_thread_id, True)
            
            # Try to set foreground
            result = win32gui.SetForegroundWindow(hwnd)
            
            # Also try BringWindowToTop
            win32gui.BringWindowToTop(hwnd)
            
            # Detach thread input
            if current_thread_id != target_thread_id:
                ctypes.windll.user32.AttachThreadInput(current_thread_id, target_thread_id, False)
            
            time.sleep(0.1)
            
            # Verify activation
            if win32gui.GetForegroundWindow() != hwnd:
                # Fallback: ShowWindow with force
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
                win32gui.SetForegroundWindow(hwnd)
            
            # 현재 창 업데이트
            title = win32gui.GetWindowText(hwnd)
            rect = win32gui.GetWindowRect(hwnd)
            self.current_window = WindowInfo(hwnd, title, rect)
            
            print(f"[WindowController] Activated: {title[:50]}")
            return True
        except Exception as e:
            print(f"[WindowController] Failed to activate window: {e}")
            return False
    
    def activate_first_window(self) -> bool:
        """첫 번째 타겟 창을 활성화"""
        self.find_all_target_windows()
        if self.windows:
            return self.activate_window(self.windows[0].hwnd)
        return False
    
    def type_text(self, text: str, interval: float = 0.02) -> bool:
        """텍스트를 현재 활성 창에 입력"""
        try:
            pyautogui.write(text, interval=interval)
            return True
        except Exception as e:
            print(f"Failed to type text: {e}")
            return False
    
    def type_text_unicode(self, text: str) -> bool:
        """유니코드 텍스트를 입력 (한글 등)"""
        try:
            # 클립보드를 통한 붙여넣기 방식
            import pyperclip
            pyperclip.copy(text)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.1)
            return True
        except Exception as e:
            print(f"Failed to type unicode text: {e}")
            return False
    
    def send_key(self, key: str) -> bool:
        """단일 키 전송"""
        try:
            pyautogui.press(key)
            return True
        except Exception as e:
            print(f"Failed to send key: {e}")
            return False
    
    def send_hotkey(self, *keys: str) -> bool:
        """핫키 조합 전송"""
        try:
            pyautogui.hotkey(*keys)
            return True
        except Exception as e:
            print(f"Failed to send hotkey: {e}")
            return False
    
    def click_at(self, x: int, y: int) -> bool:
        """특정 좌표 클릭"""
        try:
            pyautogui.click(x, y)
            return True
        except Exception as e:
            print(f"Failed to click: {e}")
            return False
    
    def click_relative(self, x_ratio: float, y_ratio: float) -> bool:
        """창 내부 상대 좌표 클릭 (0.0 ~ 1.0)"""
        if not self.current_window:
            return False
        
        rect = self.current_window.rect
        x = rect[0] + int(self.current_window.width * x_ratio)
        y = rect[1] + int(self.current_window.height * y_ratio)
        
        return self.click_at(x, y)
    
    def scroll(self, clicks: int) -> bool:
        """스크롤 (양수: 위로, 음수: 아래로)"""
        try:
            pyautogui.scroll(clicks)
            return True
        except Exception as e:
            print(f"Failed to scroll: {e}")
            return False
    
    def click_in_capture_region(self, x_ratio: float, y_ratio: float, chat_only: bool = True) -> bool:
        """캡처 영역 내 상대 좌표로 클릭 (터치 -> 마우스)
        
        Args:
            x_ratio: 캡처 영역 내 X 비율 (0.0 ~ 1.0)
            y_ratio: 캡처 영역 내 Y 비율 (0.0 ~ 1.0)
            chat_only: True면 오른쪽 40% (채팅 패널) 영역 기준
        """
        if not self.current_window:
            print("[WindowController] No current window for click")
            return False
        
        try:
            rect = self.current_window.rect
            full_width = rect[2] - rect[0]
            full_height = rect[3] - rect[1]
            
            if chat_only:
                # 채팅 패널 영역 (오른쪽 40%)
                chat_width_ratio = 0.40
                region_left = rect[0] + int(full_width * (1 - chat_width_ratio))
                region_top = rect[1] + 30  # 타이틀바 제외
                region_width = int(full_width * chat_width_ratio)
                region_height = full_height - 30
            else:
                # 전체 창
                region_left = rect[0]
                region_top = rect[1]
                region_width = full_width
                region_height = full_height
            
            # 실제 화면 좌표 계산
            x = region_left + int(region_width * x_ratio)
            y = region_top + int(region_height * y_ratio)
            
            print(f"[WindowController] Click at screen ({x}, {y}) from ratio ({x_ratio:.2f}, {y_ratio:.2f})")
            
            pyautogui.click(x, y)
            return True
        except Exception as e:
            print(f"[WindowController] Failed to click in capture region: {e}")
            return False
    
    def move_mouse_in_capture_region(self, x_ratio: float, y_ratio: float, chat_only: bool = True) -> bool:
        """캡처 영역 내 상대 좌표로 마우스 이동"""
        if not self.current_window:
            return False
        
        try:
            rect = self.current_window.rect
            full_width = rect[2] - rect[0]
            full_height = rect[3] - rect[1]
            
            if chat_only:
                chat_width_ratio = 0.40
                region_left = rect[0] + int(full_width * (1 - chat_width_ratio))
                region_top = rect[1] + 30
                region_width = int(full_width * chat_width_ratio)
                region_height = full_height - 30
            else:
                region_left = rect[0]
                region_top = rect[1]
                region_width = full_width
                region_height = full_height
            
            x = region_left + int(region_width * x_ratio)
            y = region_top + int(region_height * y_ratio)
            
            pyautogui.moveTo(x, y)
            return True
        except Exception as e:
            print(f"[WindowController] Failed to move mouse: {e}")
            return False
    
    def send_command_to_antigravity(self, command: str) -> bool:
        """Antigravity에 명령 전송 (텍스트 입력 후 Enter)"""
        try:
            # 한글이 포함되어 있으면 클립보드 방식 사용
            if any(ord(c) > 127 for c in command):
                self.type_text_unicode(command)
            else:
                self.type_text(command)
            
            time.sleep(0.05)
            self.send_key('enter')
            return True
        except Exception as e:
            print(f"Failed to send command: {e}")
            return False
    
    def get_chat_content(self) -> Optional[str]:
        """Antigravity 채팅 내용을 가져옵니다"""
        try:
            import pyperclip
            
            if not self.current_window:
                return None
            
            # 현재 창 활성화
            self.activate_window(self.current_window.hwnd)
            time.sleep(0.3)
            
            # 클립보드 백업
            old_clipboard = ""
            try:
                old_clipboard = pyperclip.paste()
            except:
                pass
            
            # 채팅 패널 영역 클릭 (보통 오른쪽 사이드바)
            # 창의 오른쪽 70% 지점, 중앙 높이 클릭
            rect = self.current_window.rect
            chat_x = rect[0] + int(self.current_window.width * 0.75)
            chat_y = rect[1] + int(self.current_window.height * 0.5)
            
            pyautogui.click(chat_x, chat_y)
            time.sleep(0.15)
            
            # 전체 선택 (Ctrl+A)
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.15)
            
            # 복사 (Ctrl+C)  
            pyautogui.hotkey('ctrl', 'c')
            time.sleep(0.2)
            
            # 선택 해제
            pyautogui.press('escape')
            time.sleep(0.1)
            
            # 클립보드 내용 가져오기
            content = pyperclip.paste()
            
            # 내용이 있으면 반환
            if content and content != old_clipboard and len(content) > 10:
                return content
            
            # 실패시 전체 화면에서 다시 시도
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.1)
            pyautogui.hotkey('ctrl', 'c')
            time.sleep(0.15)
            pyautogui.press('escape')
            
            return pyperclip.paste()
            
        except Exception as e:
            print(f"Failed to get chat content: {e}")
            return None
    
    def focus_chat_input(self) -> bool:
        """채팅 입력창에 포커스"""
        try:
            if not self.current_window:
                return False
            
            self.activate_window(self.current_window.hwnd)
            time.sleep(0.2)
            
            # 보통 하단에 입력창이 있음 - 클릭
            rect = self.current_window.rect
            input_x = rect[0] + int(self.current_window.width * 0.75)
            input_y = rect[1] + int(self.current_window.height * 0.9)
            
            pyautogui.click(input_x, input_y)
            time.sleep(0.1)
            
            return True
        except Exception as e:
            print(f"Failed to focus chat input: {e}")
            return False
    
    def open_new_antigravity(self) -> bool:
        """새 VS Code 창에서 Antigravity 실행"""
        try:
            import subprocess
            
            # VS Code를 새 창으로 실행
            # code 명령어가 PATH에 있다고 가정
            subprocess.Popen(
                ['code', '-n'],  # -n: 새 창으로 열기
                shell=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            print("[WindowController] Launched new VS Code window")
            time.sleep(2)  # 창이 열릴 때까지 대기
            
            # 창 목록 업데이트
            self.find_all_target_windows()
            
            return True
        except Exception as e:
            print(f"[WindowController] Failed to open new Antigravity: {e}")
            return False
    
    def close_window(self, hwnd: int = None) -> bool:
        """창 닫기 (Alt+F4)"""
        try:
            target_hwnd = hwnd or (self.current_window.hwnd if self.current_window else None)
            
            if not target_hwnd:
                print("[WindowController] No window to close")
                return False
            
            # 창 활성화
            self.activate_window(target_hwnd)
            time.sleep(0.2)
            
            # Alt+F4로 닫기
            pyautogui.hotkey('alt', 'F4')
            time.sleep(0.5)
            
            # 저장 안함 확인 (만약 나오면)
            # 일부 앱에서 저장 대화상자가 나올 수 있음
            
            print(f"[WindowController] Closed window: {target_hwnd}")
            
            # 창 목록 업데이트
            self.find_all_target_windows()
            
            # 현재 창이 닫힌 경우 초기화
            if self.current_window and self.current_window.hwnd == target_hwnd:
                self.current_window = None
            
            return True
        except Exception as e:
            print(f"[WindowController] Failed to close window: {e}")
            return False
    
    def get_window_count(self) -> int:
        """현재 타겟 창 개수 반환"""
        self.find_all_target_windows()
        return len(self.windows)


# 싱글톤 인스턴스
controller = WindowController()
