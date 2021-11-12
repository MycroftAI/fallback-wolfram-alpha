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

from mtranslate import translate
from requests import HTTPError

from mycroft import AdaptIntent, intent_handler
from mycroft.messagebus.message import Message
from mycroft.skills.common_query_skill import CommonQuerySkill, CQSMatchLevel
from mycroft.util.parse import normalize

from .skill.mycroft_api import WAApi
from .skill.parse import EnglishQuestionParser
from .skill.util import process_wolfram_string
from .skill.wolfram_client import WolframClient


class WolframAlphaSkill(CommonQuerySkill):

    def __init__(self):
        super().__init__()
        self.__init_client()
        self.question_parser = EnglishQuestionParser()
        self.last_query = None
        self.last_answer = None
        self.autotranslate = False

    def __init_client(self):
        # Attempt to get an AppID skill settings instead (normally this
        # doesn't exist, but privacy-conscious might want to do this)
        appID = self.settings.get("appID", None)

        if appID:
            # user has a private AppID
            self.client = WolframClient(appID)
        else:
            # use the default API for Wolfram queries
            self.client = WAApi()

    def initialize(self):
        self.on_settings_changed()
        self.settings_change_callback = self.on_settings_changed

    def on_settings_changed(self):
        self.log.debug("Settings changed")
        self.autotranslate = self.settings.get("autotranslate", True)
        self.log.debug("autotranslate: {}".format(self.autotranslate))

    def CQS_match_query_phrase(self, utt):
        self.log.debug("WolframAlpha query: " + utt)

        # TODO: Localization.  Wolfram only allows queries in English,
        #       so perhaps autotranslation or other languages?  That
        #       would also involve auto-translation of the result,
        #       which is a lot of room for introducting translation
        #       issues.

        # Automatic translation to English
        orig_utt = utt
        if self.autotranslate and self.lang[:2] != "en":
            utt = translate(utt, from_language=self.lang[:2], to_language="en")
            self.log.debug("translation: {}".format(utt))
        utterance = normalize(utt, self.lang, remove_articles=False)
        parsed_question = self.question_parser.parse(utterance)

        query = utterance
        if parsed_question:
            # Try to store pieces of utterance (None if not parsed_question)
            utt_word = parsed_question.get("QuestionWord")
            utt_verb = parsed_question.get("QuestionVerb")
            utt_query = parsed_question.get("Query")
            query = "%s %s %s" % (utt_word, utt_verb, utt_query)
            phrase = "know %s %s %s" % (utt_word, utt_query, utt_verb)
            self.log.debug("Querying WolframAlpha: " + query)
        else:
            # This utterance doesn't look like a question, don't waste
            # time with WolframAlpha.
            self.log.debug("Non-question, ignoring: " + utterance)
            return False

        try:
            response = self.client.spoken(
                utt,
                (
                    self.location["coordinate"]["latitude"],
                    self.location["coordinate"]["longitude"],
                ),
                self.config_core["system_unit"],
            )
            if response:
                response = process_wolfram_string(response, {
                    "lang": self.lang,
                    "root_dir": self.root_dir
                })
                # Automatic re-translation to 'self.lang'
                if self.autotranslate and self.lang[:2] != "en":
                    response = translate(
                        response, from_language="en", to_language=self.lang[:2]
                    )
                    utt = orig_utt
                self.log.debug("utt: {} res: {}".format(utt, response))
                return (
                    utt,
                    CQSMatchLevel.GENERAL,
                    response,
                    {"query": utt, "answer": response},
                )
            else:
                return None
        except HTTPError as e:
            if e.response.status_code == 401:
                self.bus.emit(Message("mycroft.not.paired"))
            return True
        except Exception as e:
            self.log.exception(e)
            return False

    def CQS_action(self, phrase, data):
        """If selected to answer prepare data for follow up queries.

        Currently this includes detail on the source of the answer.
        """
        if data:
            self.log.info("Setting information for follow up query")
            self.last_query = data["query"]
            self.last_answer = data["answer"]

    @intent_handler(AdaptIntent().require("Give").require("Source"))
    def handle_get_sources(self, _):
        """Intent handler to request the information source of previous answer."""
        if self.last_query:
            # Send an email to the account this device is registered to
            data = {
                "query": self.last_query,
                "answer": self.last_answer,
                "url_query": self.last_query.replace(" ", "+"),
            }

            self.send_email(
                self.__translate("email.subject", data),
                self.__translate("email.body", data),
            )
            self.speak_dialog("sent.email")
        else:
            self.speak_dialog("no.info.to.send")

    def shutdown(self):
        super(WolframAlphaSkill, self).shutdown()

    def __translate(self, template, data=None):
        return self.dialog_renderer.render(template, data)


def create_skill():
    return WolframAlphaSkill()
