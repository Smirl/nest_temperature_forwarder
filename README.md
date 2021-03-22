# nest_temperature_forwarder

Forward your temperature statistics to a time series database so you can look at
real-time graphs of temperature over time.

## Migrate from influxdb v1 to v2

You can use the `deploy/migrate.sh` script to migrate a influxdb v1 to a v2.
When the browser opens rename the bucket.


## Deployment

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

### Install helm chart (Manually)

```console
helm install nest deploy/nest_temperature_forwarder/ -n nest
```
