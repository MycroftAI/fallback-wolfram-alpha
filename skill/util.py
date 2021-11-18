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
import re
from os.path import join
from typing import Any, Optional

import requests

from mycroft.util import LOG


def get_from_nested_dict(obj: dict, key: str) -> Optional[Any]:
    """Dig through a nested dict to find a key.

    Args:
        obj: Dict object to check
        key: key of interest
    """
    if key in obj:
        return obj[key]

    for _, value in obj.items():
        if isinstance(value, dict):
            item = get_from_nested_dict(value, key)
            if item is not None:
                return item
        elif isinstance(value, list):
            for list_item in value:
                item = get_from_nested_dict(list_item, key)
                if item is not None:
                    return item


def get_image_file_from_wikipedia_url(input_url):
    """Get actual image file from a Wikipedia File: url.

    Wolfram returns url to Wikipedia's file details page rather than the
    actual image file.
    """
    protocol, domain, wiki, *remaining = input_url.split('/')

    image_url = input_url.replace(
        'http://en.wikipedia.org/wiki/File:',
        'https://upload.wikimedia.org/wikipedia/commons/c/cc/'
    )
    return image_url


def process_wolfram_string(text: str, config: dict) -> str:
    """Clean and format an answer from Wolfram into a presentable format.

    Args:
        text: Original answer from Wolfram Alpha
        config: {
            lang: language of the answer
            root_dir: of the Skill to find a regex file
        }
    Returns:
        Cleaned version of the input string.
    """
    # Remove extra whitespace
    text = re.sub(r" \s+", r" ", text)

    # Convert | symbols to commas
    text = re.sub(r" \| ", r", ", text)

    # Convert newlines to commas
    text = re.sub(r"\n", r", ", text)

    # Convert !s to factorial
    text = re.sub(r"!", r",factorial", text)

    regex_file_path = join(
        config["root_dir"], "regex", config["lang"], "list.rx")
    with open(regex_file_path, "r") as regex:
        list_regex = re.compile(regex.readline().strip("\n"))

    match = list_regex.match(text)
    if match:
        text = match.group("Definition")

    return text


def remove_nested_parentheses(input: str) -> str:
    """Remove content contained within parentheses from a string.

    This includes content that is nested within multiple sets, eg:
    Lemurs (/ˈliːmər/ (listen) LEE-mər)
    """
    ret = ''
    nest_depth = 0
    for char in input:
        if char == '(':
            nest_depth += 1
        elif (char == ')') and nest_depth:
            nest_depth -= 1
        elif not nest_depth:
            ret += char
    return ret


def save_image(img_url: str, file_path: str) -> str:
    """Save the given image result to the provided file path.

    Note that the filetype can vary so it is recommended not to provide a
    fixed file extension.
    """
    if img_url is None:
        return None
    try:
        img_data = requests.get(img_url).content
        with open(file_path, 'wb+') as f:
            f.write(img_data)
        LOG.info(f"DDG image successfully downloaded: {file_path}")
        if imghdr.what(file_path) is not None:
            return file_path
        else:
            LOG.error('Downloaded file was not a valid image')
    except Exception as err:
        LOG.exception(err)
