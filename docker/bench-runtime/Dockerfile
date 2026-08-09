FROM python:3.12-slim

COPY run_runtime_benchmark.py /opt/bench/run_runtime_benchmark.py
COPY runtime_cases.json /opt/bench/runtime_cases.json

ENTRYPOINT ["python3", "/opt/bench/run_runtime_benchmark.py"]
