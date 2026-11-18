# netrecall-lab

## 개발 환경

```bash
pip install -e ".[dev]"
pytest
python scripts/preview_concepts.py samples/concepts   # DB 반영 없이 개념 폴더 검사
cd frontend && npm install && npm test                 # UI 테스트
```

## 서버 실행

```bash
cp .env.example .env                 # GEMINI_API_KEY 입력
(cd frontend && npm run build)       # UI 빌드. 처음 한 번, UI를 고친 뒤
uvicorn backend.main:create_app --factory --reload --env-file .env
```

- 화면: http://127.0.0.1:8000/ (Codespaces는 포트 탭의 8000번 주소). UI를 빌드하지 않았으면 `/`는 404입니다
  - 학습: 원래 질문에 답 → AI 평가 → (필요하면) AI 변형 질문에 한 번 더 답 → 등급 선택 → 다음 카드
  - 개념 추가: .md 파일을 끌어다 놓으면 형식을 검사하고, 모두 통과하면 개념 폴더에 저장한 뒤 동기화합니다
- UI를 고칠 때는 `cd frontend && npm run dev`로 Vite 서버(5173번)를 띄우면 저장하자마자 반영됩니다. API 요청은 8000번 FastAPI로 넘어갑니다
- UI는 React + TypeScript + Tailwind CSS + shadcn/ui(Radix)입니다. 컴포넌트는 `npx shadcn@latest add <이름>`으로 추가합니다 (`frontend/components.json`)

API:

- `POST /sync/markdown` (`?dry_run=true`로 미리보기): 개념 폴더를 DB에 동기화
- `GET /concepts` (`?include_archived=true`), `GET /concepts/{id}`
- `GET /concepts/folders`: 개념 파일을 올릴 수 있는 폴더 (`""` = 개념 폴더 최상위)
- `POST /concepts/files` (`?dry_run=true`로 검사만) `{"folder": "network", "files": [{"name": "ospf.md", "content": "..."}]}`: 개념 파일을 검사하고, 모두 통과하면 저장 후 동기화. 하나라도 실패하면 아무것도 저장하지 않습니다 (`saved: false`)
- `GET /reviews/due`: 지금 복습할 카드 (개념의 질문 1개 = 카드 1장)
- `POST /cards/{card_id}/questions/original`: 카드 질문을 그대로 출제 (AI 호출 없음)
- `POST /cards/{card_id}/questions`: AI가 카드 질문을 변형하고, 원래 질문 대비 난이도(-2~+2)도 같은 호출에서 평가
- `POST /questions/{question_id}/answers` `{"answer": "..."}`: AI 답안 평가 (정확성·완전성·논리성·기술적 타당성·응용력)
- `POST /reviews` `{"card_id": 1, "rating": 3}`: 평가 반영 (1=Again, 2=Hard, 3=Good, 4=Easy). 등급은 AI 점수와 별개로 직접 고릅니다

학습 흐름: `GET /reviews/due` → 원래 질문 출제 → 답안 제출 → 피드백 확인 → (필요하면) 변형 질문 → 답안 제출 → 등급 선택

AI 기능은 `GEMINI_API_KEY` 환경변수가 있어야 동작합니다. 없으면 AI API만 503을 돌려주고 나머지는 그대로 동작합니다. Gemini 무료 등급은 분당 5회·하루 20회이고, 변형 질문 생성과 답안 평가가 각각 1번씩 씁니다. 원래 질문만 풀면 카드 1장에 1번입니다.
- API 문서: http://127.0.0.1:8000/docs

설정은 환경변수로 바꿉니다. [.env.example](.env.example) 참고.

## DB 스키마 변경

앱은 시작할 때 DB를 최신 리비전으로 자동 마이그레이션합니다. 모델을 바꿨다면 리비전을 만들고 검토한 뒤 커밋하세요.

```bash
alembic revision --autogenerate -m "설명"
```

## 문서

- Markdown 개념 형식: [docs/markdown-concept-format.md](docs/markdown-concept-format.md)
- 설계서: [NetRecall_Lab_SDD_v1.1.md](NetRecall_Lab_SDD_v1.1.md)
- 설계서와 다른 점: [develop-memo.md](develop-memo.md)
