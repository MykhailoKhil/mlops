import os
import sys
import tempfile

import mlflow
import pandas as pd
from sklearn.datasets import make_classification
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


STEPS = {"prepare": prepare}

if __name__ == "__main__":
    STEPS[sys.argv[1]](*sys.argv[2:])
