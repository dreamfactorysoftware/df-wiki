FROM almir/webhook
USER root
RUN apk add --no-cache git docker-cli \
 && git config --system --add safe.directory /repo
