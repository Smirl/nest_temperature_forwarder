"""Get metrics from the nest API and put them into influxdb."""

import json
import os
import sys
import time
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from datetime import datetime, timedelta
from sched import scheduler
from typing import Set

import requests
from influxdb_client import InfluxDBClient, WriteApi
from influxdb_client.client.write_api import SYNCHRONOUS

HEALTH_CHECK_PATH = "/tmp/healh_check.txt"
DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def main(health_check_path: str, once: bool):
    """Get the metrics, put them in the database, done."""

    delay_seconds = int(_get_secret("DELAY_SECONDS", 5 * 60))
    nest_access_token = _get_secret("NEST_ACCESS_TOKEN")
    weatherunlocked_app_id = _get_secret("WEATHERUNLOCKED_APP_ID")
    weatherunlocked_app_key = _get_secret("WEATHERUNLOCKED_APP_KEY")
    influx_token = _get_secret("INFLUX_TOKEN")
    influx_url = _get_secret("INFLUX_URL", "http://localhost:8086")
    influx_bucket = _get_secret("INFLUX_BUCKET", "nest_temperature_forwarder")
    influx_org = _get_secret("INFLUX_ORG", "nest_temperature_forwarder")

    client = InfluxDBClient(
        url=influx_url,
        token=influx_token,
        org=influx_org,
    )
    write_api = client.write_api(write_options=SYNCHRONOUS)

    s = scheduler(time.time, time.sleep)

    def do():
        add_data_point(
            write_api,
            influx_bucket,
            health_check_path,
            nest_access_token,
            weatherunlocked_app_id,
            weatherunlocked_app_key,
        )
        s.enter(delay_seconds, 1, do)

    # Get data points and scheduler itself to run again after DELAY_SECONDS
    do()

    # If not running once, start the scheduler
    if not once:
        try:
            s.run()
        except KeyboardInterrupt:
            _log(shutting_down="true")


def add_data_point(
    write_api: WriteApi,
    influx_bucket: str,
    health_check_path: str,
    nest_access_token: str,
    weatherunlocked_app_id: str,
    weatherunlocked_app_key: str,
) -> Set[str]:
    """Add a data point from nest thermostats and return the postal codes they are in."""
    response = requests.get(
        "https://developer-api.nest.com/", params={"auth": nest_access_token}
    )
    response.raise_for_status()
    response = response.json()

    structures = _get_structures(response)

    postal_codes = set()
    now = datetime.utcnow().strftime(DATETIME_FORMAT)

    for thermostat in response["devices"]["thermostats"].values():
        data = _parse_thermostat(thermostat)
        for metric_key, metric_value in data["metrics"].items():
            write_api.write(
                bucket=influx_bucket,
                record={
                    "measurement": metric_key,
                    "tags": {"name": data["name"]},
                    "time": now,
                    "fields": {"value": metric_value},
                },
            )
        write_api.write(
            bucket=influx_bucket,
            record={
                "measurement": "thermostat_state",
                "tags": {
                    "name": data["name"],
                    "hvac_mode": data["state"]["hvac_mode"],
                    "hvac_state": data["state"]["hvac_state"],
                },
                "time": now,
                "fields": {"value": 1},
            },
        )
        # A cleaner dict for logging
        log_info = dict(**data)
        log_info.pop("structure_id")
        log_info["state"].pop("is_using_emergency_heat")

        postal_code = structures[data["structure_id"]]["postal_code"]
        if postal_code not in postal_codes:
            weather = get_weather(
                postal_code, weatherunlocked_app_id, weatherunlocked_app_key
            )
            write_api.write(
                bucket=influx_bucket,
                record={
                    "measurement": "weather",
                    "tags": {"name": data["name"]},
                    "time": now,
                    "fields": weather,
                },
            )
            log_info["weather"] = weather
            postal_codes.add(postal_code)

        # write the time of the last data point written to disk
        with open(health_check_path, "w") as f:
            f.write(now)
        _log(log_info)


def health_check(health_check_path: str, delta: timedelta):
    """Read the last successful data collection from disk and error if not within range."""
    if not os.path.exists(health_check_path):
        # never added a point, pod might be new
        _log(health="skip")
        return
    # Get last successful date
    with open(health_check_path) as f:
        content = f.read().strip()
    date = datetime.strptime(content, DATETIME_FORMAT)
    # Raise if not within delta
    threshold = datetime.utcnow() - delta
    if date < threshold:
        _log(
            health="false",
            delta=str(delta),
            last_success=content,
            threshold=threshold.strftime(DATETIME_FORMAT),
        )
        sys.exit(1)
    else:
        _log(health="true")


def _get_secret(name, default=""):
    """Return the given secret or the default."""
    if name in os.environ:
        return os.environ[name]
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
        params={"app_id": app_id, "app_key": app_key},
    )
    response.raise_for_status()
    response = response.json()
    return {"temp_c": response["temp_c"], "feelslike_c": response["feelslike_c"]}


def _log(obj=None, now=None, **kwargs):
    """A simple json logger."""
    obj = obj if obj else {}
    now = now if now else datetime.utcnow().strftime(DATETIME_FORMAT)
    print(json.dumps(dict({"time": now}, **obj, **kwargs)))  # put time first


if __name__ == "__main__":
    parser = ArgumentParser(
        "python temperature_forwarder.py",
        description=__doc__,
        formatter_class=ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Do get metrics by check last data point witin range",
    )
    parser.add_argument(
        "--health-check-path",
        default=HEALTH_CHECK_PATH,
        help="Path on disk to store last successful run time",
    )
    parser.add_argument(
        "--health-check-delta",
        default=20,
        type=int,
        help="Number of minutes behind before failing healthcheck",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Do not start scheduler. Get and store single data point",
    )
    args = parser.parse_args()

    if args.health_check:
        delta = timedelta(minutes=args.health_check_delta)
        health_check(args.health_check_path, delta)
    else:
        main(args.health_check_path, args.once)
