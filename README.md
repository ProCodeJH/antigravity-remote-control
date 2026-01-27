# 🚀 Antigravity Remote Control System

핸드폰에서 다른 네트워크를 통해 Antigravity를 원격 제어하는 초고도 시스템

## 📂 프로젝트 구조

```
antigravity-remote-control/
├── backend/              # WebSocket 릴레이 서버
│   ├── src/server.js     # Fastify + WebSocket 통합 서버
│   └── package.json
├── agent/                # PC Agent (Python)
│   ├── agent.py          # 스크린 캡처, 입력 인젝션, AG 브릿지
│   └── requirements.txt
└── mobile/               # PWA 모바일 클라이언트
    ├── index.html        # Canvas 뷰어, 터치 제어, 가상 키보드
    └── manifest.json
```

## ⚡ 빠른 시작

### 1. 백엔드 서버 실행
```powershell
cd backend
npm install
npm run dev
```
> 서버가 `http://localhost:8080`에서 실행됩니다.

### 2. PC Agent 실행
```powershell
cd agent
pip install -r requirements.txt
python agent.py ws://localhost:8080/ws/relay test-session
```

### 3. 모바일 클라이언트 실행
```powershell
cd mobile
npx serve .
```
> 브라우저에서 `http://localhost:3000` 접속 또는 핸드폰에서 접속

## 🌐 외부 네트워크 접속 (Ngrok)

```powershell
# Ngrok 터널 생성
ngrok http 8080

# 생성된 URL을 모바일 앱에서 사용
# 예: wss://abc123.ngrok.io/ws/relay
```

## 🎮 기능

| 기능 | 설명 |
|------|------|
| 🖥️ 라이브 화면 | 실시간 PC 화면 스트리밍 (15-30 FPS) |
| 👆 터치 제어 | 탭=클릭, 롱프레스=우클릭, 스와이프=드래그 |
| ⌨️ 가상 키보드 | 전체 QWERTY + 모디파이어 (Ctrl, Alt, Shift) |
| 📊 시스템 상태 | CPU, 메모리, 배터리, 네트워크 모니터링 |
| 💬 AI 명령 | Antigravity에 음성/텍스트 명령 전달 |

## 🔧 설정

### 환경 변수 (Backend)
| 변수 | 기본값 | 설명 |
|------|--------|------|
| `PORT` | 8080 | 서버 포트 |
| `ANTIGRAVITY_URL` | http://localhost:8765 | Antigravity API 주소 |
| `TEST_MODE` | false | 세션 자동 생성 모드 |

### Agent 설정 (agent.py)
```python
CONFIG = Config(
    relay_url="ws://localhost:8080/ws/relay",
    antigravity_url="http://localhost:8765",
    session_id="test-session",
    capture_fps=15,        # 프레임레이트
    jpeg_quality=60        # 화질 (1-100)
)
```

## 📱 PWA 설치

1. 핸드폰 브라우저에서 모바일 URL 접속
2. "홈 화면에 추가" 선택
3. 앱처럼 실행 가능!

## 🔒 보안

- WebSocket TLS (WSS) 지원
- 세션 기반 인증
- 세션 타임아웃 (30분)
- Ngrok 인증 옵션

## 📋 다음 단계

1. Ngrok/Cloudflare 터널 통합
2. 생체 인증 추가
3. 오디오 스트리밍
4. E2E 암호화
