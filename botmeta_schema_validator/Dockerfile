FROM python:2
MAINTAINER James Tanner <tanner.jc@gmail.com>

ENV PYTHONUNBUFFERED 1
RUN mkdir -p /opt/server/src
COPY . /opt/server/src
RUN rm -rf /opt/server/src/tests
WORKDIR /opt/server/src/botmeta_schema_validator
RUN pip install -r requirements.txt
#RUN git clone https://github.com/ansible/ansibullbot ansibullbot.checkout
RUN ln -s /opt/server/src/ansibullbot ansibullbot
#COPY ../ ansibullbot
EXPOSE 5000
CMD ["python", "flaskapp.py"]

