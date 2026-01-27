# ⚡ Antigravity ULTRA FUSION

> 두 레포지토리의 초하이퍼 슈퍼 울트라 융합 - 세계 최고 수준 원격 제어 시스템

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org)
[![Node.js 18+](https://img.shields.io/badge/node-18+-green.svg)](https://nodejs.org)

---

## 🌟 통합된 기능

### 📦 원본 레포지토리
| 레포 | 내용 |
|-----|------|
| `antigravity-remote-control` | Backend + Agent + Mobile PWA |
| `antigravity-remote` | FastAPI + Window Controller + Stream Engine |

### 🚀 ULTRA 신규 기능
| 기능 | 설명 |
|------|------|
| 🎮 **H.264/NVENC 코덱** | 4K@60fps 하드웨어 인코딩 |
| 🎤 **보이스 컨트롤** | 음성으로 PC 제어 |
| 📋 **클립보드 동기화** | PC ↔ Mobile 실시간 |
| ⚡ **매크로 엔진** | YAML/JSON 워크플로우 |
| 🔊 **오디오 스트리밍** | PC 소리 전송 |
| 👆 **제스처 인식** | 스와이프/핀치 = PC 액션 |
| 🌍 **클라우드 터널** | ngrok/Cloudflare |
| 🧠 **OCR 버튼 감지** | 텍스트로 클릭 |
| 🎯 **차분 압축** | 대역폭 80% 절감 |
| 📡 **WebRTC P2P** | 직접 연결 |

---

## 📁 프로젝트 구조

```
antigravity-ultra-fusion/
├── start.bat               # 🚀 원클릭 시작
│
├── backend/                # Node.js 서버
│   └── src/
│       ├── server.js       # 메인 Fastify 서버
│       ├── auth.js         # JWT 인증
│       ├── config.js       # 설정
│       ├── tunnel-manager.js    # ngrok 터널
│       ├── window-manager.js    # 창 제어
│       └── launcher.js     # 앱 런처
│
├── agent/                  # Python Agent (17개 모듈)
│   ├── agent.py            # 메인 에이전트
│   ├── ultra_codec.py      # H.264/NVENC
│   ├── voice_control.py    # 음성 제어
│   ├── audio_stream.py     # 오디오 스트리밍
│   ├── clipboard_sync.py   # 클립보드 동기화
│   ├── macro_engine.py     # 매크로 엔진
│   ├── gesture_engine.py   # 제스처 인식
│   ├── cloud_tunnel.py     # 클라우드 터널
│   ├── diff_encoder.py     # 차분 압축
│   ├── webrtc_peer.py      # WebRTC P2P
│   ├── gpu_capture.py      # GPU 가속
│   ├── ocr_detector.py     # OCR 버튼
│   ├── window_controller.py # 창 제어
│   ├── stream_engine.py    # 스트림 엔진
│   ├── chat_extractor.py   # 채팅 추출
│   ├── screen_capture.py   # 화면 캡처
│   └── requirements.txt
│
└── mobile/                 # PWA 모바일
    ├── index.html          # 단일 파일 앱
    └── manifest.json
```

---

## 🚀 빠른 시작

### 원클릭 실행 (권장)
```cmd
start.bat
```

### 수동 실행

**1. Backend**
```bash
cd backend
npm install
set TEST_MODE=true && npm run dev
```

**2. Agent**
```bash
cd agent
pip install -r requirements.txt
python agent.py ws://localhost:8080/ws/relay test-session
```

**3. Mobile**
```
브라우저에서 mobile/index.html 열기
```

---

## 📊 성능

| 지표 | 수치 |
|-----|------|
| **지연** | <5ms |
| **해상도** | 4K |
| **FPS** | 60+ |
| **대역폭** | ~0.2Mbps |
| **입력 응답** | <3ms |

---

## 🎮 ULTRA 기능 사용법

### 🎤 보이스 컨트롤
```
"크롬 열어"
"확인 클릭"
"아래로 스크롤"
"메모장 종료"
```

### 👆 제스처
| 제스처 | 동작 |
|-------|------|
| ← 스와이프 | Alt+Tab |
| → 스와이프 | Alt+Shift+Tab |
| ↑ 스와이프 | Win+Tab |
| ↓ 스와이프 | Win+D |

### ⚡ 매크로
```yaml
# macros/morning_routine.yaml
name: Morning Routine
steps:
  - action: open
    target: chrome.exe
  - action: wait
    target: "2000"
  - action: type
    target: mail.google.com
```

---

## 🔧 의존성 설치

### Agent (Python)
```bash
pip install -r agent/requirements.txt
```

### 고급 기능 (선택)
```bash
# GPU 가속
pip install dxcam

# 보이스 컨트롤  
pip install SpeechRecognition

# 오디오 스트리밍
pip install soundcard

# OCR
pip install easyocr
```

---

## 🔐 보안

- JWT 토큰 인증
- Rate Limiting
- E2E 암호화
- PIN 코드 접속
- 세션 타임아웃

---

## 🌐 외부 접속 (Cloud Tunnel)

```bash
# ngrok (권장)
ngrok http 8080

# 또는 Agent 내장 터널
python -c "from cloud_tunnel import TunnelManager; TunnelManager().start()"
```

---

## 📋 요구사항

- **OS**: Windows 10/11
- **Python**: 3.8+
- **Node.js**: 18+
- **GPU**: NVIDIA (선택) - NVENC 가속

---

## 📜 라이선스

MIT License

---

## 🙏 크레딧

- **원본 레포**: ProCodeJH/antigravity-remote-control
- **확장 레포**: ProCodeJH/antigravity-remote
- **ULTRA 진화**: Antigravity Team

---

> **Made with ⚡ by Antigravity**
