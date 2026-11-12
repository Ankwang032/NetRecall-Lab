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

관리자가 라우팅 테이블에 경로를 직접 입력하는 방식이다.
라우터는 패킷의 목적지 IP를 라우팅 테이블과 비교해, 가장 길게 일치하는 경로(longest prefix match)를 골라 전달한다.

정적 경로는 다음 정보로 구성된다.

- 목적지 네트워크와 접두사 길이 (예: `192.168.20.0/24`)
- 다음 홉(next hop) 주소 또는 출구 인터페이스

Linux 예:

```bash
ip route add 192.168.20.0/24 via 10.0.0.2 dev eth1
ip route add default via 10.0.0.1
```

## Default Route

`0.0.0.0/0`은 모든 목적지와 일치하지만 접두사가 가장 짧으므로, 더 구체적인 경로가 없을 때만 사용된다.

## 장단점

- 장점: 동작이 예측 가능하고, 라우팅 프로토콜 부하가 없다.
- 단점: 링크 장애나 토폴로지 변경에 자동으로 대응하지 못한다. 경로가 많아지면 관리가 어렵다.

## 왕복 경로

통신은 양방향이다. PC1에서 PC2로 가는 경로뿐 아니라 PC2에서 PC1로 돌아오는 경로도 있어야 ping이 성공한다.

## 질문

- 서로 다른 네트워크에 있는 두 PC가 통신하려면 라우터에 어떤 설정이 필요한가?
- 다음 홉 주소를 지정하는 경우와 출구 인터페이스만 지정하는 경우의 차이를 설명하세요.
