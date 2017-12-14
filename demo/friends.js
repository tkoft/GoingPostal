

(function() {
	var addfriendbutton = null;

	var friends = [];

	function startup() {
		addfriendfield = document.getElementById('addfriendfield')
		addfriendbutton = document.getElementById('addbutton');
		addfriendfield.addEventListener("keyup", function(event) {
			event.preventDefault();
			if (event.keyCode === 13) {
				addFriend();
			}
		});
		addfriendbutton.addEventListener('click', addFriend, false);

		friendslist.innerHTML = "Loading friends list...";
		try {
			var zerorpc = require("zerorpc")
			client = new zerorpc.Client();
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
			
			friendslist.innerHTML = "Loading friends list...";
			client.invoke("retrieve", "crapchat.friendslist", function(error, res, more) {
				if (error || res.length == 0) {
					console.error(error);
					friendslist.innerHTML = "No friends to show.";
				} else {
					friends = res.split(" ");
					updateFriendsList();
				}
			});
			
		} catch (err) {
			console.error(err);
			alert("Failed to connect to CHUMP daemon.")
		}
	}
	
	function updateFriendsList() {
		friendslist.innerHTML = "";
		for (var i = 0; i < friends.length; i++) {
			var label = document.createElement("label");
			var description = document.createTextNode(friends[i]);
			var deletebutton = document.createElement("button");

			deletebutton.innerHTML = "Delete"
			deletebutton.id = "deletebutton_" + i;
			(function(i){
				deletebutton.addEventListener('click', function(){
					removeFriend(this.id.replace("deletebutton_", ""))
				}, false);
			})(i);
			label.appendChild(description);
			label.appendChild(deletebutton);
			label.style.display = "block";

			friendslist.appendChild(label);
		}
	}

	function addFriend() {
		inputText = addfriendfield.value
		if (isValidUser(inputText)) {
			friends.push(inputText);

			client.invoke("store", "crapchat.friendslist", friends.join(" "), function(error, res, more) {
				if (error) {
					console.error(error)
					alert("Failed to add friend.")
				} else {
					addfriendfield.value = ""
					updateFriendsList();
					alert("Added new friend!")
				}
			})
		} else {
			alert("Invalid user ID.")
		}
	}

	function removeFriend(i) {
		friends.splice(i, 1)
		client.invoke("store", "crapchat.friendslist", friends.join(" "), function(error, res, more) {
			if (error) {
				console.error(error)
				alert("Failed to remove friend.")
			} else {
				addfriendfield.value = ""
				updateFriendsList();
				alert("Removed friend :(")
			}
		})
	}

	function isValidUser(name)   
	{  
		return (/^\w+([\.-]?\w+)*@\w+([\.-]?\w+)*(\.\w{2,3})+$/.test(name))  
	}  

	function teardown() {
	// todo:  maybe store friends list? Unless we do it as each one is added
}

window.addEventListener('load', startup, false);
window.addEventListener('unload', teardown, false);

})();
