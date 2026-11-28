# 개발 메모

기준 문서: 설계서 `NetRecall_Lab_SDD_v1.1.md` (2026-11-12, 로컬에만 있고 커밋하지 않음)
날짜별 개발 결과(§0)와, 설계서와 다르게 결정했거나 설계서에 없는 동작을 구현에서 정한 내용(§1~)을 기록한다.

## 0. 개발 기록

### 2026-11-12

설계서 Phase 2(학습 자료 연동)의 Markdown 쪽과, Phase 1의 백엔드 뼈대를 만들었다.

| 영역 | 결과물 | 상태 |
|---|---|---|
| 공통 소스 인터페이스 | `integrations/sources/base.py` | 완료 (사용자 제공 코드) |
| Markdown 어댑터 | `integrations/sources/markdown/` | 완료 (사용자 제공 코드) |
| 동기화 계획 | `backend/services/concept_sync.py` | 완료 (사용자 제공 코드) |
| 샘플 개념 | `samples/concepts/network/` — NET-001 OSI 7계층 → NET-005 IP 주소와 서브넷 → NET-010 Static Routing | 완료 |
| 형식 명세 | `docs/markdown-concept-format.md` | 완료 |
| 미리보기 스크립트 | `scripts/preview_concepts.py` — DB 반영 없이 검사, 읽기 오류 시 종료 코드 1 | 완료 |
| DB 모델 | `backend/models/concept.py` — `concepts`, `concept_relations`, `concept_labs` | 완료 |
| DB 반영 계층 | `backend/services/concept_store.py` — 상태 읽기·계획·반영을 한 트랜잭션으로, `dry_run` 지원 | 완료 |
| API | `backend/main.py`, `backend/api/` — `/health`, `POST /sync/markdown`, `GET /concepts`, `GET /concepts/{id}` | 완료 |
| 프로젝트 설정 | `pyproject.toml`, `.gitignore`, `.env.example`, `README.md` | 완료 |

검증

- 테스트 79개 통과 (`pytest`)

  | 파일 | 개수 | 범위 |
  |---|---:|---|
  | `tests/sources/test_base.py` | 4 | 내용 해시, 인터페이스 |
  | `tests/sources/test_markdown_parser.py` | 27 | frontmatter 검증, 제목 대체, 질문 섹션 |
  | `tests/sources/test_markdown_scan.py` | 9 | 건너뛰기 규칙, 심볼릭 링크, 폴더 밖 경로, BOM·CRLF, 크기 상한, 오류 격리, id 중복 |
  | `tests/services/test_concept_sync.py` | 15 | 생성·갱신·이동·보관·복구·충돌·참조 경고 |
  | `tests/services/test_concept_store.py` | 13 | DB 반영, 연결 교체, 롤백, dry run, FK 검사 |
  | `tests/test_api.py` | 6 | API 동작 |
  | `tests/test_samples_and_preview.py` | 5 | 샘플 무결성, 미리보기 종료 코드 |

- 실제 서버(uvicorn)를 띄워 샘플 3개 동기화, `/concepts`·`/docs` 응답 확인

작업 중 확인한 것

- 제공 코드에서 고쳐야 할 버그는 찾지 못했다. 설계서와 다르게 동작하는 부분은 §3에 적었다.
- 제목 없는 파일은 이름을 바꾸면 `updated`로 분류된다 (§3).
- PyYAML은 `802.1Q`를 문자열로, `22`·`yes`·날짜는 문자열이 아닌 값으로 읽는다 (§7).

다음 작업

1. FSRS 복습 엔진 (계획표 8단계): `review_cards`(`card_json` + `due_at`, D4), `review_logs`, 오늘 복습할 개념 API
2. 그 전에 Alembic 도입 여부 결정 (§4 스키마 생성)
3. 이후: LLM Provider 인터페이스와 AI 질문 생성·답안 평가 → UI → MVP(설계서 §7.1) 완성

### 2026-11-13

설계서 Phase 3(FSRS 복습 시스템)의 백엔드와, 스키마 마이그레이션(Alembic)을 만들었다.

| 영역 | 결과물 | 상태 |
|---|---|---|
| 마이그레이션 | `alembic.ini`, `backend/migrations/` — `0001` 개념 테이블, `0002` 복습 테이블. 앱 시작 시 자동 upgrade (D6) | 완료 |
| 질문 최소 개수 | 개념마다 질문 3개 이상 필수 (D5). 모든 소스에 적용되도록 `concept_sync.py`에서 검사. 샘플 3개에 질문 1개씩 추가, 형식 명세 갱신 | 완료 |
| FSRS 감싸기 | `integrations/fsrs/` — py-fsrs 6.3을 쓰는 유일한 곳 | 완료 |
| DB 모델 | `backend/models/review.py` — `review_cards`, `review_logs` | 완료 |
| 카드 동기화 | `backend/services/concept_store.py` — 개념 반영과 같은 트랜잭션에서 질문별 카드 생성·비활성화·복구 | 완료 |
| 복습 서비스 | `backend/services/review_service.py` — 복습할 카드 조회, 평가 반영(카드 갱신 + 기록 추가를 한 트랜잭션) | 완료 |
| API | `GET /reviews/due`, `POST /reviews` | 완료 |

검증

- 테스트 112개 통과 (`pytest`). 새로 추가·변경한 파일:

  | 파일 | 개수 | 범위 |
  |---|---:|---|
  | `tests/test_migrations.py` | 3 | 마이그레이션 결과 = 모델, 반복 실행, `0001`에서 데이터 유지한 채 upgrade |
  | `tests/test_fsrs.py` | 6 | 새 카드, 등급별 다음 복습일, 간격 증가, 잘못된 등급 |
  | `tests/services/test_review_service.py` | 8 | 복습 대상 조회, 평가 반영, 비활성·보관 카드 거부, 롤백 |
  | `tests/services/test_concept_store.py` | 20 (+7) | 질문 변경·복구·순서 변경·이동·보관 시 카드 처리 |
  | `tests/services/test_concept_sync.py` | 19 (+4) | 질문 3개 미만 오류, 저장된 개념 유지(이동 포함), 소스 무관 적용 |
  | `tests/test_api.py` | 11 (+5) | 복습 흐름, 422·404·409 |

- 실제 서버(uvicorn)를 띄워 샘플 동기화 → 카드 9장 → Again·Good·Easy 평가 → 남은 카드 6장, `alembic_version = 0002` 확인

작업 중 확인한 것

- SQLAlchemy identity map은 객체를 약하게 참조한다. 같은 카드라도 방금 쓴 객체는 시간대가 있는 값, DB에서 다시 읽은 객체는 시간대 없는 값을 갖는다(§4 시간대). 복습 API는 응답에서 항상 KST(`+09:00`)로 바꿔 내보낸다(D7). 개념 API에는 시각 필드가 없다.
- py-fsrs 기본 학습 단계는 1분·10분이다. 새 카드에 Again은 1분 뒤, Good은 10분 뒤, Easy는 며칠 뒤가 된다.

다음 작업

1. LLM Provider 인터페이스와 AI 질문 생성·답안 평가 (Phase 4). 카드의 질문(`review_cards.question`)을 기준으로 출제한다
2. UI → MVP(설계서 §7.1) 완성

### 2026-11-13 (2) — Phase 4 AI 학습 평가

설계서 Phase 4의 백엔드(질문 생성, 답안 제출, 답안 평가, 피드백)를 만들었다. 실습 추천은 개념에 연결된 실습 id 중에서만 고른다.

| 영역 | 결과물 | 상태 |
|---|---|---|
| LLM 인터페이스 | `integrations/llm/` — `LLMClient`(스키마로 검증된 객체 반환), Gemini 구현(google-genai 3.3), `GEMINI_API_KEY`·`NETRECALL_GEMINI_MODEL` (D8) | 완료 |
| 프롬프트·스키마 | `backend/services/ai_prompts.py` — 변형 질문, 난이도 평가(D9), 답안 평가 5개 항목(D10), `PROMPT_VERSION` | 완료 |
| DB 모델 | `backend/models/assessment.py` — `questions`, `answer_submissions`, `answer_evaluations`, 리비전 `0003` | 완료 |
| 서비스 | `backend/services/assessment_service.py` — 질문 생성(호출 2번), 답안 평가(답안·평가 한 트랜잭션) | 완료 |
| API | `POST /cards/{card_id}/questions`, `POST /questions/{question_id}/answers` | 완료 |
| 공통 | `backend/core/time.py` — KST 변환을 복습·평가 API가 같이 쓴다 | 완료 |

검증

- 테스트 139개 통과 (`pytest`). 실제 Gemini는 호출하지 않는다(가짜 LLM `tests/fakes.py`).

  | 파일 | 개수 | 범위 |
  |---|---:|---|
  | `tests/test_llm_gemini.py` | 8 | 요청 구성(system·JSON 스키마), 잘못된 응답·API 실패 → `LLMError`, 환경변수 |
  | `tests/services/test_assessment_service.py` | 12 | 생성·난이도 별도 호출, 비활성·보관 카드 거부, 실패 시 미저장, 실습 id 걸러내기, 점수 범위 |
  | `tests/test_api_assessments.py` | 7 | 전체 학습 흐름, 키 없음 503, LLM 실패 502, 404, 답안 길이 422 |

- **실제 Gemini 호출은 아직 확인하지 못했다.** 작업 환경에 API 키가 없다. 기본 모델 `gemini-3.6-flash`는 Google 릴리스 노트(2026-07-21 GA)를 근거로 정했고, 모델 목록 문서끼리 내용이 달라 키를 넣고 확인해야 한다 (§7).

다음 작업

1. 실제 Gemini로 샘플 카드 질문 생성·평가 확인, 프롬프트 조정
2. 기본 UI → MVP(설계서 §7.1) 완성

### 2026-11-16 — 기본 UI, 실제 Gemini 확인

설계서 Phase 1의 기본 UI를 만들어 MVP(§7.1) 흐름을 화면에서 끝까지 진행할 수 있게 했다. 실제 Gemini를 처음 호출해 확인했다.

| 영역 | 결과물 | 상태 |
|---|---|---|
| UI | `frontend/` — React 19 + TypeScript + Vite. 동기화 → 복습할 카드 → AI 질문 → 답안 → 평가 → 등급 → 다음 복습일 | 완료 |
| UI 제공 | `backend/main.py` — `frontend/dist`가 있으면 `/`에서 보여 준다. API 경로가 먼저 매칭된다. 루트 → `/docs` 리다이렉트는 넣지 않았다 | 완료 |
| 호출 수 줄이기 | 난이도 평가를 질문 생성 호출에 합쳤다 (D11). 카드 1장당 호출 3번 → 2번 | 완료 (실제 호출은 미확인) |
| 변형 질문 프롬프트 | 외운 답이 통하지 않게, 답의 단서를 적지 않게 고쳤다. `PROMPT_VERSION = 2026-11-16.1` | **미검증** (하루 한도) |
| 한도 초과 문구 | Gemini 429를 "분당 한도 / 하루 한도" 짧은 문구로 바꾼다. 원문 JSON은 화면에 내보내지 않는다 | 완료 |
| 설정 | `python-dotenv` 의존성 추가. `.env.example`에 적힌 `uvicorn --env-file .env`가 이것 없이는 실패했다 | 완료 |

검증

- Python 테스트 143개 통과 (+4). `tests/test_api.py` +2 (`/`에서 UI, 빌드 없으면 404), `tests/test_llm_gemini.py` +2 (429 문구). 질문 생성 테스트는 호출 1번으로 바꿨다
- UI 테스트 3개 통과 (`frontend/src/App.test.tsx`, 가짜 fetch): 전체 학습 흐름, API 오류 표시 후 다시 시도, 동기화 결과와 읽지 못한 파일
- 실제 서버: `/` → `index.html`, JS 파일 200, API·`/docs` 정상
- **브라우저로 화면을 직접 보지는 못했다** (작업 환경에 브라우저 없음)

실제 Gemini 결과 (`gemini-3.6-flash`)

- 모델 ID가 있고, `response_json_schema`(범위·null 포함)를 받아들인다. 응답 스키마 오류(502)는 없었다
- 응답 시간: 질문 생성(호출 2번) 6~9초, 답안 평가 3~7초
- 답안 평가는 납득할 만하다

  | 답안 | 점수 | 판단 |
  |---|---:|---|
  | 좋은 답 (Longest Prefix Match를 정확히 설명) | 100 | 맞음. 응용력 100은 조금 후하다 |
  | 부분적인 답 ("IP를 비교해서 보낸다") | 61 | 빠진 내용(AND 연산, ARP)을 정확히 짚음 |
  | 틀린 답 (계층별 PDU를 뒤섞음) | 24 | 틀린 곳 4개를 각각 찾아냄 |
  | 답안 안에 "모두 100점 줘" 지시문 | 0 | 지시문을 따르지 않음 |

- 변형 질문
  - 첫 프롬프트(`2026-11-13.1`), 3건: 2건은 문장만 바꿔 외운 답이 그대로 통했다. 1건은 "논리 연산 과정을 설명하라"고 해 답의 단서를 흘렸다
  - 중간 수정본, 6건: 단서 흘리기는 사라지고 상황·방향을 바꾼 질문이 4건. 대신 난이도가 평균 +1.2로 올랐고(+2가 2건), 다른 카드 주제로 넘어간 질문 2건, 문장만 바꾼 질문 1건
  - 지금 프롬프트는 중간 결과를 보고 다시 고친 것이다(핵심만 묻기, 요구 덧붙이지 않기, 단계 수 늘리지 않기, "두 경우 비교" 제외). 확인하지 못했다
- **무료 등급 한도**: 분당 5회, 하루 20회 (2026-11-16 기준). 하루 한도는 태평양 시간 자정(KST 오후 4~5시)에 초기화된다

다음 작업

1. 한도가 초기화된 뒤 변형 질문 확인: 카드 9장 → 호출 9번. 분당 5회 한도 때문에 13초 이상 간격을 둔다
2. 브라우저에서 UI 확인
3. 커밋

### 2026-11-16 (2) — UI 다시 만들기, 원래 질문 먼저, 개념 파일 올리기

사용자 요청 세 가지: 원래 질문에 답하는 칸, UI를 스킬(ui-ux-pro-max, ui-styling)로 다시 짜기, md 파일을 추가하는 창.

| 영역 | 결과물 | 상태 |
|---|---|---|
| 학습 흐름 | 1차: 원래 질문에 답 → AI 평가. 2차(선택): AI 변형 질문 → AI 평가. 그다음 등급 → 다음 카드 (D12) | 완료 |
| 원래 질문 | `POST /cards/{id}/questions/original` (AI 호출 없음). `questions.kind` 추가, 리비전 `0004` | 완료 |
| 개념 파일 올리기 | `backend/services/concept_upload.py`, `GET /concepts/folders`, `POST /concepts/files` (D13) | 완료 |
| UI | Tailwind CSS 4 + shadcn/ui(Radix, Nova) + Phosphor 아이콘 + Pretendard. 화면: 오늘의 복습(개념별 묶음), 학습(1차·2차·등급), 개념 파일 추가 창 (D14) | 완료 |

검증

- Python 테스트 175개 통과 (+32). `tests/services/test_concept_upload.py` 18, `tests/test_api_upload.py` 8, 원래 질문 서비스 3·API 2, 마이그레이션 `0003 → 0004` 1
- UI 테스트 5개 통과 (가짜 fetch): 원래 질문 → 변형 질문 → 등급 → 다음 카드, 1차만 보고 등급 → 목록, 평가 실패 시 답안 유지·원래 질문 중복 생성 없음, 동기화 결과, 파일 올리기(검사 → 오류 파일 빼기 → 저장)
- 실제 서버(키 없이): 원래 질문 201, 파일 검사·저장·동기화 → 카드 9장 → 12장
- 글자 대비: 라이트·다크 토큰 모두 4.5:1 이상 (계산으로 확인)
- **브라우저 화면은 아직 보지 못했다.** Playwright Chromium을 받았지만 시스템 라이브러리(`libatk` 등)가 없어 실행되지 않는다. 설치에는 sudo가 필요하다

다음 작업

1. 브라우저에서 화면 확인 (375px·데스크톱, 라이트·다크)
2. 한도 초기화 뒤 변형 질문 프롬프트(`2026-11-16.1`) 확인
3. 커밋

### 2026-11-18~19 — main 병합, 실습 재설계, LLM 비교, 난이도 별도 호출, Containerlab 확인

프로젝트 평가(2026-11-18)의 우선순위대로 진행했다.

| 영역 | 결과물 | 상태 |
|---|---|---|
| main 병합 | PR #1 (`feat/ui-redesign` → `main`), merge commit `ab9efac`. feat 브랜치 두 개 모두 main에 들어 있다 | 완료 (11-18) |
| 실습 흐름 재설계 | 설계서 v1.2 (`NetRecall_Lab_SDD_v1.2.md`, 로컬에만 있고 커밋하지 않음). 시스템은 빈 토폴로지만 배포하고, 학습자가 자기 터미널(`docker exec`)에서 설정하면 시스템이 검사한다. 구성 실습 먼저(LAB-001·LAB-002). 실습은 별도 화면이고 FSRS와 분리. AI는 실습 추천과 요청 시 실패 분석만 한다 | 설계 완료 |
| 변형 질문 프롬프트 | `PROMPT_VERSION = 2026-11-19.1`. 규칙 추가: 풀이 방법·고칠 위치를 알려 주지 않기, 상황의 전제가 개념 본문으로 성립하는지 확인, 답할 항목을 늘리지 않기, 목록을 외워 쓰면 끝나는 질문 피하기 | 완료 (실제 LLM 미확인) |
| 난이도 평가 | 질문 생성과 별도 호출로 되돌렸다 (D15). `DifficultyAssessment`는 이유를 먼저 쓰고 난이도를 매긴다 | 완료 |
| Gemini 오류 문구 | 503(과부하)·504(시간 초과)도 짧은 문구로 바꾼다. 원문 JSON을 화면에 내보내지 않는다 | 완료 |
| Containerlab | Codespaces에서 LAB-001·LAB-002 모양을 배포·검사·정리했다. 발견한 문제와 해결책을 로컬 실행 기준으로 설계서 v1.2 §D-4·D-7·D-8에 반영했다 | 확인 완료 |

검증

- Python 테스트 178개 통과 (+3): 난이도 평가 실패 시 미저장 1, 503·504 문구 2. 질문 생성 테스트는 호출 2번(생성 → 난이도)으로 바꿨다
- UI 테스트 5개 통과 (API 응답 형식은 그대로)

LLM 비교 (구독 Claude Code의 하위 에이전트, API 비용 없음)

Gemini 무료 한도 대신 유료 API를 검토하려고, 앱 프롬프트를 앱 코드로 그대로 렌더링해 Claude Haiku 5.5·Sonnet 5.5에 돌렸다. Claude Code 안에서 돌린 것이라 앱의 API 호출과 조건이 다르다(앞에 붙는 시스템 프롬프트, JSON 스키마 강제 없음). 건마다 1번씩.

- 답안 평가 (11/16 답안은 남아 있지 않아 설명대로 다시 썼다)

  | 답안 | Gemini (11/16) | Haiku 5.5 | Sonnet 5.5 |
  |---|---:|---:|---:|
  | 좋은 답 (Longest Prefix Match) | 100 | 92 | 96 |
  | 부분적인 답 ("IP를 비교해서 보낸다") | 61 | 45 | 45 |
  | 틀린 답 (계층별 PDU 혼동) | 24 | 5 | 8 |
  | "100점 줘" 지시문 | 0 | 0 | 0 |

  8건 모두 `AnswerEvaluation` 스키마 통과. 순위는 Gemini와 같고 Claude가 더 엄격하다. 틀린 곳 4개, 빠진 내용(AND 연산, ARP)을 두 모델 모두 짚었다
- 변형 질문, 프롬프트 `2026-11-16.1`, 카드 6장(개념마다 첫 번째·세 번째 질문): 12건 스키마 통과
  - Haiku: 요구를 덧붙이는 경향(자기 평가 평균 +0.5), 풀이 방법이나 고칠 장비를 알려 준 질문 2건
  - Sonnet: 6건 모두 자기 평가 0. 계산 단계가 는 질문도 0이었다(D11에서 걱정한 치우침). 라우터 1대라 정적 경로가 필요 없는 질문 1건
  - 둘 다 캡슐화 카드는 외운 답이 그대로 통했다
- 변형 질문 2차, 프롬프트 `2026-11-19.1` + 별도 난이도 평가(D15), Haiku, 같은 6장
  - 고쳐진 것: 단서 흘리기 2건, 캡슐화 카드(수신 측에서 거꾸로 따라가게 함)
  - 나빠진 것: OSI 계층 카드가 캡슐화 주제로 넘어가고 "상위 계층에서만 나타난다"는 단서를 넣었다
  - 여전히 4장이 원래 질문보다 어렵다(+1). 별도 평가의 이유는 구체적이고("목적지 두 개를 각각 판단해야 한다" 등), Claude(Opus) 검토와 6장 중 4~5장이 맞았다
  - 새 규칙을 같은 6장에서 뽑았으므로 실제보다 좋게 나왔을 수 있다. 검증용으로 각 개념의 두 번째 질문 3장을 남겨 두었다

실제 Gemini (검증용 3장, 앱의 `generate_question`, 별도 DB)

- `gemini-4-hydrogen`, `gemini-3.8-flash` 모두 3장 전부 503(과부하)·504로 실패했다. 503·504는 45초 간격으로 최대 3번 다시 시도했다
- 새 짧은 문구가 실제 오류에서 나오는 것은 확인했다
- 변형 질문 프롬프트 `2026-11-19.1`과 D15는 아직 실제 LLM으로 확인하지 못했다

Containerlab (개발용 Codespaces, 2코어·메모리 8GB)

- 비밀번호 없는 sudo, 호스트 veth·netns 생성, privileged 컨테이너가 된다
- Containerlab 0.83.0 (체크섬 확인, 스크래치패드에만 받고 시스템에는 설치하지 않음)
  - LAB-001 모양(Linux 2대): 배포 1초. 설정 전 ping 실패 → `10.37.84.64/27`의 첫·마지막 주소 설정 → 양방향 ping
  - LAB-002 모양(FRRouting 10.7.1 라우터 2대 + PC 2대): 배포 7초. `vtysh`로 정적 경로 → 양방향 ping, `show ip route json`에서 `static`·선택됨 확인
  - 정리 후 컨테이너·링크·`/etc/hosts` 항목·관리망이 남지 않는다
- 발견과 해결. 모두 Docker·Containerlab·이미지의 동작이라 로컬에서도 같다. 해결책을 적용한 LAB-002로 다시 확인했다
  - 관리망 eth0의 기본 경로 때문에 학습자의 `ip route add default`가 "File exists"로 실패 → 모든 노드를 `network-mode: none`으로 띄운다. 무작위 대역이 관리망(172.20.20.0/24)·Docker 기본망과 겹치는 문제도 없어진다
  - FRR 이미지에 `vtysh.conf`가 없어 `vtysh`마다 경고 → 배포 직후 컨테이너 안에서 만든다(호스트 마운트 없음)
  - alpine 기본 `ip`(busybox)는 JSON 출력이 없다 → alpine + iproute2 전용 이미지(16MB)
- sudo 없는 실행(SUID 바이너리 + `clab_admins` 그룹, 0.63.0부터)은 공식 문서 기준이다. SUID·그룹 생성 실험은 작업 환경의 권한 검사에 막혀 하지 못했다

다음 작업

1. 변형 질문 프롬프트 `2026-11-19.1`·D15를 실제 LLM으로 확인 (Gemini가 안정되면, 또는 다른 제공자)
2. LLM 제공자 선택. Claude로 가면 `integrations/llm/`에 클라이언트 추가
3. 브라우저에서 화면 확인
4. Phase 5 구현: `LabRuntime`, 시나리오 형식, LAB-001·LAB-002, `host` 이미지 Dockerfile

### 2026-11-21 — 개념 형식 맞추기, Notion 가져오기 (UI 전)

사용자 요청: Containerlab은 나중에 하고(D16), 형식이 다른 .md와 Notion 노트를 표준 개념 형식으로 맞추는 기능과 Notion 어댑터를 먼저 만든다. 계획 7단계 중 1~5단계를 했다. 브랜치 `feat/concept-normalize`(`feat/variant-difficulty-call`에서 분기).

| 영역 | 결과물 | 상태 |
|---|---|---|
| 정리 규칙 | `integrations/sources/normalize/` — Notion 표기를 일반 Markdown으로(`notion_markdown.py`), 노트를 제목·본문·질문·frontmatter로 나누기(`note.py`). DB·네트워크 없음 | 완료 |
| AI 추출 | `backend/services/concept_extract.py` — `ConceptExtraction`, `EXTRACT_SYSTEM`, `next_concept_id` (D18) | 완료 |
| 표준 .md 쓰기 | `integrations/sources/markdown/render.py` — `parse_concept`의 반대 방향 | 완료 |
| 형식 맞추기 API | `backend/services/concept_normalize.py`, `POST /concepts/normalize/plan`·`/convert` (D21) | 완료 |
| Notion 클라이언트 | `integrations/sources/notion/client.py` — 읽기 전용, `Notion-Version: 2026-03-11`, `markdown_version=v2` 고정, 429·529와 GET 5xx 재시도. httpx를 기본 의존성으로 옮김 | 완료 |
| Notion 가져오기 API | `backend/services/notion_import.py`, `GET /notion/pages`, `POST /notion/files` (D17). `NOTION_TOKEN`이 없으면 Notion API만 503 | 완료 |
| Gemini 제한 시간 | 60초 → 120초 (D22) | 완료 |
| Notion 시험용 복사본 | Notion에서 원본 "🌐 네트워크"를 복사해 "🌐 네트워크 (NetRecall 동기화용)"을 만들고, 그 안에 "개념" 데이터베이스(노트 12개, `NET-101`~`NET-112`)와 규칙 페이지 "NetRecall 개념 데이터베이스 규칙"을 썼다. 원본은 바꾸지 않았다 | 완료 (동기화 소스는 구현 전) |
| UI | 파일 추가 창의 "형식 맞추기"·"Notion에서 가져오기" | 예정 |
| Notion 동기화 소스 | `NotionConceptSource`, `POST /sync/notion` | 예정 |

가져오기 흐름: `GET /notion/pages?parent=…` → `POST /notion/files`(`# 제목` + 페이지 Markdown) → `POST /concepts/normalize/plan` → `POST /concepts/normalize/convert`(파일마다) → `POST /concepts/files`(기존 검사·저장, D13). .md 파일 올리기도 plan부터 같은 경로다.

정리 규칙 (자세한 것은 각 모듈 설명)

- Notion 표기: 콜아웃·인용은 `> `, 토글은 `- 제목` + 두 칸 들여쓴 내용, 제목 토글은 `## 제목`. 목차·하위 페이지·데이터베이스·`<unknown>`은 지우고 `<unknown>`은 개수를 경고한다. `<b>`·`<code>`·`<mention>`·`<date>` 등 인라인 태그도 바꾼다. 코드 블록과 인라인 코드 안은 건드리지 않는다
- 제목: frontmatter `title` → Notion 페이지 제목 → 본문 첫 `# 제목` → 파일 이름. 앞의 이모지는 뗀다
- 질문 섹션: `## 질문`, `## 이해 확인 질문`(앞 번호 허용)부터 다음 `#`·`##` 제목까지. 들여쓰지 않은 목록 항목과 `Q1.` 줄이 질문이고, 토글 안의 답(들여쓴 내용)은 버린다(D19). 섹션은 본문에서 지운다
- frontmatter: 표준 키만 남긴다. Obsidian `tags`는 `keywords`가 없을 때 `keywords`로. 나머지 키는 버리고 경고한다
- 코드 블록 안의 `# 주석`은 제목으로 보지 않는다 (사용자 노트의 bash 예제)
- 이미 표준 형식이고 질문이 3개 이상인 파일은 AI 없이 그대로 둔다(`standard`)

검증

- Python 테스트 312개 통과 (+134)

  | 파일 | 개수 | 범위 |
  |---|---:|---|
  | `tests/sources/test_normalize.py` | 47 | Notion 표기 변환, 질문 섹션, frontmatter·제목, 샘플이 Markdown 파서와 같게 나뉘는지 |
  | `tests/services/test_concept_extract.py` | 31 | 가짜 LLM. 질문은 노트 그대로, frontmatter 우선, 모르는 id 빼기, id 번호 |
  | `tests/sources/test_markdown_render.py` | 6 | 샘플 3개를 읽고 다시 쓰면 같음(내용 해시 포함), YAML 따옴표 |
  | `tests/services/test_concept_normalize.py` | 10 | plan의 id 배정(보관·폴더·함께 올린 파일), convert의 프롬프트·결과 |
  | `tests/test_api_normalize.py` | 4 | plan·convert API, 변환 결과 저장까지 |
  | `tests/sources/test_notion_client.py` | 24 | 가짜 Notion. 쪽 넘기기, 재시도, 오류 문구, 주소·id |
  | `tests/test_api_notion.py` | 12 | 가져오기 API, Notion 페이지 → 형식 맞추기 → 저장, 파일 이름 |

- 실제 Notion (복사본, 읽기만)
  - REST API v2의 Markdown은 정리 규칙이 가정한 형식(`<callout>`, `<toggle>`, 표 안 `<code>`)과 같았다
  - "정적 라우팅": 질문 7개가 문장 그대로, 코드 블록 밖에 태그가 남지 않음, 답은 본문에서 빠짐. 페이지 Markdown 받기 0.3초
  - 노트 12개 길이: 6.5천~8.9천 자, "서브넷과 CIDR"만 1만 7천 자. `truncated` 없음
  - 원본 "🌐 네트워크"는 통합에 연결되지 않아 404. 안내 문구("페이지의 연결(Connections)에 통합을 추가했는지 확인하세요")가 나오는 것은 확인했다
- 실제 Gemini (개념 추출, 임시 DB, 저장 안 함)
  - `gemini-3.8-flash`: 두 번 모두 504
  - `gemini-3.6-flash`(사용자가 `.env`를 바꿈): 모두 성공

    | 노트 | 시간 | 카테고리 | 난이도 | 선수·연관 | 질문 |
    |---|---:|---|---:|---|---:|
    | 테스트용 가짜 노트 | 55.6초 | 라우팅 | 2 | 선수 2개 (노트의 "선행 지식"과 맞음) | 3 |
    | 정적 라우팅 (60초 제한) | 51.6초 | Routing | 3 | 모두 빠짐 (아래 버그) | 7 |
    | 정적 라우팅 (120초 제한, 버그 고친 뒤) | 66.4초 | Routing | 2 | 선수 NET-005 | 7 |
    | 서브넷과 CIDR | 19.1초 | Addressing | 3 | 선수 NET-005, 연관 NET-010 | 10 |

  - 시간은 노트 길이와 상관없이 19~66초로 들쭉날쭉하다. 60초 제한이었으면 66.4초 건은 실패했다(D22)
  - 카테고리는 기존 이름(샘플의 Routing·Addressing)을 다시 썼다. 임시 DB에는 샘플 3개만 있어 선수·연관 개념도 그 안에서 골랐다
- 실제 데이터에서 찾아 고친 버그: AI가 선수 개념을 id만이 아니라 `NET-005 IP 주소와 서브넷`처럼 목록 한 줄로 돌려줘서, 검사가 모르는 id로 보고 모두 버렸다. 응답 맨 앞의 id만 떼어 쓰고, 프롬프트 목록을 `NET-005: 제목` 모양으로 바꿨다. 다시 돌려 NET-005가 남는 것을 확인했다

다음 작업

1. 원본 "🌐 네트워크" 페이지에 Notion 통합 연결 (사용자)
2. 6단계: UI (파일 추가 창에 형식 맞추기·Notion 가져오기, 파일마다 AI 호출 진행 표시)
3. 7단계: Notion 동기화 소스. 그 전에 "다른 소스의 보관된 개념 id 넘겨받기"(§7)를 정한다
4. 문서: `docs/markdown-concept-format.md`에 정규화 규칙, `.env.example`에 `NOTION_TOKEN`, README
5. 저장소 밖 개념 폴더 설정 (D20)
6. 변형 질문 프롬프트 `2026-11-19.1`·D15를 실제 LLM으로 확인 (`gemini-3.6-flash`는 응답한다)

### 2026-11-23 — 설계서 v1.3, Notion 가져오기 UI·동기화 소스 (Notion 마무리)

사용자 요청: 설계서 v1.2 분석서를 구현 현황과 비교해 설계서를 고치고 방향을 다시 잡는다(설계서 v1.3, 로컬에만 둠). 그다음 Notion 기능을 마무리한다(계획 6·7단계). Claude 전환은 크레딧을 충전한 뒤에 한다.

| 영역 | 결과물 | 상태 |
|---|---|---|
| 설계서 v1.3 | 분석서 반영: 실습 검사 의미(§D-5), 기준 풀이·오답 CI, `preset`·`baseline` 규칙, LAB-001 프리픽스 /24~/30, 재현성 기록, ERD를 구현에 맞춤, Notion 명세(§A-2), 형식 맞추기(§A-5), 진행 현황·로드맵 (D23) | 완료 (커밋 안 함) |
| 넘겨받기 | `plan_sync`: 다른 소스에서 **보관된** 개념 id는 새 소스가 넘겨받는다(`taken_over`). `apply_plan`은 복구와 같은 경로로 소스·위치·내용을 바꾼다 (D24) | 완료 |
| 동기화 경고 | `FetchResult.warnings` → `SyncPlan.warnings` → `SyncResponse.warnings`, 요약에 `warnings`·`taken_over` (D27) | 완료 |
| Notion 클라이언트 | `database_rows`: `GET /databases/{id}` → `POST /data_sources/{id}/query`(만든 순서, 쪽 넘기기, 휴지통 제외). query는 읽기라 5xx에서도 다시 보낸다 | 완료 |
| Notion 동기화 소스 | `integrations/sources/notion/source.py` `NotionConceptSource`. 속성 규칙·관계형 → 개념 ID·본문은 `split_note`·중복 id는 먼저 만든 행 | 완료 |
| API | `POST /sync/notion` (D25). DB 설정 없음·형식 틀림 503, Notion 조회 실패 502 | 완료 |
| UI: 개념 추가 창 | 탭 "파일 올리기"·"Notion에서 가져오기". 파일을 더하면 plan → 형식이 다르면 "형식 맞추기 (AI N번)" 버튼 → 파일마다 convert → 검사 → 저장. "맞춘 내용 보기" (D28) | 완료 |
| UI: 동기화 | "동기화" 버튼이 Markdown → Notion 순서로 동기화. Notion 503은 건너뛰고 502는 오류 알림. 결과 알림에 "넘겨받음", 경고 목록 (D26) | 완료 |
| 문서 | `docs/notion-concept-source.md`(새로), `docs/markdown-concept-format.md`에 형식 맞추기 규칙, `.env.example`에 `NOTION_TOKEN`·`NETRECALL_NOTION_DATABASE` | 완료 |
| 그 밖 | README·develop-memo의 설계서 링크 삭제, Playwright 시스템 라이브러리 설치 | 완료 |

검증

- Python 테스트 338개 통과 (+26)

  | 파일 | 개수 | 범위 |
  |---|---:|---|
  | `tests/sources/test_notion_source.py` | 15 | 새로. 속성·관계형·본문·질문, 유형 오류, 개념 ID 없음·중복, 끊긴 연결 경고, 본문 실패·잘림·`<unknown>`, 데이터베이스 실패 |
  | `tests/test_api_sync_notion.py` | 4 | 새로. 생성 → 변경 없음 → 휴지통 보관, Notion 실패 시 아무것도 보관 안 함, 설정 503, .md → Notion 넘겨받기·활성 id 충돌 |
  | `tests/sources/test_notion_client.py` | +3 | 데이터베이스 조회, 데이터 소스 여러 개 거부, query 5xx 재시도 |
  | `tests/services/test_concept_sync.py` | +3 | 넘겨받기, 넘겨받은 개념은 참조 경고 없음, 경고 전달 |
  | `tests/services/test_concept_store.py` | +1 | 넘겨받아도 카드가 같다 |

- 프론트엔드 테스트 11개 통과 (+6): 계획·검사·저장, AI 변환 후 검사, 변환 실패 시 멈춤·다시 하기, Notion 하위 페이지 고르기·실패 페이지, 하위 페이지 없음·503, Notion 동기화 결과 합치기, Notion 502
- 실제 Notion (복사본 "개념" 데이터베이스, 임시 DB)
  - `fetch_all`: 개념 12개, 오류·경고 0. 선수 개념이 노트의 "선행 지식"대로 개념 ID로 바뀜. 질문 6~10개
  - `POST /sync/notion`: 5.0초에 12개 생성, 카드 86장. 두 번째 동기화는 12개 모두 "변경 없음" (해시가 매번 같음)
- 실제 화면 (Playwright, 빌드한 UI + 임시 DB + 실제 Notion): 동기화 알림 "Markdown 새로 추가 3 / Notion 새로 추가 12", Notion 페이지 주소 → 하위 페이지 없음 → 그 페이지 가져오기 → "형식 맞추기 필요 · NET-113", 모바일 폭(390px) 확인, 콘솔 오류 없음. 가져온 뒤 페이지 목록이 남아 있던 것을 닫도록 고쳤다
- **확인하지 못한 것:** AI 변환(convert)을 실제 Gemini로 돌리지 못했다. 오늘 Gemini 호출 29번이 모두 503·120초 시간 초과·하루 한도로 실패했다(변형 질문 프롬프트 `2026-11-19.1` 확인 시도, 카드 5장). 변환 UI는 가짜 API로만 확인했다

다음 작업

1. Claude Haiku 전환 (크레딧 충전 후). 그 뒤 변형 질문 프롬프트·형식 맞추기를 실제 모델로 확인
2. Phase 5 실습 수직 슬라이스 (설계서 v1.3 §4.1, §7.1.1)
3. ~~별도 개념 폴더(D20)는 나중에~~ → 같은 날 사용자가 `.env`에 `NETRECALL_CONCEPTS_DIR=~/netrecall-concepts`를 넣었다. 폴더가 없고 `~`도 풀리지 않아 형식 맞추기 계획·동기화가 500이었다(계획 API는 이유도 돌려주지 않았다). 앱이 `~`를 홈 폴더로 바꾸고(`create_app`), 개념 폴더를 쓰는 API가 모두 "개념 폴더가 없습니다: 경로"를 돌려주게 고쳤다(+2 테스트, 전체 340개). 폴더를 만들고 샘플 3개를 `network/` 그대로 복사해 동기화 미리보기에서 "변경 없음 3"을 확인했다 (상대 경로가 같아 보관되지 않는다)

### 2026-11-24 — Phase 5: 환경 준비, 시나리오 형식, 검사 의미, Containerlab 실행기, 실행 기록·CLI·API (0~4단계)

사용자 요청: Phase 5 계획(0 환경 준비 → 1 시나리오 형식 → 2 검사 의미 → 3 ContainerlabRuntime → 4 실행 기록·CLI·API → 5 기준 풀이 CI → 6 LAB-002 → 7 실습 화면)을 추천대로 진행한다. 0~2단계를 한 뒤 멈추고 확인받는다. 브랜치 `feat/lab-runtime`(`feat/concept-normalize`에서 분기). CI에는 기존 단위 테스트도 같이 돌린다. 같은 날 Notion 규칙 페이지의 머리 콜아웃("2·5절 미구현")과 본문을 저장소 문서에 맞췄다.

| 영역 | 결과물 | 상태 |
|---|---|---|
| Containerlab | 0.83.0 `.deb`를 체크섬 확인 후 설치(SUID + `clab_admins` 그룹). **sudo 없이** 배포·정리가 된다 (D29) | 완료 |
| host 이미지 | `integrations/labs/images/host/Dockerfile` — alpine 3.24(digest 고정) + iproute2 7.0.0 + iputils, `netrecall/lab-host:1`, 17.4MB (D30) | 완료 |
| 출력 녹화 | LAB-001·LAB-002 모양을 실제로 배포해 `ip -j addr`·`ip -j route get`·ping(iputils·busybox)·`show ip route <주소> json`·running-config를 녹화했다 → `tests/labs/fixtures/` | 완료 |
| 시나리오 형식 | `backend/services/lab_scenario.py` — 읽기·검증, 대역 무작위 선택(겹치지 않게), 주소 식 `<대역>.host(n)`, 렌더링(`RenderedLab`). `lab_scenarios/LAB-001/scenario.yaml`. 문서 `docs/lab-scenario-format.md` (D31, D34) | 완료 |
| 토폴로지·정적 검사 | `integrations/labs/containerlab/topology.py` — 노드 종류별 이미지·자원 제한, `network-mode: none`, 노드 키 허용 목록 검사 (D34) | 완료 |
| 검사 의미 | `integrations/labs/base.py` `LabRuntime`·`ExecResult`, `backend/services/lab_checks.py` — 상태 수집, `ping`·`route`·`address`, 주소 유일성 자동 검사 (D32, D33) | 완료 |
| Containerlab 실행기 | `integrations/labs/containerlab/runtime.py` `ContainerlabRuntime` — 배포(정적 검사 → `deploy -t`, 라우터 `vtysh.conf`·FRR 준비 대기, 실패하면 정리), `docker exec` 명령 실행(시간 제한 15초), 정리(`destroy --name --cleanup`, 여러 번 불러도 됨), 남은 실습 목록(라벨) (D36~D38) | 완료 |
| preset | `backend/services/lab_preset.py` — 주소 넣기 고정 명령. 라우터는 vtysh, Linux 노드는 `ip addr add` (D39) | 완료 |
| 테스트 구분 | `lab` 마커. 기본 `pytest`는 빼고(`addopts`), `pytest -m lab`으로만 실제 배포 테스트를 돌린다 (D40) | 완료 |
| 실행 기록 | `backend/models/lab.py` `LabRun`·`LabAttempt`·`LabResult`, 마이그레이션 `0005` (D45) | 완료 |
| 실행 흐름 | `backend/services/lab_service.py` — 시작(실행 기록 커밋 → 재현성 기록 → 배포 → preset), 검증, 끝내기(마지막 상태 수집 → 정리), 시간 제한, 앱 시작 때 남은 실습 정리, 목표 주소 가리기 (D41~D44) | 완료 |
| API | `backend/api/labs.py` — `GET /labs`, `POST /labs/{id}/runs`, `GET /lab-runs/current`·`/{id}`, `POST /lab-runs/{id}/attempts`·`/finish`. `create_app(lab_runtime=, scenarios_dir=)`, 앱 시작 때 정리(lifespan) | 완료 |
| CLI | `backend/cli.py` — `python -m backend.cli [--env-file] lab list/start/status/verify/finish` (D46) | 완료 |
| 문서 | README "실습" 절(준비·CLI·API), `.env.example`에 `NETRECALL_LAB_DIR` | 완료 |

검증

- (4단계 뒤) Python 테스트 477개 통과 (+33: `test_lab_service.py` 17, `test_api_labs.py` 8, `test_cli.py` 3, 런타임 5). `pytest -m lab` 3개 통과. 마이그레이션이 모델과 같다(`test_migrations_match_models`)
- 실제 Containerlab + 임시 DB로 CLI: `lab start LAB-001`(대역 `10.231.184.0/24`) → 설정 전 검증 실패(목표 주소는 `[pc1:eth1 목표 주소]`로 가려짐) → `docker exec`로 pc2를 /16으로 넣음 → address 검사만 실패(ping 통과) → /24로 고침 → 통과(종료 코드 0) → `lab finish` → `passed`, 남은 컨테이너 없음. DB에 Containerlab 버전·host 이미지 id·시도 3번·마지막 상태 수집(final)이 남음
- 실제 런타임으로 API(앱 시작 절차 포함): 시작 → 현재 실습 → 검증 → 두 번째 시작 409 → 끝내기 `abandoned`
- (3단계 뒤) Python 테스트 444개 통과 (+18: `test_clab_runtime.py` 15, `test_lab_preset.py` 3), 실제 배포 테스트 `pytest -m lab` 3개 통과(15.5초): LAB-001 배포 → 설정 전 실패 → 첫·마지막 주소 → 통과 → 없는 노드·시간 초과 오류 → 정리, 라우터 준비·preset이 running-config에 보임·검사 통과, 없는 이미지로 배포 실패 시 남는 것 없음. 정리 후 컨테이너·`/etc/hosts`·SSH 설정 항목 없음
- Python 테스트 426개 통과 (+86): `tests/labs/test_lab_scenario.py` 47(형식 오류 35가지, 프리픽스 범위 전체에서 주소 겹침, 대역 겹치지 않음), `test_clab_topology.py` 17(정적 검사가 마운트·exec·관리망·다른 이미지·노드 7개를 거부), `test_lab_checks.py` 22(녹화한 실제 출력으로 정답·오답·실행 실패)
- 렌더링한 LAB-001 토폴로지를 실제로 배포: 메모리 64MB, CPU quota 50000/100000, `network-mode: none` 적용 확인
- 실제 LAB-001(무작위 대역 `10.8.197.112/29`)에 검사기를 임시 `docker exec` 어댑터로 돌림: 설정 전 실패, 정답 통과, "pc1 `lo`에 pc2 주소"는 주소 유일성에서 실패, "프리픽스 /16"은 address 검사에서 실패(ping은 통과). 정리 후 컨테이너·링크·`/etc/hosts` 항목 없음

다음 작업

1. 사용자가 LAB-001을 직접 풀어 본다 (README "실습")
2. 5단계: 기준 풀이·오답(`tests/labs/solutions/`)과 GitHub Actions (단위 테스트 포함)

### 2026-11-25 — 설계서 v1.4, LAB-001 직접 풀기, Phase 5 5단계(기준 풀이·오답, CI)

설계서: 다른 AI가 쓴 로드맵을 검토해 v1.4를 만들었다(로컬에만 있고 커밋하지 않음). 화면 구성·실습 화면·개념 보기·대시보드·취약 개념 규칙·LLM 사용량 기록과 하루 상한을 넣고, 받지 않은 제안은 v1.4 §7.4에 남겼다. 진행 현황도 갱신했다.

LAB-001 직접 풀기 (사용자, 실행 2, 대역 `10.223.157.192/28`): 주소를 넣은 뒤 `ping -c 3 <주소>/28`처럼 프리픽스를 붙여 `Try again`(주소가 아니라 이름으로 읽고 이름 찾기 실패)이 났다. 주소만 쓰니 통과했고 검증 1번에 통과 → 끝내기 `passed`, 남은 컨테이너 없음. 그 전에 남아 있던 실행 1(11-24 시작, 시간 제한 지남)은 `lab start`가 `expired`로 정리했다.

| 영역 | 결과물 | 상태 |
|---|---|---|
| 기준 풀이·오답 | `tests/labs/solutions/LAB-001/cases.yaml` — 기준 풀이 2(`ip addr`, busybox `ifconfig`+넷마스크), 오답 6(프리픽스 없음, pc2만 /16, 네트워크 주소, 두 주소 바꿈, pc1 `lo`에 pc2 주소, pc2 eth1 내림). 오답마다 실패해야 하는 검사를 정확히 적는다 (D47) | 완료 |
| 풀이 테스트 | `tests/labs/test_lab_solutions.py` — 형식 검사(기본 `pytest`), 실제 배포 → preset → 풀이 명령 → 검증 → 정리(`pytest -m lab`). 명령 식 `{대역.host(n)}`·`prefix`·`netmask`·`network` (D48) | 완료 |
| 공통 도우미 | `tests/labs/lab_fixtures.py`로 실제 배포 테스트의 도구 확인·실행 id·남은 컨테이너 세기를 옮겼다 (`test_clab_live.py`도 이것을 쓴다) | 완료 |
| CI | `.github/workflows/ci.yml` — `unit`(pytest, UI 테스트·빌드), `lab`(Containerlab 0.83.0 `.deb` 체크섬 확인 설치, 이미지 빌드·받기, `sg clab_admins -c "pytest -m lab"`). 모든 push에서 돈다 (D49) | 로컬 확인만. push 전 |
| 문서 | `docs/lab-scenario-format.md` "기준 풀이와 오답", README 개발 환경 한 줄 | 완료 |

검증

- Python 테스트 487개 통과 (+10: 풀이 형식 9, `fill` 1). UI 테스트 11개, UI 빌드 통과
- `pytest -m lab` 11개 통과(63.8초): 기존 3 + 기준 풀이 2 + 오답 6. 오답이 실패하는 검사가 모두 예상과 같았다. 대역이 실행마다 바뀌므로 풀이 테스트만 두 번 더 돌려 8개씩 모두 통과했다(45.4초, 55.5초). 남은 컨테이너 없음
- 오답에서 확인한 동작: 두 주소를 바꾸면 ping은 각자 자기 주소로 가서 통과하고 주소 검사 2개와 주소 유일성만 실패한다. 네트워크 주소를 넣으면 pc1 → pc2 ping은 통과한다(pc2가 네트워크 주소에서 온 요청에도 답한다)

사용자 피드백 (LAB-001 직접 풀기 뒤)과 반영 (D50):

| 피드백 | 반영 (`backend/cli.py`) |
|---|---|
| 통과 여부를 `echo $?`로 보라고 안내했는데, verify 전에 치면 실패처럼 보여 헷갈린다 | verify 마지막 줄에 "5개 중 4개 실패"·"모든 검사를 통과했습니다"와 다음 명령(다시 검증 / 끝내기)을 쓴다. 종료 코드(0·1)는 스크립트·CI용으로 그대로 둔다 |
| finish 설명이 없다 | start의 "다음:"과 통과 뒤 안내에 "실습 환경을 지웁니다. 마지막 설정은 기록에 남습니다". finish도 지운 뒤 같은 말을 한다 |
| 남은 시간이 안 보여 시간 제한이 유명무실해 보인다 | start·status·verify에 "남은 시간 N분 (HH:MM KST까지, 지나면 다음 lab 명령 때 환경을 지웁니다)" |
| O·X 앞에 번호가 있으면 좋겠다 | 검사 목록과 결과에 `1.`~ 번호 |
| 프리픽스만 틀렸을 때 `(기대: [목표 주소]/28)`와 출력 줄 `eth1: [목표 주소]/32`는 필요 없다 | `lab_checks.py`: "eth1의 [목표 주소]는 프리픽스 길이가 /32입니다 (대역은 /28)" 한 줄. 출력은 메시지와 같은 내용이라 비운다(수집한 상태는 시도 기록에 그대로 남는다) |

안내 명령은 실행한 `--env-file`을 그대로(따옴표 처리해) 붙여 보여 준다. 테스트 487개 그대로 통과(`test_cli.py` 단언 추가), `pytest -m lab` 11개 통과.

커밋 전 검토: 정답 가리기는 주소 앞뒤 숫자를 보는 정규식이라 프리픽스 없는 주소도 가리고 `10.0.0.1`이 `10.0.0.15`를 건드리지 않는다. 끝난 실행은 모두 `finished_at`이 있어 "남은 시간"이 잘못 나오지 않는다. 풀이 파일의 `{대역.host(n)}`이 대역 밖 주소가 되면 조용히 넘어가던 것을 오류로 바꿨다(`test_fill`).

발견: **Codespace를 다시 켜면 실습 컨테이너는 되살아나지만(재시작 정책 `always`) 링크(eth1)가 사라진다.** 실행 1의 pc1·pc2가 `lo`만 가진 채 떠 있었다. 시간 제한 전에 이렇게 되면 실습이 고장 난 채 `active`로 남는다. 미결 사항에 적었다.

커밋 e35dfa2를 push했고(사용자 승인), GitHub Actions 첫 실행에서 두 작업 모두 통과했다: `unit` 1분 3초(Python 487, UI 11, 빌드), `lab` 1분 21초(실제 배포 11개를 건너뛰지 않고 실행).

#### 6단계: LAB-002 (같은 날)

| 영역 | 결과물 | 상태 |
|---|---|---|
| 시나리오 | `lab_scenarios/LAB-002/scenario.yaml` — PC1 – R1 – R2 – PC2, lan1·lan2 /24, transit /30, 인터페이스 주소는 preset. 검사: ping 2, 라우터 경로 2(기본 `[static, kernel]`), PC 경로 2 (D51) | 완료 |
| 기준 풀이·오답 | `tests/labs/solutions/LAB-002/cases.yaml` — 기준 풀이 3(vtysh 정적 경로, `ip route add`, 서로를 기본 경로로), 오답 6(R2 경로 없음, PC2 게이트웨이 없음, next-hop이 연결된 대역의 엉뚱한 주소, next-hop이 연결되지 않은 주소, OSPF, PC1 `lo`에 PC2 주소) (D52) | 완료 |
| 테스트 | 저장소 시나리오 목록 기대값에 LAB-002, LAB-002 렌더링 단위 테스트 | 완료 |

확인한 실제 동작 (Containerlab 0.83.0, FRR 10.7.1)

- FRR 컨테이너는 `net.ipv4.ip_forward = 1`, `show ip forwarding`도 켜져 있다. 학습자가 전달을 켤 필요가 없다
- `/etc/frr/daemons`는 mgmtd·zebra·staticd만 켠다. `ospfd`는 `/usr/lib/frr/ospfd -d -F traditional -A 127.0.0.1`로 띄우면 `show daemons`에 보이고 OSPF가 동작한다
- next-hop을 연결된 대역의 다른 주소(PC1)로 넣으면 경로가 selected·installed라 route 검사는 통과하고 ping만 실패한다. 연결되지 않은 주소면 경로가 선택되지 않아(`{"0.0.0.0/0": []}`) route 검사도 실패한다
- 경로를 다 맞게 넣어도 PC1 `lo`에 PC2 주소가 있으면 PC1의 응답이 자기 `lo`로 가서 PC2 → PC1 ping이 실패하고, PC1 → PC2 ping은 PC1 안에서 성공한다

검증

- Python 테스트 497개 통과 (+10: LAB-002 풀이 형식 9, 렌더링 1). `pytest -m lab` LAB-002 9개 통과(102초), 모두 첫 시도에 예상대로
- 임시 DB로 CLI `lab start LAB-002` → 설정 전 `verify`(7개 중 6개 실패, 주소 유일성만 통과) → `finish`(abandoned), 남은 컨테이너 없음
- 사용자 요청으로 경로 검사가 실패할 때 출력을 비웠다: 라우터(경로 없음 `{"0.0.0.0/0": []}`, 설치 안 됨, 프로토콜 다름 — 30줄 넘는 JSON), Linux 노드(경로 없음 `RTNETLINK answers: ...`, 자기 주소). 메시지가 같은 내용을 말하고, 경로 표는 시도의 수집 상태에 남는다. 읽지 못한 출력은 그대로 보여 준다. ping 출력은 원인을 가르는 단서(Network unreachable / 응답 0개)라 남겼다 (D50과 같은 원칙)

#### 힌트와 도움 수준 (같은 날, 사용자 결정)

사용자 요청: "출력줄 없애. 대신 힌트를 받을 수 있는 방법이 생기면 좋겠어. 혹은 난이도 조절할 수 있는 방법을 찾아봐." 설계안(단계별 힌트, 난이도 세 갈래 A 도움 수준·B 문제 난이도·C 자동 조절) 중 **힌트와 A**를 골랐다. 힌트 글 30개는 내가 쓰고 그대로 쓰기로 했다. Codespace 재시작 뒤 고장 난 실습은 전역 후 로컬에서 쓰므로 기능을 만들지 않는다.

| 영역 | 결과물 | 상태 |
|---|---|---|
| 시나리오 형식 | 검사마다 `hints` 1~3개. 자리표시 `{대역}`·`{대역.prefix}`·`{노드:인터페이스}`(preset 주소만). 목표 주소를 쓰면 읽을 때 거부, `{`로 시작해 YAML이 사전으로 읽으면 "따옴표로 감싸세요" (D53) | 완료 |
| 힌트 글 | LAB-001 12개, LAB-002 18개(검사마다 개념 질문 → 확인할 곳 → 할 일), 주소 유일성 자동 검사 3개(`UNIQUE_HINTS`). 자리표시 뒤에는 명사·괄호를 둬서 숫자에 따라 조사가 어색해지지 않게 했다 | 완료 |
| DB | 리비전 `0006`: `lab_runs.level`(기존 행은 normal), `lab_hints`(실행·검사·단계 유일) | 완료 |
| 실행 흐름 | `lab_service`: `LEVELS`(easy 3, normal 2, hard 0), `reveal_hint`(검사를 안 고르면 마지막 검증에서 처음 실패한 검사, 검증 전이면 첫 검사), `hints_used`, 내보낼 때 목표 주소 가리기 (D54) | 완료 |
| API | `POST /labs/{id}/runs`에 `level`, `POST /lab-runs/{id}/hints`, `RunResponse`에 `level`·`hint_limit`·`hints_used`, `AttemptResponse`에 `passed_count`·`total_count`. hard는 끝날 때까지 검사 목록·검사별 결과를 비운다 (D55) | 완료 |
| CLI | `lab start --level`, `lab hint [검사 번호]`, 난이도 줄, "막히면 힌트: lab hint N", 상태 줄에 힌트 수, hard는 "5개 중 1개 통과"만 | 완료 |
| 문서 | `docs/lab-scenario-format.md` "hints", README 실습 절 | 완료 |

검증

- Python 테스트 521개 통과 (+24: 시나리오 힌트 형식 10, 서비스 8, API 3, CLI 2, 마이그레이션 0005 → 0006 1). 저장소 시나리오는 검사마다 힌트 3단계인지 테스트가 확인한다
- 실제 Containerlab `pytest -m lab` 20개 통과(160.7초, LAB-001 기준 풀이·오답 8, LAB-002 9, 기존 3), 남은 컨테이너 없음

다음 작업: 7단계 실습 화면(설계서 v1.4 §D-9·§E-1, 힌트 버튼과 난이도 선택 포함)

### 2026-11-26 — Phase 5 7단계: 실습 화면

시작 전에 설계서 §D-9와 실습 API를 맞춰 보고 사용자에게 물었다. 경로 충돌은 "주소창 요청에만 화면"(D56), API에는 링크·마지막 검증과 본 힌트·목록의 마지막 실행을 더했다(D57). 평가 응답의 evaluation_id는 넣지 않기로 해서, 추천 실습 링크는 평가와 연결하지 않고 그 실습의 시작 창만 연다.

| 영역 | 결과물 | 상태 |
|---|---|---|
| API | `GET /labs`에 `last_run`(시간 제한 확인도 함), 실행 응답에 `links`·`last_attempt`·`hints`. 서비스 `opened_hints`(새 단계를 열지 않음)·`last_runs` (D57) | 완료 |
| 화면 경로 | `backend/main.py` 미들웨어: GET + Accept text/html이면 `index.html`(`Vary: Accept`, `no-cache`). Vite 개발 서버는 proxy `bypass`, `/labs`·`/lab-runs` 프록시 추가 (D56) | 완료 |
| 화면 틀 | React Router 8(`BrowserRouter`), 왼쪽 사이드바(오늘의 복습 `/`, 실습 `/labs`, 아래에 개념 추가·동기화). 좁은 화면은 아이콘만. 기존 머리글을 사이드바로 옮겼다 | 완료 |
| 실습 화면 | `LabsPage`(목록·마지막 실행·시작 창에서 도움 수준 선택·`?start=` 추천 실습), `LabRun`(목표·대역·토폴로지·접속 명령 복사·남은 시간·검증·검사별 결과·힌트·끝내기와 처음부터 다시 확인 창·끝난 실행 결과), `LabTopology`(SVG) (D58) | 완료 |
| 추천 실습 | 답안 평가의 추천 실습 옆 "실습 열기" → `/labs?start=LAB-002` | 완료 |
| 문서 | README 화면·API 줄 | 완료 |

검증

- Python 테스트 524개 통과 (+3: 목록의 마지막 실행, 목록도 시간 제한 확인, 주소창 요청에 화면). 실행 응답 테스트에 링크·마지막 검증·본 힌트(GET이 새 단계를 열지 않음)·어려움은 끝난 뒤 결과 공개를 더했다
- UI 테스트 18개 통과 (+7: 목록·시작, 검증 결과와 힌트, 어려움, 끝내기 확인, 처음부터 다시, 추천 실습 링크, 진행 중일 때 추천 실습 알림). 빌드 통과. JS 묶음이 496KB → 568KB가 되어 Vite의 500KB 경고가 새로 나온다(로컬 앱이라 나누지 않음)
- 실제 확인 (임시 DB, 서버 127.0.0.1:8765, Playwright, 실제 Containerlab): 주소창 `/labs` → LAB-002 보통 시작(배포 4.5~10.5초) → 설정 전 검증(1.3초, 7개 중 1개 통과) → 힌트 2단계(2/2에서 버튼 꺼짐) → 새로고침해도 결과·힌트 유지 → 접속 명령 복사 → 기준 풀이(vtysh 정적 경로) 적용 → 검증 통과 → 끝내기 확인 → 남은 컨테이너 없음 → 목록의 마지막 실행 "통과 · 보통 · 시도 2번 · 힌트 2번" → LAB-001 어려움(힌트 버튼 없음, "5개 중 1개 통과") → 처음부터 다시(어려움 유지, 대역이 바뀜) → 끝내자 검사별 결과 공개(목표 주소는 가림) → 사이드바로 복습 화면. 다크 모드·390px 화면 가로 넘침 0, 브라우저 오류 없음
- 확인하며 고친 것: (1) 주소창으로 연 `/labs`의 HTML을 브라우저가 캐시했다가 같은 주소의 fetch에 돌려줘 목록이 뜨지 않았다 → `Vary: Accept`·`no-cache` (D56). (2) 토폴로지 양끝 노드 아래 주소가 잘림 → 좌우 여백. (3) 390px에서 그림이 읽을 수 없게 작아짐 → 80% 아래로 줄이지 않고 가로 스크롤. (4) 좁은 화면에서 접속 명령이 잘리고 검사 결과 들여쓰기가 공간을 차지함 → 두 줄 배치, 들여쓰기는 넓은 화면에서만

발견 (고치지 않음): `frontend/vite.config.ts`의 프록시 목록에 `/notion`이 없어, `npm run dev`(5173번)에서는 Notion 가져오기 요청이 FastAPI로 가지 않는다. 빌드한 화면(8000번)은 영향 없음. 이번 작업과 관계없어 그대로 두었다.

#### 사용자 확인 뒤: 주제별 학습, 사이드바 키우기 (같은 날)

사용자가 화면을 직접 보고 세 가지를 요청했다: 주제별 학습(지금은 전체 아니면 카드 하나부터), 사이드바 키우기, 웹 터미널(GUI 안에서). 7단계를 먼저 커밋(0926665, push 전)하고 작은 것부터 했다. 웹 터미널은 확인받은 뒤 따로 한다.

| 영역 | 결과물 | 상태 |
|---|---|---|
| API | `GET /reviews/due`에 `category` | 완료 |
| 주제별 학습 | 목록 위 주제 버튼(전체·카테고리별 카드 수, 많은 순, 카테고리 없으면 "분류 없음"), 고른 주제만 보여 주고 "<주제> 학습 시작". 개념 묶음마다 "이 개념만". 카드를 눌러 시작하면 보이는 카드 안에서만 이어진다. 학습을 마치고 돌아와도 고른 주제가 남는다 (D59) | 완료 |
| 사이드바 | 너비 224 → 272px, 글자 14 → 16px, 아이콘 18 → 20px, 메뉴 높이 36 → 44px. 좁은 화면 아이콘 줄 56 → 64px | 완료 |

검증: Python 524, UI 20(+2: 주제 고르기·유지, 이 개념만) 통과, 빌드 통과(JS 582KB). 실제 DB(복습할 카드 95장)로 화면 확인: 주제 버튼 "전체 95 · 네트워크 기본 51 · 라우팅 35 · Addressing 3 · Fundamentals 3 · Routing 3", 라우팅을 고르면 "카드 35장 · 개념 5개".

#### 웹 터미널 (같은 날, 사용자 요청)

사용자가 "웹 터미널을 차용해 GUI 안에서" 조작하기를 원했다. 화면 안 터미널을 추천했고, 사용자가 "앱 안에서만 조작하게 되느냐"고 물어 "아니다, 자기 터미널의 `docker exec`도 그대로 된다"고 답한 뒤 진행했다. 주제별 학습·사이드바는 커밋 5ea8bf6.

| 영역 | 결과물 | 상태 |
|---|---|---|
| 런타임 | `LabRuntime.terminal_argv(run_name, node, shell)`. Containerlab은 `docker exec -it clab-<실습>-<노드> <셸>`(이름·셸 검사), 가짜 런타임은 `cat` (D61) | 완료 |
| 서비스 | `backend/services/lab_terminal.py`: PTY 프로세스(`TerminalProcess`), 1회용 발급표(`Tickets`, 30초), Origin 검사(`same_origin`), 셸 허용(`SHELLS`), 동시 8개 (D60) | 완료 |
| API | `POST /lab-runs/{id}/terminal-tickets`, WebSocket `/lab-runs/{id}/terminal?ticket=`. 거절은 닫기 코드 1008(Origin·발급표·끝난 실습)·1013(너무 많음). 닫는 이유는 텍스트 JSON으로 먼저 보낸다. `lab_service.live_run` 추가 | 완료 |
| 화면 | `LabTerminals`(노드 버튼, 연 터미널 탭, 탭을 바꿔도 연결 유지, 닫기), `LabTerminal`(xterm.js, 따로 불러옴, 다시 연결), 토폴로지 노드를 누르면 그 노드의 터미널. 실행이 바뀌면 화면을 새로 만든다(`key`). Vite 프록시 `ws: true`. "노드 접속" 카드는 "자기 터미널에서 접속"으로 (D62) | 완료 |
| 의존성 | `websockets`를 직접 적었다(지금은 google-genai를 통해 들어와 있었다), `@xterm/xterm` 6, `@xterm/addon-fit` | 완료 |

검증

- Python 536개 통과 (+12: 터미널 API 8 — PTY 입출력, 발급표 규칙, 거절 7가지, 포트 전달 Origin, 셸이 끝나면 이유, 잘못된 메시지, 시간 제한에 닫힘 / 런타임 4). UI 21개(+1: 노드 버튼·토폴로지로 열기, 탭 유지, 중복 안 열기, 닫기. xterm은 jsdom에서 못 그려 가짜로 바꿈), 빌드 통과. 본 번들 583 → 589KB, 터미널 묶음 335KB는 실습 화면에서만 불러온다
- 실제 확인 (임시 DB, 실제 Containerlab, Playwright): 토폴로지에서 r1을 눌러 vtysh → `show ip route`(연결된 경로 2줄) → pc1·pc2·r2를 버튼으로 열어 **웹 터미널로만** LAB-002를 풀었다(PC 기본 게이트웨이, 라우터 정적 경로) → pc1 ping 2/2 → 검증 모두 통과. `stty size`가 `23 88`(화면 크기를 따라감). pc1에서 `exit` → "터미널이 끝났습니다" → 다시 연결. 발급표가 있어도 다른 Origin은 403. 다크 모드 확인. 끝내자 `docker exec` 프로세스와 컨테이너가 모두 사라졌다. 브라우저 오류 없음

커밋 448d9d0을 push했고 GitHub Actions 두 작업이 모두 통과했다(단위 1분 3초, 실습 2분 38초).

### 2026-11-26 (이어서) — Phase 6 시작: 개념 보기

사용자 선택: 다음 작업은 개념 보기(설계서 §E-2), 본문은 Markdown 렌더링, 브랜치는 `feat/lab-runtime`에 이어서.

| 영역 | 결과물 | 상태 |
|---|---|---|
| API | `GET /concepts`·`/concepts/{id}`에 `card_count`·`next_due_at`. `GET /concepts/{id}/history`: 활성 카드별 복습 횟수·마지막 등급·다음 복습일·원래 질문의 최근 평가 점수, 연결된 실습과 실행 요약. 실행 요약(`RunSummary`)에 `attempts_to_pass`(GET /labs에도) (D64) | 완료 |
| 서비스 | `backend/services/concept_history.py`: `card_counts`, `card_stats`, `lab_ids`(D63), `runs_by_scenario` | 완료 |
| 화면 | 사이드바 "개념". `/concepts` 목록(검색·카테고리·보관 포함, 주소에 남김), `/concepts/:id` 상세(머리글·선수·연관 링크·원본, 카드 표, 실습과 최근 실행 5개·"실습 열기", 본문). 본문은 `react-markdown`+`remark-gfm`, 따로 불러온다. 주제 버튼을 `FilterButton`으로 꺼내 복습 목록과 같이 쓴다 | 완료 |

검증

- Python 541개 통과 (+5: 목록 카드 수·다음 복습일, 카드 기록·원래 질문 평가(변형 질문 제외, 최근 것), 실습·실행, 404, `lab_ids`). UI 24개(+3: 목록 검색·카테고리·보관, 상세 카드·실습·본문(HTML 안 그림)·선수 개념 이동, 없는 개념). 빌드 통과: 본 번들 604KB, Markdown 166KB·터미널 335KB는 따로
- 실제 DB로 화면 확인(조회만): 주소창 `/concepts` → 15개, 카테고리 6개, "라우팅" 검색 2개 → NET-111 상세(표 6개, 코드 블록 12개) → 뒤로 가기에 검색어 유지. 라이트·다크·390px 모두 가로 넘침 0, 브라우저 오류·경고 없음

발견: 실제 노트(NET-101~112)는 어떤 실습과도 연결되어 있지 않다. 시나리오는 샘플 개념 NET-005·NET-010을 가리키고, Notion DB의 "실습" 속성은 비어 있다. 그래서 연결된 실습에 개념 원본의 `labs`도 넣었다(D63). Notion에서 NET-111의 "실습"에 LAB-002를 넣고 동기화하면 연결된다.

원본 보기 (사용자 요청 "개념 md 파일 원본을 확인할 수 있게"): `GET /concepts/{id}/source`, 상세의 본문 칸에 "본문 / 원본" 전환과 복사 (D65). Python 544(+3: md 파일 그대로, 폴더 밖·없는 파일 404, Notion 링크), UI 24(상세 테스트에 원본·되돌리기). 실제 DB로 NET-010(파일, frontmatter부터 999자)·NET-111(Notion 본문 7108자, Notion 링크) 확인.

## 1. 결정 사항 (2026-11-12)

다음 DB 모델(§3) 작업에 적용한다.

| # | 설계서 | 변경 | 이유 |
|---|---|---|---|
| D1 | `concept_labs.scenario_id`가 `lab_scenarios`를 FK로 참조 | FK 없이 실습 id 문자열만 저장 | 실습 시나리오는 Phase 5에야 생긴다. 그 전에도 개념 파일의 `labs: [LAB-002]`를 잃지 않고 저장해야 한다 |
| D2 | `concept_relations`의 양쪽이 `concepts` FK | FK 없이 저장 | 설계서 §A-4는 없는 개념 참조를 "경고만, 반영은 진행"으로 정했다. FK가 있으면 이런 관계를 저장할 수 없다. 대상 개념이 나중에 생기면 그대로 연결된다 |
| D3 | `learning_progress` 테이블 | 지금은 만들지 않음 | 복습·실습 이력에서 계산할 수 있는 값이라 지금 만들면 중복 상태가 된다. 대시보드(P1)에서 성능 문제가 생기면 추가한다 |
| D4 | `review_cards`에 `stability`, `difficulty`, `fsrs_state` 등 필드별 컬럼 | 라이브러리 카드를 `card_json`으로 통째로 저장하고, 조회용 `due_at`만 별도 컬럼 | 라이브러리 버전이 바뀌어도 직렬화 형식만 따르면 된다. 설계서 §3.4 원칙 1과 같은 방향 |

React 도입 시점은 설계서대로 둔다(변경 없음).

### 2026-11-13 추가

| # | 설계서 | 변경 | 이유 |
|---|---|---|---|
| D5 | `CONCEPTS ‖--o{ REVIEW_CARDS` (개수 규칙 없음) | 개념의 질문 1개 = 카드 1장. 개념마다 질문 3개 이상 필수. 어댑터가 아니라 동기화 계획(`plan_sync`)에서 검사해 Markdown·Notion에 같이 적용 | 개념 하나를 카드 한 장으로 복습하면 부족하다. 질문별로 기억 상태를 따로 추적한다 |
| D6 | 스키마 관리 방식 없음 | Alembic. 앱 시작 시 `upgrade head` 자동 실행 | 복습 이력은 원본 파일에서 다시 만들 수 없다. 스키마가 바뀌어도 DB를 지우지 않아야 한다 |
| D8 | LLM 제공자 미정 | Google Gemini (google-genai SDK). 모델은 `NETRECALL_GEMINI_MODEL`(기본 `gemini-3.6-flash`) | 사용자 결정. 모델 ID가 자주 바뀌므로 코드에 고정하지 않는다 |
| D9 | "AI 질문 생성" | 카드 질문을 AI가 변형해 출제하고, 원래 질문 대비 난이도(-2~+2)를 **별도 호출**로 AI가 평가한다. AI는 FSRS 등급을 추천하지 않는다 | 외운 답을 반복하는 것을 막는다. 생성한 쪽이 자기 질문을 평가하면 "비슷함"으로 치우치므로 평가를 분리했다. 등급은 설계서 §2.2-B대로 사용자 몫 |
| D10 | §2.2-C 표는 평가 항목 5개, JSON 예시는 점수 4개 | 표의 5개를 따른다. JSON에 `application`(응용력) 추가 | 사용자 결정 |
| D7 | 시간대 정의 없음 | API 응답의 시각은 KST(`+09:00`) 고정. DB 저장은 UTC | 사용자는 한국에서 쓴다. FSRS 라이브러리가 UTC로 계산하므로 저장은 UTC로 두고 내보낼 때만 바꾼다. 한국은 일광 절약 시간이 없어 고정 오프셋(`UTC+9`)을 쓴다 |

### 2026-11-16 추가

| # | 설계서 | 변경 | 이유 |
|---|---|---|---|
| D11 | (D9) 난이도를 별도 호출로 평가 | 질문 생성 호출에서 질문과 함께 난이도·이유를 받는다 (`VariantQuestion`). 생성한 쪽이 평가하면 "비슷함"으로 치우칠 수 있어, 프롬프트에 "의도가 아니라 만든 질문을 기준대로 따진다", "단계나 요구가 늘었으면 0으로 매기지 않는다"를 넣었다 | Gemini 무료 등급이 하루 20회라 카드 1장에 호출 3번이면 하루 6장쯤이 최대다. 사용자 결정 |

### 2026-11-16 (2) 추가

| # | 설계서 | 변경 | 이유 |
|---|---|---|---|
| D12 | §7.1 "AI가 서술형 질문을 생성한다" | 먼저 원래 질문(카드 질문)에 답하고 AI가 평가한다. 변형 질문은 필요할 때 2차로 받는다. 원래 질문도 `questions` 행으로 저장하고 `kind = original`, 모델·프롬프트 버전·난이도는 비운다. 답안과 평가는 변형 질문과 같은 테이블·엔드포인트를 쓴다 | 사용자 결정. 원래 질문만 풀면 카드 1장에 AI 호출 1번이라 무료 한도 안에서 더 많이 복습할 수 있다 |
| D13 | (없음) | UI에서 .md 파일을 올리면 저장 전에 검사한다: 파일 이름, 같은 이름 파일, 크기, 형식(어댑터 파서), id 중복(폴더·함께 올린 파일), 질문 개수·다른 소스 id 충돌(`plan_sync`를 그대로 돌림). 하나라도 실패하면 아무것도 저장하지 않는다. 덮어쓰지 않는다(`open("x")`). 저장 위치는 개념 폴더 안의 기존 폴더 중에서 고른다. 업로드는 JSON(이름·내용)으로 받아 `python-multipart` 의존성을 피했다 | 형식이 틀린 파일이 폴더에 남으면 동기화할 때마다 오류가 난다. 보관된 Markdown 개념과 같은 id는 허용한다(동기화에서 복구된다) |
| D14 | 프론트엔드 React | React + Tailwind CSS 4 + shadcn/ui(Radix 기반, Nova 프리셋). 아이콘 Phosphor, 글꼴 Pretendard(npm으로 번들, 외부 요청 없음). 디자인 방향은 ui-ux-pro-max 추천(미니멀·스위스 스타일, 청록 주색). 다크 모드는 시스템 설정을 따른다 | 사용자 결정 |

### 2026-11-19 추가

| # | 설계서 | 변경 | 이유 |
|---|---|---|---|
| D15 | (D11) 질문 생성 호출에서 난이도도 받는다 | 난이도를 다시 별도 호출로 평가한다 (`DifficultyAssessment`, `DIFFICULTY_SYSTEM`). 두 질문에 답하려면 무엇이 필요한지 각각 따진 뒤 비교하고, 이유를 먼저 쓴 다음 난이도를 매긴다. "단계나 항목이 늘었으면 0으로 매기지 않는다"는 유지한다. 두 호출 중 하나라도 실패하면 저장하지 않는다 | 같은 호출의 자기 평가가 "비슷함"으로 치우치는 것을 Sonnet 비교에서 확인했다(6건 모두 0). 사용자 결정. 변형 질문은 카드 1장에 호출 2번이 된다 |

### 2026-11-21 추가

| # | 설계서 | 변경 | 이유 |
|---|---|---|---|
| D16 | §4 개발 단계 순서 (Phase 5 Containerlab) | Containerlab 구현을 미루고 개념 형식 맞추기와 Notion 연동을 먼저 한다 | 사용자 결정 |
| D17 | §A-2 Notion 소스 = 동기화 소스(`source_ref`는 page ID) | 두 방식을 모두 만든다. 먼저 가져오기(Notion 페이지 → 형식 맞추기 → .md 저장, 이후 .md가 원본), 다음에 동기화 소스(Notion 데이터베이스 속성 = 메타데이터). 한 노트에는 한 방식만 쓴다(같은 노트를 둘 다 쓰면 id 충돌이나 중복 개념) | 사용자 결정. 사용자 노트는 속성 없는 일반 페이지라 가져오기는 Notion 구조를 바꾸지 않고 쓸 수 있다. 동기화 소스는 시험용 복사본 데이터베이스로 만든다 |
| D18 | §A "개념 구조화" (방법 정의 없음) | 형식 맞추기는 AI 위주: 카테고리·키워드·난이도·선수·연관 개념을 AI가 채운다. 다만 본문은 규칙으로 정리하고 AI가 고쳐 쓰지 않는다. 질문은 노트 문장을 그대로 쓰고, AI는 합쳐서 3개가 안 될 때만 더한다(코드로 보장). frontmatter에 있는 값이 AI 값보다 먼저다. 선수·연관 개념은 알려진 개념의 id만 받는다. id는 규칙으로 정한다(접두사 + 같은 접두사 번호 중 가장 큰 것 + 1, 빈 번호는 채우지 않음). 동기화 경로에는 AI를 쓰지 않는다 | AI 위주는 사용자 결정. 본문을 AI가 고치면 원문이 빠질 수 있고, 질문 문장이 바뀌면 카드가 새로 생긴다. 동기화마다 AI를 부르면 결과가 달라져 카드가 흔들린다. 빈 번호를 다시 쓰면 보관된 개념과 헷갈린다 |
| D19 | (없음) | Notion 토글 안의 모범 답안은 버린다. 질문 섹션 전체를 본문에서 지운다 | 사용자 결정. 기존 `## 질문` 규칙과 같다 |
| D20 | 개념 폴더 기본값 `samples/concepts` | 형식을 맞춘 사용자 노트는 저장소 밖 별도 폴더(`NETRECALL_CONCEPTS_DIR`)에 저장한다. 2026-11-23 `~/netrecall-concepts`로 설정하고 샘플 3개를 복사했다 | 사용자 결정. 사용자 노트가 커밋되거나 샘플(NET-001·005·010)과 섞이지 않게 한다 |
| D21 | (없음) | 형식 맞추기 API를 두 단계로 나눈다. plan은 AI 없이 모든 파일의 처리 방법과 id를 정하고, convert는 파일 하나씩 AI로 채운다. convert는 plan에서 정한 다른 파일의 id·제목을 받아 아직 저장하지 않은 파일도 선수 개념으로 고를 수 있다 | AI 호출이 파일 하나에 19~66초 걸린다. 한 요청에서 여러 파일을 처리하면 수 분이 걸리고 진행 상황을 보여 줄 수 없다 |
| D22 | (D8) Gemini 호출 제한 시간 60초 | 120초 | 개념 추출이 66.4초 걸린 건이 있었다(`gemini-3.6-flash`). 사용자 결정. 답안 평가·변형 질문도 같은 설정이라 최대 대기 시간이 같이 늘었다 |

### 2026-11-23 추가

| # | 설계서 | 변경 | 이유 |
|---|---|---|---|
| D23 | 설계서 v1.2 | 설계서 v1.3으로 방향을 다시 잡았다. Notion 6·7단계 → 실습(Phase 5). LLM은 Claude Haiku(`claude-haiku-5-5`)로 바꾸되 크레딧 충전 뒤에. 녹화 응답 제공자는 Phase 7에서 판단. AI 평가 골든 세트는 Phase 7. route 검사는 조회한 경로가 selected·installed이고 static·kernel이면 통과 | 사용자 결정 (route 검사는 사용자가 맡김) |
| D24 | §A-4 "다른 소스가 이미 쓰는 id → 충돌" | 그 개념이 다른 소스에서 **보관된** 상태면 넘겨받는다(`taken_over`). 두 소스 모두 활성이면 지금처럼 충돌 | 사용자 결정. 노트를 소스 사이로 옮겨도 복습 이력이 이어진다 (§7 미결 해결) |
| D25 | (없음) | 동기화할 Notion 데이터베이스는 환경변수 `NETRECALL_NOTION_DATABASE`(주소나 id). 화면에서 바꾸지 않는다 | 사용자 결정. 개념 폴더(`NETRECALL_CONCEPTS_DIR`)와 같은 방식 |
| D26 | (없음) | 따로 "Notion 동기화" 버튼을 두지 않고, "동기화" 버튼이 Markdown → Notion 순서로 둘 다 한다. Notion이 설정되지 않은 503은 조용히 건너뛴다 | 설정 여부를 알려 주는 API를 따로 만들지 않아도 된다. Notion을 쓰지 않는 사람에게 쓸모없는 버튼이 보이지 않는다 |
| D27 | (없음) | 동기화 결과에 `warnings`를 더했다 (Notion: 내보내지 못한 블록, 잘린 페이지, 끊긴 연결) | Notion 규칙 페이지가 "빼고 경고"라고 정한 경우를 알릴 곳이 없었다 |
| D28 | (없음) | 개념 추가 창은 모든 파일을 plan부터 거친다. AI 변환은 자동으로 하지 않고 "형식 맞추기 (AI N번)" 버튼으로 시작한다. 파일 하나가 실패하면 멈추고, 다시 누르면 남은 파일부터 한다 | 파일 하나에 20~60초, 하루 20회 한도. 실패가 이어지면(과부하·한도) 남은 호출을 버리지 않기 위해 |

### 2026-11-24 추가

| # | 설계서 | 변경 | 이유 |
|---|---|---|---|
| D29 | §D-7 "sudo 없는 실행은 가정" | Codespaces에서 확인했다. 공식 `.deb`가 SUID와 `clab_admins` 그룹을 만들고, 그룹에 든 사용자는 sudo 없이 `containerlab deploy/destroy`를 한다. 그룹은 새 로그인부터 적용돼 이번 세션은 `sg clab_admins`로 확인했다 | 남은 가정은 WSL(Docker Desktop·WSL 안 Docker)뿐이다 |
| D30 | §D-4 host 이미지 (alpine 3.20 + iproute2) | alpine 3.24(digest 고정) + iproute2 + iputils | alpine 3.20은 2026-04에 지원이 끝났다. iputils ping은 응답 대기·전체 시간 옵션이 검사 의미와 맞다 |
| D31 | §D-4 검사 `to: pc2:eth1` | 검사 대상은 인터페이스(`노드:ethN`)로만 가리키고, 그 주소는 `preset.addresses`나 `address` 검사에서 정한다. 이 표가 주소 유일성 검사의 "의도한 곳"이다. 주소 식은 `<대역>.host(n)`, `n<0`은 뒤에서(`-1` = 마지막 사용 가능 주소) | LAB-001은 주소 없이 배포하므로 preset에 주소가 없다. 주소를 직접 쓰면 실행마다 바뀌는 대역을 쓸 수 없고, 유일성 검사의 기준도 없다 |
| D32 | §D-5 route: Linux 노드는 `ip -j route get` | Linux 노드에는 `protocol`을 쓸 수 없고, 경로가 있고 `local`이 아니면 통과다 | `ip route get` 결과에 프로토콜이 없다(녹화 확인). 프로토콜 조건은 라우터에만 의미가 있다 |
| D33 | §D-5 ping "3번 보내 1번 이상 응답, 한 번에 1초, 전체 5초" | `ping -n -c 3 -W 1`, 판정은 종료 코드가 아니라 출력의 "N received"(iputils)·"N packets received"(busybox). 전체 시간 제한은 실행기의 명령 시간 제한으로 둔다(3단계) | iputils에 `-w`를 주면 3번 중 1번만 응답해도 종료 코드 1이다. FRR 이미지의 ping은 busybox라 출력과 `-W` 뜻이 다르다. 두 형식 모두 3초 안팎에 끝난다 |
| D34 | §D-4 정적 검사 (값 미정) | 자원 제한: host CPU 0.5·메모리 64MB, router CPU 1·메모리 256MB. 시간 제한 1~120분(기본 60). `pool`은 사설 대역 안. 노드 항목은 `kind`만, 렌더링한 토폴로지의 노드 키는 허용 목록 | 시나리오가 이미지·마운트·명령을 고를 자리를 없앤다 |
| D35 | §D-5 상태 수집 "FRRouting 노드는 실행 중인 설정과 라우팅 테이블" | 라우터도 `ip -j addr show`를 같이 모은다 | `ip addr add`로 넣은 주소는 running-config에 나오지 않는다(녹화 확인). 주소 유일성 검사에 모든 노드의 주소가 필요하다 |
| D36 | §D-7 "실행기는 고정된 인자로 `containerlab`만 호출" | 배포·정리는 `containerlab`, 노드 명령 실행과 남은 실습 목록은 `docker exec`·`docker ps`로 한다 | `containerlab exec --cmd`는 명령을 문자열 하나로 받아 나눈다. `docker exec`는 argv를 그대로 받아 셸을 거치지 않는다. 학습자 접속에도 docker 그룹이 필요하다 |
| D37 | (없음) | `docker exec`의 종료 코드만으로는 명령 실패와 docker 실패를 가를 수 없다(없는 컨테이너도 1). stderr가 `Error response from daemon:`·`OCI runtime exec failed`로 시작하면 실행 실패(`LabRuntimeError`)로 본다. 정리는 라벨로 남은 실습인지 먼저 보고, 없으면 containerlab을 부르지 않는다 | ping 응답 없음도 종료 코드 1이다. 없는 실습을 `destroy`하면 containerlab이 오류(1)를 낸다(확인함) |
| D38 | §D-5 ping "전체 5초" | 노드 명령 시간 제한 15초. 라우터는 배포 직후 `touch /etc/frr/vtysh.conf`, `vtysh -c 'show ip route json'`이 JSON을 돌려줄 때까지 최대 30초 기다린다 | zebra가 뜨기 전에는 preset·검사의 vtysh가 실패한다 |
| D39 | §D-4 preset "항목 종류마다 고정 명령" | `addresses`: 라우터는 `vtysh -c 'configure terminal' -c 'interface X' -c 'ip address A'`, Linux 노드는 `ip addr add A dev X` | 라우터에 `ip addr`로 넣으면 학습자가 보는 running-config에 나오지 않는다 |
| D40 | §D-5 "검증기 테스트" | 실제 배포 테스트는 `lab` 마커. 기본 `pytest`에서 빼고 `pytest -m lab`으로만 돌린다. 준비(도구·그룹·이미지)가 안 됐으면 건너뛰지 않고 실패한다 | 평소 테스트가 Docker 없이 빨리 끝나게 한다. CI에서 조용히 건너뛰어 통과로 보이는 것을 막는다 |
| D41 | §D-5 "결과 화면에 검사별 통과 여부와 설명, 실패한 검사의 출력" | API·CLI 응답에서 학습자에게 주지 않은 목표 주소(preset에 없고 address 검사가 정한 주소)를 `[pc1:eth1 목표 주소]`로 가린다. 메시지와 출력 모두. DB에는 그대로 남긴다 | LAB-001은 주소를 계산하는 실습인데, 가리지 않으면 검증을 한 번 누르면 "eth1에 10.37.84.65/27가 없습니다"·ping 출력으로 답이 보인다 |
| D42 | §D-2 "앱을 시작할 때 DB에서는 끝났는데 남아 있는 실습 컨테이너를 지운다" | 이 DB가 만든 실행만 정리한다. 실행 기록은 배포 전에 커밋하므로 배포 중에 멈춘 실행도 기록이 있다. 기록이 없는 실습(다른 DB, 테스트)은 건드리지 않는다. 진행 중인데 환경이 사라진 실행은 끝난 것으로 표시한다. 테스트는 `conftest.py`에서 기본 런타임을 가짜로 바꾼다 | 처음 구현은 기록 없는 실습도 지웠다. 그러면 실습을 푸는 중에 `pytest`를 돌리면 테스트 앱(임시 DB)이 진짜 실습을 지운다 |
| D43 | §D-2 "시간 제한이 지나면 자동으로 정리" | 실습 API·CLI를 부를 때와 앱을 시작할 때 확인한다. 백그라운드 타이머는 두지 않는다. 지난 실행은 마지막 상태를 수집하고 정리한다. 통과한 실행은 `passed` 그대로, 아니면 `expired` | 타이머 없이도 다음 실습을 시작하기 전에는 반드시 정리된다. 아무도 부르지 않으면 컨테이너가 제한 시간보다 오래 남을 수 있다(노드가 작아 부담이 적다) |
| D44 | §D-2 `deploying` 상태 | 배포는 요청 안에서 끝까지 기다린다(1~10초, 이미지를 처음 받으면 더). `deploying`은 그 사이에만 보인다. 정리하지 못한 실행은 `error`에 이유를 남기고 다음 앱 시작 때 다시 지운다 | 비동기 작업 없이 상태를 단순하게 둔다 |
| D45 | §3.3 ERD `lab_runs`·`lab_attempts`·`lab_results` | `topology`(텍스트) → `topology_json`(노드·링크·preset 주소. 실행 환경과 무관한 형태), `goal`·`error` 열과 `lab_results.message`를 더했다. 이미지 digest는 로컬 이미지 id(`docker image inspect .Id`)다. AI 분석 열(`analysis_*`)은 AI 실패 분석을 만들 때 더한다. 처음 통과한 시각은 시도에서 계산한다 | 렌더링한 목표를 시나리오 파일 없이 다시 보여 주고, 배포 실패 이유와 검사별 이유를 남긴다. host 이미지는 로컬에서 빌드해 레지스트리 digest가 없을 수 있다 |
| D46 | §4.1 "CLI·API 수직 슬라이스" | CLI는 서버를 거치지 않고 같은 서비스를 부른다. `--env-file`로 `.env`를 읽는다. `verify`는 통과 0·실패 1, 오류는 2. 접속 명령은 host `docker exec -it clab-nr-<id>-<노드> sh`, router는 `vtysh` | 서버 없이 실습을 돌리고 스크립트로도 쓸 수 있게 한다 |

### 2026-11-25 추가

| # | 설계서 | 변경 | 이유 |
|---|---|---|---|
| D47 | §D-5 "오답은 의도한 검사에서 실패" | 오답은 실패해야 하는 검사를 **모두 정확히** 적는다(`fails`). 더 실패하거나 덜 실패해도 테스트 실패다. 주소 유일성 자동 검사(`auto:unique-addresses`)도 적을 수 있다 | "의도한 검사가 실패했는가"만 보면 다른 검사가 함께 잘못 실패하거나 통과해도 모른다. 예: 두 주소를 바꾼 오답에서 ping이 통과한다는 것도 테스트가 고정한다 |
| D48 | §D-5 "기준 풀이·오답을 `tests/labs/solutions/<id>/`에" | 파일은 `cases.yaml` 하나. 단계는 노드별 명령 문자열이고 `shlex`로 나눠 인자 목록으로 실행한다(셸 없음). 식은 `{대역.host(n)}`·`{대역.prefix}`·`{대역.netmask}`·`{대역.network}`. 명령이 실패하면 풀이 파일의 오류로 보고 테스트를 실패시킨다 | 대역이 실행마다 바뀌므로 주소를 식으로 써야 한다. 명령 실패를 오답의 일부로 받아 주면 오타 난 풀이가 "오답이 잘 걸렸다"로 보인다 |
| D49 | §6 CI "GitHub Actions" | 작업 두 개: `unit`(Python 3.14, Node 24: pytest, UI 테스트·빌드), `lab`(Ubuntu 러너에 Containerlab 0.83.0 `.deb`를 체크섬 확인 후 설치, `clab_admins` 그룹에 넣고 `sg`로 실행). 모든 브랜치 push와 수동 실행에서 돈다 | 사용자가 단위 테스트도 같이 돌리기로 했다(11-24). 그룹은 새 로그인부터 적용되므로 같은 작업 안에서는 `sg`로 돈다. PR 트리거는 같은 저장소 push와 겹쳐 두 번 돌아서 넣지 않았다 |
| D50 | §D-5 "결과 화면에 검사별 통과 여부와 설명" | CLI 결과에 번호, 실패 개수 요약, 남은 시간, 다음에 칠 명령을 넣는다. 시간 제한 뒤 정리는 여전히 다음 lab 명령 때다(D43). 화면에서 그 사실을 같이 말한다 | 사용자 피드백(2026-11-25). 종료 코드를 사람이 읽게 하지 않는다 |
| D51 | §D-4 LAB-002 검사 (ping 2, 라우터 route 2) | PC 경로 검사 2개(`pc1-route`·`pc2-route`, Linux 노드라 프로토콜 없음)를 더했다 | 기본 게이트웨이를 빼먹어도 ping 실패만 보이면 라우터 문제인지 PC 문제인지 알 수 없다. 사용자 피드백(무엇을 고칠지 알기 쉬운 결과)에 맞췄다. 검사 목록은 시작할 때 보이므로 "PC에도 경로가 필요하다"는 단서가 되지만, 정적 라우팅 개념 자체라 숨기지 않는다 |
| D52 | 미결 "LAB-002 OSPF 오답 (ospfd 기본 꺼짐)" | 실습의 FRR은 ospfd를 켜지 않은 채 둔다. "OSPF 사용" 오답 테스트만 직접 ospfd를 띄우고, 이웃이 맺어질 때까지 `sh -c` 반복으로 최대 14초 기다린다(노드 명령 제한 15초, D38). transit은 `ip ospf network point-to-point`로 DR 선출 대기를 없앤다 | 정적 라우팅 실습에 OSPF를 켜 둘 이유가 없다. 학습자가 ospfd를 직접 켜면 route 검사의 프로토콜 조건이 막고, 테스트가 그것을 확인한다 |
| D53 | §D-6 "실패하면 AI가 원인 힌트" (Claude 전환 뒤) | AI 없이 시나리오에 적은 단계별 힌트를 먼저 둔다(설계서 v1.4 §D-10). 힌트 자리표시는 학습자가 이미 받은 값만 허용한다 | 사용자 요청. AI 분석은 아직 쓸 수 없고 호출마다 비용이 든다. 정답이 새지 않게 읽을 때 막고, 내보낼 때도 가린다 |
| D54 | (없음) | 힌트는 요청할 때 한 단계씩 열고, 이미 다 본 검사를 다시 요청하면 본 것만 다시 보여 준다(기록은 늘지 않음). 검사를 안 고르면 마지막 검증에서 처음 실패한 검사다. 마지막 검증이 통과면 고르게 한다 | 힌트 수를 실습 숙련도에 쓰려면 같은 단계를 여러 번 세지 않아야 한다 |
| D55 | §1.3 "실습 난이도 조절" (P1) | 도움 수준만 먼저: easy 힌트 3단계, normal 2단계, hard 힌트 없음 + 끝날 때까지 검사 목록·검사별 결과 숨김. 문제 난이도 단계와 자동 조절은 Phase 6 | 사용자 결정(A). 시나리오·검사가 같아 기준 풀이·오답 테스트가 그대로다 |

### 2026-11-26 추가

| # | 설계서 | 변경 | 이유 |
|---|---|---|---|
| D56 | §E-1 화면 경로 `/labs` (API `GET /labs`와 같은 경로) | 빌드한 화면이 있으면, GET이고 Accept에 `text/html`이 있으며 실제 파일·`/docs`·`/redoc`이 아닌 요청에 `index.html`을 준다(`Vary: Accept`, `Cache-Control: no-cache`). 화면의 fetch(Accept `*/*`)는 API로 간다. Vite 개발 서버도 같은 규칙(proxy `bypass`) | 사용자 선택(2026-11-26). API를 `/api` 아래로 옮기면 모든 경로·테스트·화면 호출이 바뀌고, 해시 경로는 주소에 #이 붙는다. Vary·no-cache가 없으면 Chromium이 캐시한 HTML을 같은 주소의 fetch에 돌려줬다(실제 확인). 브라우저 주소창에 API 주소를 쳐서 JSON을 보는 것은 안 된다(`/docs`는 된다) |
| D57 | §D-9 "화면은 이미 있는 실습 API만 쓴다" | 새 엔드포인트 없이 응답 필드만 더했다: `GET /labs`의 `last_run`(가장 최근 실행 요약), 실행 응답의 `links`·`last_attempt`(마지막 검증, 어려움은 끝날 때까지 결과 비움)·`hints`(검사 id → 본 힌트). `GET /labs`도 시간 제한을 확인한다 | 사용자 선택. §D-9가 요구하는 목록의 마지막 실행 결과와 토폴로지 그림에 필요하다. 힌트 API는 부를 때마다 새 단계를 열어서, 새로고침한 뒤 본 힌트를 다시 보여 줄 방법이 없었다 |
| D58 | §D-9 실습 화면 | 진행 중인 실행이 있으면 목록 대신 실행 화면. 끝낸 실행은 결과(어려움도 공개)와 "목록으로"·"다시 하기". 처음부터 다시 = 끝내기 + 같은 도움 수준으로 시작. 남은 시간이 0이 되면 실행을 다시 읽어 서버가 정리하게 한다. 화면은 현재 실행 → 목록 순서로 부른다(두 요청이 같은 실행을 함께 정리하지 않게). 토폴로지는 노드를 한 줄에 놓고 이웃 링크는 직선, 떨어진 링크는 위쪽 곡선, preset 주소는 노드 아래. 사이드바는 테마의 card·accent 색을 쓴다 | shadcn sidebar 토큰은 기본값 그대로(다크는 파란색)라 D14 청록 테마와 맞지 않는다. 노드는 최대 6개라 자동 배치 라이브러리 없이 충분하다 |
| D59 | §1.2 학습 시나리오 (오늘 복습할 카드 전체) | 주제별 학습: 카테고리(개념의 `category`)와 개념 단위로 고른다. 범위는 복습할 때가 된 카드뿐이다. 고른 주제는 서버에 저장하지 않는다 | 사용자 요청(2026-11-26). 처음 동기화하면 모든 카드가 한꺼번에 복습 대상(95장)이 된다. 때가 안 된 카드를 미리 복습하면 FSRS가 다음 간격을 짧게 잡으므로 넣지 않았다 |
| D60 | §D-8 웹 터미널(P2, 조건을 갖춘 뒤), §7.4 "넣지 않은 것" | 도입한다. 조건을 이렇게 채웠다: 서버는 `127.0.0.1`에만(README 실행 명령), WebSocket Origin이 Host나 X-Forwarded-Host와 같아야 함(포트 전달용. 브라우저 스크립트는 이 헤더를 못 넣는다), 접속마다 1회용 발급표(30초, 프로세스 메모리, 실행·노드·셸에 묶임. 설계서의 "실행마다 토큰"보다 좁다), 진행 중인 실행의 노드만(발급할 때와 접속할 때 모두 확인), 시간 제한이 되면 닫음, 동시 8개 | 사용자 요청(2026-11-26). 발급표는 일반 API 응답이라 다른 사이트는 읽지 못한다(CORS). 실습을 끝내면 노드가 지워져 접속 명령도 끝나므로 따로 세션을 추적하지 않는다(실제 확인) |
| D61 | §D-7 `LabRuntime` | `terminal_argv(run_name, node, shell)`를 더했다. API가 그 argv를 PTY에서 셸 없이 실행한다. 셸은 Linux 노드 `sh`, 라우터 `vtysh`(기본)·`sh`. 제어 터미널 없이 띄우고, 크기가 바뀌면 PTY 크기를 바꾼 뒤 SIGWINCH를 직접 보낸다 | 런타임만 docker·Containerlab을 안다(§D-7). `docker exec -it`는 PTY를 raw 모드로 바꿔 Ctrl-C 같은 키가 노드 안에서 처리된다. `preexec_fn`·fork 없이 `subprocess`만 쓴다 |
| D62 | §D-1 "학습자가 자기 터미널에서 설정", §D-9 "화면에서 노드 명령을 실행하는 기능은 없다" | 화면 안 터미널과 자기 터미널 둘 다 쓴다. 화면은 여전히 정해진 명령(검사·preset)을 실행하지 않고, 터미널은 학습자의 키 입력만 노드 셸에 전한다. 터미널 연결 중에는 DB 세션을 잡지 않는다. xterm 색은 테마 토큰에서 읽는다 | SQLite 읽기 트랜잭션을 연결 내내 잡고 있으면 검증·끝내기가 쓰지 못한다. 색 규칙은 §E-1 |
| D63 | §E-2 "실습 실행은 시나리오 파일의 concepts에 이 개념이 든 시나리오의 실행" | 연결된 실습 = 개념 원본의 `labs`(Markdown `labs`, Notion "실습" 속성) ∪ 시나리오 `concepts`에 이 개념이 든 실습. 시나리오 파일이 없는 id도 보여 주고 "실습 열기"만 뺀다 | 실제 노트는 Notion에서 오고 id가 NET-1xx라 저장소 시나리오가 가리키지 않는다. 시나리오 파일을 고치지 않고 원본 쪽에서 연결할 수 있게 한다 |
| D64 | §E-2 목록·상세·`GET /concepts/{id}/history` | 목록 검색은 제목·키워드·id(카테고리는 버튼으로 거른다). 상세는 카드 표 → 실습 → 본문 순서. 카드는 활성 카드만, 평가 점수는 원래 질문의 가장 최근 것만(변형 질문 제외). 실행은 최근 5개와 나머지 개수, `attempts_to_pass`(처음 통과한 검증 순번)와 걸린 시간. 본문은 GFM만 켜고 HTML은 그리지 않는다. 기록 조회 API는 시간 제한 정리(`expire_overdue`)를 부르지 않는다(읽기만) | 본문이 길어(7천 자) 기록을 위에 둔다. 변형 질문은 난이도가 달라 같은 기준으로 비교할 수 없다(§E-4와 같은 이유). Notion 본문에 HTML이 섞여도 실행되지 않게 한다 |
| D65 | §E-2 "원본 위치(Markdown은 파일 경로, Notion은 \"Notion\")" | 원본을 화면에서 본다. Markdown 개념은 개념 폴더의 파일을 그대로(frontmatter·질문 포함) 읽어 보여 준다. `source_ref`를 개념 폴더 기준으로 풀어 폴더 밖이면 404. Notion 개념은 파일이 없으므로 가져와 저장한 본문(Markdown)과 Notion 페이지 링크(`https://www.notion.so/<id>`)를 준다. 읽기만 한다 | 사용자 요청(2026-11-26). 동기화 뒤 파일을 옮기거나 지웠으면 "동기화하세요"라고 알린다 |

### 2026-11-28 추가

| # | 설계서 | 변경 | 이유 |
|---|---|---|---|
| D66 | §E-3·§E-4 대시보드 지표 | 오답률 = (Again + Hard) / 복습 수. 복습량·주별 오답률은 남긴 복습 기록 전부, 카테고리·학습 현황·취약 개념은 지금 복습할 카드(활성 카드, 보관되지 않은 개념)만 센다. 학습 현황은 새 카드(0회)·학습 중(Learning·Relearning)·복습 중·익숙함(기억 안정성 21일 이상) 4단계. 기준값은 `backend/services/dashboard.py`의 `RULES` 한 곳. 차트는 CSS 막대(recharts 없음), 색은 테마 토큰(발산형 등급, 청록 단계) | 사용자 선택(2026-11-28). 오답률을 Again만으로 하면 Hard로 떠올린 것을 놓친다. 같은 개수를 두 번 세지 않도록 학습 현황 범위를 복습할 카드로 맞췄다. 발산형 색과 단계 색은 `validate_palette.js`로 확인 |
| D67 | §E-1 화면 경로 `/dashboard`, §E-3 "바로 학습" | 사이드바에 대시보드를 더했다. 대시보드 맨 위 "학습 시작"과 카테고리·취약 개념·단계 줄의 "복습 시작"은 목록을 거치지 않고 학습 세션을 같은 화면에서 연다. 끝나면 대시보드로 돌아온다. 지표 API는 `/dashboard/summary` 하나 | 사용자 선택(2026-11-28). 학습 세션을 `/`에 얹으면 목록에서 온 흐름과 섞인다. 학습 세션은 여전히 경로를 두지 않고 `/dashboard` 안에서 연다 |

## 2. 진행 현황 정정

설계서 §4.5는 아래 항목을 "완료"로 적었지만, 2026-11-12 시점 저장소에는 코드가 없었다.

| 항목 | 출처 |
|---|---|
| `integrations/sources/base.py` | 사용자가 제공한 코드 그대로 |
| `integrations/sources/markdown/adapter.py` | 사용자가 제공한 코드 그대로 |
| `backend/services/concept_sync.py` | 사용자가 제공한 코드 그대로 |
| `samples/concepts/` | 다시 작성 |
| `scripts/preview_concepts.py` | 다시 작성 |
| `docs/markdown-concept-format.md` | 다시 작성 (구현 기준) |
| 테스트 | 다시 작성. 설계서의 "35개 케이스"와 개수는 다르다 |

## 3. 구현에서 정해진 동작 (설계서에 없거나 다른 것)

제공된 코드의 동작이며, 테스트로 고정했다.

- **개념 id 형식**: 설계서는 "`NET-001` 형태". 구현은 대문자 접두사 아무거나 허용한다(`[A-Z][A-Z0-9]*-\d{3,}`, 예: `LNX-001`, `CLD-001`). Linux·클라우드 분야도 다루기 때문에 맞는 방향이다.
- **내용 해시**: 설계서는 `source_ref`만 제외한다고 했다. 구현은 `source_type`도 제외한다.
- **건너뛰는 폴더**: 설계서 목록 외에 `.git/`, `node_modules/`도 건너뛴다. `templates/`는 어느 깊이에 있어도 건너뛴다. `README.md`는 대소문자를 구분하지 않는다.
- **설계서에 없는 오류 규칙**: 본문이 비면 오류. 자기 자신을 선수·연관 개념으로 지정하면 오류.
- **`## 질문` 섹션**: 목록 항목만 질문이 되고, 섹션 안의 다른 문장은 버려진다.
- **id 중복 시 "먼저 읽은 항목"**: 경로를 정렬한 순서 기준이다.
- **`updated`는 이동을 포함할 수 있다**: 내용과 위치가 같이 바뀌면 `relocated`가 아니라 `updated`로 분류된다. DB 반영 계층은 `updated`에서도 `source_ref`를 갱신한다.
- **제목 없는 파일의 이름 변경은 `updated`다**: `title`도 `# 제목`도 없으면 파일 이름이 제목이 되므로, 이름을 바꾸면 내용 해시가 바뀐다. 같은 행이 갱신될 뿐 복습 이력은 유지된다. 파일 정리를 자주 한다면 `title`을 명시하는 것이 좋다.

## 4. DB·API 구현 (2026-11-12, 계획표 6·7단계)

- **설계서 ERD에 없는 컬럼**: `concepts.keywords`, `concepts.seed_questions`(JSON), `created_at`. `seed_questions`는 개념 파일에 직접 쓴 질문이다. AI가 생성한 질문(`questions` 테이블, Phase 4)과 섞이지 않도록 이름을 나눴다.
- **D2 구체화**: `concept_relations.from_concept_id`는 FK를 건다(출발 개념은 항상 있다). `to_concept_id`만 FK가 없다.
- **보관해도 연결은 남긴다**: 보관된 개념의 관계·실습 연결 행은 지우지 않는다. 복구하면 새 내용으로 다시 채운다.
- **`(source_type, source_ref)`에 유니크 제약을 두지 않았다**: 보관된 개념이 옛 경로를 그대로 갖고 있는 상태에서, 같은 경로에 다른 id의 개념이 새로 생길 수 있기 때문이다.
- **트랜잭션 범위**: 파일 읽기는 트랜잭션 밖에서 하고, DB 상태 읽기 → 계획 수립 → 반영은 한 트랜잭션으로 묶었다. 반영 중 하나라도 실패하면 전부 되돌린다.
- **SQLite FK**: 연결마다 `PRAGMA foreign_keys=ON`을 켠다. SQLite는 기본적으로 FK를 검사하지 않는다.
- **스키마 생성**: ~~앱 시작 시 `create_all`~~ → 2026-11-13부터 Alembic (D6, §5 참고).
- **API 경로**: 설계서에 경로 정의가 없어 `POST /sync/markdown`, `GET /concepts`, `GET /concepts/{id}`로 정했다. Notion 소스가 붙으면 `POST /sync/notion`을 추가한다.
- **시간대**: SQLite는 시간대를 저장하지 않으므로 UTC로 쓰고, 읽을 때는 시간대 없는 값으로 돌아온다.

## 5. 복습 엔진 구현 (2026-11-13, 계획표 8단계)

- **마이그레이션**: `init_db`가 Alembic `upgrade head`를 실행한다. 모델을 바꾸면 `alembic revision --autogenerate -m "설명"`으로 리비전을 만들고 내용을 검토해 커밋한다. SQLite라 `render_as_batch=True`이고, 제약 이름 규칙(`NAMING_CONVENTION`)을 `Base.metadata`에 정했다. 테스트 `test_migrations_match_models`가 리비전 누락을 잡는다.
- **카드 식별**: `(concept_id, question_hash)` 유니크. 해시는 질문 문장(앞뒤 공백 제거 후) 그대로의 SHA-256이다.
  - 새 질문 → 새 카드 (바로 복습 대상)
  - 사라진 질문 → `active=false`. 행과 `review_logs`는 남는다
  - 같은 문장이 다시 생김 → 같은 카드를 다시 활성화 (기억 상태 이어짐)
  - 문장 수정(오타 포함) → 옛 카드 비활성 + 새 카드
  - 순서 변경, 파일 이동, 개념 보관·복구 → 카드 변화 없음. 보관된 개념의 카드는 복습 목록에서만 빠진다
- **설계서 ERD와 다른 컬럼**: `review_cards.id`는 정수 자동 증가(설계서는 string). `review_cards`에 `question_hash`, `question`, `active`, `created_at`, `updated_at`을 추가. `review_logs`에 py-fsrs `ReviewLog.to_dict()`를 담는 `log_json`을 추가(나중 파라미터 최적화용).
- **"오늘 복습할 카드"**: `due_at <= 지금`. 기한이 오래된 순. 한국 시간 자정 기준 하루치 묶음은 쓰지 않았다.
- **질문 개수 위반**: 오류로 보고한다. 이미 저장된 개념이면 경로가 바뀌었어도 id로 알아보고 `kept_due_to_error`로 유지한다(보관하지 않음).
- **평가 등급**: 사용자가 1~4(Again·Hard·Good·Easy)를 직접 고른다. 설계서 §2.2-B대로 AI 점수와 분리한다.
- **FSRS 설정**: py-fsrs 기본값(목표 기억률 0.9, fuzzing 켬). 테스트는 fuzzing을 끈 Scheduler로 확인한다.
- **API 오류**: 없는 카드 404, 비활성 카드·보관된 개념의 카드 409, 등급 범위 밖 422.

## 6. AI 평가 구현 (2026-11-13, Phase 4)

- **LLM 호출과 트랜잭션**: 필요한 값을 읽고 트랜잭션을 끝낸 뒤 LLM을 호출하고, 결과는 새 트랜잭션에서 저장한다. 호출 중(수 초) SQLite를 잠그지 않는다.
- **실패 처리**: LLM 호출·응답 검증이 실패하면 아무것도 저장하지 않고 502. 답안 평가가 실패하면 답안도 저장되지 않으므로, UI는 입력한 답안을 지우지 말아야 한다. 키가 없으면 AI API만 503.
- **응답 형식**: Gemini에 Pydantic 모델의 JSON 스키마(`response_json_schema`)를 보내고, 받은 응답을 같은 모델로 다시 검증한다. 점수 0~100, 난이도 -2~2 범위 밖이면 실패로 처리한다.
- **`recommended_lab`**: 개념에 연결된 실습(`concept_labs`)이 아닌 id가 오면 `null`로 바꾼다. 평가 전체를 버리지는 않는다.
- **프롬프트**: `ai_prompts.py`. 바꾸면 `PROMPT_VERSION`을 올린다. 질문·평가 행에 모델명과 프롬프트 버전을 저장한다(설계서 §3.4 원칙 3). 답안 속 지시문을 따르지 말라는 규칙을 넣었다. temperature는 지정하지 않는다(모델 기본값).
- **설계서 ERD와 다른 점**
  - `questions`: `card_id`, `base_question`(생성 당시 카드 질문), `relative_difficulty`, `difficulty_reason`, `model`, `prompt_version`, `created_at` 추가. `question_type`은 변형 질문 한 종류뿐이라 두지 않았다.
  - `answer_evaluations`: `score`는 정수(0~100). `model`, `prompt_version`, `created_at` 추가. 항목별 점수와 피드백은 `feedback_json`에 응답 그대로 저장한다.
  - id는 모두 정수 자동 증가.
- **질문 생성 시점**: 요청할 때마다 새로 만든다(미리 만들지 않음). 한 질문에 답안을 여러 번 낼 수 있다.

## 7. 미결 사항

- ~~**다른 소스의 보관된 개념도 id를 계속 점유한다**~~ → 2026-11-23 보관된 개념은 넘겨받는다(D24).
- **YAML 자동 형 변환**: 따옴표 없는 `22`(숫자), `yes`(참·거짓), `2024-01-01`(날짜)은 문자열이 아니어서 오류가 된다. 지금은 문서에 "따옴표로 감싸라"고만 적었다. → 2026-11-21: 형식 맞추기로 만든 파일은 이런 값을 따옴표로 감싸 쓴다(`render.py`). 원래 노트의 frontmatter 목록에 있던 숫자·날짜는 글자로 바꾼다.
- **Notion 어댑터**: ~~아직 저장소에 없다(설계서 §4.5 "예정").~~ → 2026-11-21 Notion 클라이언트와 가져오기 API를 만들었다. 동기화 소스(`NotionConceptSource`, `POST /sync/notion`)도 2026-11-23에 만들었다. 질문 3개 규칙은 동기화 계획에서 검사하므로 어댑터를 붙이면 그대로 적용된다. 시각을 내보내는 API를 새로 만들면 D7대로 KST로 바꾼다.
- **Notion 다시 가져오기**: 가져온 뒤에는 .md가 원본이다. 같은 이름 파일이 있으면 저장하지 않으므로(D13), Notion에서 고친 노트를 다시 반영하려면 기존 .md를 먼저 지워야 한다.
- **실제 Gemini**: ~~미확인~~ → 2026-11-16에 모델 ID, JSON 스키마, 답안 평가 품질을 확인했다. 변형 질문 프롬프트(`2026-11-16.1`)와 D11(호출 합치기)은 아직 실제로 확인하지 못했다. → 2026-11-19에 프롬프트를 `2026-11-19.1`로 바꾸고 난이도를 별도 호출로 되돌렸다(D15). 이것도 실제로 확인하지 못했다(`gemini-4-hydrogen`·`gemini-3.8-flash` 모두 503·504). → 2026-11-21: `gemini-3.8-flash`는 여전히 504, `gemini-3.6-flash`로 개념 추출이 동작했다(19~66초). 변형 질문 프롬프트와 D15는 여전히 실제로 확인하지 못했다. → 2026-11-23: `gemini-3.6-flash`로 카드 5장을 시도했지만 29번 모두 503·시간 초과·하루 한도로 실패했다. Claude Haiku로 바꾼 뒤(D23) 같은 카드로 확인한다.
- **Gemini 무료 등급 한도**: 하루 20회. 원래 질문만 풀면 카드 1장에 1번이지만, 변형 질문까지 풀면 4번(원래 질문 평가, 변형 생성, 난이도 평가, 변형 질문 평가)이라 하루 5장쯤이다(D15). 유료 전환이나 다른 모델을 검토 중이다(2026-11-19 Claude 예비 비교). 형식 맞추기는 파일 1개에 1번이라, 노트 12개를 가져온 날은 복습에 8번만 남는다.
- **복습 기록과 답안 연결**: `review_logs`와 `answer_submissions`는 아직 연결되지 않는다. 설계서 Phase 6(답안 평가를 복습에 반영)에서 정한다.
- **테스트 경고**: Starlette 1.10이 `TestClient`에서 `httpx` 사용을 지원 중단 예정이라고 경고한다. 지금은 동작에 영향이 없다. 의존성을 올릴 때 다시 확인한다.
- **실행 환경**: Codespaces의 Python은 3.14.2다. `requires-python`은 `>=3.11`로 두었다. Containerlab(Phase 5)은 ~~Codespaces에서 동작하지 않을 가능성이 높다~~ → 2026-11-19 Codespaces에서 동작을 확인했다. 실행 기준은 로컬 PC(Linux, Windows는 WSL)이고, sudo 없는 실행(`clab_admins`)은 아직 실험으로 확인하지 못했다. 설계서 v1.2 §D-7에 정리했다. → 2026-11-24 Codespaces에 Containerlab을 설치해 sudo 없는 실행을 확인했다(D29). 남은 가정은 WSL이다.
- ~~**Codespace 재시작 뒤 고장 난 실습**~~ → 2026-11-25 사용자: 전역 후 로컬 PC에서 쓰므로 기능을 만들지 않는다. (발견 내용: 실습 컨테이너는 재시작 정책 `always`로 다시 뜨지만 Containerlab이 만든 링크(veth)는 사라진다. 시간 제한 전이면 `active`인 채 검증이 계속 실패한다. 후보: 검증·상태 조회 때 링크 인터페이스가 없으면 "환경이 망가졌다"고 알리고 끝내기를 권하기, 또는 컨테이너 시작 시각이 배포 시각보다 뒤면 고장으로 보기. 7단계(실습 화면) 전에 정한다.)
- ~~**LAB-002의 OSPF 오답**~~ → 2026-11-25 ospfd는 꺼 둔 채로 두고 오답 테스트만 직접 켠다(D52). (원래 문제: FRR 이미지는 기본으로 mgmtd·zebra·staticd만 켠다, `/etc/frr/daemons`에서 ospfd=no)
