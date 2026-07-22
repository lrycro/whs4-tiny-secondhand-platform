from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Length, Regexp, ValidationError

from models import User

USERNAME_REGEX = r"^[A-Za-z0-9_]{3,20}$"
# bcrypt silently truncates input beyond 72 bytes, so the max length is capped
# at 72 to avoid two different long passwords hashing to the same value.
PASSWORD_REGEX = r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};:'\",.<>/?]).{8,72}$"


class RegistrationForm(FlaskForm):
    username = StringField(
        "아이디",
        validators=[
            DataRequired(message="아이디를 입력해주세요."),
            Regexp(
                USERNAME_REGEX,
                message="아이디는 영문/숫자/밑줄만 사용해 3~20자로 입력해주세요.",
            ),
        ],
    )
    password = PasswordField(
        "비밀번호",
        validators=[
            DataRequired(message="비밀번호를 입력해주세요."),
            Regexp(
                PASSWORD_REGEX,
                message="비밀번호는 영문, 숫자, 특수문자를 포함해 8~72자로 입력해주세요.",
            ),
        ],
    )
    password_confirm = PasswordField(
        "비밀번호 확인",
        validators=[
            DataRequired(message="비밀번호 확인을 입력해주세요."),
            EqualTo("password", message="비밀번호가 일치하지 않습니다."),
        ],
    )
    submit = SubmitField("회원가입")

    def validate_username(self, field):
        if User.query.filter_by(username=field.data).first() is not None:
            raise ValidationError("이미 사용 중인 아이디입니다.")


class LoginForm(FlaskForm):
    username = StringField("아이디", validators=[DataRequired(message="아이디를 입력해주세요.")])
    password = PasswordField(
        "비밀번호",
        validators=[
            DataRequired(message="비밀번호를 입력해주세요."),
            Length(max=72),
        ],
    )
    submit = SubmitField("로그인")
