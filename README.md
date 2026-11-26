# netrecall-lab

## 개발 환경

```bash
pip install -e ".[dev]"
pytest                  # 실제 실습 배포 테스트는 빠진다
pytest -m lab           # 실제 Containerlab으로 배포하는 테스트, 기준 풀이·오답 포함 (아래 "실습" 준비가 필요)
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
  - 실습(`/labs`): 아래 "실습" 절의 준비가 필요합니다. 도움 수준을 골라 시작 → 화면 안 터미널이나 자기 터미널에서 노드에 접속해 설정 → 검증·힌트 → 끝내기
  - 화면 경로(`/labs` 등)는 API 경로와 겹칩니다. 브라우저 주소창으로 열면(Accept: text/html) 화면을, 화면의 요청에는 API 응답을 줍니다
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
python -m backend.cli --env-file .env lab start LAB-001   # 목표·대역·접속 명령을 보여 준다 (--level easy|normal|hard)
docker exec -it clab-nr-1-pc1 sh                          # 다른 터미널에서 직접 설정
python -m backend.cli --env-file .env lab verify          # 검사별 결과. 통과하면 종료 코드 0
python -m backend.cli --env-file .env lab hint 3          # 3번 검사의 힌트를 한 단계 더 (번호를 빼면 처음 실패한 검사)
python -m backend.cli --env-file .env lab finish          # 정리
```

API:

- `GET /labs`: 실습 시나리오 목록 (`lab_scenarios/`)과 시나리오별 마지막 실행(`last_run`)
- `POST /labs/{id}/runs` (`{"evaluation_id": 3, "level": "normal"}` 모두 선택): 배포. `level`은 도움 수준으로 `easy`(힌트 3단계)·`normal`(2단계)·`hard`(힌트 없음, 끝낼 때까지 검사 목록·검사별 결과를 숨김). 응답에 목표, 대역, 배포한 주소, 노드별 접속 명령. 진행 중인 실습이 있으면 409, 배포 실패는 502
- `GET /lab-runs/current`: 진행 중인 실습 (없으면 `null`), `GET /lab-runs/{id}`. 링크(`links`), 마지막 검증 결과(`last_attempt`), 지금까지 연 힌트(`hints`)도 준다 (새 단계는 열지 않음)
- `POST /lab-runs/{id}/attempts`: 검증. 검사별 통과 여부·이유·출력. 학습자에게 주지 않은 목표 주소는 `[pc1:eth1 목표 주소]`로 가린다
- `POST /lab-runs/{id}/hints` (`{"check_id": "pc2-route"}`은 선택): 힌트를 한 단계 더 연다. 검사를 빼면 마지막 검증에서 처음 실패한 검사. 본 힌트는 기록에 남는다
- `POST /lab-runs/{id}/finish`: 마지막 상태를 남기고 정리
- `POST /lab-runs/{id}/terminal-tickets` (`{"node": "r1", "shell": "vtysh"}`, `shell`은 선택): 웹 터미널 발급표(30초, 1회용). Linux 노드는 `sh`, 라우터는 `vtysh`(기본)·`sh`
- WebSocket `/lab-runs/{id}/terminal?ticket=...`: 웹 터미널. 서버가 노드 접속 명령(`docker exec -it ...`)을 PTY에서 실행한다. Origin이 이 서버 주소가 아니거나 발급표가 맞지 않거나 끝난 실습이면 거절한다. 시간 제한이 되면 닫는다

웹 터미널: 실습 화면에서 노드 버튼이나 토폴로지 그림의 노드를 누르면 화면 안에 터미널이 열립니다. 자기 터미널에서 접속 명령을 쳐도 같은 노드에 붙습니다. 서버는 `127.0.0.1`에만 띄우고, Codespaces에서는 포트를 Public으로 바꾸지 마세요(설계서 §D-8).

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
