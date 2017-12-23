FROM python:3-alpine
MAINTAINER smirlie@googlemail.com

ADD . /opt/code

RUN pip install -r /opt/code/requirements.txt && \
	crontab -l | { cat; echo '*/5 * * * * python /opt/code/temperature_forwarder.py'; } | crontab -

CMD ["crond", "-f"]
