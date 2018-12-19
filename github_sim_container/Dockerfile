FROM python:3
MAINTAINER James Tanner <tanner.jc@gmail.com>

ENV PYTHONUNBUFFERED 1
COPY github_sim_container/requirements.txt /requirements.txt
RUN pip install -r /requirements.txt
WORKDIR /src
EXPOSE 80 443 5000
CMD ["python3", "tests/bin/github_sim.py", "--generate"]

