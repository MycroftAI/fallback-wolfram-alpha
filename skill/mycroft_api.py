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

from io import BytesIO

import wolframalpha
from mycroft.api import Api


class WAApi(Api):
    """ Wrapper for wolfram alpha calls through Mycroft Home API. """

    def __init__(self):
        super(WAApi, self).__init__("wolframAlphaSpoken")

    def get_data(self, response):
        return response

    def query(self, input):
        data = self.request({"query": {"input": input}})
        return wolframalpha.Result(BytesIO(data.content))

    def spoken(self, query, lat_lon, units="metric"):
        try:
            r = self.request(
                {
                    "query": {
                        "i": query,
                        "geolocation": "{},{}".format(*lat_lon),
                        "units": units,
                    }
                }
            )
        except HTTPError as e:
            if e.response.status_code == 401:
                raise
            else:
                r = e.response
        if r.ok:
            print(r.text)
            return r.text
        else:
            return None
