ARG ARCH=
FROM bayrell/alpine:3.11-1${ARCH}

RUN apk add python3 python3-dev gcc musl-dev; \
	pip3 install --upgrade pip; \
	pip3 install aiohttp aio-pika uuid; \
	apk del gcc musl-dev; \
	rm -rf /var/cache/apk/*; \
	echo "Ok"

ADD src /var/www