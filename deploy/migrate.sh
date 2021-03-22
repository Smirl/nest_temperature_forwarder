set -xe

docker ps -qa | xargs docker rm
docker volume ls -q | xargs docker volume rm


docker run -d -p 8086:8086 \
    -v influxdb:/var/lib/influxdb \
    -v $(PWD)/backup-2021-03-22.tar.gz:/tmp/backup-2021-03-22.tar.gz \
    --name influxdb1 \
    influxdb:1.8

sleep 5

docker exec -it -w /tmp/ influxdb1 tar -xvf backup-2021-03-22.tar.gz
docker exec -it -w /tmp/ influxdb1 influxd restore --portable backup-2021-03-22

docker kill influxdb1


docker run --rm -p 8086:8086 \
    -v influxdb:/var/lib/influxdb \
    --entrypoint "" \
    influxdb:2.0 \
    chown -R influxdb:influxdb /var/lib/influxdb/


docker run -d -p 8086:8086 \
    --name influxdb2 \
    -v influxdb:/var/lib/influxdb \
    -v influxdb2:/var/lib/influxdb2 \
    -e DOCKER_INFLUXDB_INIT_MODE=upgrade \
    -e DOCKER_INFLUXDB_INIT_USERNAME=admin \
    -e DOCKER_INFLUXDB_INIT_PASSWORD=gr4f4n4-p455w0rd-4726182 \
    -e DOCKER_INFLUXDB_INIT_ORG=nest_temperature_forwarder \
    -e DOCKER_INFLUXDB_INIT_BUCKET=nest_temperature_forwarder \
    -e DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=TETVIFzddk1yEzjMshSabqrdD4SNhLNiq3Xzn_qknMg7IkNurwCqEJD8naDukgVr1ZQ080ikEmmWphgefW5RUQ== \
    influxdb:2.0

open http://localhost:8086/
sleep 60

docker exec -it -w /tmp/ influxdb2 influx backup -b nest_temperature_forwarder backup
docker exec -it -w /tmp/ influxdb2 tar -cvf backup.tar.gz backup
docker cp influxdb2:/tmp/backup.tar.gz ./backup.tar.gz

docker kill influxdb2
