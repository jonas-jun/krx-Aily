# fin-aily 리포트 개선 계획

`krx_aily_plan.md` 항목 1·2 반영 계획

---

## 항목 1. 주주환원 및 밸류업 분석

### 목표
DART 공시와 증권사 리포트에서 배당·자사주·ROE 정보를 추출해
§2 사업 및 재무 성과 분석 하위에 주주환원 분석을 추가한다.

### 현황 파악
| 필요 데이터 | 현재 수집 여부 | 비고 |
|---|---|---|
| ROE | 미계산 | net_income·equity는 이미 수집 중 → 코드로 계산 가능 |
| 배당 현황 | 미수집 | DART `alotMatter.json` API 별도 호출 필요 |
| 자사주 취득/소각 | 부분적 | 공시 원문(document.xml)에 포함되나 구조화 안 됨 |
| 주주환원율 | 미계산 | (배당총액 + 자사주취득) / 순이익 — 배당 데이터 수집 후 계산 가능 |

### 구현 단계

#### Phase 1-A — ROE Python 계산 (백엔드, 난이도 낮음)
- `metrics.py`: `compute_roe(net_income, equity)` 함수 추가
- `dart_service.py`의 `_IS_CF_FIELDS` 또는 `enrich_quarters()`에서 ROE 파생 지표로 추가
- `report_analyzer.py`의 `_build_is_table()`: ROE 컬럼 추가

#### Phase 1-B — 프롬프트 지시문 추가 (백엔드, 난이도 낮음)
- `report_analyzer.py`의 §2 섹션 지시문에 아래 문구 삽입:
  > **주주환원 및 자본 효율성:** DART 공시에 나타난 배당, 자사주 매입/소각 현황을 요약하고,
  > 증권사 리포트에서 언급된 ROE 개선 여부 및 주주환원 정책 변화를 분석하라.
- 대상 함수: `_build_full_report_prompt()`, `_build_dart_only_prompt()` 둘 다

#### Phase 1-C — DART 배당 공시 API 수집 (백엔드, 난이도 중간)
- DART `alotMatter.json` API: 배당에 관한 사항 (주당 배당금, 배당성향, 배당수익률)
- `dart_service.py`에 `fetch_dart_dividend(corp_code)` 함수 추가
- `research_router.py`의 analyze 엔드포인트에서 병렬 수집 후 `analyze_reports()`에 전달
- 프롬프트 내 별도 블록으로 주입

**권장 우선순위:** Phase 1-A → 1-B → 1-C 순서로 단계적 적용

---

## 항목 2. 증권사 편향성 및 의견 불일치 포착

### 목표
한국 증권사 리포트의 구조적 긍정 편향을 감안해,
표면적 투자의견보다 **목표주가 방향성**과 **증권사 간 시각 차이**를 명시적으로 분석하도록 §6을 보강한다.

### 현황 파악
| 필요 데이터 | 현재 수집 여부 | 비고 |
|---|---|---|
| 현재 목표주가 | 수집 중 | `_extract_target_prices()`에서 추출 |
| 직전 목표주가 | 미추출 | 리포트 본문에 "목표주가 X→Y원으로 하향" 형태로 존재 |
| 증권사 간 의견 차이 | 미분석 | 프롬프트 지시 없음 |
| EPS 추정치 방향 | 미추출 | 일부 리포트에 포함 |

### 구현 단계

#### Phase 2-A — 목표주가 방향성 추출 (백엔드, 난이도 낮음)
- `report_analyzer.py`의 `_build_target_price_prompt()` 수정:
  - 기존: `report_target_prices` (현재 목표주가 배열)만 추출
  - 변경: `prev_target_prices` (직전 목표주가) 및 `direction` (상향/하향/유지/신규) 추가 추출
- `AnalysisResult` 또는 `SourceItem`에 `prev_target_price`, `tp_direction` 필드 추가
- 프론트엔드 소스 목록에 방향성 배지 표시 (↑/↓/→)

#### Phase 2-B — §6 프롬프트 보강 (백엔드, 난이도 낮음)
- `_build_full_report_prompt()`의 §6 지시문에 아래 내용 추가:
  > * **목표주가 방향성 분석:** 각 증권사의 이번 목표주가가 직전 대비 상향/하향/유지인지 명시하고,
  >   하향 조정이 있다면 그 이유와 투자 의미를 분석하라.
  > * **컨센서스 이면의 뉘앙스:** 투자의견이 모두 긍정적이더라도 EPS 추정치 하향,
  >   목표주가 하향, 증권사 간 핵심 가정 차이(Bull vs. Bear 논리)를 날카롭게 포착하라.

#### Phase 2-C — 목표주가 방향성 프론트엔드 표시 (프론트엔드, 난이도 낮음)
- `SourceList` 컴포넌트에 목표주가 옆 방향 배지 추가
  - 상향: 초록 ▲, 하향: 빨강 ▼, 유지: 회색 →, 신규: 파랑 NEW

**권장 우선순위:** Phase 2-B (즉시 효과) → 2-A → 2-C 순서

---

## 요약 로드맵

| Phase | 내용 | 변경 파일 | 난이도 | 효과 |
|---|---|---|---|---|
| 1-A | ROE 계산 + IS 테이블 컬럼 추가 | `metrics.py`, `report_analyzer.py` | 낮음 | 즉시 |
| 1-B | 주주환원 프롬프트 지시문 추가 | `report_analyzer.py` | 낮음 | 즉시 |
| 2-B | 편향성·의견차 §6 프롬프트 보강 | `report_analyzer.py` | 낮음 | 즉시 |
| 2-A | 목표주가 방향성 추출 | `report_analyzer.py`, 응답 모델 | 중간 | 중간 |
| 2-C | 프론트 방향성 배지 | `frontend/components` | 낮음 | 중간 |
| 1-C | DART 배당 공시 API 수집 | `dart_service.py`, `research_router.py` | 중간 | 높음 |
