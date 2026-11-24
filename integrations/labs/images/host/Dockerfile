# 실습 host 노드 (Linux). alpine 기본 ip(busybox)는 JSON 출력(ip -j)이 없어 iproute2를 넣는다.
# ping은 iputils(응답 대기·전체 시간 옵션이 검사 의미와 맞다).
# 빌드: docker build -t netrecall/lab-host:1 integrations/labs/images/host
FROM alpine:3.24@sha256:f59abe656b692d901e184be3445e084786602108599d2a51d229c0f5a48c71bf
RUN apk add --no-cache iproute2 iputils
CMD ["sleep", "infinity"]
