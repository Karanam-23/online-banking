from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
import datetime, random, string

db = SQLAlchemy()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128))
    email = db.Column(db.String(256), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False)
    accounts = db.relationship("Account", backref="user", lazy=True)

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    number = db.Column(db.String(64), unique=True, default=lambda: "AC" + ''.join(random.choice(string.digits) for _ in range(10)))
    balance = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(8), default="INR")
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    transactions = db.relationship("Transaction", backref="account", lazy=True)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("account.id"))
    amount = db.Column(db.Float)
    type = db.Column(db.String(64))
    category = db.Column(db.String(64), nullable=True)
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class VirtualCard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    number = db.Column(db.String(32))
    expiry = db.Column(db.String(8))
    cvv = db.Column(db.String(8))
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class ScheduledTransfer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    from_account_id = db.Column(db.Integer, db.ForeignKey("account.id"))
    to_account_id = db.Column(db.Integer, db.ForeignKey("account.id"))
    from_account = db.relationship("Account", foreign_keys=[from_account_id], backref="scheduled_out")
    to_account = db.relationship("Account", foreign_keys=[to_account_id], backref="scheduled_in")
    amount = db.Column(db.Float)
    execute_at = db.Column(db.DateTime)
    status = db.Column(db.String(32), default="PENDING")
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
