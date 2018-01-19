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
import wolframalpha
from os.path import dirname, join
from requests import HTTPError

from adapt.intent import IntentBuilder
from mycroft.api import Api
from mycroft.messagebus.message import Message
from mycroft.skills.core import FallbackSkill, intent_handler
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


class WAApi(Api):
    def __init__(self):
        super(WAApi, self).__init__("wa")

    def get_data(self, response):
        return response

    def query(self, input):
        data = self.request({"query": {"input": input}})
        return wolframalpha.Result(StringIO(data.content))


class WolframAlphaSkill(FallbackSkill):
    PIDS = ['Value', 'NotableFacts:PeopleData', 'BasicInformation:PeopleData',
            'Definition', 'DecimalApproximation']

    def __init__(self):
        FallbackSkill.__init__(self, name="WolframAlphaSkill")
        self.__init_client()
        self.question_parser = EnglishQuestionParser()
        self.last_query = None
        self.last_answer = None

    def __init_client(self):
        # TODO: Storing skill-specific settings in mycroft.conf is deprecated.
        # Should be stored in the skill's local settings.json instead.
        appID = self.config.get('api_key')
        if not appID:
            # Attempt to get an AppID skill settings instead (normally this
            # doesn't exist, but privacy-conscious might want to do this)
            appID = self.settings.get('appID', None)

        if appID and not self.config.get('proxy'):
            # user has a private AppID
            self.client = wolframalpha.Client(appID)
        else:
            # use the default API for Wolfram queries
            self.client = WAApi()

    def initialize(self):
        self.register_fallback(self.handle_fallback, 10)

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

    def handle_fallback(self, message):
        utt = message.data.get('utterance')
        self.log.debug("WolframAlpha fallback attempt: " + utt)
        lang = message.data.get('lang')
        if not lang:
            lang = "en-us"

        # TODO: Localization.  Wolfram only allows queries in English,
        #       so perhaps autotranslation or other languages?  That
        #       would also involve auto-translation of the result,
        #       which is a lot of room for introducting translation
        #       issues.

        utterance = normalize(utt, lang, remove_articles=False)
        parsed_question = self.question_parser.parse(utterance)

        query = utterance
        if parsed_question:
            # Try to store pieces of utterance (None if not parsed_question)
            utt_word = parsed_question.get('QuestionWord')
            utt_verb = parsed_question.get('QuestionVerb')
            utt_query = parsed_question.get('Query')
            query = "%s %s %s" % (utt_word, utt_verb, utt_query)
            phrase = "know %s %s %s" % (utt_word, utt_query, utt_verb)
            self.log.debug("Querying WolframAlpha: " + query)
        else:
            # This utterance doesn't look like a question, don't waste
            # time with WolframAlpha.
            self.log.debug("Non-question, ignoring: " + utterance)
            return False

        try:
            self.enclosure.mouth_think()
            res = self.client.query(query)
            result = self.get_result(res)
        except HTTPError as e:
            if e.response.status_code == 401:
                self.emitter.emit(Message("mycroft.not.paired"))
            return True
        except Exception as e:
            self.log.exception(e)
            return False

        if result:
            response = self.process_wolfram_string(result)

            # remember for any later 'source' request
            self.last_query = query
            self.last_answer = response

            self.speak(response)
            return True
        else:
            return False

    @staticmethod
    def __find_pod_id(pods, pod_id):
        # Wolfram returns results in "pods".  This searches a result
        # structure for a specific pod ID.
        # See https://products.wolframalpha.com/api/documentation/
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

    @intent_handler(IntentBuilder("Info").require("Give").require("Source"))
    def handle_get_sources(self, message):
        if self.last_query:
            # Send an email to the account this device is registered to
            data = {"query": self.last_query,
                    "answer": self.last_answer,
                    "url_query": self.last_query.replace(" ", "+")}

            self.send_email(self.__translate("email.subject", data),
                            self.__translate("email.body", data))
            self.speak_dialog("sent.email")
        else:
            self.speak_dialog("no.info.to.send")

    def shutdown(self):
        self.remove_fallback(self.handle_fallback)
        super(WolframAlphaSkill, self).shutdown()

    def __translate(self, template, data=None):
        return self.dialog_renderer.render(template, data)


def create_skill():
    return WolframAlphaSkill()
