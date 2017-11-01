# Copyright 2017 Mycroft AI Inc.
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
from StringIO import StringIO

import re
import ssl
import requests
import json

from os.path import dirname, join
from requests import HTTPError

from mycroft.api import Api
from mycroft.messagebus.message import Message
from mycroft.skills.core import FallbackSkill
from mycroft.util.log import LOG
from mycroft.util.parse import normalize


class EnglishQuestionParser(object):
    """
    Poor-man's english question parser. Not even close to conclusive, but
    appears to construct some decent w|a queries and responses.
    """

    def __init__(self):
        self.regexes = [
            # Match things like:
            #    * when X was Y, e.g. "tell me when america was founded"
            #    how X is Y, e.g. "how tall is mount everest"
            re.compile(
                ".*(?P<QuestionWord>who|what|when|where|why|which|whose) "
                "(?P<Query1>.*) (?P<QuestionVerb>is|are|was|were) "
                "(?P<Query2>.*)"),
            # Match:
            #    how X Y, e.g. "how do crickets chirp"
            re.compile(
                ".*(?P<QuestionWord>who|what|when|where|why|which|how) "
                "(?P<QuestionVerb>\w+) (?P<Query>.*)")
        ]

    def _normalize(self, groupdict):
        if 'Query' in groupdict:
            return groupdict
        elif 'Query1' and 'Query2' in groupdict:
            # Join the two parts into a single 'Query'
            return {
                'QuestionWord': groupdict.get('QuestionWord'),
                'QuestionVerb': groupdict.get('QuestionVerb'),
                'Query': ' '.join([groupdict.get('Query1'), groupdict.get(
                    'Query2')])
            }

    def parse(self, utterance):
        for regex in self.regexes:
            match = regex.match(utterance)
            if match:
                return self._normalize(match.groupdict())
        return None


class WolframAlphaSkill(FallbackSkill):

    def __init__(self):
        FallbackSkill.__init__(self, name="WolframAlphaSkill")

        # Support 'api_key' in the old mycroft.conf location
        self.api_key = self.config.get('api_key')

        # TODO: Localization support for questions in other languages
        self.question_parser = EnglishQuestionParser()

    def initialize(self):
        self.register_fallback(self.handle_fallback, 8)

    def handle_fallback(self, message):
        if not self.api_key:
            # attempt to get from webUI
            self.api_key = self.settings.get('api_key', None)
        if not self.api_key:
            # still not found, prompt user to get a key
            self.speak_dialog("need.api.key")
            return

        utt = message.data.get('utterance')
        LOG.debug("WolframAlpha fallback attempt: " + utt)
        lang = message.data.get('lang')
        if not lang:
            lang = "en-us"

        # Convert things like "what's ..." to "what is ..."
        utterance = normalize(utt, lang)
        parsed_question = self.question_parser.parse(utterance)

        if parsed_question:
            # Try to store pieces of utterance (None if not parsed_question)
            utt_word = parsed_question.get('QuestionWord')
            utt_verb = parsed_question.get('QuestionVerb')
            utt_query = parsed_question.get('Query')
            query = "%s %s %s" % (utt_word, utt_verb, utt_query)
        else:
            # This utterance doesn't look like a question, don't waste
            # time with WolframAlpha.
            LOG.debug("Unknown intent: " + utterance)
            return False

        others = []
        try:
            self.enclosure.mouth_think()

            # Query Wolfram Alpha directly
            LOG.debug("Falling back to WolframAlpha: " + query)
            url = "https://api.wolframalpha.com/v2/query?input="
            url += query.replace(" ", "+")
            url += "&format=image,plaintext&output=JSON&appid="
            url += self.api_key
            res = requests.get(url)

            resp = json.loads(res.content)
            if resp["queryresult"]["success"]:
                # We got a result structure, interpret it
                str = ""
                for pod in resp["queryresult"]["pods"]:
                    LOG.info("Pod title: "+pod["title"])
                    if pod["title"] == "Result":
                        str = pod["subpods"][0]["plaintext"]

                if str == "":
                    # If no 'Result', look for a 'Statement'
                    for pod in resp["queryresult"]["pods"]:
                        if pod["title"] == "Statement":
                            str = pod["subpods"][0]["plaintext"]

                # TODO: Look for unit conversion opportunities
                # TODO: Help pronunciation, e.g. 6'3" as '6 foot 3 inches'

                # Remove anything in parenthesis (assuming it is
                # just parenthetical and not important)
                str = re.sub("\(.*\)", "", str)

                if str == "":
                    return False
                else:
                    self.speak(str)
                    return True
        except Exception as e:
            LOG.info("Exception caught")
            LOG.exception(e)
            return False

    def shutdown(self):
        self.remove_fallback(self.handle_fallback)
        super(WolframAlphaSkill, self).shutdown()


def create_skill():
    return WolframAlphaSkill()
