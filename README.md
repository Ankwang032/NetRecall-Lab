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
- `GET /reviews/due`: 지금 복습할 카드 (개념의 질문 1개 = 카드 1장)
- `POST /reviews` `{"card_id": 1, "rating": 3}`: 평가 반영 (1=Again, 2=Hard, 3=Good, 4=Easy)
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
