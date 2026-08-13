FROM python:3.12-slim

LABEL daedalmap.benchmark.contract="campaign-v1"

COPY routing_score.py /opt/bench/routing_score.py
COPY run_routing_benchmark.py /opt/bench/run_routing_benchmark.py
COPY routing_cases.json /opt/bench/routing_cases.json

ENTRYPOINT ["python3", "/opt/bench/run_routing_benchmark.py"]
