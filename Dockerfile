FROM ubuntu:20.04

ENV DEBIAN_FRONTEND noninteractive


ENV JAVA_VERSION=11

ENV INSTALL_DIR=${INSTALL_DIR:-/usr}
ARG LIB_DEV_LIST="apt-utils automake pkg-config libpcre3-dev zlib1g-dev liblzma-dev libpq-dev gcc default-libmysqlclient-dev  libssl-dev libffi-dev"
ARG LIB_BASIC_LIST="curl iputils-ping nmap net-tools build-essential software-properties-common apt-transport-https"
ARG LIB_COMMON_LIST="python3-pip python3-setuptools python3-dev"
#ARG LIB_TOOL_LIST="graphviz libsqlite3-dev sqlite3 git xz-utils"

RUN apt-get update -y && \
    apt-get install -y ${LIB_DEV_LIST} && \
    apt-get install -y ${LIB_BASIC_LIST} && \
    apt-get install -y ${LIB_COMMON_LIST} && \
    #apt-get install -y ${LIB_TOOL_LIST} && \
    apt-get install -y sudo && \
    apt-get clean -y && \
    rm -rf /var/lib/apt/lists/*


#RUN apt-get update && apt-get install tesseract-ocr -y
RUN apt-get -y update
RUN apt-get install poppler-utils -y

RUN apt-get update && apt-get install -y locales && rm -rf /var/lib/apt/lists/* && \
    localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8
ENV LANG en_US.utf8


RUN apt-get update && apt-get install -y --no-install-recommends \
		bzip2 \
		unzip \
		xz-utils \
	&& rm -rf /var/lib/apt/lists/*

# Default to UTF-8 file.encoding
ENV LANG C.UTF-8

ENV JAVA_HOME=/usr/lib/jvm/java-${JAVA_VERSION}-openjdk-amd64
ENV PATH=$JAVA_HOME/bin:$PATH

# ------------------
# OpenJDK Java:
# ------------------
ARG OPENJDK_PACKAGE=${OPENJDK_PACKAGE:-openjdk-${JAVA_VERSION}-jdk}



ARG OPENJDK_INSTALL_LIST="${OPENJDK_PACKAGE} ${OPENJDK_SRC}"

RUN apt-get update -y && \
    apt-get install -y ${OPENJDK_INSTALL_LIST} && \
    ls -al ${INSTALL_DIR} ${JAVA_HOME} && \
    export PATH=$PATH ; echo "PATH=${PATH}" ; export JAVA_HOME=${JAVA_HOME} ; echo "java=`which java`" && \
    rm -rf /var/lib/apt/lists/*

# Update package list and install LibreOffice
RUN apt-get update && \
    apt-get install -y libreoffice && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir /code

RUN apt-get update

RUN apt-get install libgl1 -y
RUN apt-get install ghostscript python3-tk -y

COPY ./requirements.txt /
RUN python3 -m pip install --upgrade pip && \
pip3 install -r requirements.txt
RUN python3 -m pip install -U pydantic spacy==3.1.3
RUN echo "deb http://us-west-2.ec2.archive.ubuntu.com/ubuntu/ trusty multiverse deb http://us-west-2.ec2.archive.ubuntu.com/ubuntu/ trusty-updates multiverse deb http://us-west-2.ec2.archive.ubuntu.com/ubuntu/ trusty-backports main restricted universe multiverse" | tee /etc/apt/sources.list.d/multiverse.list
RUN apt-get update -y
RUN apt-get install ttf-mscorefonts-installer -y
RUN apt-get install -y fonts-opensymbol -y
RUN fc-cache -f -v
RUN python3 -m nltk.downloader stopwords
RUN apt-get install unixodbc-dev -y
RUN curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
RUN echo "deb [arch=amd64] https://packages.microsoft.com/ubuntu/18.04/prod bionic main" | tee /etc/apt/sources.list.d/mssql-release.list
RUN apt update -y
RUN ACCEPT_EULA=Y apt-get install -y msodbcsql17
COPY ./code /code
WORKDIR /code

ENV PATH=${PATH}:${HOME}/.local/bin

ENV PATH=${PATH}:${JAVA_HOME}/bin
ARG CONNECT_STR

RUN python3 download_models.py ${CONNECT_STR}

# EXPOSE 80
# CMD ["gunicorn", "--bind=0.0.0.0:80","--timeout", "3000", "--workers=8" ,"app:app"]

COPY entrypoint.sh ./

# Start and enable SSH
RUN apt-get update \
    && apt-get install -y --no-install-recommends dialog \
    && apt-get install -y --no-install-recommends openssh-server \
    && echo "root:Docker!" | chpasswd \
    && chmod u+x ./entrypoint.sh
COPY sshd_config /etc/ssh/

EXPOSE 80 3000 2222

ENTRYPOINT [ "./entrypoint.sh" ]