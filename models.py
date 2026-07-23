import enum
from datetime import datetime, timedelta, timezone

import bcrypt
from flask_login import UserMixin

from extensions import db

LOGIN_LOCK_THRESHOLD = 5
LOGIN_LOCK_DURATION = timedelta(minutes=15)
REPORT_BLOCK_THRESHOLD = 5


def _utcnow():
    # naive UTC on purpose: SQLite's DATETIME column round-trip through SQLAlchemy does
    # not reliably preserve tzinfo, so keep everything naive-but-UTC to avoid ending up
    # with a mix of aware/naive datetimes that can't be compared (locked_until checks).
    return datetime.now(timezone.utc).replace(tzinfo=None)


def format_kst_time(dt):
    # single formatting helper shared by the Jinja filter (server-rendered chat
    # history) and the Socket.IO payloads (live messages), so both ever show the
    # exact same "HH:MM" string instead of the client trying to parse/convert an
    # ISO timestamp itself (naive-UTC strings are ambiguous across browsers)
    if dt is None:
        return ""
    return (dt + timedelta(hours=9)).strftime("%H:%M")


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class ProductStatus(str, enum.Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"


class ReportTargetType(str, enum.Enum):
    USER = "user"
    PRODUCT = "product"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    bio = db.Column(db.Text, nullable=True)
    balance = db.Column(db.Integer, nullable=False, default=0)
    role = db.Column(db.Enum(UserRole), nullable=False, default=UserRole.USER)
    status = db.Column(db.Enum(UserStatus), nullable=False, default=UserStatus.ACTIVE)
    report_count = db.Column(db.Integer, nullable=False, default=0)
    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    products = db.relationship("Product", backref="seller", lazy=True)

    __table_args__ = (db.CheckConstraint("balance >= 0", name="ck_user_balance_non_negative"),)

    def set_password(self, raw_password):
        self.password_hash = bcrypt.hashpw(
            raw_password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    def check_password(self, raw_password):
        return bcrypt.checkpw(
            raw_password.encode("utf-8"), self.password_hash.encode("utf-8")
        )

    def is_admin(self):
        return self.role == UserRole.ADMIN

    def is_active_status(self):
        return self.status == UserStatus.ACTIVE

    def is_locked(self):
        return self.locked_until is not None and self.locked_until > _utcnow()

    def register_failed_login(self):
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= LOGIN_LOCK_THRESHOLD:
            self.locked_until = _utcnow() + LOGIN_LOCK_DURATION
            self.failed_login_attempts = 0

    def reset_failed_login(self):
        self.failed_login_attempts = 0
        self.locked_until = None

    def register_report(self):
        self.report_count += 1
        if self.report_count >= REPORT_BLOCK_THRESHOLD:
            self.status = UserStatus.SUSPENDED

    def __repr__(self):
        return f"<User {self.id} {self.username}>"


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Integer, nullable=False)
    image_filename = db.Column(db.String(255), nullable=True)
    seller_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    status = db.Column(db.Enum(ProductStatus), nullable=False, default=ProductStatus.ACTIVE)
    report_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    __table_args__ = (db.CheckConstraint("price >= 0", name="ck_product_price_non_negative"),)

    def register_report(self):
        self.report_count += 1
        if self.report_count >= REPORT_BLOCK_THRESHOLD:
            self.status = ProductStatus.BLOCKED

    def __repr__(self):
        return f"<Product {self.id} {self.name}>"


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    target_type = db.Column(db.Enum(ReportTargetType), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    reporter = db.relationship("User", foreign_keys=[reporter_id])

    __table_args__ = (
        db.CheckConstraint("length(reason) >= 1 AND length(reason) <= 500", name="ck_report_reason_length"),
    )

    def __repr__(self):
        return f"<Report {self.id} {self.target_type.value}:{self.target_id}>"


class ChatThread(db.Model):
    """A 1:1 chat scoped to one product: always between that product's seller and
    one prospective buyer (matching real marketplace apps -- the same two people
    get a SEPARATE thread per product, not one continuous DM regardless of item)."""

    __tablename__ = "chat_threads"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    product = db.relationship("Product")
    buyer = db.relationship("User", foreign_keys=[buyer_id])

    __table_args__ = (
        db.UniqueConstraint("product_id", "buyer_id", name="uq_chat_thread_product_buyer"),
    )

    def seller_id(self):
        return self.product.seller_id

    def is_participant(self, user_id):
        return user_id in (self.buyer_id, self.seller_id())

    def other_party_id(self, current_user_id):
        return self.buyer_id if current_user_id == self.seller_id() else self.seller_id()

    def room_name(self):
        return f"chat_thread_{self.id}"

    def __repr__(self):
        return f"<ChatThread {self.id} product={self.product_id} buyer={self.buyer_id}>"


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    thread_id = db.Column(db.Integer, db.ForeignKey("chat_threads.id"), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    sender = db.relationship("User", foreign_keys=[sender_id])
    thread = db.relationship("ChatThread", backref=db.backref("messages", lazy=True))

    __table_args__ = (
        db.CheckConstraint("length(content) >= 1 AND length(content) <= 1000", name="ck_message_content_length"),
    )

    def __repr__(self):
        return f"<Message {self.id} thread={self.thread_id}>"


class GlobalMessage(db.Model):
    """F9's all-users broadcast chat -- deliberately a separate model from Message
    (which is now scoped to one ChatThread each) rather than a nullable thread_id,
    since there's exactly one global room and no per-thread concept applies to it."""

    __tablename__ = "global_messages"

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    sender = db.relationship("User", foreign_keys=[sender_id])

    __table_args__ = (
        db.CheckConstraint(
            "length(content) >= 1 AND length(content) <= 1000", name="ck_global_message_content_length"
        ),
    )

    def __repr__(self):
        return f"<GlobalMessage {self.id}>"


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    receiver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    amount = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    sender = db.relationship("User", foreign_keys=[sender_id])
    receiver = db.relationship("User", foreign_keys=[receiver_id])

    __table_args__ = (db.CheckConstraint("amount > 0", name="ck_transaction_amount_positive"),)

    def __repr__(self):
        return f"<Transaction {self.id} {self.sender_id}->{self.receiver_id} {self.amount}>"


class AdminActionLog(db.Model):
    __tablename__ = "admin_action_logs"

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False)
    target_type = db.Column(db.String(20), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    admin = db.relationship("User", foreign_keys=[admin_id])

    def __repr__(self):
        return f"<AdminActionLog {self.id} {self.action} {self.target_type}:{self.target_id}>"
