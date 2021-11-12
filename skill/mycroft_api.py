# Copyright 2021 Mycroft AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from requests import HTTPError

from mycroft.api import Api
from mycroft.util import LOG


class WAApi():
    """Wrapper for multiple WolframAlpha API endpoints through Mycroft Home."""

    def __init__(self) -> None:
        self.simple_api = WASimpleApi()
        self.spoken_api = WASpokenApi()

    def get_visual_answer(self, *args, **kwargs):
        """Get visual answer to a query."""
        return self.simple_api.get_visual(*args, **kwargs)

    def get_spoken_answer(self, *args, **kwargs):
        """Get speakable answer to a query."""
        return self.spoken_api.get_spoken(*args, **kwargs)


class WASimpleApi(Api):
    """ Wrapper for the WolframAlpha Simple API through Mycroft Home."""

    def __init__(self):
        super(WASimpleApi, self).__init__("wolframAlphaSimple")

    def get_visual(self, query, lat_lon, units="metric", optional_params: dict = {}):
        request_params = {
            "i": query,
            "geolocation": "{},{}".format(*lat_lon),
            "units": units,
            **optional_params
        }
        try:
            response = self.request({"query": request_params})
        except HTTPError as err:
            if err.response.status_code == 401:
                raise
            else:
                LOG.exception(err)
                return None
        return response


class WASpokenApi(Api):
    """ Wrapper for the WolframAlpha Spoken API through Mycroft Home."""

    def __init__(self):
        super(WASpokenApi, self).__init__("wolframAlphaSpoken")

    def get_spoken(self, query, lat_lon, units="metric"):
        try:
            response = self.request(
                {
                    "query": {
                        "i": query,
                        "geolocation": "{},{}".format(*lat_lon),
                        "units": units,
                    }
                }
            )
        except HTTPError as err:
            if err.response.status_code == 401:
                raise
            else:
                LOG.exception(err)
                return None
        return response
