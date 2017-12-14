

(function() {
	var messagelist = null;
	var photo = null;
	var messageDataList = [];

	function startup() {
		messagelist = document.getElementById('messagelist');

		photo = document.getElementById('photo');
		photo.style.display = "none";

		try {
			var zerorpc = require("zerorpc")
			client = new zerorpc.Client()
			client.connect(require('process').env['SOCKET']);
			client.on("error", function(error) {
				console.error("RPC client error:", error);
				alert("CHUMP encountered an error.")
			})

			client.invoke("get_addr", function(error, res, more) {
				if (error) {
					console.error(error);
				} else {
					localuser = res
					document.getElementById('tagline').innerHTML = "Welcome, " + localuser + "!";
				}
			})

			messagelist.innerHTML = "Loading...";
			client.invoke("retrieve", "crapchat.unread", function(error, res, more) {
				if (error) {
					console.error(error);
				} else if (res.length > 0) {
					oldUnread = JSON.parse(res);
					messageDataList = messageDataList.concat(oldUnread);
				}
				updateMessages()
			});

			messagelist.innerHTML = "Loading...";
			client.invoke("recv", "crapchat.photo", function(error, res, more) {
				if (error) {
					console.error(error);
				} else if (res.length > 0) {
					console.log(res)
					messageDataList = messageDataList.concat(res);
				}
				updateMessages()
			});

		} catch (err) {
			console.error(err);
			alert("Failed to connect to CHUMP daemon.")
		}
	}

	function updateMessages() {
		if (messageDataList.length == 0) {
			messagelist.innerHTML = "No messages.";
		} else {
			messagelist.innerHTML = "";
			for (var i = 0; i < messageDataList.length; i++) {
				var button = document.createElement("button");
				var label = document.createTextNode(messageDataList[i]["sender"]);

				button.appendChild(label);
				button.id = "button_" + i;
				button.style.display = "block";
				(function(i){
					button.addEventListener('click', function(){
						showmessage(this.id.replace("button_", ""), messageDataList[i]["body"])
						this.remove();
						messageDataList.splice(i, 1);
						updateMessages();
					}, false);
				})(i); // closure over i
				//messagelist.removeChild(document.getElementById(this.id));
				messagelist.appendChild(button);
			}
		}
	}

	function showmessage(i,data) {
		messagelist.style.display = "none";
		photo.setAttribute('src', data);
		photo.style.display = "block";
		setTimeout(function() {
			photo.setAttribute('src', '');
			photo.style.display = "none";
			messagelist.style.display = "inline-block";
		}, 5000);
	}

	function teardown() {
		client.invoke("store", "crapchat.unread", JSON.stringify(messageDataList), function(error, res, more) {
			if (error) {
				console.error("Failed to save unread messages.");
				alert.dialog("Failed to save unread messages.");
			} 
		});
		// todo:  store unopened messages since they're already deleted from server
	}
	window.addEventListener('load', startup, false);
	window.addEventListener('beforeunload', teardown, false);
})();
	