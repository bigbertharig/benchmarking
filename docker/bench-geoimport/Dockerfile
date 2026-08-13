FROM python:3.12-slim

LABEL daedalmap.benchmark.contract="campaign-v1"

COPY run_geoimport_benchmark.py /opt/bench/run_geoimport_benchmark.py
COPY geoimport_cases.json /opt/bench/geoimport_cases.json
COPY geoimport_system_prompt.md /opt/bench/geoimport_system_prompt.md

ENTRYPOINT ["python3", "/opt/bench/run_geoimport_benchmark.py"]
