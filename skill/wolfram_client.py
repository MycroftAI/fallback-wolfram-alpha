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

import requests
import wolframalpha

SPOKEN_URL = "http://api.wolframalpha.com/v1/spoken"


class WolframClient(wolframalpha.Client):
    """Extended Wolfram client with spoken method.

    Adds a method to retrieve text from the spoken API.
    """

    def spoken(self, query, lat_lon, units="metric"):
        r = requests.get(
            SPOKEN_URL,
            params={
                "appid": self.app_id,
                "i": query,
                "geolocation": "{},{}".format(*lat_lon),
                "units": units,
            },
        )
        if r.ok:
            return r.text
        else:
            return None
