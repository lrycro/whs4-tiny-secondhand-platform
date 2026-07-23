from flask_wtf import FlaskForm
from wtforms import HiddenField, IntegerField, SubmitField, TextAreaField
from wtforms.validators import AnyOf, DataRequired, Length, NumberRange
from wtforms.widgets import HiddenInput


class ReportForm(FlaskForm):
    target_type = HiddenField(
        validators=[DataRequired(), AnyOf(["user", "product"], message="잘못된 신고 대상입니다.")]
    )
    target_id = IntegerField(
        widget=HiddenInput(), validators=[DataRequired(message="잘못된 신고 대상입니다."), NumberRange(min=1)]
    )
    reason = TextAreaField(
        "신고 사유",
        validators=[
            DataRequired(message="신고 사유를 입력해주세요."),
            Length(max=500, message="신고 사유는 500자 이하로 입력해주세요."),
        ],
    )
    submit = SubmitField("신고하기")
