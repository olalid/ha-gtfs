# HA-GTFS
A GTFS interpreter implementation for Home Assistant
The main advantage with this integration compared to the default one in Home Assistant is that it has better compatibility with more complex schedules such as the ones from trafiklab.

# Manual installation
Download the repository and extract the custom_components/ha-gtfs folder in your Home Assistant configuration directory.

# Configuration

```
sensor:
  - platform: ha-gtfs
    gtfs_file: /var/opt/homeassistant/gtfs/otraf.zip
    departures:
    - name: "Next bus from Gamla Linköping (A)"
      stopid: 9022005000215001
```