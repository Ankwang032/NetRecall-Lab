import pytest

from tests.fakes import FakeLabRuntime


@pytest.fixture(autouse=True)
def no_real_lab_runtime(monkeypatch):
    """앱·CLI를 쓰는 테스트가 진짜 Docker의 실습을 건드리지 않게 한다 (앱은 시작할 때 남은 실습을 정리한다).

    실제 배포 테스트(pytest -m lab)는 런타임을 직접 만들므로 영향이 없다.
    """
    monkeypatch.setattr("backend.main.containerlab_from_env", FakeLabRuntime)
    monkeypatch.setattr("backend.cli.containerlab_from_env", FakeLabRuntime)
