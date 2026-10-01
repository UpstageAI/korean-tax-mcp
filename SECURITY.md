# Security

- 이 서버는 읽기 전용입니다. 공개 자료(국세법령정보시스템·법제처)를 조회하고, 키는 사용자 환경변수로만 받습니다.
- 키(`LAW_OC`, `UPSTAGE_API_KEY`)는 로그·캐시에 저장하지 않습니다. 캐시(`~/.cache/korean-tax-mcp`)에는 공개 조회 결과만 저장됩니다.
- 보안 문제는 공개 이슈 대신 GitHub의 "Report a vulnerability"(Security Advisories)로 알려 주세요.
