FROM prefecthq/prefect:2-python3.12

COPY ./ /tmp/rca_kpis

RUN pip install uv
RUN uv pip install --system prefect-aws /tmp/rca_kpis
