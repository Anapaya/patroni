FROM python:3.5

ENV CONSULVERSION=1.3.1
ENV HOME=/home/patroni

RUN echo "deb http://apt.postgresql.org/pub/repos/apt/ stretch-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && curl -sSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add - \
    && apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    postgresql-10 expect && apt-get clean -y
RUN pip3 install behave codacy-coverage coverage coveralls flake8 mock pytest-cov pytest setuptools

RUN groupadd patroni && useradd -g patroni -d $HOME patroni && chown -R patroni: $HOME
USER patroni
WORKDIR $HOME
COPY --chown=patroni:patroni . .

RUN pip3 install --user -r requirements.txt
RUN curl -L https://releases.hashicorp.com/consul/${CONSULVERSION}/consul_${CONSULVERSION}_linux_amd64.zip \
    | gunzip > consul && chmod +x consul
