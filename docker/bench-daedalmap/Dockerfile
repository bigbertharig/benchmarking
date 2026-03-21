FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/bench
ENV PATH="/opt/bench/bin:$PATH"

COPY requirements.txt /opt/bench/requirements.txt
RUN pip install --no-cache-dir -r /opt/bench/requirements.txt

COPY benchmark_catalog.json /opt/bench/benchmark_catalog.json
COPY benchmark_prompt.py /opt/bench/benchmark_prompt.py
COPY llm_benchmark_runner.py /opt/bench/llm_benchmark_runner.py
COPY llm_benchmark_v1.json /opt/bench/llm_benchmark_v1.json
COPY llm_benchmark_v2.json /opt/bench/llm_benchmark_v2.json
COPY run.sh /opt/bench/run.sh

RUN chmod +x /opt/bench/run.sh

WORKDIR /opt/bench
ENTRYPOINT ["/opt/bench/run.sh"]
