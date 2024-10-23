FROM python:latest

WORKDIR /app

RUN apt update
RUN apt install -y python3-dev graphviz libgraphviz-dev pkg-config
RUN apt install -y latexmk
RUN apt install -y texlive-lang-japanese
RUN apt install -y texlive-latex-extra
RUN apt install -y texlive-science

COPY ./requirement.txt /app/requirement.txt
RUN pip install -r requirement.txt


