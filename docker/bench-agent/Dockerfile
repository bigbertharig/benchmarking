FROM python:3.12-slim

LABEL daedalmap.benchmark.contract="campaign-v1"

COPY agent_harness.py /opt/bench/agent_harness.py
COPY run_agent_benchmark.py /opt/bench/run_agent_benchmark.py
COPY agent_cases.json /opt/bench/agent_cases.json

ENTRYPOINT ["python3", "/opt/bench/run_agent_benchmark.py"]
