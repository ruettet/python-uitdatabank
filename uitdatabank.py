import requests
from json import loads
from requests_oauthlib import OAuth1
from configparser import ConfigParser
from datetime import datetime, timedelta
from codecs import open
from os.path import dirname


class UiTdatabankSearchResults():
    def __init__(self, results_string):
        """
        Initializes the uitdatabank search results
        :param results_string: the json output of the uitdatabank json
        :return: None
        """
        self.results = loads(results_string)

    @staticmethod
    def _get_when_from_event(event):
        """
        Fetches the dates and hours at which the event starts
        :param event: the 'event' json document that is produced by the UiTdatabank v2 api
        :return: a list of python datetime objects indicating at what day and hour the event starts
        """
        return [datetime.fromtimestamp(ts["date"] / 1000.) + timedelta(milliseconds=ts["timestart"], hours=1)
                for ts in event["event"]["calendar"]["timestamps"]["timestamp"]]

    def get_events(self):
        for item in self.results["rootObject"]:
            if "event" in item and item["event"]["eventdetails"]["eventdetail"][0]["longdescription"]:
                yield {
                    "title": item["event"]["eventdetails"]["eventdetail"][0]["title"],
                    "description": item["event"]["eventdetails"]["eventdetail"][0]["longdescription"],
                    "when": self._get_when_from_event(item)
                }


class UiTdatabank():
    def __init__(self, settings_file="settings_example.cfg", test=False):
        self.settings = ConfigParser()
        self.test = test
        self.settings.read(settings_file)
        self.auth = OAuth1(self.settings["oauth"]["app_key"],
                           self.settings["oauth"]["app_secret"],
                           self.settings["oauth"]["user_token"],
                           self.settings["oauth"]["user_secret"])
        self.url = self.settings["uitdatabank"]["url"]
        self.headers = {'Accept': 'application/json'}
        with open(dirname(__file__) + "/resources/supported_event_query_fields.txt", "r", "utf-8") as f:
            self.supported_event_query_fields = [item.strip() for item in f.readlines()]
        with open(dirname(__file__) + "/resources/supported_production_query_fields.txt", "r", "utf-8") as f:
            self.supported_production_query_fields = [item.strip() for item in f.readlines()]
        with open(dirname(__file__) + "/resources/supported_query_parameter_fields.txt", "r", "utf-8") as f:
            self.supported_query_parameter_fields = [item.strip() for item in f.readlines()]

    def find(self, params):
        """
        Main find method that makes the actual api call
        :param params: the full query, containing the q, fq, etc. fields
        :return: An uitdatabank searchresults object
        """
        return UiTdatabankSearchResults(requests.get(self.url, auth=self.auth, params=params, headers=self.headers).text)

    def construct_query_parameters(self, kwargs):
        """
        Validates the query parameter fields, and constructs a query that can be send to the API
        :param kwargs: a dictionary containing all the parameters for the query, e.g. {"q": "city:Brussels", "fq":"type:event"}
        :return: a dictionary of parameters that can be sent to the API, e.g. using the find() method
        """
        out = {}
        for key, value in kwargs.items():
            if key in self.supported_query_parameter_fields:
                out[key] = value
            else:
                raise ValueError("Not a correct query parameter")
        return out

    @staticmethod
    def __construct_query(supported_fields, key_value_tuples_with_booleans=list):
        """
        Validates a specific type of query against a list of supported fields
        :param supported_fields: a list of fields that is supported in the given type of query
        :param key_value_tuples_with_booleans: a list of (key, value) tuples, potentially with booleans in between, that will be rewritten to a query
        :return: a string that can be passed to "q" in the api call
        """
        if len(key_value_tuples_with_booleans) % 2 == 0:
            raise ValueError("Not a correct query")
        else:
            q = ""
            for i, item in enumerate(key_value_tuples_with_booleans):
                if (i % 2) == 0 and isinstance(item, tuple) and len(item) == 2 and item[0] in supported_fields:
                    q += ":".join(item)
                elif (i % 2) == 0 and isinstance(item, str) and item not in ["AND", "OR", "NOT"] and len(key_value_tuples_with_booleans) == 1:
                    q += item
                elif (i % 2) != 0 and isinstance(item, str) and item in ["AND", "OR", "NOT"]:
                    q += " " + item + " "
                else:
                    raise ValueError("Not a correct query")
            return q

    def construct_production_query(self, key_value_tuples_with_booleans=list):
        """
        Construct a query for a production
        :param key_value_tuples_with_booleans: a list of fields that is supported in the given type of query
        :return: (a string that can be passed to "q" in the api call, a string that can be passed to "fq" in the api call)
        """
        return self.__construct_query(self.supported_production_query_fields, key_value_tuples_with_booleans), "type:production"

    def construct_event_query(self, key_value_tuples_with_booleans=list):
        """
        Construct a query for events
        :param key_value_tuples_with_booleans: a list of fields that is supported in the given type of query
        :return: (a string that can be passed to "q" in the api call, a string that can be passed to "fq" in the api call)
        """
        return self.__construct_query(self.supported_event_query_fields, key_value_tuples_with_booleans), "type:event"

    def find_upcoming_events_by_organiser_label(self, organiser_label):
        q, fq = self.construct_event_query([("organiser_label", organiser_label), "AND", ("startdate", "[NOW TO *]")])
        params = self.construct_query_parameters({'q': q, 'fq': fq, 'rows': 10 if self.test else 10000})
        return self.find(params)
