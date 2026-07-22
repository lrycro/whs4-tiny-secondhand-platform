from flask_wtf import FlaskForm
from wtforms import PasswordField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, EqualTo, Length, Optional, Regexp

from blueprints.auth.forms import PASSWORD_REGEX


class BioForm(FlaskForm):
    bio = TextAreaField(
        "소개글",
        validators=[Optional(), Length(max=500, message="소개글은 500자 이하로 입력해주세요.")],
    )
    submit_bio = SubmitField("소개글 저장")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField(
        "현재 비밀번호",
        validators=[DataRequired(message="현재 비밀번호를 입력해주세요."), Length(max=72)],
    )
    new_password = PasswordField(
        "새 비밀번호",
        validators=[
            DataRequired(message="새 비밀번호를 입력해주세요."),
            Regexp(
                PASSWORD_REGEX,
                message="비밀번호는 영문, 숫자, 특수문자를 포함해 8~72자로 입력해주세요.",
            ),
        ],
    )
    new_password_confirm = PasswordField(
        "새 비밀번호 확인",
        validators=[
            DataRequired(message="새 비밀번호 확인을 입력해주세요."),
            EqualTo("new_password", message="새 비밀번호가 일치하지 않습니다."),
        ],
    )
    submit_password = SubmitField("비밀번호 변경")
