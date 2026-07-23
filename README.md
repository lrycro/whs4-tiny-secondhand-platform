# whs4-tiny-secondhand-platform
WHS 4기 Secure Coding 과제 - Tiny Second-hand Shopping Platform 개발

## 로컬 실행

```bash
# 1. 가상환경 생성 (conda 예시 -- venv도 무방)
conda create -n secure-coding python=3.11
conda activate secure-coding

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 환경변수 설정
cp .env.example .env
# .env를 열어 SECRET_KEY를 실제 랜덤 값으로 채우기 (비워두면 프로세스마다
# 랜덤 생성되어 재시작 시 세션이 끊김 -- 로컬 개발 편의를 위해 채워두는 걸 권장)

# 4. 서버 실행 (Flask-SocketIO 앱이라 `flask run`이 아니라 이 명령 사용)
python app.py
# -> http://127.0.0.1:5000
```

관리자 계정이 필요하면 서버를 한 번이라도 실행해서(위 4번, DB 테이블이 생성됨) DB 파일이 만들어진 뒤 아래 "관리자 계정 생성" 절차를 따르세요.

외부에 HTTPS로 데모(ngrok 등)할 때는 [배포 시 주의사항](#배포-시-주의사항)을 먼저 확인하세요.

## 배포 시 주의사항

- `SESSION_COOKIE_SECURE`는 기본값이 `true`(프로덕션 기준)입니다. 로컬 `http://localhost` 개발 환경에서만 `.env`에 `SESSION_COOKIE_SECURE=false`를 설정하세요. **ngrok 등으로 외부에 HTTPS로 배포/데모할 때는 이 오버라이드를 반드시 제거(또는 `true`로 설정)해야 세션 쿠키에 `Secure` 플래그가 적용됩니다.**
- `FLASK_DEBUG`도 기본값이 `false`(프로덕션 기준)입니다. Flask 디버그 모드가 켜져 있으면 에러 발생 시 스택 트레이스/소스코드/원격 코드 실행 콘솔까지 그대로 노출됩니다. 로컬에서 인터랙티브 디버깅이 필요할 때만 `.env`에 `FLASK_DEBUG=true`를 임시로 추가하고, 배포/데모 시에는 반드시 제거하세요.

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

(테스트 실행법, 보안 체크리스트 요약 등 나머지 문서는 11단계에서 정리 예정)
