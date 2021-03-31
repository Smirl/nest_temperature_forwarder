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
  weatherunlocked_app_id: ""
  weatherunlocked_app_key: ""
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
