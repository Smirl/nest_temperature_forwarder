"""Get metrics from the nest API and put them into influxdb."""

from datetime import datetime
import os
import logging
import logging.handlers

from influxdb import InfluxDBClient
import requests


logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)
handler = logging.handlers.RotatingFileHandler(
    '/var/log/tempforw.log',
    maxBytes=50000,
    backupCount=1
)
handler.setLevel(logging.INFO)
logger.addHandler(handler)
handler = logging.StreamHandler()
logger.addHandler(handler)


def main():
    """Get the metrics, put them in the database, done."""
    access_token, influx_password = _get_secrets()
    response = requests.get(
        'https://developer-api.nest.com/',
        params={'auth': access_token}
    ).json()

    metrics = []
    for thermostat in response['devices']['thermostats'].values():
        data = _parse_thermostat(thermostat)
        for metric_key, metric_value in data['metrics'].items():
            metrics.append({
                'measurement': metric_key,
                'tags': {
                    'name': data['name'],
                },
                'time': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                'fields': {
                    'value': metric_value
                }
            })
    client = InfluxDBClient(
        'influxdb', 8086, 'writer',
        influx_password, 'nest_temperature_forwarder'
    )
    client.write_points(metrics)


def _get_secrets():
    """Return the loaded secrets."""
    access_token = os.environ.get('NEST_ACCESS_TOKEN', 'foo')
    influx_password = 'writer'
    if os.path.exists('/run/secrets/nest_access_token'):
        with open('/run/secrets/nest_access_token') as f:
            access_token = f.read().strip()
    if os.path.exists('/run/secrets/influxdb_write_user_password'):
        with open('/run/secrets/influxdb_write_user_password') as f:
            influx_password = f.read().strip()
    return access_token, influx_password


def _get_structures(response):
    """Get info about structures."""
    return {
        s['structure_id']: {
            'postal_code': s['postal_code'],
            'time_zone': s['time_zone'],
            'name': s['name'],
        }
        for s in response['structures'].values()
    }


def _parse_thermostat(thermostat):
    """Return the InfluxDBClient compatible metric body."""
    return {
        'name': thermostat['name'],
        'structure_id': thermostat['structure_id'],
        'state': {
            'hvac_mode': thermostat['hvac_mode'],
            'hvac_state': thermostat['hvac_state'],
            'is_using_emergency_heat': thermostat['is_using_emergency_heat'],
        },
        'metrics': {
            'ambient_temperature_c': thermostat['ambient_temperature_c'],
            'eco_temperature_high_c': thermostat['eco_temperature_high_c'],
            'eco_temperature_low_c': thermostat['eco_temperature_low_c'],
            'humidity': thermostat['humidity'],
            'target_temperature_c': thermostat['target_temperature_c'],
            'target_temperature_high_c': thermostat['target_temperature_high_c'],
            'target_temperature_low_c': thermostat['target_temperature_low_c'],
        }
    }


if __name__ == '__main__':
    main()
