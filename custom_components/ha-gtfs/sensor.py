import warnings

warnings.simplefilter(action="ignore", category=FutureWarning)
import logging
from datetime import date, datetime, timedelta

import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
import pandas as pd
import voluptuous as vol
from gtfslite import GTFS
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_NAME
from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)

ATTR_STOP_ID = "Stop ID"
ATTR_STOP_NAME = "Stop name"
ATTR_TRIP_ID = "Trip ID"
ATTR_ROUTE = "Route"
ATTR_DUE_IN = "Due in"
ATTR_DUE_AT = "Due at"
ATTR_DIRECTION = "Direction"

CONF_STOP_ID = "stopid"
CONF_DEPARTURES = "departures"
CONF_GTFS_FILE = "gtfs_file"

DEFAULT_NAME = "Next Bus"
ICON = "mdi:bus"

TIME_STR_FORMAT = "%H:%M:%S"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_GTFS_FILE): cv.string,
        vol.Optional(CONF_DEPARTURES): [
            {
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                vol.Required(CONF_STOP_ID): cv.string,
            }
        ],
    }
)


def due_in_minutes(timestamp):
    """Get the remaining minutes from now until a given datetime object."""
    diff = timestamp - dt_util.now().replace(tzinfo=None)
    return int(diff.total_seconds() / 60)


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Get public transport sensor."""
    sensors = []
    for departure in config.get(CONF_DEPARTURES):
        sensors.append(
            PublicTransportSensor(
                config.get(CONF_GTFS_FILE),
                departure.get(CONF_STOP_ID),
                departure.get(CONF_NAME),
            )
        )
    add_devices(sensors)


class PublicTransportSensor(Entity):
    """Implementation of a public transport sensor."""

    def __init__(self, filename, stop, name):
        """Initialize the sensor."""
        self._name = name
        self._stop = stop
        self._data = PublicTransportData(filename, stop)
        self._next_ride = None
        self.update()

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        self._next_ride = self._data.get_next()
        if self._next_ride is not None:
            return due_in_minutes(self._next_ride["arrival_dt"])
        else:
            if self._data.isvalid() is True:
                return "-"
            else:
                return "GTFS data invalid"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if self._data.isvalid() is False:
            attrs = {ATTR_DUE_IN: "Invalid"}
            return

        attrs = {
            ATTR_STOP_ID: self._stop,
            ATTR_DUE_IN: self.state,
        }
        if self._next_ride is not None:
            attrs[ATTR_STOP_NAME] = self._data.get_stop_name()
            attrs[ATTR_DUE_AT] = self._next_ride["arrival_time"]
            attrs[ATTR_ROUTE] = self._next_ride["route_short_name"]
            attrs[ATTR_DIRECTION] = self._next_ride["stop_headsign"]
            attrs[ATTR_TRIP_ID] = self._next_ride["trip_id"]
        return attrs

    @property
    def unit_of_measurement(self):
        """Return the unit this state is expressed in."""
        return "min"

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return ICON

    def update(self):
        """Get the latest data from GTFS file if needed."""
        self._data.update()


class PublicTransportData(object):
    """The Class for handling the data retrieval."""

    def __init__(self, gtfs_file, stop_id):
        """Initialize."""
        self._gtfs_file = gtfs_file
        self._stop_id = stop_id
        self._stop_name = ""
        self._valid = False

    def _time_to_sec(self, timestr):
        sp = timestr.split(":")
        seconds = int(sp[0]) * 3600
        seconds = seconds + int(sp[1]) * 60
        seconds = seconds + int(sp[2])
        return seconds

    def isvalid(self):
        return self._valid

    def update(self):
        """Retrive information from the GTFS file"""
        gtfs = GTFS.load_zip(self._gtfs_file)

        """ Init date and time objects """
        now_d = date.today()
        tomorrow_d = now_d + timedelta(days=1)
        now_dt = datetime.now().replace(microsecond=0)
        tomorrow_dt = now_dt + timedelta(days=1)

        """ Check if the GTFS files is valid for todays and tomorrows date """
        if (gtfs.valid_date(now_d) and gtfs.valid_date(tomorrow_d)) is False:
            _LOGGER.error("GTFS file is not valid for todays or tomorrows date.")
            empty = []
            self._today_stop_times = pd.DataFrame(empty)
            self._tomorrow_stop_times = pd.DataFrame(empty)
            self._valid = False
            return

        trips = gtfs.day_trips(now_d)
        stop_times = gtfs.stop_times[
            gtfs.stop_times.trip_id.isin(trips.trip_id)
            & (gtfs.stop_times.stop_id == self._stop_id)
            & (gtfs.stop_times.pickup_type != 2)
        ]
        today_stop_times = stop_times.sort_values(by="arrival_time")

        trips = gtfs.day_trips(tomorrow_d)
        stop_times = gtfs.stop_times[
            gtfs.stop_times.trip_id.isin(trips.trip_id)
            & (gtfs.stop_times.stop_id == self._stop_id)
            & (gtfs.stop_times.pickup_type != 2)
        ]
        tomorrow_stop_times = stop_times.sort_values(by="arrival_time")

        stop_name = gtfs.stops[gtfs.stops.stop_id == self._stop_id].iloc[0]["stop_name"]

        for index, stop in today_stop_times.iterrows():
            trip = gtfs.trips[gtfs.trips.trip_id == stop["trip_id"]].iloc[0]
            line = gtfs.routes[gtfs.routes.route_id == trip["route_id"]].iloc[0][
                "route_short_name"
            ]
            today_stop_times.loc[[index], ["route_short_name"]] = line
            temp_td = timedelta(seconds=self._time_to_sec(stop["arrival_time"]))
            today_stop_times.loc[[index], ["arrival_dt"]] = (
                now_dt.replace(tzinfo=None, hour=0, minute=0, second=0) + temp_td
            )

        for index, stop in tomorrow_stop_times.iterrows():
            trip = gtfs.trips[gtfs.trips.trip_id == stop["trip_id"]].iloc[0]
            line = gtfs.routes[gtfs.routes.route_id == trip["route_id"]].iloc[0][
                "route_short_name"
            ]
            tomorrow_stop_times.loc[[index], ["route_short_name"]] = line
            temp_td = timedelta(seconds=self._time_to_sec(stop["arrival_time"]))
            tomorrow_stop_times.loc[[index], ["arrival_dt"]] = (
                tomorrow_dt.replace(tzinfo=None, hour=0, minute=0, second=0) + temp_td
            )

        self._today_stop_times = today_stop_times
        self._tomorrow_stop_times = tomorrow_stop_times
        self._stop_name = stop_name
        self._init_date = now_d
        self._valid = True

    def get_stop_name(self):
        if self._valid is False:
            return None

        return self._stop_name

    def get_next(self):
        if self._valid is False:
            return None

        now_d = date.today()
        now_dt = datetime.now().replace(microsecond=0)

        if now_d != self._init_date:
            self.update()

        nowstr = now_dt.strftime(TIME_STR_FORMAT)
        next_times = self._today_stop_times[
            (self._today_stop_times.arrival_time >= nowstr)
        ]

        if next_times.size > 0:
            next_time = next_times.iloc[0]
        else:
            if self._tomorrow_stop_times.size > 0:
                next_time = self._tomorrow_stop_times.iloc[0]
            else:
                next_time = None

        return next_time
