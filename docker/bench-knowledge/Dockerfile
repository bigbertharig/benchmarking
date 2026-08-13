FROM python:3.13-slim

LABEL daedalmap.benchmark.contract="campaign-v1"

COPY run_knowledge_benchmark.py /opt/bench/run_knowledge_benchmark.py
COPY knowledge_cases.json /opt/bench/knowledge_cases.json

WORKDIR /opt/bench
ENTRYPOINT ["python3", "/opt/bench/run_knowledge_benchmark.py"]
