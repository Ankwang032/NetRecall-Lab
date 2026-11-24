# netrecall-lab

## 개발 환경

```bash
pip install -e ".[dev]"
pytest                  # 실제 실습 배포 테스트는 빠진다
pytest -m lab           # 실제 Containerlab으로 배포하는 테스트 (아래 "실습" 준비가 필요)
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
- `POST /cards/{card_id}/questions`: AI가 카드 질문을 변형하고, 별도 호출로 원래 질문 대비 난이도(-2~+2)를 평가
- `POST /questions/{question_id}/answers` `{"answer": "..."}`: AI 답안 평가 (정확성·완전성·논리성·기술적 타당성·응용력)
- `POST /reviews` `{"card_id": 1, "rating": 3}`: 평가 반영 (1=Again, 2=Hard, 3=Good, 4=Easy). 등급은 AI 점수와 별개로 직접 고릅니다

학습 흐름: `GET /reviews/due` → 원래 질문 출제 → 답안 제출 → 피드백 확인 → (필요하면) 변형 질문 → 답안 제출 → 등급 선택

AI 기능은 `GEMINI_API_KEY` 환경변수가 있어야 동작합니다. 없으면 AI API만 503을 돌려주고 나머지는 그대로 동작합니다. Gemini 무료 등급은 분당 5회·하루 20회이고, 변형 질문은 2번(생성, 난이도 평가), 답안 평가는 1번 씁니다. 원래 질문만 풀면 카드 1장에 1번입니다.
- API 문서: http://127.0.0.1:8000/docs

설정은 환경변수로 바꿉니다. [.env.example](.env.example) 참고.

## 실습 (Containerlab)

시스템은 설정이 빈 토폴로지를 배포하고, 학습자가 노드에 접속해 직접 설정하면 검사합니다. 실습은 한 번에 하나만 진행하고, 시간 제한(기본 60분)이 지나면 다음 실습 명령·API 호출 때 정리합니다.

준비 (한 번, Linux 또는 WSL):

```bash
# Containerlab 0.83.0: 릴리스의 .deb를 받아 체크섬 확인 후 설치. sudo 없이 쓰도록 clab_admins 그룹을 만든다
V=0.83.0
curl -fsSLO https://github.com/srl-labs/containerlab/releases/download/v$V/containerlab_${V}_linux_amd64.deb
curl -fsSLO https://github.com/srl-labs/containerlab/releases/download/v$V/checksums.txt
grep "containerlab_${V}_linux_amd64.deb" checksums.txt | sha256sum -c -
sudo dpkg -i containerlab_${V}_linux_amd64.deb
sudo usermod -aG clab_admins,docker $USER   # 다시 로그인해야 적용 (그 전에는 sg clab_admins -c "명령")

# 노드 이미지
docker build -t netrecall/lab-host:1 integrations/labs/images/host
docker pull quay.io/frrouting/frr:10.7.1
```

`clab_admins` 그룹에 든 사용자는 Containerlab을 root 권한으로 돌릴 수 있습니다. 학습자 본인만 넣으세요.

명령줄 (서버 없이):

```bash
python -m backend.cli --env-file .env lab list
python -m backend.cli --env-file .env lab start LAB-001   # 목표·대역·접속 명령을 보여 준다
docker exec -it clab-nr-1-pc1 sh                          # 다른 터미널에서 직접 설정
python -m backend.cli --env-file .env lab verify          # 검사별 결과. 통과하면 종료 코드 0
python -m backend.cli --env-file .env lab finish          # 정리
```

API:

- `GET /labs`: 실습 시나리오 목록 (`lab_scenarios/`)
- `POST /labs/{id}/runs` (`{"evaluation_id": 3}`은 선택): 배포. 응답에 목표, 대역, 배포한 주소, 노드별 접속 명령. 진행 중인 실습이 있으면 409, 배포 실패는 502
- `GET /lab-runs/current`: 진행 중인 실습 (없으면 `null`), `GET /lab-runs/{id}`
- `POST /lab-runs/{id}/attempts`: 검증. 검사별 통과 여부·이유·출력. 학습자에게 주지 않은 목표 주소는 `[pc1:eth1 목표 주소]`로 가린다
- `POST /lab-runs/{id}/finish`: 마지막 상태를 남기고 정리

토폴로지 파일은 `NETRECALL_LAB_DIR`(기본 `~/.netrecall/labs`)에 생깁니다. 앱은 시작할 때 이 DB가 만든 실습 중 끝났는데 남은 컨테이너를 지웁니다.

## DB 스키마 변경

앱은 시작할 때 DB를 최신 리비전으로 자동 마이그레이션합니다. 모델을 바꿨다면 리비전을 만들고 검토한 뒤 커밋하세요.

```bash
alembic revision --autogenerate -m "설명"
```

## 문서

- Markdown 개념 형식: [docs/markdown-concept-format.md](docs/markdown-concept-format.md)
- 실습 시나리오 형식: [docs/lab-scenario-format.md](docs/lab-scenario-format.md)
- 설계서와 다른 점: [develop-memo.md](develop-memo.md)
