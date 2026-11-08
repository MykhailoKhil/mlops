import logging
import os
from contextlib import asynccontextmanager

import mlflow
import pandas as pd
from fastapi import FastAPI, HTTPException
from prometheus_client import Gauge
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel

MODEL_NAME = os.environ.get("MODEL_NAME", "classifier")
# git is the source of truth for what runs: a bump of this value (via PR) is the promotion
VERSION = os.environ["MODEL_VERSION"]

mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
log = logging.getLogger("serve")

model = None
feature_names: list[str] = []
MODEL_VERSION_METRIC = Gauge("model_version", "Registry version of the model being served")


@asynccontextmanager
async def lifespan(app):
    global model, feature_names
    # no try/except on purpose: a version that fails to load must abort startup, so the pod never
    # turns Ready and the rollout stalls while the previous version keeps serving
    model = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}/{VERSION}")
    feature_names = model.metadata.get_input_schema().input_names()
    MODEL_VERSION_METRIC.set(int(VERSION))
    log.warning("serving %s v%s", MODEL_NAME, VERSION)
    yield


app = FastAPI(lifespan=lifespan)
Instrumentator().instrument(app).expose(app)


class Request(BaseModel):
    features: list[float]


@app.get("/healthz")
def healthz():
    return {"status": "ok", "model_version": VERSION}


@app.post("/predict")
def predict(req: Request):
    if len(req.features) != len(feature_names):  # trust boundary: the model defines the expected width
        raise HTTPException(422, f"expected {len(feature_names)} features, got {len(req.features)}")
    X = pd.DataFrame([req.features], columns=feature_names)
    return {"prediction": int(model.predict(X)[0]), "model_version": VERSION}
