# whs4-tiny-secondhand-platform
WHS 4기 Secure Coding 과제 - Tiny Second-hand Shopping Platform 개발

## 배포 시 주의사항

- `SESSION_COOKIE_SECURE`는 기본값이 `true`(프로덕션 기준)입니다. 로컬 `http://localhost` 개발 환경에서만 `.env`에 `SESSION_COOKIE_SECURE=false`를 설정하세요. **ngrok 등으로 외부에 HTTPS로 배포/데모할 때는 이 오버라이드를 반드시 제거(또는 `true`로 설정)해야 세션 쿠키에 `Secure` 플래그가 적용됩니다.**

## 관리자(admin) 계정 생성

회원가입 폼으로는 `role`을 절대 `admin`으로 만들 수 없습니다 (폼에 해당 필드 자체가 없고, 서버에서도 항상 기본값 `user`로 생성). 관리자 계정은 아래 두 방법 중 하나로만 만들 수 있습니다.

**방법 1: CLI 명령 (권장)**

```bash
flask create-admin <username> <password>
```

- 아이디가 이미 존재하면 해당 계정을 admin으로 승격
- 존재하지 않으면 admin 계정을 새로 생성

**방법 2: `flask shell`**

```bash
flask shell
```
```python
>>> from extensions import db
>>> from models import User, UserRole
>>> user = User.query.filter_by(username="기존아이디").first()
>>> user.role = UserRole.ADMIN
>>> db.session.commit()
```

(나머지 환경설정/실행법은 10~11단계에서 정리 예정)
