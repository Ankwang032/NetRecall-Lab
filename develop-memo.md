# 개발 메모

기준 문서: [NetRecall_Lab_SDD_v1.1.md](NetRecall_Lab_SDD_v1.1.md) (2026-11-12)
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

- **다른 소스의 보관된 개념도 id를 계속 점유한다**: Notion에서 보관된 `NET-001`이 있으면, Markdown의 `NET-001`은 계속 충돌로 보고된다. 소스를 옮길 때 문제가 된다. Notion 어댑터를 붙일 때 정한다.
- **YAML 자동 형 변환**: 따옴표 없는 `22`(숫자), `yes`(참·거짓), `2024-01-01`(날짜)은 문자열이 아니어서 오류가 된다. 지금은 문서에 "따옴표로 감싸라"고만 적었다.
- **Notion 어댑터**: 아직 저장소에 없다(설계서 §4.5 "예정"). 질문 3개 규칙은 동기화 계획에서 검사하므로 어댑터를 붙이면 그대로 적용된다. 시각을 내보내는 API를 새로 만들면 D7대로 KST로 바꾼다.
- **실제 Gemini 미확인**: 키를 넣고 (1) 기본 모델 ID가 실제로 있는지, (2) `response_json_schema`의 `minimum`/`maximum`/`anyOf(null)`이 받아들여지는지, (3) 질문·평가 품질을 샘플로 확인해야 한다.
- **복습 기록과 답안 연결**: `review_logs`와 `answer_submissions`는 아직 연결되지 않는다. 설계서 Phase 6(답안 평가를 복습에 반영)에서 정한다.
- **테스트 경고**: Starlette 1.10이 `TestClient`에서 `httpx` 사용을 지원 중단 예정이라고 경고한다. 지금은 동작에 영향이 없다. 의존성을 올릴 때 다시 확인한다.
- **실행 환경**: Codespaces의 Python은 3.14.2다. `requires-python`은 `>=3.11`로 두었다. Containerlab(Phase 5)은 Codespaces에서 동작하지 않을 가능성이 높아, 설계서 §4.4대로 Linux VM에서 진행한다.
