#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
from multiprocessing import Process
from threading import Thread
import zipfile
from flask import (
    Flask,
    request,
    redirect,
    url_for,
    flash,
    render_template,
    send_file,
    send_from_directory,
    Response,
    jsonify
)
from werkzeug.utils import secure_filename

from server_variables import UPLOAD_FOLDER
from modeling_process import allowed_file, modeling
from app import app, db, user, model, process
from flask_login import current_user, login_required
from bson.objectid import ObjectId

DEBUG = False

@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon",
    )


@app.route("/upload", methods=["POST"])
def upload_file():
    # 전송받은 파일
    print("request", request, file=sys.stderr)
    received_files = request.files.to_dict()
    # 전송받은 사용자 정보
    received_form = request.form.to_dict()

    # 콘솔에 전송 받은 정보들 출력
    print("request files", received_files, file=sys.stderr)
    print("request form", received_form, file=sys.stderr)

    # TODO: 유저 authentication
    # 제공된 계정 정보가 user DB 정보와 일치하지 않는다면 모델링을 허용하지 않음

    # 파일이 존재하지 않는다면
    if "file" not in received_files:
        data = "No file was sent"
        print(data, file=sys.stderr)
        return data, 400

    # 유저 정보가 주어지지 않았다면
    if "userid" not in received_form:
        data = "No required user info sent"
        print(data, file=sys.stderr)
        return data, 400

    received_file = received_files["file"]
    current_userid = received_form["userid"]
    current_token = received_form["usertoken"] if "usertoken" in received_form else None
    current_modelId = received_form["modelid"] if "modelid" in received_form else None
    username = None

    # 파일 이름이 존재하지 않는다면
    if received_file.filename == "":
        data = "No filename provided"
        print(data, file=sys.stderr)
        return data, 400

    # 파일 타입이 zip이 아니라면
    if not allowed_file(received_file.filename):
        data = "Please send file in .zip format"
        print(data, file=sys.stderr)
        return data, 400

    # 이미 해당 유저가 요청한 모델링이 진행중이라면, 추가적인 모델링 생성 요청을 막는다.
    if process.find_one(
            { "$and": [
                {"user": ObjectId(current_userid)},
                {"status": {
                    "$nin": ["complete", "failed"]
                }}
            ]}
        ) is not None:
        data = "Another Modeling Process is Already Running"
        return data, 400

    # 유저 정보가 MongoDB 상에 존재하는지 확인
    # TODO: password 정보도 받아, user authentication 구현하기
    # user authentication 구현은 애플리케이션에서 하도록 하자
    # 현재는 들어온 모든 유저 데이터를 user 테이블에 저장

    current_user = user.find_one({"_id": ObjectId(current_userid)})
    if current_user is None:
        data = "No User info on Database"
        return data, 400
    else: 
        username = current_user["name"]
        useremail = current_user["email"]
        if current_token is not None:
            user.update_one(
                {"_id": ObjectId(current_userid)},
                {"$set": {"deviceToken": current_token}},
            )

    # 모든 조건이 충족되었을 시 모델링 시작
    filename = secure_filename(received_file.filename)
    userpath = os.path.join(UPLOAD_FOLDER, current_userid)
    inputpath = os.path.join(userpath, "input")
    outputpath = os.path.join(userpath, "output")
    userZipFile = os.path.join(inputpath, filename)

    # 업로드 할 파일들이 위치할 폴더 생성
    if not (os.path.isdir(userpath)):
        os.makedirs(os.path.join(userpath), mode=0o777)
    if not (os.path.isdir(inputpath)):
        os.makedirs(os.path.join(inputpath), mode=0o777)
    if not (os.path.isdir(outputpath)):
        os.makedirs(os.path.join(outputpath), mode=0o777)

    # 전송 받은 zip 파일 저장
    received_file.save(userZipFile)
    zip_ref = zipfile.ZipFile(userZipFile, "r")
    # zip 파일 압축 풀기
    zip_ref.extractall(inputpath)
    zip_ref.close()
    # zip 파일 삭제
    os.remove(userZipFile)

    # 모델링 쓰레드 시작
    p = Thread(target=modeling, args=(filename, current_userid, username, useremail, current_token, current_modelId))
    p.start()
    return "Modeling Process Started", 200


@login_required
@app.route("/process")
def render_process():
    processes = process.find({})
    return render_template("process.html", title="Process List", processes=processes)


@login_required
@app.route("/model")
def render_model():
    models = model.find({})
    return render_template("model.html", title="Model List", models=models)


@login_required
@app.route("/user")
def render_user():
    users = user.find({})
    return render_template("user.html", title="User List", users=users)