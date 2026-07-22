import enum
from datetime import datetime, timezone

import bcrypt
from flask_login import UserMixin

from extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


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
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    products = db.relationship("Product", backref="seller", lazy=True)

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

    def __repr__(self):
        return f"<User {self.id} {self.username}>"


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Integer, nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    status = db.Column(db.Enum(ProductStatus), nullable=False, default=ProductStatus.ACTIVE)
    report_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    __table_args__ = (db.CheckConstraint("price >= 0", name="ck_product_price_non_negative"),)

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

    def __repr__(self):
        return f"<Report {self.id} {self.target_type.value}:{self.target_id}>"


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    # 'global' for the all-user chat, 'dm_<uid1>_<uid2>' (uid1 < uid2) for 1:1 chat
    room = db.Column(db.String(100), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    sender = db.relationship("User", foreign_keys=[sender_id])

    def __repr__(self):
        return f"<Message {self.id} room={self.room}>"


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
