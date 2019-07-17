FROM ubuntu:16.04

RUN apt-get update -y && \
   apt-get install -y python3 python3-dev python3-pip

COPY . /app_data

WORKDIR /app_data

RUN pip3 install -r requirements.txt

ENTRYPOINT [ "python3" ]

CMD [ "bhav_copy.py" ]