import sys
import os
import shutil
from datetime import datetime
from subprocess import Popen
from multiprocessing import current_process
import threading
from bson.objectid import ObjectId
import uuid
import boto3
import urllib.parse
import zipfile
from firebase_admin import messaging
from pyfcm import FCMNotification
import requests
import json

from modeling_module import *
from server_variables import (
    UPLOAD_FOLDER,
    ALLOWED_EXTENSIONS,
    WEBSITE_DOMAIN,
)
from modeling_variables import INVERSE
from app import user, model, process
from config import ACCESS_KEY, SECRET_KEY, S3_LOCATION, S3_BUCKET_NAME, FIREBASE_SERVER_KEY

# ZIP 파일만 허용
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def modeling(filename, current_userid, username, useremail, current_token, current_modelId):
    try:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'key=' + FIREBASE_SERVER_KEY,
        }

        user_objectId = ObjectId(current_userid)
        pstep = None
        userpath = os.path.join(UPLOAD_FOLDER, current_userid)
        inputpath = os.path.join(userpath, "input")
        outputpath = os.path.join(userpath, "output")

        process.create_index("date", expireAfterSeconds=86400)
        processInsertResult = process.insert_one(
            {
                "fileName": filename,
                "userId": user_objectId,
                "pid": threading.currentThread().ident,
                "status": "ready",
                "step": 0,
                "date": datetime.utcnow(),
            }
        )
        processId = processInsertResult.inserted_id

        has_colour = has_colours(sys.stdout)
        conf = ConfContainer(inputpath, outputpath)
        steps = stepsStore()
        setArgs(conf, steps)
        setConfs(conf)
        steps.apply_conf(conf)

        print("# Using input dir  :  {}".format(conf.input_dir), file=sys.stderr)
        print("#       output_dir :  {}".format(conf.output_dir), file=sys.stderr)
        print("# First step  :  {}".format(conf.first_step), file=sys.stderr)
        print("# Last step :  {}".format(conf.last_step), file=sys.stderr)

        step_num = 0

        for cstep in range(conf.first_step, conf.last_step + 1):
            message_title = str(cstep)
            print("first_step: %s cstep: %s last_step %s" % (conf.first_step, cstep, conf.last_step), file=sys.stderr)
            try:
                printout(
                    has_colour, "#{}. {}".format(cstep, steps[cstep].info), effect=INVERSE
                )
            except IndexError:
                print(
                    "There are not enough steps in stepsStore.step_data to get to last_step",
                    file=sys.stderr,
                )
                break

            opt = getattr(conf, str(cstep))
            if opt is not None:
                # add - sign to short options and -- to long ones
                for o in range(0, len(opt), 2):
                    if len(opt[o]) > 1:
                        opt[o] = "-" + opt[o]
                    opt[o] = "-" + opt[o]
            else:
                opt = []

            # Remove steps[cstep].opt options now defined in opt
            for anOpt in steps[cstep].opt:
                if anOpt in opt:
                    idx = steps[cstep].opt.index(anOpt)
                    if DEBUG:
                        print(
                            "#\t"
                            + "Remove "
                            + str(anOpt)
                            + " from defaults options at id "
                            + str(idx),
                            file=sys.stderr,
                        )
                    del steps[cstep].opt[idx : idx + 2]

            cmdline = [steps[cstep].cmd] + steps[cstep].opt + opt

            print(cmdline, file=sys.stderr)

            # process 테이블 정보 갱신
            process.update_one(
                {"_id": processId}, {"$set": {"status": "start", "step": step_num}},
            )

            # 현재 모델링 단계 시작
            pStep = subprocess.Popen(cmdline)

            # process 테이블 정보 갱신
            process.update_one(
                {"_id": processId}, {"$set": {"status": "working", "step": step_num}},
            )

            # firebase 메시지 전송
            if current_token is not None:
                message = messaging.Message(
                    data={"message_title": "", "message_body": "", "step": str(step_num), "status": "working", "modelid": current_modelId },
                    token=current_token,
                )
                response = messaging.send(message)
                print(
                    "successfully sent message working on step" + str(step_num),
                    file=sys.stderr,
                )

            # 현재 모델링 단계가 끝날 때 까지 대기
            pStep.wait()

            # 현재 모델링 결과의 output이 제대로 나왔는지 확인
            if check_step_success(step_num, outputpath):
                process.update_one(
                    {"_id": processId},
                    {"$set": {"status": "finished", "step": step_num}},
                )
                message_body = "success"
            else:
                process.update_one(
                    {"_id": processId},
                    {"$set": {"status": "failed", "step": step_num}},
                )
                message_body = "failed"

            if current_token is not None:
                message = messaging.Message(
                    data={"message_title": "", "message_body": "", "step": str(step_num), "status": message_body, "modelid": current_modelId},
                    token=current_token,
                )

                response = messaging.send(message)
                print("successfully sent message result", file=sys.stderr)

            # 현재 모델링 단계가 실패했다면 모델링 쓰레드 종료하기
            if message_body == "failed":
                break

            step_num += 1

        # for 문이 끝까지 실행되었을 때
        else:
            model_path = os.path.join(outputpath, "mvs")
            modelName = username + "_" + str(uuid.uuid4())
            filePath = os.path.join(model_path, "%s.zip" % modelName)

            # zip 파일 생성하기
            zip_result = zipfile.ZipFile(filePath, "w")
            # 모델링 결과물들 중 zip 파일에 넣은 파일들 선정하기
            for folder, subfolders, files in os.walk(model_path):
                for file_inside in files:
                    file_name = str(file_inside)
                    if file_name.endswith("texture.mtl") or file_name.endswith("texture.obj") or file_name.endswith("map_Kd.jpg"):
                        print(file_name, file=sys.stderr)
                        zip_result.write(
                            os.path.join(model_path, file_name),
                            file_name,
                            compress_type=zipfile.ZIP_DEFLATED,
                        )
            zip_result.close()

            # 완성된 모델링 결과물 zip 파일 s3에 업로드하기
            s3 = boto3.client("s3", aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY)
            s3.upload_file(
                filePath,
                S3_BUCKET_NAME,
                "model/{}/{}".format(useremail, modelName + ".zip")
            )

            # 프로세스 테이블에서 현재 프로세스 지우기
            process.update_one(
                    {"_id": processId},
                    {"$set": {"status": "complete"}},
                )

            # 모델 테이블에 현재 생성한 모델 정보 넣기
            uploadLocation = (
                "https://fittinghome.s3.ap-northeast-2.amazonaws.com/model/%s/%s"
                % (useremail, modelName + ".zip")
            )
            modelInsertResult = model.insert_one(
                {
                    "user": user_objectId,
                    "modelName": modelName,
                    "modelLocation": uploadLocation,
                    "uploadDate": datetime.utcnow(),
                }
            )
            modelId = modelInsertResult.inserted_id

            # 유저 테이블에 현재 모델 생성한 유저의 모델 목록 갱신하기
            user.update_one(
                {"_id": user_objectId}, {"$push": {"models": ObjectId(modelId)}}
            )

            # 안드로이드에 현재 생성한 모델을 다운로드 받을 수 있는 링크 제공하기
            message_title = "Download URL"
            message_body = uploadLocation

            if current_token is not None:
                message = messaging.Message(
                    data={"message_title": "모델링 완료됨", "message_body": "다운로드: " + uploadLocation, "link": uploadLocation, "modelid": current_modelId},
                    token=current_token,
                )

                response = messaging.send(message)
                print("Successfully sent message", file=sys.stderr)

            # 업로드 한 zip 파일 서버에서 삭제
            shutil.rmtree(userpath, ignore_errors=True)
    except Exception as e:
        print("Error Occurred", e, file=sys.stderr)
        shutil.rmtree(userpath, ignore_errors=True)
