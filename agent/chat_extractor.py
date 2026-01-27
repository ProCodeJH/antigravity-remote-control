"""
Antigravity Chat Extractor v3
Precise extraction of VS Code Antigravity conversation history
"""

import time
import re
from typing import Optional, List, Dict
from dataclasses import dataclass
import pyperclip
import pyautogui
import win32gui
import win32con


@dataclass
class ChatMessage:
    """Represents a single chat message"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: Optional[str] = None


class ChatExtractor:
    """Extract chat content from Antigravity VS Code panel"""
    
    def __init__(self):
        self.last_content: str = ""
        self.last_extraction_time: float = 0
        self.extraction_cooldown: float = 1.0  # seconds
        
    def find_antigravity_window(self) -> Optional[int]:
        """Find the VS Code window with Antigravity"""
        result = {"hwnd": None, "best_match": ""}
        
        def enum_callback(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                # Look for Antigravity or Visual Studio Code
                if "Antigravity" in title or ("Visual Studio Code" in title and "antigravity" in title.lower()):
                    result["hwnd"] = hwnd
                    result["best_match"] = title
                    return False  # Stop enumeration
            return True
        
        try:
            win32gui.EnumWindows(enum_callback, None)
        except:
            pass
            
        return result["hwnd"]
    
    def activate_window(self, hwnd: int) -> bool:
        """Bring window to foreground - bypass Windows security"""
        try:
            import ctypes
            
            # Get current foreground window
            current_hwnd = win32gui.GetForegroundWindow()
            current_thread_id = ctypes.windll.user32.GetWindowThreadProcessId(current_hwnd, None)
            target_thread_id = ctypes.windll.user32.GetWindowThreadProcessId(hwnd, None)
            
            # Restore if minimized
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.05)
            
            # Alt key trick (releases SetForegroundWindow lock)
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)  # Alt down
            ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)  # Alt up
            time.sleep(0.02)
            
            # Attach thread input if different threads
            if current_thread_id != target_thread_id:
                ctypes.windll.user32.AttachThreadInput(current_thread_id, target_thread_id, True)
            
            # Bring to foreground
            win32gui.SetForegroundWindow(hwnd)
            win32gui.BringWindowToTop(hwnd)
            
            # Detach thread input
            if current_thread_id != target_thread_id:
                ctypes.windll.user32.AttachThreadInput(current_thread_id, target_thread_id, False)
            
            time.sleep(0.1)
            print(f"[ChatExtractor] Window activated")
            return True
        except Exception as e:
            print(f"[ChatExtractor] Failed to activate window: {e}")
            return False
    
    def get_window_rect(self, hwnd: int) -> Optional[tuple]:
        """Get window rectangle"""
        try:
            return win32gui.GetWindowRect(hwnd)
        except:
            return None
    
    def extract_chat_content(self, hwnd: Optional[int] = None) -> Optional[str]:
        """
        Extract full chat content from Antigravity panel.
        Scrolls to top first to ensure we get all content.
        """
        # Reduce cooldown for testing
        now = time.time()
        if now - self.last_extraction_time < 0.5:
            return self.last_content
        
        if hwnd is None:
            hwnd = self.find_antigravity_window()
            
        if hwnd is None:
            print("[ChatExtractor] No Antigravity window found")
            return None
        
        try:
            # Activate the window
            if not self.activate_window(hwnd):
                return None
            
            time.sleep(0.2)
            
            # Get window rect for positioning
            rect = self.get_window_rect(hwnd)
            if not rect:
                return None
            
            left, top, right, bottom = rect
            width = right - left
            height = bottom - top
            
            # Click on the chat panel area (right side of VS Code)
            chat_x = left + int(width * 0.70)  # Right 30% of window
            chat_y = top + int(height * 0.4)   # Upper-middle
            
            # Focus on chat area
            pyautogui.click(chat_x, chat_y)
            time.sleep(0.15)
            
            # Scroll to top of chat first
            pyautogui.hotkey('ctrl', 'home')
            time.sleep(0.2)
            
            # Clear clipboard first
            pyperclip.copy("")
            
            # Select all in the focused area
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.15)
            
            # Copy to clipboard
            pyautogui.hotkey('ctrl', 'c')
            time.sleep(0.2)
            
            # Click somewhere neutral to deselect
            pyautogui.press('escape')
            
            # Get clipboard content
            content = pyperclip.paste()
            
            if content and len(content.strip()) > 10:
                self.last_content = content
                self.last_extraction_time = now
                print(f"[ChatExtractor] Extracted {len(content)} characters")
                return content
            else:
                print("[ChatExtractor] No valid content extracted")
                return self.last_content if self.last_content else None
                
        except Exception as e:
            print(f"[ChatExtractor] Extraction error: {e}")
            return self.last_content if self.last_content else None
    
    def parse_chat_messages(self, raw_content: str) -> List[ChatMessage]:
        """Parse raw content into structured chat messages"""
        messages = []
        
        if not raw_content:
            return messages
        
        lines = raw_content.split('\n')
        current_role = "assistant"
        current_content = []
        
        for line in lines:
            # Detect user messages (typically start with specific patterns)
            if line.strip().startswith("You:") or line.strip().startswith(">"):
                # Save previous message
                if current_content:
                    messages.append(ChatMessage(
                        role=current_role,
                        content='\n'.join(current_content).strip()
                    ))
                current_role = "user"
                current_content = [line.replace("You:", "").replace(">", "").strip()]
            elif line.strip().startswith("Antigravity:") or line.strip().startswith("Assistant:"):
                # Save previous message
                if current_content:
                    messages.append(ChatMessage(
                        role=current_role,
                        content='\n'.join(current_content).strip()
                    ))
                current_role = "assistant"
                current_content = [line.replace("Antigravity:", "").replace("Assistant:", "").strip()]
            else:
                current_content.append(line)
        
        # Add last message
        if current_content:
            messages.append(ChatMessage(
                role=current_role,
                content='\n'.join(current_content).strip()
            ))
        
        return messages
    
    def format_for_display(self, raw_content: str) -> str:
        """Format raw chat content for mobile display"""
        if not raw_content:
            return ""
        
        # Clean up common formatting issues
        formatted = raw_content
        
        # Preserve code blocks
        formatted = re.sub(r'```(\w+)?\n', r'\n[CODE]\n', formatted)
        formatted = formatted.replace('```', '\n[/CODE]\n')
        
        # Format headers
        formatted = re.sub(r'^(#{1,3})\s+(.+)$', r'\n=== \2 ===\n', formatted, flags=re.MULTILINE)
        
        # Format checkmarks
        formatted = formatted.replace('[x]', '[OK]')
        formatted = formatted.replace('[ ]', '[  ]')
        formatted = formatted.replace('✅', '[OK]')
        formatted = formatted.replace('❌', '[X]')
        
        # Format bullet points
        formatted = re.sub(r'^[\s]*[-*]\s+', '  - ', formatted, flags=re.MULTILINE)
        
        # Remove excessive blank lines
        formatted = re.sub(r'\n{3,}', '\n\n', formatted)
        
        return formatted.strip()


# Global instance
_chat_extractor: Optional[ChatExtractor] = None

def get_chat_extractor() -> ChatExtractor:
    """Get or create the global chat extractor instance"""
    global _chat_extractor
    if _chat_extractor is None:
        _chat_extractor = ChatExtractor()
    return _chat_extractor
