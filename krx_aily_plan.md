# krx-Aily 개발 기획안

---

## [완료] 디자인 리브랜딩 (issue #11)

| 항목 | 변경 전 | 변경 후 |
|---|---|---|
| 서비스명 | KRX-Aily | fin-Aily-kr |
| 핵심 컬러 | rose-500 (그라디언트) | Rose Red `#EF4444` |
| 보조 컬러 | slate 계열 | Navy Blue `#1E3A5F` |
| 로고 | 텍스트 전용 | SVG 로고 (▲ 아이콘 + KR 배지) |

### 완료된 변경 파일
- `tailwind.config.js` — `primary: #EF4444`, `brand: #1E3A5F` 커스텀 컬러
- `Logo.tsx` — 점 없는 i(ı) + 빨간 삼각형 + KR 배지 SVG 컴포넌트
- `Header.tsx` — SVG 로고 적용, 활성 Nav 링크 `#EF4444`
- `app/layout.tsx` — 타이틀 `fin-Aily-kr` 변경
- `app/page.tsx` — 이모지·h1 제거, Hero 로고(size=lg)
- 리포트 컴포넌트 5종 — Primary 컬러 `#EF4444` 일괄 적용

---

## [진행 예정] 리포트 페이지 UX 개선

### 기능 1. 종목명 앞 이모지 제거

**현재**
```
📈 삼성전자  005930
```
**변경 후**
```
삼성전자  005930
```

- **파일**: `app/report/[ticker]/page.tsx` line 53
- **작업**: `<span className="text-xl">📈</span>` 제거

---

### 기능 2. 목표주가 카드에 현재주가 표시

#### 목표 UI

```
┌─────────────────────────────────────┐
│ 목표주가                             │
│                                     │
│  평균 목표주가        현재주가        │
│  85,000원            72,400원       │
│  최저 75,000  최고 95,000  괴리율 +17.4% │
└─────────────────────────────────────┘
```

- 현재주가와 평균 목표주가를 나란히 표시
- 괴리율 = `(목표주가 평균 - 현재주가) / 현재주가 × 100`
- 괴리율 양수(목표 > 현재) → Rose Red `#EF4444`, 음수 → slate

#### 구현 범위

**Backend**

1. `backend/app/services/price_fetcher.py` 신규 생성
   - 네이버 금융 API로 현재주가 조회
   - `https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{ticker}`
   - 반환 타입: `float | None`

2. `backend/app/routers/research_router.py`
   - `TargetPrice` 모델에 `current_price: float | None` 필드 추가
   - `/analyze` 엔드포인트에서 `fetch_current_price(ticker)` 병렬 호출 (리포트 분석과 동시)

**Frontend**

3. `frontend/lib/api.ts`
   - `TargetPrice` 인터페이스에 `current_price: number | null` 추가

4. `frontend/components/report/TargetPriceCard.tsx`
   - 현재주가 섹션 추가
   - 괴리율 계산 및 색상 조건부 적용

#### 데이터 흐름

```
/analyze POST
  ├─ fetch_reports_with_pdf(ticker)   # 기존
  ├─ fetch_current_price(ticker)      # 신규 (병렬)
  └─ analyze_reports(...)             # 기존
       ↓
  AnalyzeResponse.target_price.current_price
```

#### 괴리율 계산

```
gap = (avg_target - current_price) / current_price * 100
표시: "+17.4%" 또는 "-3.2%"
색상: 양수 → text-[#EF4444], 음수 → text-slate-500
```

#### 예외 처리
- 현재주가 조회 실패 시 `current_price: null` 반환 (분석 전체는 중단하지 않음)
- `current_price`가 null이면 괴리율 섹션 미표시

---

## 구현 순서 (기능 2)

| 순서 | 파일 | 내용 |
|---|---|---|
| 1 | `backend/app/services/price_fetcher.py` | 현재주가 조회 서비스 신규 |
| 2 | `backend/app/routers/research_router.py` | `TargetPrice` 모델 + `/analyze` 수정 |
| 3 | `frontend/lib/api.ts` | `TargetPrice` 타입 수정 |
| 4 | `frontend/components/report/TargetPriceCard.tsx` | UI 구현 |
| 5 | `frontend/app/report/[ticker]/page.tsx` | 📈 이모지 제거 |
