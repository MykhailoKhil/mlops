FROM python:3.12-slim
RUN pip install --no-cache-dir mlflow-skinny==3.18.0 scikit-learn==1.9.1 pandas==3.1.1 skops==0.16.0 \
    fastapi==0.162.2 uvicorn==0.54.0 prometheus-fastapi-instrumentator==8.1.0
ENV GIT_PYTHON_REFRESH=quiet
WORKDIR /app
COPY ml/serve.py .
CMD ["uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8000"]
