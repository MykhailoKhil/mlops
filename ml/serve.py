import logging
import os
import threading
import time
from contextlib import asynccontextmanager

import mlflow
import pandas as pd
from fastapi import FastAPI, HTTPException
from mlflow import MlflowClient
from prometheus_client import Gauge
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel

MODEL_NAME = os.environ.get("MODEL_NAME", "classifier")
ALIAS = os.environ.get("MODEL_ALIAS", "production")
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "30"))
mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
log = logging.getLogger("serve")

# (model, version, feature names) swapped as one tuple so a request never mixes versions
current = (None, None, None)
MODEL_VERSION = Gauge("model_version", "Registry version of the model being served")


def refresh():
    global current
    version = MlflowClient().get_model_version_by_alias(MODEL_NAME, ALIAS).version
    if version != current[1]:
        # load by number, not alias, so the loaded model is exactly the version we report
        model = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}/{version}")
        current = (model, version, model.metadata.get_input_schema().input_names())
        MODEL_VERSION.set(int(version))
        log.warning("serving %s v%s", MODEL_NAME, version)


def poll():
    while True:
        time.sleep(POLL_SECONDS)
        try:
            refresh()
        except Exception:  # keep serving the old model if the registry is briefly down
            log.exception("model refresh failed")


@asynccontextmanager
async def lifespan(app):
    try:
        refresh()
    except Exception:
        log.exception("initial model load failed; /healthz stays 503 until the poller succeeds")
    threading.Thread(target=poll, daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)
Instrumentator().instrument(app).expose(app)


class Request(BaseModel):
    features: list[float]


@app.get("/healthz")
def healthz():
    if current[0] is None:
        raise HTTPException(503, "model not loaded")
    return {"status": "ok", "model_version": current[1]}


@app.post("/predict")
def predict(req: Request):
    model, version, names = current
    if model is None:
        raise HTTPException(503, "model not loaded")
    if len(req.features) != len(names):  # trust boundary: the model defines the expected width
        raise HTTPException(422, f"expected {len(names)} features, got {len(req.features)}")
    X = pd.DataFrame([req.features], columns=names)
    return {"prediction": int(model.predict(X)[0]), "model_version": version}
