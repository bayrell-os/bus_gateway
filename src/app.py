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
from aiohttp import web

app = None
connection = None
stop = False


async def create_web_server(loop):
	
	try:
		# Create web server
		runner = web.AppRunner(app)
		await runner.setup()
		site = web.TCPSite(runner, '0.0.0.0', 80)
		await site.start()
		
		print("Created web server")
		
	except BaseException as err:
		print("Unexpected error: " + str(err))



async def connect_rabbit_mq(loop):
	
	try:
		AMQP_HOST = os.environ['AMQP_HOST']
		AMQP_PORT = os.environ['AMQP_PORT']
		
		# Connect to RabbitMQ
		connection = await aio_pika.connect_robust("amqp://" + AMQP_HOST + ":" + AMQP_PORT, loop=loop)
		
		print("Connect to RabbitMQ")
		
	except BaseException as err:
		
		print("Unexpected error: " + str(err))
		connection = None



async def main(loop):
	
	# Connect
	await asyncio.wait([ loop.create_task( create_web_server(loop) ), loop.create_task( connect_rabbit_mq(loop) ) ])
	
	# Loop
	while True:
		await asyncio.sleep(3600)
	
	# Close connection
	await runner.cleanup()
	await connection.close()
	

# Bus
async def bus(request):
	s = "{'code':10}\n"
	return web.Response(text=s)
	
	
if __name__ == "__main__":
	
	app = web.Application()
	app.router.add_route("POST", "/bus/{app_name}/{object_name}/{interface_name}/{method_name}/", bus)


	loop = asyncio.get_event_loop()
	loop.run_until_complete( main(loop) )
	loop.close()
