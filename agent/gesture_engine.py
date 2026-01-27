"""
ULTRA Gesture Recognition Engine
=================================
모바일 제스처를 PC 액션으로 변환

제스처:
- swipe_left  → Alt+Tab
- swipe_right → Alt+Shift+Tab
- swipe_up    → Win+Tab
- swipe_down  → Win+D
- pinch_in    → Ctrl+-
- pinch_out   → Ctrl++
- two_finger_scroll → 스크롤
- three_finger_drag → 윈도우 이동
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional, Callable
from enum import Enum
import time
import math


class GestureType(Enum):
    """제스처 타입"""
    NONE = "none"
    TAP = "tap"
    DOUBLE_TAP = "double_tap"
    LONG_PRESS = "long_press"
    SWIPE_LEFT = "swipe_left"
    SWIPE_RIGHT = "swipe_right"
    SWIPE_UP = "swipe_up"
    SWIPE_DOWN = "swipe_down"
    PINCH_IN = "pinch_in"
    PINCH_OUT = "pinch_out"
    TWO_FINGER_SCROLL = "two_finger_scroll"
    THREE_FINGER_SWIPE = "three_finger_swipe"
    ROTATE = "rotate"


@dataclass
class TouchPoint:
    """터치 포인트"""
    id: int
    x: float
    y: float
    timestamp: int


@dataclass
class GestureEvent:
    """제스처 이벤트"""
    gesture_type: GestureType
    start_pos: Tuple[float, float]
    end_pos: Tuple[float, float]
    delta: Tuple[float, float]
    scale: float  # 핀치 스케일
    rotation: float  # 회전 각도
    velocity: float
    duration: int  # ms
    finger_count: int


class GestureRecognizer:
    """제스처 인식기"""
    
    # 제스처 임계값
    SWIPE_THRESHOLD = 50  # 픽셀
    SWIPE_VELOCITY = 200  # 픽셀/초
    LONG_PRESS_DURATION = 500  # ms
    DOUBLE_TAP_INTERVAL = 300  # ms
    PINCH_THRESHOLD = 0.2  # 20% 스케일 변화
    
    def __init__(self):
        self.touch_points: dict = {}  # id -> [TouchPoint, ...]
        self.last_tap_time = 0
        self.last_tap_pos = (0, 0)
    
    def on_touch_start(self, touch_id: int, x: float, y: float):
        """터치 시작"""
        self.touch_points[touch_id] = [TouchPoint(
            id=touch_id, x=x, y=y, timestamp=int(time.time() * 1000)
        )]
    
    def on_touch_move(self, touch_id: int, x: float, y: float):
        """터치 이동"""
        if touch_id in self.touch_points:
            self.touch_points[touch_id].append(TouchPoint(
                id=touch_id, x=x, y=y, timestamp=int(time.time() * 1000)
            ))
    
    def on_touch_end(self, touch_id: int, x: float, y: float) -> Optional[GestureEvent]:
        """터치 종료 및 제스처 인식"""
        if touch_id not in self.touch_points:
            return None
        
        points = self.touch_points[touch_id]
        points.append(TouchPoint(id=touch_id, x=x, y=y, timestamp=int(time.time() * 1000)))
        
        # 제스처 분석
        gesture = self._analyze_gesture(points)
        
        # 메모리 정리
        del self.touch_points[touch_id]
        
        return gesture
    
    def _analyze_gesture(self, points: List[TouchPoint]) -> GestureEvent:
        """제스처 분석"""
        if len(points) < 2:
            return self._create_event(GestureType.TAP, points)
        
        first = points[0]
        last = points[-1]
        
        dx = last.x - first.x
        dy = last.y - first.y
        distance = math.sqrt(dx**2 + dy**2)
        duration = last.timestamp - first.timestamp
        velocity = distance / (duration / 1000) if duration > 0 else 0
        
        # 스와이프 판별
        if distance > self.SWIPE_THRESHOLD and velocity > self.SWIPE_VELOCITY:
            if abs(dx) > abs(dy):
                gesture_type = GestureType.SWIPE_RIGHT if dx > 0 else GestureType.SWIPE_LEFT
            else:
                gesture_type = GestureType.SWIPE_DOWN if dy > 0 else GestureType.SWIPE_UP
        
        # 롱 프레스 판별
        elif duration > self.LONG_PRESS_DURATION and distance < self.SWIPE_THRESHOLD:
            gesture_type = GestureType.LONG_PRESS
        
        # 더블 탭 판별
        elif distance < self.SWIPE_THRESHOLD:
            now = int(time.time() * 1000)
            if now - self.last_tap_time < self.DOUBLE_TAP_INTERVAL:
                gesture_type = GestureType.DOUBLE_TAP
            else:
                gesture_type = GestureType.TAP
            self.last_tap_time = now
        else:
            gesture_type = GestureType.NONE
        
        return self._create_event(gesture_type, points, (dx, dy), velocity, duration)
    
    def _create_event(
        self,
        gesture_type: GestureType,
        points: List[TouchPoint],
        delta: Tuple[float, float] = (0, 0),
        velocity: float = 0,
        duration: int = 0
    ) -> GestureEvent:
        first = points[0]
        last = points[-1]
        
        return GestureEvent(
            gesture_type=gesture_type,
            start_pos=(first.x, first.y),
            end_pos=(last.x, last.y),
            delta=delta,
            scale=1.0,
            rotation=0.0,
            velocity=velocity,
            duration=duration,
            finger_count=1
        )


class GestureActionMapper:
    """제스처 → PC 액션 매핑"""
    
    DEFAULT_MAPPINGS = {
        GestureType.SWIPE_LEFT: ("hotkey", "alt+tab"),
        GestureType.SWIPE_RIGHT: ("hotkey", "alt+shift+tab"),
        GestureType.SWIPE_UP: ("hotkey", "win+tab"),
        GestureType.SWIPE_DOWN: ("hotkey", "win+d"),
        GestureType.PINCH_IN: ("hotkey", "ctrl+minus"),
        GestureType.PINCH_OUT: ("hotkey", "ctrl+plus"),
        GestureType.DOUBLE_TAP: ("double_click", None),
        GestureType.LONG_PRESS: ("right_click", None),
        GestureType.THREE_FINGER_SWIPE: ("hotkey", "ctrl+win+left"),
    }
    
    def __init__(self, custom_mappings: dict = None):
        self.mappings = {**self.DEFAULT_MAPPINGS}
        if custom_mappings:
            self.mappings.update(custom_mappings)
    
    def get_action(self, gesture: GestureEvent) -> Tuple[str, Optional[str]]:
        """제스처에 대응하는 액션 반환"""
        return self.mappings.get(gesture.gesture_type, ("none", None))
    
    def set_mapping(self, gesture_type: GestureType, action: str, params: str = None):
        """매핑 설정"""
        self.mappings[gesture_type] = (action, params)


class GestureExecutor:
    """제스처 실행기"""
    
    def __init__(self, mapper: GestureActionMapper = None):
        self.mapper = mapper or GestureActionMapper()
        import pyautogui
        self.pyautogui = pyautogui
    
    def execute(self, gesture: GestureEvent) -> dict:
        """제스처 실행"""
        action, params = self.mapper.get_action(gesture)
        
        try:
            if action == "hotkey" and params:
                keys = params.replace("win", "win").split("+")
                self.pyautogui.hotkey(*keys)
                return {"success": True, "action": action, "keys": keys}
            
            elif action == "click":
                self.pyautogui.click(gesture.end_pos[0], gesture.end_pos[1])
                return {"success": True, "action": "click"}
            
            elif action == "double_click":
                self.pyautogui.doubleClick(gesture.end_pos[0], gesture.end_pos[1])
                return {"success": True, "action": "double_click"}
            
            elif action == "right_click":
                self.pyautogui.rightClick(gesture.end_pos[0], gesture.end_pos[1])
                return {"success": True, "action": "right_click"}
            
            elif action == "scroll":
                amount = gesture.delta[1]
                self.pyautogui.scroll(int(amount))
                return {"success": True, "action": "scroll", "amount": amount}
            
            elif action == "none":
                return {"success": True, "action": "none"}
            
            return {"success": False, "error": f"Unknown action: {action}"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}


class UltraGestureEngine:
    """ULTRA 제스처 엔진 통합"""
    
    def __init__(self):
        self.recognizer = GestureRecognizer()
        self.mapper = GestureActionMapper()
        self.executor = GestureExecutor(self.mapper)
    
    def process_touch(self, event_type: str, touch_id: int, x: float, y: float) -> Optional[dict]:
        """터치 이벤트 처리"""
        if event_type == "start":
            self.recognizer.on_touch_start(touch_id, x, y)
            return None
        
        elif event_type == "move":
            self.recognizer.on_touch_move(touch_id, x, y)
            return None
        
        elif event_type == "end":
            gesture = self.recognizer.on_touch_end(touch_id, x, y)
            if gesture and gesture.gesture_type != GestureType.NONE:
                result = self.executor.execute(gesture)
                result["gesture"] = gesture.gesture_type.value
                return result
        
        return None
    
    def get_mappings(self) -> dict:
        """현재 매핑 반환"""
        return {
            g.value: {"action": a[0], "params": a[1]}
            for g, a in self.mapper.mappings.items()
        }
    
    def set_mapping(self, gesture: str, action: str, params: str = None):
        """매핑 설정"""
        try:
            gesture_type = GestureType(gesture)
            self.mapper.set_mapping(gesture_type, action, params)
            return True
        except ValueError:
            return False


if __name__ == "__main__":
    engine = UltraGestureEngine()
    
    print("Gesture Mappings:")
    for gesture, mapping in engine.get_mappings().items():
        print(f"  {gesture}: {mapping['action']} {mapping['params'] or ''}")
