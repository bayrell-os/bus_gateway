ARG ARCH=
FROM bayrell/alpine:3.13-1${ARCH}

RUN apk add python3 python3-dev gcc musl-dev py3-pip; \
	pip3 install --upgrade pip; \
	pip3 install aiohttp aio-pika uuid; \
	apk del gcc musl-dev; \
	rm -rf /var/cache/apk/*; \
	echo "Ok"

ADD files /src/files
RUN cd ~; \
	cp -rf /src/files/etc/* /etc/; \
	rm -rf /src/files; \
	echo "Ok"
	
ADD src /var/www