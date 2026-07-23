from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired, FileSize
from PIL import Image, UnidentifiedImageError
from wtforms import IntegerField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange, Optional, ValidationError

ALLOWED_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "gif", "webp"]
ALLOWED_IMAGE_FORMATS = {"PNG", "JPEG", "GIF", "WEBP"}


def validate_image_content(form, field):
    # extension allowlist (FileAllowed) only checks the client-supplied filename string,
    # which a malicious upload can trivially fake -- actually parse the file with Pillow
    # to confirm it's a real, decodable image of an allowed format
    file_storage = field.data
    if not file_storage or not file_storage.filename:
        return

    try:
        file_storage.stream.seek(0)
        with Image.open(file_storage.stream) as image:
            image.verify()
            detected_format = image.format
    except (UnidentifiedImageError, OSError):
        raise ValidationError("올바른 이미지 파일이 아닙니다.")
    finally:
        file_storage.stream.seek(0)

    if detected_format not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError("지원하지 않는 이미지 형식입니다.")


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
        # InputRequired (checks the raw submitted value), not DataRequired (checks the
        # coerced value's truthiness) -- DataRequired treats a submitted "0" as "missing"
        # and shows the wrong message instead of accepting it (NumberRange(min=0) allows 0)
        validators=[
            InputRequired(message="가격을 입력해주세요."),
            NumberRange(min=0, message="가격은 0 이상이어야 합니다."),
        ],
    )
    photo = FileField(
        "사진",
        validators=[
            Optional(),
            FileAllowed(ALLOWED_IMAGE_EXTENSIONS, message="jpg, jpeg, png, gif, webp 파일만 업로드할 수 있습니다."),
            FileSize(max_size=5 * 1024 * 1024, message="파일 크기는 5MB 이하여야 합니다."),
            validate_image_content,
        ],
    )
    submit = SubmitField("저장")


class ProductCreateForm(ProductForm):
    # SPEC.md P3/F5: 사진은 상품 등록 시 필수. 수정(ProductForm) 시에는 기존 사진을
    # 유지할 수 있어야 하므로 photo가 선택값이어야 해서, 등록 전용으로 필드를 오버라이드한다.
    photo = FileField(
        "사진",
        validators=[
            FileRequired(message="상품 사진을 등록해주세요."),
            FileAllowed(ALLOWED_IMAGE_EXTENSIONS, message="jpg, jpeg, png, gif, webp 파일만 업로드할 수 있습니다."),
            FileSize(max_size=5 * 1024 * 1024, message="파일 크기는 5MB 이하여야 합니다."),
            validate_image_content,
        ],
    )
