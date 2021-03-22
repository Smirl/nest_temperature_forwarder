FROM python:3.9-alpine
ADD . /opt/code
RUN apk add --no-cache gcc musl-dev && \
	pip install -r /opt/code/requirements.txt && \
	apk del gcc musl-dev
CMD ["python", "/opt/code/temperature_forwarder.py"]
