FROM eclipse-temurin:17-jre
WORKDIR /srv/zhixue
RUN useradd --system --uid 10001 --create-home zhixue && mkdir data && chown zhixue:zhixue data
COPY build/install/auth-server/ /opt/zhixue/
USER zhixue
ENV AUTH_BIND_ADDRESS=0.0.0.0
EXPOSE 8087
VOLUME ["/srv/zhixue/data"]
ENTRYPOINT ["/opt/zhixue/bin/auth-server"]
