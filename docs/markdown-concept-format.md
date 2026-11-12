# Markdown 개념 형식

로컬 폴더의 `.md` 파일을 학습 개념으로 가져오는 형식입니다. 파일 하나가 개념 하나입니다.
구현: [integrations/sources/markdown/adapter.py](../integrations/sources/markdown/adapter.py)

## 예시

```markdown
---
id: NET-010
title: Static Routing
category: Routing
keywords: [Routing Table, Next Hop, Default Route]
difficulty: 2
prerequisites: [NET-005]
related: [NET-001]
labs: [LAB-002]
---

# Static Routing

본문 설명...

## 질문

- 서로 다른 네트워크에 있는 두 PC가 통신하려면 라우터에 어떤 설정이 필요한가?
```

## frontmatter 필드

파일은 반드시 첫 줄의 `---`로 시작하는 YAML frontmatter를 가져야 합니다.

| 필드 | 필수 | 형식 | 설명 |
|---|---|---|---|
| `id` | 필수 | 대문자 접두사 + `-` + 숫자 3자리 이상 (예: `NET-001`, `LNX-012`) | 개념 식별자. 파일 이름·위치가 바뀌어도 같은 개념으로 판단하는 기준 |
| `title` | 선택 | 문자열 | 없으면 본문 첫 `# 제목`, 그것도 없으면 파일 이름 |
| `category` | 선택 | 문자열 | |
| `keywords` | 선택 | 문자열 목록 | 중복 자동 제거 |
| `difficulty` | 선택 | 1~5 정수 | |
| `prerequisites` | 선택 | 개념 id 목록 | 선수 개념 |
| `related` | 선택 | 개념 id 목록 | 연관 개념 |
| `labs` | 선택 | `LAB-` + 숫자 3자리 이상 목록 | 연결된 실습 시나리오 |
| `questions` | 선택 | 문자열 목록 | AI 질문 생성 시 참고할 직접 작성 질문 |

- 목록 필드는 값이 하나면 문자열로 써도 됩니다 (`labs: LAB-001`).
- 목록 항목은 모두 문자열이어야 합니다. YAML은 따옴표 없는 `22`를 숫자로, `yes`/`no`를 참·거짓으로, `2024-01-01`을 날짜로 읽으므로 이런 값은 따옴표로 감싸세요 (`keywords: [SSH, "22"]`).
- 정의되지 않은 키는 오류입니다. 오타 난 필드가 조용히 무시되는 것을 막기 위해서입니다.
- 자기 자신을 `prerequisites`나 `related`에 넣으면 오류입니다.

## 본문

- 본문이 비어 있으면 오류입니다.
- `## 질문` 섹션의 목록 항목(`-` 또는 `*`)은 `questions`에 합쳐지고, 섹션 전체가 본문에서 제거됩니다. 섹션은 다음 `## ` 제목이나 파일 끝에서 끝납니다. 섹션 안의 목록이 아닌 문장은 버려집니다.
- `questions` frontmatter와 `## 질문` 섹션을 함께 쓸 수 있습니다. 중복은 제거됩니다.

## 폴더 스캔 규칙

- 지정한 폴더 아래의 `*.md`를 하위 폴더까지 경로 순서대로 읽습니다.
- 다음은 건너뜁니다.
  - 경로의 어느 부분이든 `.` 또는 `_`로 시작하는 파일·폴더 (`.obsidian/`, `_draft.md` 등)
  - `templates/`, `node_modules/` 폴더
  - `README.md` (대소문자 무관)
  - 심볼릭 링크
- 지정 폴더 밖의 파일은 읽지 않습니다.
- 파일 크기 상한은 기본 512KB입니다.
- UTF-8 BOM과 Windows 줄바꿈(CRLF)은 자동 처리합니다.

## 오류 처리

- 파일 하나의 오류는 그 파일만 건너뛰고 오류 목록에 기록합니다. 나머지 파일은 계속 읽습니다.
- 같은 폴더 안에서 `id`가 겹치면 경로 순서상 먼저 읽은 파일만 반영하고, 나머지는 오류로 보고합니다.

동기화 규칙(생성·갱신·이동·보관·복구·충돌)은 [backend/services/concept_sync.py](../backend/services/concept_sync.py)의 모듈 설명을 보세요.

## 미리보기

DB에 반영하지 않고 폴더를 검사합니다. 읽기 오류가 있으면 종료 코드 1입니다.

```bash
python scripts/preview_concepts.py path/to/concepts
```
