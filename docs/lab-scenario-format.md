# 실습 시나리오 형식

실습 시나리오는 저장소의 `lab_scenarios/<시나리오 id>/scenario.yaml` 파일입니다. 폴더 하나가 시나리오 하나이고, 폴더 이름과 `id`가 같아야 합니다.
구현: [backend/services/lab_scenario.py](../backend/services/lab_scenario.py) (읽기·렌더링), [integrations/labs/containerlab/topology.py](../integrations/labs/containerlab/topology.py) (토폴로지 파일·정적 검사)

시스템은 설정이 빈 토폴로지를 배포하고, 학습자가 노드에 직접 설정한 결과를 검사합니다. 그래서 시나리오 파일에는 **정답 설정도, 명령도 쓰지 않습니다.** 검사 종류마다 실행할 명령은 코드에 고정되어 있고, 시나리오 파일의 값은 검증한 노드 이름·인터페이스·주소로만 명령 인자에 들어갑니다.

## 예시

```yaml
id: LAB-002
title: 라우터 두 대 너머로 통신하기
type: build
concepts: [NET-010]
time_limit_minutes: 60

parameters:              # 실행마다 무작위로 고른다. 서로 겹치지 않는다
  lan1:    {pool: 10.0.0.0/8, prefix: 24}
  lan2:    {pool: 10.0.0.0/8, prefix: 24}
  transit: {pool: 172.16.0.0/12, prefix: 30}

nodes:
  pc1: {kind: host}
  r1:  {kind: router}
  r2:  {kind: router}
  pc2: {kind: host}

links:
  - [pc1:eth1, r1:eth1]
  - [r1:eth2, r2:eth2]
  - [r2:eth1, pc2:eth1]

preset:                  # 배포할 때 넣는 주소. 나머지는 학습자 몫
  addresses:
    pc1:eth1: lan1.host(10)
    r1:eth1:  lan1.host(1)
    r1:eth2:  transit.host(1)
    r2:eth2:  transit.host(2)
    r2:eth1:  lan2.host(1)
    pc2:eth1: lan2.host(10)

goal: |
  PC1({lan1})과 PC2({lan2})가 서로 ping되게 하라. 동적 라우팅 프로토콜은 쓰지 않는다.

checks:
  - id: pc1-to-pc2
    description: PC1 → PC2 ping
    ping: {from: pc1, to: pc2:eth1}
  - id: r1-route
    description: R1이 LAN2로 갈 때 직접 넣은 경로를 쓴다
    route: {node: r1, to: pc2:eth1, protocol: [static, kernel]}
```

주소 없이 배포하고 학습자가 주소를 정하는 실습은 `preset` 대신 `address` 검사로 주소의 위치를 정합니다. [LAB-001](../lab_scenarios/LAB-001/scenario.yaml)이 그 예입니다.

## 최상위 필드

| 필드 | 필수 | 형식 | 설명 |
|---|---|---|---|
| `id` | 필수 | `LAB-` + 숫자 3자리 이상 | 폴더 이름과 같아야 합니다. 개념 frontmatter의 `labs`가 이 id를 가리킵니다 |
| `title` | 필수 | 문자열 | |
| `type` | 필수 | `build` | 구성 실습. 장애 해결(`troubleshoot`)은 아직 없습니다 |
| `concepts` | 필수 | 개념 id 목록 (1개 이상) | 이 실습이 다루는 개념 |
| `time_limit_minutes` | 선택 | 1~120 정수, 기본 60 | 시간이 지나면 환경을 지웁니다 |
| `parameters` | 선택 | 아래 참고 | 실행마다 고르는 주소 대역 |
| `nodes` | 필수 | 아래 참고 | 1~6개 |
| `links` | 필수 | 아래 참고 | |
| `preset` | 선택 | 아래 참고 | 배포할 때 넣는 설정 |
| `goal` | 필수 | 문자열 | 학습자에게 보여 줄 목표. `{대역 이름}`은 고른 대역(예: `10.37.84.64/27`)으로 바뀝니다 |
| `checks` | 필수 | 아래 참고 (1개 이상) | |

모든 단계에서 정의되지 않은 키는 오류입니다. 오타 난 키가 조용히 무시되는 것을 막고, 이미지·마운트·명령 같은 것이 시나리오에 들어올 자리를 없애기 위해서입니다.

## parameters: 주소 대역

```yaml
parameters:
  net:     {pool: 10.0.0.0/8, prefix: {min: 24, max: 30}}   # 길이도 실행마다 고른다
  transit: {pool: 172.16.0.0/12, prefix: 30}               # 길이 고정
```

- 실행마다 `pool` 안에서 `prefix` 길이의 대역을 무작위로 고릅니다. 외운 설정을 그대로 붙여 넣지 못하게 하기 위해서입니다. 고른 값은 실행 기록에 남습니다.
- 여러 대역은 서로 겹치지 않게 고릅니다. 100번 안에 겹치지 않는 조합을 찾지 못하면 실행을 만들지 못하므로 `pool`을 넉넉하게 잡으세요.
- `pool`은 사설 대역(`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`) 안이어야 합니다.
- `prefix`는 `pool`의 길이 이상, 30 이하입니다. /31·/32에는 "첫 번째·마지막 사용 가능 주소"가 없어서 쓰지 않습니다.

## 주소 식: `<대역>.host(n)`

| 식 | 뜻 | `10.37.84.64/27`일 때 |
|---|---|---|
| `net.host(1)` | 첫 번째 사용 가능 주소 | `10.37.84.65/27` |
| `net.host(10)` | 앞에서 10번째 | `10.37.84.74/27` |
| `net.host(-1)` | 마지막 사용 가능 주소 (브로드캐스트 바로 앞) | `10.37.84.94/27` |

- 주소에는 대역의 프리픽스 길이가 붙습니다.
- 읽을 때 **가장 작은 대역**(`prefix`의 최댓값) 기준으로 `n`이 사용 가능 주소 안에 있는지 확인합니다. `/30`이면 `host(1)`, `host(2)`, `host(-1)`, `host(-2)`만 됩니다.
- 길이가 범위로 바뀌는 대역은 범위 안의 모든 길이에서 서로 다른 인터페이스의 주소가 겹치지 않는지도 확인합니다 (예: `/29`에서는 `host(5)`와 `host(-2)`가 같은 주소).

## nodes · links

```yaml
nodes:
  pc1: {kind: host}      # Linux (alpine + iproute2)
  r1:  {kind: router}    # FRRouting
links:
  - [pc1:eth1, r1:eth1]
```

- 노드 이름은 소문자로 시작하는 영문·숫자 15자 이하입니다. 노드 항목에는 `kind`만 씁니다.
- 노드 종류별 이미지와 자원 제한은 코드 한 곳([topology.py](../integrations/labs/containerlab/topology.py))에서 정합니다. host는 CPU 0.5개·메모리 64MB, router는 CPU 1개·메모리 256MB입니다.
- 모든 노드는 관리망 없이 뜹니다. 노드는 실습 링크로만 통신하고, 호스트 네트워크나 인터넷에 닿지 않습니다. 학습자 접속(`docker exec`)과 검사는 그대로 됩니다.
- 인터페이스는 `eth1`부터 씁니다. `eth0`은 관리망 자리라 쓰지 않습니다. 인터페이스 하나는 링크 하나에만 씁니다.

## preset: 배포할 때 넣는 설정

```yaml
preset:
  addresses:
    r1:eth1: lan1.host(1)
```

- 지금은 `addresses`(인터페이스 주소)만 있습니다. 항목 종류마다 실행할 명령은 코드에 고정되어 있습니다.
- 인터페이스는 `links`에 있어야 합니다.

## checks: 검사

```yaml
checks:
  - id: pc1-to-pc2                 # 소문자·숫자·-, 시나리오 안에서 겹치지 않게
    description: PC1 → PC2 ping    # 결과 화면에 보여 줄 설명
    ping: {from: pc1, to: pc2:eth1}
```

검사 하나에 종류 하나(`ping`, `route`, `address`)만 씁니다. 검사는 **최종 상태만** 봅니다. 목표를 만족하면 어떤 방법으로 설정했든 통과합니다.

| 종류 | 형식 | 통과 조건 |
|---|---|---|
| `ping` | `{from: 노드, to: 노드:인터페이스}` | `from`에서 `to` 주소로 3번 보내 1번 이상 응답이 온다. 응답 대기는 한 번에 1초. 첫 패킷은 ARP 때문에 실패할 수 있어 1번만 요구합니다 |
| `route` | `{node: 노드, to: 노드:인터페이스, protocol: [...]}` | `node`에서 `to` 주소로 경로를 **조회**했을 때 고른 경로(최장 일치)가 있다. 라우터는 그 경로가 선택·설치 상태이고 프로토콜이 `protocol` 목록에 있어야 합니다. 정확히 같은 프리픽스를 요구하지 않으므로 기본 경로나 요약 경로로 풀어도 통과합니다 |
| `address` | `{interface: 노드:인터페이스, address: 주소 식}` | 그 인터페이스에 그 주소와 프리픽스 길이가 있다. 같은 인터페이스에 다른 주소가 더 있어도 됩니다 |

- `to`는 주소가 아니라 인터페이스로 씁니다. 그 인터페이스의 주소는 `preset.addresses`나 `address` 검사에서 정해져 있어야 합니다. 둘 다 같은 인터페이스를 정하면 주소가 같아야 합니다.
- `route.protocol`
  - 라우터는 생략하면 `[static, kernel]`입니다. vtysh로 넣은 정적 경로는 `static`, `ip route add`로 넣은 경로는 FRRouting이 `kernel`로 표시합니다. 둘 다 직접 넣은 정적 경로입니다. 막아야 하는 것은 동적 라우팅(`ospf`, `bgp` 등)입니다.
  - 고를 수 있는 값: `kernel`, `connected`, `local`, `static`, `ospf`, `bgp`, `rip`, `isis`
  - Linux 노드(`host`)에는 쓸 수 없습니다. Linux의 경로 조회 결과에는 프로토콜이 나오지 않습니다.

**주소 유일성 (자동):** 모든 검증에 자동으로 붙습니다. 검사가 가리키는 주소는 의도한 노드·인터페이스에만 있어야 합니다. 예를 들어 PC1의 `lo`에 PC2 주소를 넣으면 PC1 → PC2 ping이 PC1 안에서 성공하는데, 이런 경우를 실패로 잡습니다.

## 배포 전 정적 검사

실행마다 렌더링한 Containerlab 토폴로지 파일을 배포 직전에 다시 검사합니다. 통과하지 못하면 배포하지 않습니다.

- 실습 이름은 `nr-<실행 id>`입니다. 정리할 때 이 접두사만 지웁니다.
- 노드 1~6개, 노드 항목의 키는 `kind`·`image`·`network-mode`·`cpu`·`memory`뿐입니다. 호스트 경로 마운트(`binds`)나 실행 명령(`exec`)은 들어갈 수 없습니다.
- 이미지는 노드 종류별로 정한 것만, `network-mode`는 `none`, 자원 제한은 노드 종류별 값과 같아야 합니다.
- 링크 끝점은 있는 노드의 `ethN`이고, 한 번씩만 씁니다.
