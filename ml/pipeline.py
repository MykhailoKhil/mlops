import os
import sys
import tempfile

import mlflow
import pandas as pd
from sklearn.datasets import make_classification
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split

mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
mlflow.set_experiment("classifier")

N_FEATURES = 20
SEED = 42  # one seed for the whole dataset; drift checks must sample from it, never re-generate


def prepare():
    X, y = make_classification(
        n_samples=5000, n_features=N_FEATURES, n_informative=10, random_state=SEED
    )
    df = pd.DataFrame(X, columns=[f"f{i}" for i in range(N_FEATURES)])
    df["target"] = y
    train, test = train_test_split(df, test_size=0.2, random_state=SEED, stratify=y)
    with mlflow.start_run(run_name="pipeline") as run:
        d = tempfile.mkdtemp()
        train.to_parquet(f"{d}/train.parquet")
        test.to_parquet(f"{d}/test.parquet")
        mlflow.log_artifacts(d, "data")
        mlflow.log_params({"n_samples": len(df), "n_features": N_FEATURES, "seed": SEED})
        # Argo reads this file as the step's output parameter
        open("/tmp/run_id", "w").write(run.info.run_id)
        print(f"run_id={run.info.run_id}")


def train(run_id):
    d = mlflow.artifacts.download_artifacts(run_id=run_id, artifact_path="data")
    train, test = pd.read_parquet(f"{d}/train.parquet"), pd.read_parquet(f"{d}/test.parquet")
    X_train, y_train = train.drop(columns="target"), train["target"]
    X_test, y_test = test.drop(columns="target"), test["target"]
    params = {"n_estimators": 100, "random_state": SEED}
    model = RandomForestClassifier(**params).fit(X_train, y_train)
    pred = model.predict(X_test)
    with mlflow.start_run(run_id=run_id):
        mlflow.log_params(params)
        mlflow.log_metrics({"accuracy": accuracy_score(y_test, pred), "f1": f1_score(y_test, pred)})
        # Tree is the only type skops flags for RandomForest; we trained this model ourselves
        mlflow.sklearn.log_model(
            model, name="model", input_example=X_test.head(2),
            skops_trusted_types=["sklearn.tree._tree.Tree"],
        )
        print(f"trained run_id={run_id} accuracy={accuracy_score(y_test, pred):.4f}")


STEPS = {"prepare": prepare, "train": train}

if __name__ == "__main__":
    STEPS[sys.argv[1]](*sys.argv[2:])
