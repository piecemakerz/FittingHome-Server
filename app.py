import os
import sys
from flask import Flask
import firebase_admin
from firebase_admin import credentials
from pymongo import MongoClient, database, collection
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from werkzeug.debug import DebuggedApplication
from flask_cors import CORS, cross_origin

basedir = os.path.abspath(os.path.dirname(__file__))
dbfile = os.path.join(basedir, "admindb.db")

app = Flask(__name__)
# wsgi 디버깅을 위해 추가
app.wsgi_app = DebuggedApplication(app.wsgi_app, True)
cors = CORS(app)

# SQLAlchemy 데이터베이스 세팅
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + dbfile
app.config["SQLALCHEMY_COMMIT_ON_TEARDOWN"] = True
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config[
    "SECRET_KEY"
] = r"\xcau\\xf4D\x12CB\xbc\xfa-\x0c\x05\x93\xb2\x85my\x9a+pm\xcd8\x16"
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

db = SQLAlchemy(app)
db.create_all()
# Flask-login 세팅
login_manager = LoginManager(app)
# Mongo Atlas 클라우드 데이터베이스 세팅
client = MongoClient(
    "mongodb+srv://hw3053919:hw28397672@cluster0-7yrpp.mongodb.net/test?retryWrites=true&w=majority"
)
mongodb = database.Database(client, "test")
# MongoDB에서 테이블 가져오기
user = collection.Collection(mongodb, "users")
model = collection.Collection(mongodb, "models")
process = collection.Collection(mongodb, "processes")

print("user count" + str(user.count_documents({})), file=sys.stderr)
print("model count" + str(model.count_documents({})), file=sys.stderr)
print("process count" + str(process.count_documents({})), file=sys.stderr)

# firebase 세팅
if not len(firebase_admin._apps):
    cred = credentials.Certificate(
        "/home/worker/3DReconstruction/server/firebase_json/fithome-unity-firebase-adminsdk-f0040-14dde2c50f.json"
    )
    firebase_admin.initialize_app(cred)

import models, server, login_module, modeling_process

if __name__ == "__main__":
    app.run(host="0.0.0.0")
