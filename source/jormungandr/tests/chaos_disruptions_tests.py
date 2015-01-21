# Copyright (c) 2001-2014, Canal TP and/or its affiliates. All rights reserved.
#
# This file is part of Navitia,
#     the software to build cool stuff with public transport.
#
# Hope you'll enjoy and contribute to this project,
#     powered by Canal TP (www.canaltp.fr).
# Help us simplify mobility and open public transport:
#     a non ending quest to the responsive locomotion way of traveling!
#
# LICENCE: This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
# Stay tuned using
# twitter @navitia
# IRC #navitia on freenode
# https://groups.google.com/d/forum/navitia
# www.navitia.io
from kombu.connection import BrokerConnection
from kombu.entity import Exchange
from kombu.pools import producers
from retrying import Retrying
from jormungandr.interfaces.parsers import parse_input_date
from jormungandr.utils import str_to_time_stamp
from tests import gtfs_realtime_pb2
from tests_mechanism import AbstractTestFixture, dataset
from check_utils import *
import chaos_pb2
from time import sleep
import uuid


#we need to generate a unique topic not to have conflict between tests
chaos_rt_topic = 'bob_{}'.format(uuid.uuid1())


class ChaosDisruptionsFixture(AbstractTestFixture):
    """
    Mock a chaos disruption message, in order to check the api
    """
    def _get_producer(self):
        producer = producers[self.mock_chaos_connection].acquire(block=True, timeout=2)
        self._connections.add(producer.connection)
        return producer

    def setup(self):
        self.mock_chaos_connection = BrokerConnection("pyamqp://guest:guest@localhost:5672")
        self._connections = {self.mock_chaos_connection}
        self._exchange = Exchange('navitia', durable=True, delivry_mode=2, type='topic')
        self.mock_chaos_connection.connect()

    def teardown(self):
        #we need to release the amqp connection
        self.mock_chaos_connection.release()

    def send_chaos_disruption(self, disruption_name, impacted_obj, impacted_obj_type, start=None, end=None,
                              message='default_message', is_deleted=False, blocking=False):
        item = make_mock_chaos_item(disruption_name, impacted_obj, impacted_obj_type, start, end, message, is_deleted, blocking)
        with self._get_producer() as producer:
            producer.publish(item, exchange=self._exchange, routing_key=chaos_rt_topic, declare=[self._exchange])


    def send_chaos_disruption_and_sleep(self, disruption_name, impacted_obj, impacted_obj_type, start=None, end=None,
                              message='default_message', is_deleted=False, blocking=False):
        status = self.query_region('status')
        last_loaded_data = get_not_null(status['status'], 'last_rt_data_loaded')
        self.send_chaos_disruption(disruption_name, impacted_obj, impacted_obj_type,
                start, end, message, is_deleted, blocking)
        #we sleep a bit to let kraken reload the data
        self.poll_until_reload(last_loaded_data)

    def poll_until_reload(self, previous_val):
        """
        poll until the kraken have reloaded its data

        check that the last_rt_data_loaded field is different from the first call
        """
        Retrying(stop_max_delay=10 * 1000, wait_fixed=100,
                 retry_on_result=lambda status: get_not_null(status['status'], 'last_rt_data_loaded') == previous_val) \
            .call(lambda: self.query_region('status'))

    def wait_for_rabbitmq_cnx(self):
        """
        poll until the kraken is connected to rabbitmq

        small timeout because it must not be long (otherwise it way be a server configuration problem)
        """
        Retrying(stop_max_delay=1 * 1000, wait_fixed=50,
                 retry_on_result=lambda status: get_not_null(status['status'], 'is_connected_to_rabbitmq') is False) \
            .call(lambda: self.query_region('status'))


@dataset([("main_routing_test", ['--BROKER.rt_topics='+chaos_rt_topic, 'spawn_maintenance_worker'])])
class TestChaosDisruptions(ChaosDisruptionsFixture):
    """
    Note: it is done as a new fixture, to spawn a new kraken, in order not the get previous disruptions
    """
    def test_disruption_on_stop_area_b(self):
        """
        when calling the pt object stopB, at first we have no disruptions,

        then we mock a disruption sent from chaos, and we call again the pt object stopB
        we then must have a disruption
        """
        self.wait_for_rabbitmq_cnx()
        response = self.query_region('stop_areas/stopB')

        stops = get_not_null(response, 'stop_areas')
        assert len(stops) == 1
        stop = stops[0]
        #at first no disruption
        assert 'disruptions' not in stop

        self.send_chaos_disruption_and_sleep("bob_the_disruption", "stopB",
                "stop_area")

        #and we call again, we must have the disruption now
        response = self.query_region('stop_areas/stopB')
        stops = get_not_null(response, 'stop_areas')
        assert len(stops) == 1
        stop = stops[0]

        disruptions = get_not_null(stop, 'disruptions')

        #at first we got only one disruption on B
        assert len(disruptions) == 1

        assert any(d['uri'] == 'bob_the_disruption' for d in disruptions)


@dataset([("main_routing_test", ['--BROKER.rt_topics='+chaos_rt_topic, 'spawn_maintenance_worker'])])
class TestChaosDisruptionsLineSection(ChaosDisruptionsFixture):
    """
    Note: it is done as a new fixture, to spawn a new kraken, in order not the get previous disruptions
    """
    def test_disruption_on_line_section(self):
        """
        when calling the pt object line:A, at first we have no disruptions,

        then we mock a disruption sent from chaos, and we call again the pt object line:A
        we then must have one disruption
        """
        self.wait_for_rabbitmq_cnx()
        response = self.query_region('lines/A')

        lines = get_not_null(response, 'lines')
        assert len(lines) == 1
        line = lines[0]
        #at first no disruption
        assert 'disruptions' not in line

        self.send_chaos_disruption_and_sleep("bobette_the_disruption", "A",
                "line_section", start="stopA", end="stopB", blocking=True)

        #and we call again, we must have the disruption now
        response = self.query_region('lines/A')
        lines = get_not_null(response, 'lines')
        assert len(lines) == 1
        line = lines[0]

        disruptions = get_not_null(line, 'disruptions')

        #at first we got only one disruption
        assert len(disruptions) == 1
        assert any(d['uri'] == 'bobette_the_disruption' for d in disruptions)




@dataset([("main_routing_test", ['--BROKER.rt_topics='+chaos_rt_topic, 'spawn_maintenance_worker'])])
class TestChaosDisruptions2(ChaosDisruptionsFixture):
    """
    Note: it is done as a new fixture, to spawn a new kraken, in order not the get previous disruptions
    """
    def test_disruption_on_journey(self):
        """
        same kind of test with a call on journeys

        at first no disruptions, we add one and we should get it
        """
        self.wait_for_rabbitmq_cnx()
        response = self.query_region(journey_basic_query)

        stops_b_to = [s['to']['stop_point'] for j in response['journeys'] for s in j['sections']
                      if s['to']['embedded_type'] == 'stop_point' and s['to']['id'] == 'stop_point:stopB']

        assert stops_b_to

        for b in stops_b_to:
            assert 'disruptions' not in b['stop_area']
        #we create a list with every 'to' section to the stop B (the one we added the disruption on)
        self.send_chaos_disruption_and_sleep("bob_the_disruption", "stopB", "stop_area")

        response = self.query_region(journey_basic_query)

        #the response must be still valid (this test the kraken data reloading)
        is_valid_journey_response(response, self.tester, journey_basic_query)

        stops_b_to = [s['to']['stop_point'] for j in response['journeys'] for s in j['sections']
                      if s['to']['embedded_type'] == 'stop_point' and s['to']['id'] == 'stop_point:stopB']

        assert stops_b_to

        for b in stops_b_to:
            disruptions = get_not_null(b['stop_area'], 'disruptions')

            #at first we got only one disruption on A
            assert len(disruptions) == 1

            assert any(d['uri'] == 'bob_the_disruption' for d in disruptions)

@dataset([("main_routing_test", ['--BROKER.rt_topics='+chaos_rt_topic, 'spawn_maintenance_worker'])])
class TestChaosDisruptionsBlocking(ChaosDisruptionsFixture):
    """
    Note: it is done as a new fixture, to spawn a new kraken, in order not the get previous disruptions
    """
    def test_disruption_on_journey(self):
        """
        We send blocking disruptions and test if the blocked object is not used
        by the journey.
        Then we delete it and test if use the blocked object
        """
        self.wait_for_rabbitmq_cnx()
        response = self.query_region(journey_basic_query)

        assert "journeys" in response

        self.send_chaos_disruption_and_sleep("blocking_line_disruption", "A",
                "line", blocking=True)

        response = self.query_region(journey_basic_query+ "&disruption_active=true")

        links = []

        def get_line_id(k, v):
            if k != "links" or not "type" in v or not "id" in v or v["type"] != "line":
                return
            links.append(v["id"])

        walk_dict(response, get_line_id)
        assert all(map(lambda id_ : id_ != "A", links))

        # We send a blocking disruption on line A
        self.send_chaos_disruption_and_sleep("blocking_line_disruption", "A",
                "line", blocking=True, is_deleted=True)
        response = self.query_region(journey_basic_query+ "&disruption_active=true")
        links = []
        walk_dict(response, get_line_id)
        assert any(map(lambda id_ : id_ == "A", links))

        #We try to block the route
        self.send_chaos_disruption_and_sleep("blocking_route_disruption",
                "A:0", "route", blocking=True)
        response = self.query_region(journey_basic_query+ "&disruption_active=true")

        links = []
        def get_route_id(k, v):
            if k != "links" or not "type" in v or not "id" in v or v["type"] != "route":
                return
            links.append(v["id"])

        walk_dict(response, get_route_id)
        assert all(map(lambda id_ : id_ != "A:0", links))

        self.send_chaos_disruption_and_sleep("blocking_route_disruption",
                "A:0", "route", blocking=True, is_deleted=True)
        response = self.query_region(journey_basic_query+ "&disruption_active=true")

        links = []
        walk_dict(response, get_route_id)
        assert any(map(lambda id_ : id_ == "A:0", links))

        #We try to block the network
        self.send_chaos_disruption_and_sleep("blocking_network_disruption",
                "base_network", "network", blocking=True)

        response = self.query_region(journey_basic_query+ "&disruption_active=true")

        assert all(map(lambda j: len([s for s in j["sections"] if s["type"] == "public_transport"]) == 0,
                       response["journeys"]))

        self.send_chaos_disruption_and_sleep("blocking_network_disruption",
                "base_network", "network", blocking=True, is_deleted=True)
        response = self.query_region(journey_basic_query+ "&disruption_active=true")
        links = []
        def get_network_id(k, v):
            if k != "links" or not "type" in v or not "id" in v or v["type"] != "network":
                return
            links.append(v["id"])

        walk_dict(response, get_network_id)
        assert any(map(lambda id_ : id_ == "base_network", links))



@dataset([("main_routing_test", ['--BROKER.rt_topics='+chaos_rt_topic, 'spawn_maintenance_worker'])])
class TestChaosDisruptionsBlockingOverlapping(ChaosDisruptionsFixture):
    """
    Note: it is done as a new fixture, to spawn a new kraken, in order not the get previous disruptions
    """
    def test_disruption_on_journey(self):
        """
        We block the network and the line A, we test if there's no public_transport
        journey.
        We delete the network disruption and test if there's a journey using
        the line B.
        """
        self.wait_for_rabbitmq_cnx()
        response = self.query_region(journey_basic_query)

        assert "journeys" in response

        self.send_chaos_disruption_and_sleep("blocking_line_disruption", "A",
                "line", blocking=True)
        self.send_chaos_disruption_and_sleep("blocking_network_disruption",
                "base_network", "network", blocking=True)
        self.poll_until_reload(last_loaded_data)

        response = self.query_region(journey_basic_query+ "&disruption_active=true")

        assert all(map(lambda j: len([s for s in j["sections"] if s["type"] == "public_transport"]) == 0,
                       response["journeys"]))

        self.send_chaos_disruption_and_sleep("blocking_network_disruption", "base_network", "network", blocking=True, is_deleted=True)
        response = self.query_region(journey_basic_query+ "&disruption_active=true")
        links = []
        def get_line_id(k, v):
            if k != "links" or not "type" in v or not "id" in v or v["type"] != "line":
                return
            links.append(v["id"])
        walk_dict(response, get_line_id)
        assert all(map(lambda id_ : id_ != "A", links))






@dataset([("main_routing_test", ['--BROKER.rt_topics='+chaos_rt_topic, 'spawn_maintenance_worker'])])
class TestChaosDisruptionsUpdate(ChaosDisruptionsFixture):
    """
    Note: it is done as a new fixture, to spawn a new kraken, in order not the get previous disruptions
    """
    def test_disruption(self):
        """
        test /disruptions and check that an update of a disruption is correctly done
        """
        self.wait_for_rabbitmq_cnx()
        query = 'disruptions?datetime=20140101T000000&_current_datetime=20140101T000000'
        response = self.query_region(query)

        assert response['disruptions'][0]['network']['disruptions']
        eq_(len(response['disruptions'][0]['network']['disruptions']), 1)

        status = self.query_region('status')
        last_loaded_data = get_not_null(status['status'], 'last_rt_data_loaded')

        #we create a disruption on the network
        self.send_chaos_disruption("test_disruption", "base_network", "network", message='message')

        #we sleep a bit to let kraken reload the data
        self.poll_until_reload(last_loaded_data)

        response = self.query_region(query)

        assert 'disruptions' in response
        eq_(len(response['disruptions']), 1)
        assert response['disruptions'][0]['network']['disruptions']
        eq_(len(response['disruptions'][0]['network']['disruptions']), 2)
        for disruption in response['disruptions'][0]['network']['disruptions']:
            if disruption['uri'] == 'test_disruption':
                eq_(disruption['messages'][0]['text'], 'message')

        status = self.query_region('status')
        last_loaded_data = get_not_null(status['status'], 'last_rt_data_loaded')

        #we update the previous disruption
        self.send_chaos_disruption("test_disruption", "base_network", "network", message='update')
        self.poll_until_reload(last_loaded_data)

        response = self.query_region(query)

        assert 'disruptions' in response
        eq_(len(response['disruptions']), 1)
        assert response['disruptions'][0]['network']['disruptions']
        eq_(len(response['disruptions'][0]['network']['disruptions']), 2)
        for disruption in response['disruptions'][0]['network']['disruptions']:
            if disruption['uri'] == 'test_disruption':
                eq_(disruption['messages'][0]['text'], 'update')

        status = self.query_region('status')
        last_loaded_data = get_not_null(status['status'], 'last_rt_data_loaded')

        #we delete the disruption
        self.send_chaos_disruption("test_disruption", "base_network", "network", is_deleted=True)
        self.poll_until_reload(last_loaded_data)

        response = self.query_region(query)
        assert response['disruptions'][0]['network']['disruptions']
        eq_(len(response['disruptions'][0]['network']['disruptions']), 1)
        for disruption in response['disruptions'][0]['network']['disruptions']:
                assert disruption['uri'] != 'test_disruption', 'this disruption must have been deleted'


def make_mock_chaos_item(disruption_name, impacted_obj, impacted_obj_type, start, end,
                         message_text='default_message', is_deleted=False, blocking=False):
    feed_message = gtfs_realtime_pb2.FeedMessage()
    feed_message.header.gtfs_realtime_version = '1.0'
    feed_message.header.incrementality = gtfs_realtime_pb2.FeedHeader.DIFFERENTIAL
    feed_message.header.timestamp = 0

    feed_entity = feed_message.entity.add()
    feed_entity.id = disruption_name
    feed_entity.is_deleted = is_deleted

    disruption = feed_entity.Extensions[chaos_pb2.disruption]

    disruption.id = disruption_name
    disruption.cause.id = "CauseTest"
    disruption.cause.wording = "CauseTest"
    disruption.reference = "DisruptionTest"
    disruption.publication_period.start = str_to_time_stamp("20100412T165200")
    disruption.publication_period.end = str_to_time_stamp("20200412T165200")

    # Tag
    tag = disruption.tags.add()
    tag.name = "rer"
    tag.id = "rer"
    tag = disruption.tags.add()
    tag.name = "metro"
    tag.id = "rer"

    # Impacts
    impact = disruption.impacts.add()
    impact.id = "impact_" + disruption_name + "_1"
    impact.severity.id = "SeverityTest"
    impact.severity.wording = "SeverityTest"
    impact.severity.color = "#FFFF00"
    enums_impact = gtfs_realtime_pb2.Alert.DESCRIPTOR.enum_values_by_name
    impact.severity.effect = enums_impact["NO_SERVICE"].number if blocking else enums_impact["REDUCED_SERVICE"].number

    # ApplicationPeriods
    application_period = impact.application_periods.add()
    application_period.start = str_to_time_stamp("20100412T165200")
    application_period.end = str_to_time_stamp("20200412T165200")

    # PTobject
    type_col = {
        "network": chaos_pb2.PtObject.network,
        "stop_area": chaos_pb2.PtObject.stop_area,
        "line": chaos_pb2.PtObject.line,
        "line_section": chaos_pb2.PtObject.line_section,
        "route": chaos_pb2.PtObject.route
    }

    ptobject = impact.informed_entities.add()
    ptobject.uri = impacted_obj
    ptobject.pt_object_type = type_col.get(impacted_obj_type, chaos_pb2.PtObject.unkown_type)
    if ptobject.pt_object_type == chaos_pb2.PtObject.line_section:
        line_section = ptobject.pt_line_section
        line_section.line.uri = impacted_obj
        line_section.line.pt_object_type = chaos_pb2.PtObject.line
        pb_start = line_section.start_point
        pb_start.uri = start
        pb_start.pt_object_type = chaos_pb2.PtObject.stop_area
        pb_end = line_section.end_point
        pb_end.uri = end
        pb_end.pt_object_type = chaos_pb2.PtObject.stop_area

    # Messages
    message = impact.messages.add()
    message.text = message_text
    message.channel.id = "sms"
    message.channel.name = "sms"
    message.channel.max_size = 60
    message.channel.content_type = "text"

    message = impact.messages.add()
    message.text = message_text
    message.channel.name = "email"
    message.channel.id = "email"
    message.channel.max_size = 250
    message.channel.content_type = "html"

    return feed_message.SerializeToString()
