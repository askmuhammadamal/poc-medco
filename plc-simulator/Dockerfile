# Modbus PLC simulator (test target). Optional — only used for the demo.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

EXPOSE 5020

# Listen on all interfaces so the middleware container can reach it.
ENTRYPOINT ["python", "plc_sim.py", "--host", "0.0.0.0"]
CMD ["--mode", "known"]
