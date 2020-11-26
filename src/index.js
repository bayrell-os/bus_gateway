const express = require('express');
const app = express();
const bodyParser = require('body-parser');
const multer = require('multer');
const upload = multer(); // for parsing multipart/form-data
const expressWs = require('express-ws')(app);
const uuid = require('uuid');
const amqp = require('amqplib/callback_api');
const { promisify } = require('util');

// Errors
const ERROR_OK = 1;
const ERROR_UNKOWN = -1;
const ERROR_AMPQ = -1001;
const ERROR_AMPQ_TIMEOUT = -1002;
const ERROR_AMPQ_CONNECTION_ERROR = -1003;

// Constant
const AMQP_RESPONSE_TIME = 20000;
const AMQP_MESSAGE_TTL = 10000;
const AMQP_HOST = process.env["AMQP_HOST"];
const AMQP_PORT = process.env["AMQP_PORT"];
const AMQP_LOGIN = process.env["AMQP_LOGIN"];
const AMQP_PASSWORD = process.env["AMQP_PASSWORD"];


var amqp_channel = null;
var amqp_confirm_channel = null;

app.use(bodyParser.json()); // for parsing application/json
app.use(bodyParser.urlencoded({ extended: true })); // for parsing application/x-www-form-urlencoded


// Run app
(async () => {
	
	try
	{
		// Connect to RabbitMQ
		const amqp_connect = promisify(amqp.connect);
		const conn = await amqp_connect('amqp://' + AMQP_HOST + ":" + AMQP_PORT);
		
		// Create channel
		conn.createChannel
		(
			function(err, ch)
			{
				amqp_channel = ch;
			}
		);
		
		// Create confirm channel
		conn.createConfirmChannel
		(
			function(err, ch)
			{
				amqp_confirm_channel = ch;
			}
		);
	}
	catch (err)
	{
		console.error(err)
	}
	
})();



// Bus gateway
app.post
(
	'/bus/:app_name/:object_name/:interface_name/:method_name',
	upload.array(),
	async (request, response, next) =>
	{
		var response_sended = false;
		var app_name = request.params.app_name;
		var object_name = request.params.object_name;
		var interface_name = request.params.interface_name;
		var method_name = request.params.method_name;
		var amqp_tmp_queue = null;
		
		try
		{
			if (amqp_channel == null || amqp_confirm_channel == null)
			{
				response.json
				({
					"code": ERROR_AMPQ_CONNECTION_ERROR,
					"message": "AMQP Channel is not defined",
				});
				return;
			}
			
			// Request data
			var request_body_data = {};
			if (request.body.data != undefined) request_body_data = request.body.data;
			
			// Create temp queue
			try
			{
				var res = await new Promise
				(
					(success, error) =>
					{
						// http://www.squaremobius.net/amqp.node/channel_api.html#channel_assertQueue
						amqp_channel.assertQueue
						(
							'',
							{
								// Scopes the queue to the current connection 
								exclusive: true,
								
								// The queue deleted when broker restart
								durable: false,
								
								// The queue will be deleted when the number of consumers drops to zero
								autoDelete: true,
								
								// Queue arguments
								arguments:
								{
									
									// The queue will be destroyed after n millisecond of disuse
									expires: AMQP_RESPONSE_TIME + AMQP_MESSAGE_TTL + 10000,
									
								},
							},
							(err, res) =>
							{
								if (err) error(err); else success(res);
							}
						);
					}
				);
				
				amqp_tmp_queue = res.queue;
			}
			catch (err)
			{
				response.json
				({
					"code": ERROR_AMPQ,
					"message": "Failed to create temporary queue. " + err.message,
				});
				return;
			}
			
			// Set temporary queue
			var correlation_id = uuid.v4();
			
			// Listen temporary queue
			amqp_channel.consume
			(
				amqp_tmp_queue, 
				
				// Receive message
				async (msg) =>
				{
					if (!response_sended)
					{
						if (msg == null)
						{
							response.json
							({
								"code": ERROR_AMPQ,
								"message": "Message is null",
							});
							response_sended = true;
						}
						else
						{
							if (msg.properties.correlationId == correlation_id)
							{
								var data = msg.content.toString()
								if (typeof data == "string")
								{
									response.send(data);
								}
								else
								{
									response.json(data);
								}
							}
						}
					}
					
					// Delete temporary queue
					if (amqp_tmp_queue != null)
					{
						amqp_channel.deleteQueue( amqp_tmp_queue );
						amqp_tmp_queue = null;
					}
				}, 
				
				// Consume options
				{
					// The broker won't expect an acknowledgement of messages delivered to this consumer
					noAck: true,
					
					// The broker won't let anyone else consume from this queue
					exclusive: true,
				}
			);
			
			
			// Build message
			var str = JSON.stringify
			({
				"app_name": app_name,
				"interface_name": interface_name || "default",
				"object_name": object_name,
				"method_name": method_name,
				"data": request_body_data.data || {},
			});
			
			
			// Send message
			await new Promise
			(
				(success, error) =>
				{
					try
					{
						// http://www.squaremobius.net/amqp.node/channel_api.html#channel_publish
						amqp_confirm_channel.publish
						(
							// Exchange
							app_name,
							
							// Routing key
							'',
							
							// Content
							new Buffer.from( str ),
							
							// Options
							{
								// The message will be discarded after given number of milliseconds
								expiration: AMQP_MESSAGE_TTL,
								
								// The message will be deleted when broker restarted
								persistent: false,
								
								// Reply to Queue
								replyTo: amqp_tmp_queue,
								correlationId: correlation_id,
							},
							
							function(e, r)
							{
								if (e) error(e); else success(r);
							}
						);
					}
					catch (err)
					{
						error(err);
					}
				}
			);
			
			
			// The queue will be destroyed after max_response_time + message_ttl millisecond
			setTimeout
			(
				() =>
				{
					if (!response_sended)
					{
						response.json
						({
							"code": ProxyRequest.ERROR_AMPQ_TIMEOUT,
							"message": "Timeout error",
						});
						response_sended = true;
					}
					
					// Delete temporary queue
					if (amqp_tmp_queue != null)
					{
						amqp_channel.deleteQueue( amqp_tmp_queue );
						amqp_tmp_queue = null;
					}
				},
				AMQP_RESPONSE_TIME + AMQP_MESSAGE_TTL + 2000
			);
			
		}
		catch (err)
		{
			// Delete temporary queue
			if (amqp_tmp_queue != null)
			{
				amqp_channel.deleteQueue( amqp_tmp_queue );
				amqp_tmp_queue = null;
			}
			
			// Send response
			if (!response_sended)
			{
				response.json
				({
					"code": ERROR_UNKOWN,
					"message": err.message,
				});
			}
			console.error(err);
			next(err);
		}
	}
);


// Listen 80 port
app.listen(80, function ()
{
	console.log('Bus gateway listening on port 80!');
});
