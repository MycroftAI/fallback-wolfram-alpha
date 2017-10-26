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
            re.compile(
                ".*(?P<QuestionWord>who|what|when|where|why|which|whose) "
                "(?P<Query1>.*) (?P<QuestionVerb>is|are|was|were) "
                "(?P<Query2>.*)"),
            re.compile(
                ".*(?P<QuestionWord>who|what|when|where|why|which|how) "
                "(?P<QuestionVerb>\w+) (?P<Query>.*)")
        ]

    def _normalize(self, groupdict):
        if 'Query' in groupdict:
            return groupdict
        elif 'Query1' and 'Query2' in groupdict:
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
    PIDS = ['Value', 'NotableFacts:PeopleData', 'BasicInformation:PeopleData',
            'Definition', 'DecimalApproximation']

    def __init__(self):
        FallbackSkill.__init__(self, name="WolframAlphaSkill")
        self.__init_client()
        self.question_parser = EnglishQuestionParser()

    def __init_client(self):
        self.api_key = self.config.get('api_key')

    def initialize(self):
        self.init_dialog(dirname(__file__))
        self.register_fallback(self.handle_fallback, 8)

    def get_result(self, res):
        try:
            return next(res.results).text
        except:
            result = None
            try:
                for pid in self.PIDS:
                    result = self.__find_pod_id(res.pods, pid)
                    if result:
                        result = result[:5]
                        break
                if not result:
                    result = self.__find_num(res.pods, '200')
                return result
            except:
                return result

    # TODO: Localization
    def handle_fallback(self, message):
        utt = message.data.get('utterance')
        LOG.debug("WolframAlpha fallback attempt: " + utt)
        lang = message.data.get('lang')
        if not lang:
            lang = "en-us"

        utterance = normalize(utt, lang)
        parsed_question = self.question_parser.parse(utterance)

        query = utterance
        others = []
        if parsed_question:
            # Try to store pieces of utterance (None if not parsed_question)
            utt_word = parsed_question.get('QuestionWord')
            utt_verb = parsed_question.get('QuestionVerb')
            utt_query = parsed_question.get('Query')
            if utt_verb == "'s":
                utt_verb = 'is'
                parsed_question['QuestionVerb'] = 'is'
            query = "%s %s %s" % (utt_word, utt_verb, utt_query)
            phrase = "know %s %s %s" % (utt_word, utt_query, utt_verb)
            LOG.debug("Falling back to WolframAlpha: " + query)
        else:
            # This utterance doesn't look like a question, don't waste
            # time with WolframAlpha.

            # TODO: Log missed intent
            LOG.debug("Unknown intent: " + utterance)
            return False

        try:
            self.enclosure.mouth_think()

            url = "https://api.wolframalpha.com/v2/query?input="
            url += query.replace(" ", "+")
            url += "&format=image,plaintext&output=JSON&appid="
            url += self.api_key
            res = requests.get(url)

            resp = json.loads(res.content)
            if resp["queryresult"]["success"]:
                # We got a result structure, interpret it
                # self.get_result(resp["queryresult"]["pods"])
                LOG.info("parsing resp")
                str = ""
                for pod in resp["queryresult"]["pods"]:
                    LOG.info("Pod title: "+pod["title"])
                    if pod["title"] == "Result":
                        str = pod["subpods"][0]["plaintext"]

                str = re.sub("\(.*\)", "", str)
                self.speak(str)
                return True
           
            # res = self.client.query(query)
            # SSP

            # result = self.get_result(res)
            if result is None:
                others = self._find_did_you_mean(res)
        except HTTPError as e:
            if e.response.status_code == 401:
                self.emitter.emit(Message("mycroft.not.paired"))
            return True
        except Exception as e:
            LOG.info("Exception caught")	
            LOG.exception(e)
            return False

        if result:
            input_interpretation = self.__find_pod_id(res.pods, 'Input')
            verb = "is"
            structured_syntax_regex = re.compile(".*(\||\[|\\\\|\]).*")
            if parsed_question:
                if not input_interpretation or structured_syntax_regex.match(
                        input_interpretation):
                    input_interpretation = parsed_question.get('Query')
                verb = parsed_question.get('QuestionVerb')

            if "|" in result:  # Assuming "|" indicates a list of items
                verb = ":"

            LOG.info("Result: "+str(result))
            result = self.process_wolfram_string(result)
            LOG.debug("======== Asking: "+input_interpretation)
            input_interpretation = \
                self.process_wolfram_string(input_interpretation)

            # This approach speaks portions of the question back.  The
            # output is stilted and awkward, so commented out.
            # response = "%s %s %s" % (input_interpretation, verb, result)
            response = result
            
            self.speak(response)
            return True
        else:
            if len(others) > 0:
                self.speak_dialog('others.found',
                                  data={'utterance': utterance,
                                        'alternative': others[0]})
                return True
            else:
                return False

    @staticmethod
    def __find_pod_id(pods, pod_id):
        for pod in pods:
            if pod_id in pod.id:
                return pod.text
        return None

    @staticmethod
    def __find_num(pods, pod_num):
        for pod in pods:
            if pod.node.attrib['position'] == pod_num:
                return pod.text
        return None

    @staticmethod
    def _find_did_you_mean(res):
        value = []
        root = res.tree.find('didyoumeans')
        if root is not None:
            for result in root:
                value.append(result.text)
        return value

    def process_wolfram_string(self, text):
        # Remove extra whitespace
        text = re.sub(r" \s+", r" ", text)

        # Convert | symbols to commas
        text = re.sub(r" \| ", r", ", text)

        # Convert newlines to commas
        text = re.sub(r"\n", r", ", text)

        # Convert !s to factorial
        text = re.sub(r"!", r",factorial", text)

        with open(join(dirname(__file__), 'regex',
                       self.lang, 'list.rx'), 'r') as regex:
            list_regex = re.compile(regex.readline())

        match = list_regex.match(text)
        if match:
            text = match.group('Definition')

        return text

    def shutdown(self):
        self.remove_fallback(self.handle_fallback)
        super(WolframAlphaSkill, self).shutdown()

    def stop(self):
        pass


def create_skill():
    return WolframAlphaSkill()
