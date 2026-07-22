from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileSize
from wtforms import IntegerField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

# extension allowlist only (no image-content sniffing) -- fine for this project's
# threat model, but a spoofed-extension upload would slip through; note for the
# step 10 security re-check.
ALLOWED_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "gif", "webp"]


class ProductForm(FlaskForm):
    name = StringField(
        "상품명",
        validators=[
            DataRequired(message="상품명을 입력해주세요."),
            Length(max=200, message="상품명은 200자 이하로 입력해주세요."),
        ],
    )
    description = TextAreaField(
        "설명",
        validators=[Optional(), Length(max=2000, message="설명은 2000자 이하로 입력해주세요.")],
    )
    price = IntegerField(
        "가격",
        validators=[
            DataRequired(message="가격을 입력해주세요."),
            NumberRange(min=0, message="가격은 0 이상이어야 합니다."),
        ],
    )
    photo = FileField(
        "사진",
        validators=[
            Optional(),
            FileAllowed(ALLOWED_IMAGE_EXTENSIONS, message="jpg, jpeg, png, gif, webp 파일만 업로드할 수 있습니다."),
            FileSize(max_size=5 * 1024 * 1024, message="파일 크기는 5MB 이하여야 합니다."),
        ],
    )
    submit = SubmitField("저장")
