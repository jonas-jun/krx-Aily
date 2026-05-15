# KRX-Aily 배포 계획

## 스택

| 레이어 | 서비스 | 비고 |
|--------|--------|------|
| 백엔드 | Google Cloud Run | fin-Aily Dockerfile 구조 동일 적용 |
| 프론트엔드 | Vercel | fin-Aily와 동일 |
| 컨테이너 저장소 | Artifact Registry | 리전: asia-northeast3 (서울) |
| 이미지 빌드 | Cloud Build | 로컬 Docker 불필요 |

---

## Phase 1 — 코드 수정

배포 전 아래 파일들을 수정/추가해야 한다.

### 1-1. `backend/Dockerfile`

- Python 버전: `3.11-slim` → `3.13-slim` (fin-Aily와 통일)
- 포트: `8000` 하드코딩 → `${PORT:-8080}` (Cloud Run은 PORT 환경변수로 포트를 동적 할당)

```dockerfile
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run은 기본적으로 PORT 환경변수로 8080을 제공합니다.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
```

### 1-2. `backend/.dockerignore` (신규)

fin-Aily와 동일하게 적용. `.env` 파일이 이미지에 포함되지 않도록 한다.

```
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
.venv/
.env
.env.*
!.env.example
.pytest_cache/
.mypy_cache/
.ruff_cache/
tests/
.git/
.gitignore
.vscode/
.idea/
.DS_Store
*.md
```

### 1-3. `backend/.env.example` (신규)

```env
GEMINI_API_KEY=your-gemini-api-key-here

APP_ENV=production
DEBUG=false
CORS_ORIGINS=["https://your-vercel-domain.vercel.app"]
```

### 1-4. `frontend/.env.local.example` (신규)

```env
# 개발 환경
NEXT_PUBLIC_API_URL=http://localhost:8000/api

# 프로덕션 (Cloud Run 배포 후 URL로 교체)
# NEXT_PUBLIC_API_URL=https://krx-aily-backend-xxxx.run.app/api
```

---

## Phase 2 — GCP 초기 설정 (최초 1회)

```bash
# 1. GCP 프로젝트 설정
gcloud config set project PROJECT_ID

# 2. 필요한 API 활성화
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com

# 3. Artifact Registry 저장소 생성
gcloud artifacts repositories create krx-aily \
  --repository-format=docker \
  --location=asia-northeast3 \
  --description="KRX-Aily Docker images"
```

---

## Phase 3 — 백엔드 배포 (Cloud Run)

Cloud Build를 사용하면 로컬 Docker 없이 GCP에서 직접 빌드 + 푸시한다.

```bash
# 이미지 빌드 & Artifact Registry 푸시
gcloud builds submit ./backend \
  --tag asia-northeast3-docker.pkg.dev/PROJECT_ID/krx-aily/backend

# Cloud Run 배포
gcloud run deploy krx-aily-backend \
  --image asia-northeast3-docker.pkg.dev/PROJECT_ID/krx-aily/backend \
  --platform managed \
  --region asia-northeast3 \
  --allow-unauthenticated \
  --set-env-vars "GEMINI_API_KEY=실제키값,APP_ENV=production,DEBUG=false,CORS_ORIGINS=[\"https://krx-aily.vercel.app\"]"
```

배포 완료 후 URL 확인:
```
https://krx-aily-backend-xxxx.run.app
```

---

## Phase 4 — 프론트엔드 배포 (Vercel)

1. [vercel.com](https://vercel.com) → New Project → `jonas-jun/krx-Aily` 연결
2. 설정:

| 항목 | 값 |
|------|----|
| Root Directory | `frontend` |
| Framework Preset | Next.js (자동 감지) |

3. 환경 변수:

| 키 | 값 |
|----|----|
| `NEXT_PUBLIC_API_URL` | `https://krx-aily-backend-xxxx.run.app/api` |

---

## Phase 5 — CORS 업데이트

Vercel 배포 완료 후 확정된 도메인을 Cloud Run 환경변수에 반영한다.

```bash
gcloud run services update krx-aily-backend \
  --region asia-northeast3 \
  --update-env-vars "CORS_ORIGINS=[\"https://krx-aily.vercel.app\"]"
```

---

## 배포 체크리스트

- [ ] Phase 1: 코드 수정 완료 및 커밋
- [ ] Phase 2: GCP 프로젝트 설정, API 활성화, Artifact Registry 생성
- [ ] Phase 3: Cloud Run 백엔드 배포 및 URL 확인
- [ ] Phase 4: Vercel 프론트엔드 배포 및 `NEXT_PUBLIC_API_URL` 설정
- [ ] Phase 5: CORS_ORIGINS 업데이트 후 정상 동작 확인

---

## 재배포 (업데이트 시)

```bash
# 백엔드만 업데이트
gcloud builds submit ./backend \
  --tag asia-northeast3-docker.pkg.dev/PROJECT_ID/krx-aily/backend

gcloud run deploy krx-aily-backend \
  --image asia-northeast3-docker.pkg.dev/PROJECT_ID/krx-aily/backend \
  --region asia-northeast3
```

프론트엔드는 `main` 브랜치 push 시 Vercel이 자동 배포한다.
