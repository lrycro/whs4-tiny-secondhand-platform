from flask_wtf import FlaskForm
from wtforms import IntegerField, StringField, SubmitField
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange

from models import CHARGE_MAX_AMOUNT


class TransferForm(FlaskForm):
    receiver_username = StringField(
        "받는 사람 아이디",
        validators=[DataRequired(message="받는 사람 아이디를 입력해주세요."), Length(max=50)],
    )
    amount = IntegerField(
        "송금액",
        # InputRequired (checks the raw submitted value), not DataRequired (checks the
        # coerced value's truthiness) -- DataRequired would treat a submitted "0" as
        # "missing" and show the wrong message instead of falling through to NumberRange
        validators=[
            InputRequired(message="송금액을 입력해주세요."),
            NumberRange(min=1, message="송금액은 1원 이상이어야 합니다."),
        ],
    )
    submit = SubmitField("송금하기")


class ChargeForm(FlaskForm):
    amount = IntegerField(
        "충전 금액",
        validators=[
            InputRequired(message="충전 금액을 입력해주세요."),
            NumberRange(
                min=1,
                max=CHARGE_MAX_AMOUNT,
                message=f"충전 금액은 1원 이상 {CHARGE_MAX_AMOUNT:,}원 이하여야 합니다.",
            ),
        ],
    )
    submit = SubmitField("충전하기")
