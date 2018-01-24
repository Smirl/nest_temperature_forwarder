# nest_temperature_forwarder

Forward your temperature statistics to a time series database so you can look at real-time graphs of temperature over time

## Deployment

This is deployed as a docker stack. There are 4 secrets set up in the
swarm:

	* nest_access_token
	* influxdb_admin_password
	* influxdb_read_user_password
	* influxdb_write_user_password
	* weatherunlocked_app_id
	* weatherunlocked_app_key


The stack is updated with:

	git pull
	docker build -t registry.smirlwebs.com/smirl/nest_temperature_forwarder:1.X.0
	docker stack deploy -c docker-compose.yml nest

Ensure to update the docker-compose file for the correct version.

Passwords should be in a secure place (like lastpass).
