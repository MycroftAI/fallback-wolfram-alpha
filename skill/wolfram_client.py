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

import imghdr
import requests
from requests import HTTPError

from mycroft.api import Api
from mycroft.util import LOG

from .ddg_image_search import search_ddg_images
from .util import (
    get_from_nested_dict,
    get_image_file_from_wikipedia_url,
    remove_nested_parentheses,
    save_image
)

# TODO add error handling to all API calls


class WolframAlphaClient():
    """Wrapper for multiple WolframAlpha API endpoints."""

    def __init__(self, cache_dir=None, app_id=None) -> None:
        self.cache_dir = cache_dir
        self.image_path = self.cache_dir + '/answer'

        # Different Wolfram scanners provide different data
        # This is an attempt to split them between those that should be
        # presented with a picture, vs those that should only be text.
        self.scanners_with_pics = ['Data']
        self.scanners_with_text = ['Simplification']

        self.simple_api = WolframSimpleApi(cache_dir, app_id)
        self.spoken_api = WolframSpokenApi(app_id)
        self.v2_api = WolframV2Api(cache_dir, app_id)

    def get_spoken_answer(self, *args, **kwargs):
        """Get speakable answer to a query."""
        return self.spoken_api.get_spoken_answer(*args, **kwargs)

    def get_visual_answer(self, *args, **kwargs):
        """Get visual answer to a query."""
        data = self.v2_api.get_visual(*args, **kwargs)

        # Map pods by ID to reduce looping over data['pods'] list
        pods = dict()
        for pod in data['pods']:
            pods[pod['id']] = pod

        if len(data['pods']) > 1:
            # index 0 is Input Interpretation
            primary_answer_pod = data['pods'][1]
        else:
            # I don't think this can happen...
            primary_answer_pod = None

        # Return only text for queries that should not have an image
        if primary_answer_pod['scanner'] in self.scanners_with_text:
            title = self._generate_text_answer(pods, primary_answer_pod)
            return title, None

        title = self._get_title_of_answer(pods)

        image = self._get_image_from_answer(pods, primary_answer_pod, title)

        return title, image

    def _get_image_from_answer(self, pods: dict, primary_pod: dict, title: str) -> str:
        """Download a valid image in a visual answer to local cache.

        Args:
            pods: Dict of all pods keyed by Pod ID.
            primary_pod: The first pod returned after the Input Interpretation.
            title: Expected title of answer used for fallback image search.

        Returns:
            File path of image.
        """
        image = None
        # If a 3rd party imagesource exists, see if it's actually an image
        # Some of these are perfect, others are html pages containing an image
        if primary_pod['scanner'] in self.scanners_with_pics:
            image_url = get_from_nested_dict(pods, 'imagesource')
            if image_url and 'wikipedia.org/wiki/File:' in image_url:
                image_url = get_image_file_from_wikipedia_url(image_url)
            LOG.error(f"Image: {image_url}")
            image = save_image(image_url, self.image_path)
            if image is None:
                image = search_ddg_images(title, self.image_path)
        return image

    def _generate_text_answer(self, pods: dict, primary_pod: dict) -> str:
        """Generate a short textual representation of a visual answer.

        Args:
            pods: Dict of all pods keyed by Pod ID.
            primary_pod: The first pod returned after the Input Interpretation.
        """
        question = get_from_nested_dict(pods['Input'], 'plaintext')
        answer = get_from_nested_dict(primary_pod, 'plaintext')
        title = f"{question} = {answer}"
        return title

    def _get_title_of_answer(self, pods: dict) -> str:
        """Extract a title from a visual answer.

        1. Prioritises any 'Result' pod.
        2. Then the Input Interpretation pod
        3. Fallback to the first plaintext answer in any pod.

        Args:
            pods: Dict of all pods keyed by Pod ID.
            primary_pod: The first pod returned after the Input Interpretation.
        """
        if pods.get('Result'):
            title = get_from_nested_dict(pods['Result'], 'plaintext')
        else:
            title = get_from_nested_dict(pods['Input'], 'plaintext')
        if not title:
            title = get_from_nested_dict(pods, 'plaintext')

        clean_title = remove_nested_parentheses(title)
        return clean_title.title()

    def _log_all_response_data(self, data: dict):
        """For debugging only - prints all Wolfram response data.
        
        This includes the pod info.
        """
        for key in data.keys():
            print(key)
            print(data[key])
            print('')

    def _log_pod_info(self, data: dict):
        """For debugging only - prints all pod info."""
        for idx, pod in enumerate(data['pods']):
            print(f"{idx}. {pod['id'].upper()}")
            print(f"- Scanner: {pod['scanner']}")
            for item in pod:
                print(f"{item}: {pod[item]}")
                print("")
            print('------------')
            print('')


class WolframV2Api(Api):
    """ Wrapper for the WolframAlpha Full Results v2 API.

    https://products.wolframalpha.com/api/documentation/

    Pods of interest
    - Input interpretation - Wolfram's determination of what is being asked about.
    - Name - primary name of 
    """

    def __init__(self, cache_dir, app_id=None):
        super(WolframV2Api, self).__init__("wa")
        self.cache_dir = cache_dir
        self.app_id = app_id
        if app_id is None:
            # Proxy via Selene using Mycroft.Api request method
            self.make_request = self.request
        else:
            self.make_request = self.request_direct

    def get_visual(self, query, lat_lon, units="metric", optional_params: dict = {}):
        request_params = {
            'query': {
                "input": query,
                "geolocation": "{},{}".format(*lat_lon),
                "units": units,
                'mode': 'Default',
                'format': 'image,plaintext',
                "output": "json",
                **optional_params
            }
        }
        try:
            response = self.make_request(request_params)
            # response = self.request(request_params)
        except HTTPError as err:
            if err.response.status_code == 401:
                raise
            else:
                LOG.exception(err)
                return None
                
        return response.json().get('queryresult')   
        
    def request_direct(self, params):
        params = params['query']
        params['appid'] = self.app_id
        url = 'http://api.wolframalpha.com/v2/query'
        response = requests.get(url, params)
        return response


class WolframSimpleApi(Api):
    """ Wrapper for the WolframAlpha Simple API."""

    def __init__(self, cache_dir, app_id=None):
        super(WolframSimpleApi, self).__init__("wolframAlphaSimple")
        self.cache_dir = cache_dir
        self.app_id = app_id
        if app_id is None:
            # Proxy via Selene using Mycroft.Api request method
            self.make_request = self.request
        else:
            self.make_request = self.request_direct

    def get_visual(self, query, lat_lon, units="metric", optional_params: dict = {}):
        request_params = {
            'query': {
                "i": query,
                "geolocation": "{},{}".format(*lat_lon),
                "units": units,
                **optional_params
            }
        }
        response = self.make_request(request_params)

        image_file_path = f"{self.cache_dir}/answer_image"

        with open(image_file_path, "wb") as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)

        image_filetype = imghdr.what(image_file_path)
        LOG.error(image_filetype)

        return image_file_path
        
    def request_direct(self, params):
        params = params['query']
        params['appid'] = self.app_id
        url = 'http://api.wolframalpha.com/v1/simple'
        response = requests.get(url, params)
        return response


class WolframSpokenApi(Api):
    """ Wrapper for the WolframAlpha Spoken API."""

    def __init__(self, app_id=None):
        super(WolframSpokenApi, self).__init__("wolframAlphaSpoken")
        self.app_id = app_id
        if app_id is None:
            # Proxy via Selene using Mycroft.Api request method
            self.make_request = self.request
        else:
            self.make_request = self.request_direct

    def get_spoken_answer(self, query, lat_lon, units="metric"):
        """Get answer as short speakable string."""
        request_params = {
            "query": {
                "i": query,
                "geolocation": "{},{}".format(*lat_lon),
                "units": units,
            }
        }
        try:
            response = self.make_request(request_params)
        except HTTPError as err:
            if err.response.status_code == 401:
                raise
            else:
                LOG.exception(err)
                return None
        return response
        
    def request_direct(self, params):
        params = params['query']
        params['appid'] = self.app_id
        url = 'http://api.wolframalpha.com/v1/spoken'
        response = requests.get(url, params)
        return response.text
