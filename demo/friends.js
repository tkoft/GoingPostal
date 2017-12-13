

(function() {
	function startup() {
		friendslist.innerHTML = "Loading friends list...";
		try {
			var zerorpc = require("zerorpc")
			client = new zerorpc.Client();
			client.connect(require('process').env['SOCKET']);
			client.on("error", function(error) {
				console.error("RPC client error:", error);
				alert("CHUMP encountered an error.")
			})

			client.invoke("retrieve", "crapchat.frendslist", function(error, res, more) {
				if (error) {
					console.error(error);
					friendslist.innerHTML = "No friends to show.";
				} else {
					friendslist.innerHTML = "";
					friends = res.split(" ");
					console.log(friends)
					for (var i = 0; i < friends.length; i++) {
						var label = document.createElement("label");
						var description = document.createTextNode(friends[i] + "Delete")
						var deletebutton = document.createElement("button");
						
						deletebutton.innerHTML = "Delete"

						label.appendChild(description);
						label.appendChild(deletebutton);
						label.style.display = "block";

						friendslist.appendChild(label);
					}
				}
			});
		} catch (err) {
			console.error(err);
			alert("Failed to connect to CHUMP daemon.")
		}
	}
	
	function teardown() {
		// todo:  store unopened messages since they're already deleted from server
	}

	window.addEventListener('load', startup, false);
	window.addEventListener('unload', teardown, false);

})();
