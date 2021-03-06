import sys
from flask import render_template, flash, redirect, url_for, request
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.urls import url_parse
from app import app
from models import Admin
from forms import LoginForm


@app.route("/")
@app.route("/index")
def index():
    if not current_user.is_authenticated:
        return redirect(url_for("login"))
    return render_template("index.html", title="Admin Console")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    try:
        form = LoginForm()
        if form.validate_on_submit():
            user = Admin.query.filter_by(adminId=form.username.data).first()
            if user is None or not user.check_password(form.password.data):
                flash("Invalid username or password")
                return redirect(url_for("login"))
            login_user(user, remember=form.remember_me.data)
            flash("Logged in successfully")
            # next_page = request.args.get("next")
            # if not next_page or url_parse(next_page).netloc != "":
            #     next_page = url_for("/")
            return redirect(url_for("index"))
    except Exception as e:
        print(e, file=sys.stderr)
        flash("Exception Occurred!")
    return render_template("login.html", title="Sign In", form=form)


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("index"))
