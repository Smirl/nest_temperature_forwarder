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
    "/var/log/tempforw.log", maxBytes=50000, backupCount=1
)
handler.setLevel(logging.INFO)
logger.addHandler(handler)
handler = logging.StreamHandler()
logger.addHandler(handler)


def main():
    """Get the metrics, put them in the database, done."""
    access_token = _get_secret("nest_access_token")
    influx_password = _get_secret("influxdb_write_user_password", "writer")
    weatherunlocked_app_id = _get_secret("weatherunlocked_app_id")
    weatherunlocked_app_key = _get_secret("weatherunlocked_app_key")

    response = requests.get(
        "https://developer-api.nest.com/", params={"auth": access_token}
    )
    response.raise_for_status()
    response = response.json()

    structures = _get_structures(response)

    metrics = []
    postal_codes = set()

    for thermostat in response["devices"]["thermostats"].values():
        data = _parse_thermostat(thermostat)
        for metric_key, metric_value in data["metrics"].items():
            metrics.append(
                {
                    "measurement": metric_key,
                    "tags": {"name": data["name"],},
                    "time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "fields": {"value": metric_value},
                }
            )
        metrics.append(
            {
                "measurement": "thermostat_state",
                "tags": {
                    "name": data["name"],
                    "hvac_mode": data["state"]["hvac_mode"],
                    "hvac_state": data["state"]["hvac_state"],
                },
                "time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "fields": {"value": 1},
            }
        )

        postal_code = structures[data["structure_id"]]["postal_code"]
        if postal_code not in postal_codes:
            weather = get_weather(
                postal_code, weatherunlocked_app_id, weatherunlocked_app_key
            )
            metrics.append(
                {
                    "measurement": "weather",
                    "tags": {"name": data["name"],},
                    "time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "fields": weather,
                }
            )
            postal_codes.add(postal_code)

    client = InfluxDBClient(
        "influxdb", 8086, "writer", influx_password, "nest_temperature_forwarder"
    )
    client.write_points(metrics)


def _get_secret(name, default=""):
    """Return the given secret or the default."""
    if name.upper() in os.environ:
        return os.environ[name]
    path = "/run/secrets/{name}".format(name=name)
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    elif default:
        return default
    else:
        raise Exception(f"Missing secret {name}")


def _get_structures(response):
    """Get info about structures."""
    return {
        s["structure_id"]: {
            "postal_code": s["postal_code"],
            "time_zone": s["time_zone"],
            "name": s["name"],
        }
        for s in response["structures"].values()
    }


def _parse_thermostat(thermostat):
    """Return the InfluxDBClient compatible metric body."""
    return {
        "name": thermostat["name"],
        "structure_id": thermostat["structure_id"],
        "state": {
            "hvac_mode": thermostat["hvac_mode"],
            "hvac_state": thermostat["hvac_state"],
            "is_using_emergency_heat": thermostat["is_using_emergency_heat"],
        },
        "metrics": {
            "ambient_temperature_c": thermostat["ambient_temperature_c"],
            "eco_temperature_high_c": thermostat["eco_temperature_high_c"],
            "eco_temperature_low_c": thermostat["eco_temperature_low_c"],
            "humidity": thermostat["humidity"],
            "target_temperature_c": thermostat["target_temperature_c"],
            "target_temperature_high_c": thermostat["target_temperature_high_c"],
            "target_temperature_low_c": thermostat["target_temperature_low_c"],
        },
    }


def get_weather(postal_code, app_id, app_key):
    """Call the weather unlocked API for the given postal_code."""
    response = requests.get(
        "http://api.weatherunlocked.com/api/current/uk.{0}".format(postal_code),
        params={"app_id": app_id, "app_key": app_key,},
    )
    response.raise_for_status()
    response = response.json()
    return {"temp_c": response["temp_c"], "feelslike_c": response["feelslike_c"]}


if __name__ == "__main__":
    main()
