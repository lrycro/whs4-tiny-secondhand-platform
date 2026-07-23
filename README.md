# whs4-tiny-secondhand-platform
WHS 4기 Secure Coding 과제 - Tiny Second-hand Shopping Platform 개발

## 배포 시 주의사항

- `SESSION_COOKIE_SECURE`는 기본값이 `true`(프로덕션 기준)입니다. 로컬 `http://localhost` 개발 환경에서만 `.env`에 `SESSION_COOKIE_SECURE=false`를 설정하세요. **ngrok 등으로 외부에 HTTPS로 배포/데모할 때는 이 오버라이드를 반드시 제거(또는 `true`로 설정)해야 세션 쿠키에 `Secure` 플래그가 적용됩니다.**

(나머지 환경설정/실행법은 10~11단계에서 정리 예정)
