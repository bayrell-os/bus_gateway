#!/usr/bin/python3

# Bayrell Cloud OS
#
# (c) Copyright 2020 "Ildar Bikmamatov" <support@bayrell.org>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import asyncio
import aio_pika
import os
import json
import uuid
from aiohttp import web

app = None

AMQP_RESPONSE_TIME = 10000;
AMQP_MESSAGE_TTL = 5000;


# Errors
ERROR_OK = 1;
ERROR_UNKOWN = -1;
ERROR_AMPQ = -1001;
ERROR_AMPQ_TIMEOUT = -1002;
ERROR_AMPQ_CONNECTION_ERROR = -1003;


class App:
	
	def __init__(self, loop):
		self.amqp_connection = None
		self.amqp_channel = None
		self.amqp_callback_queue = None
		self.web_app = web.Application()
		self.web_app.router.add_route(
			"POST",
			"/bus/{app_name}/{object_name}/{interface_name}/{method_name}/",
			self.bus
		)
		self.web_runner = None
		self.futures = {}
		self.loop = loop
	
	
	async def create_web_server(self):
		
		try:
			# Create web server
			self.web_runner = web.AppRunner(self.web_app)
			await self.web_runner.setup()
			site = web.TCPSite(self.web_runner, '0.0.0.0', 80)
			await site.start()
			
			print("Created web server")
			
		except BaseException as err:
			print("Unexpected error: " + str(err))



	async def connect_rabbit_mq(self):
		
		try:
			AMQP_HOST = os.environ['AMQP_HOST']
			AMQP_PORT = os.environ['AMQP_PORT']
			
			# Connect to RabbitMQ
			self.amqp_connection = await aio_pika.connect_robust(
				"amqp://" + AMQP_HOST + ":" + AMQP_PORT,
				loop=loop
			)
			
			# Create channel
			self.amqp_channel = await self.amqp_connection.channel()
			
			# Create temporary queue
			self.amqp_callback_queue = await self.amqp_channel.declare_queue(exclusive=True)
			await self.amqp_callback_queue.consume(self.on_response)
			
			print("Connect to RabbitMQ")
			
		except BaseException as err:
			
			print("Unexpected error: " + str(err))
			self.amqp_connection = None



	async def main(self):
		
		# Connect
		await asyncio.wait([
			self.loop.create_task( self.create_web_server() ),
			self.loop.create_task( self.connect_rabbit_mq() )
		])
		
		# Loop
		while True:
			await asyncio.sleep(1)
		
		# Close connection
		await self.amqp_connection.close()
		await self.web_runner.cleanup()
		


	# Create web response
	def response(self, response, s):
		if response == None:
			response = web.Response(text=s + "\n")
		return response
		
		

	# Response from RabbitMQ
	async def on_response(self, message):
		if message.correlation_id in self.futures:
			future = self.futures.pop(message.correlation_id)
			future.set_result( str(message.body.decode()).strip() )
		

	# Bus
	async def bus(self, request):
		
		res = None
		
		# Create future
		correlation_id = str(uuid.uuid4())
		future = loop.create_future()
		self.futures[correlation_id] = future
		
		app_name = request.match_info.get("app_name", "")
		interface_name = request.match_info.get("interface_name", "default")
		object_name = request.match_info.get("object_name", "")
		method_name = request.match_info.get("method_name", "")
		data = None
		
		try:
			
			# Create exchange
			exchange = await self.amqp_channel.declare_exchange(
				app_name,
				aio_pika.ExchangeType.DIRECT,
				durable = True,
				auto_delete = True
			)
			
			# Send message
			await exchange.publish(
				aio_pika.Message(
					str(json.dumps
					({
						"app_name": app_name,
						"interface_name": interface_name,
						"object_name": object_name,
						"method_name": method_name,
						"data": data,
					})).encode(),
					content_type = "text/plain",
					expiration = AMQP_MESSAGE_TTL,
					correlation_id = correlation_id,
					reply_to = self.amqp_callback_queue.name,
				),
				routing_key = "",
			)
			
			# Wait response
			try:
				
				await asyncio.wait_for( future, timeout=(AMQP_RESPONSE_TIME + AMQP_MESSAGE_TTL + 2000) / 1000 )
				res = self.response(res, str(future.result()))
				
			except asyncio.TimeoutError:
				pass
			
		except BaseException as err:
			res = self.response(res, json.dumps({ "code": ERROR_UNKOWN, "error_message": str(err), }))
		
		
		
		# Remove key
		if correlation_id in self.futures:
			del self.futures[correlation_id]
		
		
		res = self.response(res, json.dumps({ "code": ERROR_UNKOWN, "error_message": "No response", }))
		
		return res
	
	
if __name__ == "__main__":
	loop = asyncio.get_event_loop()
	loop.run_until_complete( App(loop).main() )
	loop.close()
