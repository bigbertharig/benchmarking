FROM python:3.12-slim

LABEL daedalmap.benchmark.contract="campaign-v1"

RUN pip install --no-cache-dir pandas pyarrow

COPY run.sh /opt/bench/run.sh
COPY dataimport_cases.json /opt/bench/dataimport_cases.json
COPY dataimport_system_prompt.md /opt/bench/dataimport_system_prompt.md

RUN chmod +x /opt/bench/run.sh

ENTRYPOINT ["/opt/bench/run.sh"]
