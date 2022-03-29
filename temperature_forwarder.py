"""Get metrics from the nest API and put them into influxdb."""

import json
import logging
import os
import sys
import time
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from datetime import datetime, timedelta
from operator import truth
from sched import scheduler
from typing import Optional, Set

import requests
from influxdb_client import InfluxDBClient, WriteApi
from influxdb_client.client.write_api import SYNCHRONOUS

DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
HEALTH_CHECK_PATH = "/tmp/healh_check.txt"
LOG_LEVEL = logging.INFO
NO_DEFAULT = object()


def main(health_check_path: str, once: bool, delay_seconds: int):
    """Get the metrics, put them in the database, done."""
    postal_code = _get_secret("POSTAL_CODE", "")
    nest_access_token = _get_secret("NEST_ACCESS_TOKEN", "")
    openweathermap_api_key = _get_secret("OPENWEATHERMAP_API_KEY", "")
    influx_token = _get_secret("INFLUX_TOKEN", "")
    influx_url = _get_secret("INFLUX_URL", "http://localhost:8086")
    influx_bucket = _get_secret("INFLUX_BUCKET", "nest_temperature_forwarder")
    influx_org = _get_secret("INFLUX_ORG", "nest_temperature_forwarder")

    if influx_token:
        client = InfluxDBClient(
            url=influx_url,
            token=influx_token,
            org=influx_org,
        )
        write_api = client.write_api(write_options=SYNCHRONOUS)
    else:
        write_api = None

    _log(
        delay_seconds=delay_seconds,
        postal_code=postal_code,
        use_influx=truth(write_api),
        use_nest=truth(nest_access_token),
        use_weather=truth(openweathermap_api_key),
        level=logging.DEBUG,
    )

    s = scheduler(time.time, time.sleep)

    def do():
        add_data_points(
            write_api,
            influx_bucket,
            health_check_path,
            postal_code,
            nest_access_token,
            openweathermap_api_key,
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


def add_data_points(
    write_api: Optional[WriteApi],
    influx_bucket: str,
    health_check_path: str,
    postal_code: str,
    nest_access_token: str,
    openweathermap_api_key: str,
):
    """Add a data point from nest thermostats & return the postal codes they are in."""
    records = []
    postal_codes = set()

    # If any "hard coded" postal codes we add them now
    if postal_code:
        postal_codes.add(postal_code)

    # Get nest data
    if nest_access_token:
        _log({"message": "calling nest api"}, level=logging.DEBUG)
        nest_records, nest_postal_codes = get_nest_records(nest_access_token)
        records.extend(nest_records)
        postal_codes |= nest_postal_codes

    # Get weather for all postcodes
    if openweathermap_api_key:
        _log(message="calling openweathermap api", level=logging.DEBUG)
        weather_records = get_weather_records(postal_codes, openweathermap_api_key)
        records.extend(weather_records)

    # Write all records to influxdb
    now = datetime.utcnow().strftime(DATETIME_FORMAT)
    if write_api:
        _log(message="trying to write to influxdb", level=logging.DEBUG)
        for record in records:
            write_api.write(bucket=influx_bucket, record=dict(time=now, **record))
        _log(message=f"wrote {len(records)} records", level=logging.DEBUG)

    # write the time of the last data point written to disk
    with open(health_check_path, "w") as f:
        f.write(now)


def health_check(health_check_path: str, delta: timedelta):
    """Read the last successful data collection from disk & error if not in range."""
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


def _get_secret(name, default=NO_DEFAULT):
    """Return the given secret or the default."""
    if name in os.environ:
        return os.environ[name]
    elif default is not NO_DEFAULT:
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


def get_nest_records(nest_access_token: str):
    """
    Call the nest api to get temperature and state records.

    Return records to be written to influxdb and found postal codes.
    """
    records = []
    postal_codes = set()

    # Request the "soon to be deprecated" nest api
    response = requests.get(
        "https://developer-api.nest.com/", params={"auth": nest_access_token}
    )
    response.raise_for_status()
    response = response.json()
    structures = _get_structures(response)

    # For each thermostat, get the records for temperature and state
    for thermostat in response["devices"]["thermostats"].values():
        data = _parse_thermostat(thermostat)
        for metric_key, metric_value in data["metrics"].items():
            records.append(
                {
                    "measurement": metric_key,
                    "tags": {"name": data["name"]},
                    "fields": {"value": metric_value},
                }
            )
        records.append(
            {
                "measurement": "thermostat_state",
                "tags": {
                    "name": data["name"],
                    "hvac_mode": data["state"]["hvac_mode"],
                    "hvac_state": data["state"]["hvac_state"],
                },
                "fields": {"value": 1},
            }
        )

        # A cleaner dict for logging
        log_info = dict(**data)
        log_info.pop("structure_id")
        log_info["state"].pop("is_using_emergency_heat")
        _log(log_info)  # log raw data as json

        # Add postal_code to get weather information
        postal_code = structures[data["structure_id"]]["postal_code"]
        postal_codes.add(postal_code)

    return records, postal_codes


def get_weather_records(postal_codes: Set[str], api_key: str):
    """Call the weather unlocked API for the given postal_codes."""
    for postal_code in postal_codes:
        # It works best if we just get the first part of the post code
        code = postal_code.strip().split(' ')[0][:4]
        _log(message=f"using postal code {code}", level=logging.DEBUG)
        response = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={
                "zip": f"{code},gb",
                "appid": api_key,
                "units": "metric",
                "mode": "json",
                "lang": "en",
            },
        )
        response.raise_for_status()
        response = response.json()
        weather = {
            "temp_c": response["main"]["temp"],
            "feelslike_c": response["main"]["feels_like"],
        }
        _log(weather)
        yield {
            "measurement": "weather",
            "tags": {"postal_code": postal_code},
            "fields": weather,
        }


def _log(obj=None, now=None, level=logging.INFO, **kwargs):
    """A simple json logger."""
    if level >= LOG_LEVEL:
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
        "--delay-seconds",
        type=int,
        default=5 * 60,
        help="Seconds between data points",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Do not start scheduler. Get and store single data point",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )
    args = parser.parse_args()

    LOG_LEVEL = logging.DEBUG if args.verbose else logging.INFO

    if args.health_check:
        delta = timedelta(minutes=args.health_check_delta)
        health_check(args.health_check_path, delta)
    else:
        main(args.health_check_path, args.once, args.delay_seconds)
