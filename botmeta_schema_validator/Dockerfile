FROM python:2
MAINTAINER James Tanner <tanner.jc@gmail.com>

ENV PYTHONUNBUFFERED 1
RUN mkdir -p /opt/server/src
COPY . /opt/server/src
WORKDIR /opt/server/src
RUN pip install -r requirements.txt
RUN git clone https://github.com/ansible/ansibullbot ansibullbot.checkout
RUN ln -s ansibullbot.checkout/ansibullbot ansibullbot
EXPOSE 5000
CMD ["python", "flaskapp.py"]

