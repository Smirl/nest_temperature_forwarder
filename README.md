# nest_temperature_forwarder

Forward your temperature statistics to a time series database so you can look at
real-time graphs of temperature over time.

## Migrate from influxdb v1 to v2

Backup v1 influxdb:

```console
kubectl exec -it influxdb -- bash
> cd /tmp/
> influxd backup -db nest_temperature_forwarder -portable backup-v1
> tar -cvf backup-v1.tar.gz backup-v1/
kubectl cp influxdb:/tmp/backup-v1.tar.gz ./backup-v1.tar.gz
```

You can use the `deploy/migrate.sh` script to migrate a influxdb v1 to a v2.
When the browser opens rename the bucket without `autogen`.

A new backup named `backup-v2.tar.gz` will be available to restore a clean helm
install from.

```console
kubectl cp ./backup-v2.tar.gz influxdb:/tmp/backup-v2.tar.gz
kubectl exec -it influxdb -- bash
> export INFLUX_TOKEN=<TOKEN>
> export INFLUX_ORG=nest_temperature_forwarder
> cd /tmp/
> tar -xvf backup-v2.tar.gz backup-v2/
> influx restore --full backup-v2/
```

## Cronjob or Deployment

Older versions of `nest_temperature_forwarder` ran as a kubernetes cronjob.
It now runs as a deployment with a scheduler in python code. This is to save
pod churn on smaller kubernetes clusters.

When running as a cronjob make sure to add `--once`.

## Usage

Usually `nest_temperature_forwarder` should be run in a kubernetes cluster.
However it can be run in any environment using environment variables and flags
to configure it.

### Flags

```
usage: python temperature_forwarder.py [-h] [--health-check] [--health-check-path HEALTH_CHECK_PATH] [--health-check-delta HEALTH_CHECK_DELTA] [--once]

Get metrics from the nest API and put them into influxdb.

optional arguments:
  -h, --help            show this help message and exit
  --health-check        Do get metrics by check last data point witin range (default: False)
  --health-check-path HEALTH_CHECK_PATH
                        Path on disk to store last successful run time (default: /tmp/healh_check.txt)
  --health-check-delta HEALTH_CHECK_DELTA
                        Number of minutes behind before failing healthcheck (default: 20)
  --once                Do not start scheduler. Get and store single data point (default: False)
```

### Environment variables

| Name | Description | Default |
| - | - | - |
| `DELAY_SECONDS` | Seconds between data points | 300 |
| `NEST_ACCESS_TOKEN` | API token for nest | |
| `OPENWEATHERMAP_API_KEY` | API Key for https://openweathermap.org/ | |
| `INFLUX_TOKEN` | API token for influxdb | |
| `INFLUX_URL` | influxdb full url | http://localhost:8086 |
| `INFLUX_BUCKET` | influxdb bucket name | nest_temperature_forwarder |
| `INFLUX_ORG` | influxdb organization name | nest_temperature_forwarder |

## Deployment

Github Actions are triggered to build and deploy the app on release. Release
Drafter is used to draft releases based on pull request titles. A service
account is used to deploy via helm3. This must be created first.

### `nest_temperature_forwarder` Secret

```yaml
---
apiVersion: v1
kind: Secret
metadata:
  name: nest-temperature-forwarder
  namespace: nest
stringData:
  nest_access_token: ""
  openweathermap_api_key: ""
  # Admin user used for both influx and grafana
  admin-user: "admin"
  admin-password: ""
  admin-token: ""
```

### Grafana datasources

```yaml
---
apiVersion: v1
kind: Secret
metadata:
  name: grafana-datasources
  namespace: nest
  labels:
    grafana_datasource: "true"
stringData:
  datasources.yaml: |
    apiVersion: 1
    datasources:
      - name: influxdb
        type: influxdb
        access: proxy
        url: http://nest-influxdb2:80
        secureJsonData:
          token: "MATCH TOKEN ABOVE"
        jsonData:
          version: Flux
          organization: nest_temperature_forwarder
          defaultBucket: nest_temperature_forwarder
```

### Github Actions Setup

To create the service account and permissions, a cluster-admin needs to apply
the following:

```console
kubectl apply -f deploy/serviceaccount.yaml
```

[Secrets][github-actions-secrets] for github actions are as follows:

- `DOCKER_TOKEN`: _The PAT token for ghcr.io_
- `K8S_SECRET`: _The full yaml secret for the serviceaccount_
- `K8S_URL` : _The url of the kubernetes api server_

[github-actions-secrets]: https://github.com/Smirl/nest_temperature_forwarder/settings/secrets
