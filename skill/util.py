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

import re
from os.path import join


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
