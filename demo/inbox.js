
(function() {
    var messagelist = null;
    var photo = null;
    var messageDataList = null;

    function startup() {
	messagelist = document.getElementById('messagelist');
	messagelist.innerHTML = "Loading...";

	photo = document.getElementById('photo');
	photo.style.display = "none";

	try {
	    var zerorpc = require("zerorpc")
	    client = new zerorpc.Client();
	    client.connect("tcp://127.0.0.1:2900");
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
		    console.log("CHUMP username: " + localuser)
		}
	    })

	    client.invoke("recv", "crapchat-photo", function(error, res, more) {
		if (error) {
		    console.error(error);
		} else {
		    if (res.length > 0) {
			messageDataList += res;
			messagelist.innerHTML = "";
			for (var i = 0; i < res.length; i++) {
			    var button = document.createElement("button");
			    var label = document.createTextNode(res[i]["sender"]);
			    
			    button.appendChild(label);
			    button.id = "button_" + i;
			    button.style.display = "block";
			    console.log(res[i]["sender"]);
			    button.addEventListener('click', function(){
				showmessage(this.id.replace("button_", ""))
				this.remove();
				//messagelist.removeChild(document.getElementById(this.id));
			    }, false);
			    messagelist.append(button);
			}
		    } else {
			messagelist.innerHTML = "No messages.";
		    }
		}
	    });
	} catch (err) {
	    console.error(err);
	    alert("Failed to connect to CHUMP daemon.")
	}

    }

    function showmessage(i) {
	messagelist.style.display = "none";
	photo.setAttribute('src', data);
	photo.style.display = "block";
	setTimeout(function() {
	    photo.style.display = "none";
	    messagelist.style.display = "block";
	}, 5000);
    }

    function teardown() {
	
	
    }
    window.addEventListener('load', startup, false);
    window.addEventListener('unload', teardown, false);
})();
