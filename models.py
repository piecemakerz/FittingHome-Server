from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


class Admin(UserMixin, db.Model):
    __tablename__ = "admin"
    id = db.Column(db.Integer, primary_key=True)
    adminId = db.Column(db.String(64), unique=True)
    adminPassword_hash = db.Column(db.String(128))

    def set_password(self, password):
        self.adminPassword_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.adminPassword_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(user_id)
