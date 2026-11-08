import os
import sys
import tempfile

import mlflow
import pandas as pd
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException
from sklearn.datasets import load_breast_cancer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split

mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
mlflow.set_experiment("classifier")

MODEL_NAME = "classifier"
ALIAS = "candidate"  # passed the quality gate; it only reaches prod when a PR pins its version in git
DRIFT_EXIT_CODE = 10  # distinct from 1 (any uncaught exception) so a crash is never mistaken for drift
SEED = 42  # fixed split seed; drift checks must sample from this same dataset, never from a different one


def prepare():
    df = load_breast_cancer(as_frame=True).frame  # real data, bundled with sklearn (no download)
    y = df["target"]
    train, test = train_test_split(df, test_size=0.2, random_state=SEED, stratify=y)
    with mlflow.start_run(run_name="pipeline") as run:
        d = tempfile.mkdtemp()
        train.to_parquet(f"{d}/train.parquet")
        test.to_parquet(f"{d}/test.parquet")
        mlflow.log_artifacts(d, "data")
        mlflow.log_params({"dataset": "breast_cancer", "n_samples": len(df), "n_features": df.shape[1] - 1, "seed": SEED})
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


def register(run_id):
    client = MlflowClient()
    accuracy = client.get_run(run_id).data.metrics["accuracy"]
    version = mlflow.register_model(f"runs:/{run_id}/model", MODEL_NAME)
    try:
        current = client.get_model_version_by_alias(MODEL_NAME, ALIAS)
        current_acc = client.get_run(current.run_id).data.metrics["accuracy"]
    except MlflowException:  # no production alias yet
        current, current_acc = None, -1.0
    # strictly better, so re-registering an equal model does not churn the alias (and the GitOps PR)
    if accuracy > current_acc:
        client.set_registered_model_alias(MODEL_NAME, ALIAS, version.version)
        print(f"v{version.version} is now {ALIAS} (accuracy {accuracy:.4f} > {current_acc:.4f})")
    else:
        print(f"v{version.version} registered, kept v{current.version} as {ALIAS} ({accuracy:.4f} <= {current_acc:.4f})")


def drift(run_id, shift="0", n_shifted="5"):
    from scipy.stats import ks_2samp  # scipy ships with scikit-learn

    d = mlflow.artifacts.download_artifacts(run_id=run_id, artifact_path="data")
    ref = pd.read_parquet(f"{d}/train.parquet").drop(columns="target")
    # same dataset, held-out rows: stands in for production traffic. Never generate "live" data
    # separately (e.g. another random_state): that gives a different distribution and false drift.
    live = pd.read_parquet(f"{d}/test.parquet").drop(columns="target")
    cols = list(ref.columns)[: int(n_shifted)]
    live[cols] = live[cols] + float(shift) * ref[cols].std()  # controlled shift, in reference std units
    # Bonferroni: 30 tests at 0.05 would flag ~1.5 features by chance alone
    alpha = 0.05 / ref.shape[1]
    pvals = {c: ks_2samp(ref[c], live[c]).pvalue for c in ref.columns}
    drifted = {c: p for c, p in pvals.items() if p < alpha}
    print(f"drift: {len(drifted)}/{len(pvals)} features (alpha={alpha:.5f}, shift={shift} std on {len(cols)} features)")
    for c, p in sorted(drifted.items(), key=lambda kv: kv[1]):
        print(f"  {c}: p={p:.2e}")
    if drifted:
        sys.exit(DRIFT_EXIT_CODE)


STEPS = {"prepare": prepare, "train": train, "register": register, "drift": drift}

if __name__ == "__main__":
    STEPS[sys.argv[1]](*sys.argv[2:])
