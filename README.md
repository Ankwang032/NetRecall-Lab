# netrecall-lab

## 개발 환경

```bash
pip install -e ".[dev]"
pytest
python scripts/preview_concepts.py samples/concepts   # DB 반영 없이 개념 폴더 검사
```

## 서버 실행

```bash
uvicorn backend.main:create_app --factory --reload
```

- `POST /sync/markdown` (`?dry_run=true`로 미리보기): 개념 폴더를 DB에 동기화
- `GET /concepts` (`?include_archived=true`), `GET /concepts/{id}`
- API 문서: http://127.0.0.1:8000/docs

설정은 환경변수로 바꿉니다. [.env.example](.env.example) 참고.

## 문서

- Markdown 개념 형식: [docs/markdown-concept-format.md](docs/markdown-concept-format.md)
- 설계서와 다른 점: [develop-memo.md](develop-memo.md)
