FROM python:3.12-slim
RUN pip install --no-cache-dir mlflow-skinny==3.18.0 scikit-learn==1.9.1 pandas==3.1.1 pyarrow==26.0.1 skops==0.16.0
# mlflow probes for git; the image has none, so silence the warning
ENV GIT_PYTHON_REFRESH=quiet
WORKDIR /app
COPY ml/pipeline.py .
