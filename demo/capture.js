
(function() {
    // The width and height of the captured photo. We will set the
    // width to the value defined here, but the height will be
    // calculated based on the aspect ratio of the input stream.

    var width = 320;    // We will scale the photo width to this
    var height = 0;     // This will be computed based on the input stream

    // |streaming| indicates whether or not we're currently streaming
    // video from the camera. Obviously, we start at false.

    var streaming = false;

    // The various HTML elements we need to configure or control. These
    // will be set by the startup() function.

    var video = null;
    var camera = null;
    var canvas = null;
    var photo = null;

    var startcontrols = null;
    var capturebutton = null;
    var sendcontrols = null;
    var sendbutton = null;
    var friendslist = null;

    var localstream = null;
    var localuser = null;
    var client = null;

    function startup() {
    	video = document.getElementById('video');
    	camera = document.getElementById('camera');
    	canvas = document.getElementById('canvas');
    	photo = document.getElementById('photo');

    	startcontrols = document.getElementById('startcontrols');
    	capturebutton = document.getElementById('capturebutton');
    	sendcontrols = document.getElementById('sendcontrols');
    	sendbutton = document.getElementById('sendbutton');
    	friendslist = document.getElementById('friendslist');

    	capturebutton.addEventListener('click', takepicture, false);
    	sendbutton.addEventListener('click', preparesend, false);

    	try {
    		var zerorpc = require("zerorpc")
    		client = new zerorpc.Client();
    		client.connect(require('process').env['SOCKET']);
	    // client.connect("tcp://127.0.0.1:2900");
	    console.log("connected");
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
	} catch (err) {
		console.error(err);
		alert("Failed to connect to CHUMP daemon.")
	}

	resetCamera();
}

function resetCamera() {
	navigator.getMedia = ( navigator.getUserMedia ||
		navigator.webkitGetUserMedia ||
		navigator.mozGetUserMedia ||
		navigator.msGetUserMedia);
	navigator.getMedia(
	{
		video: true,
		audio: false
	},
	function(stream) {
		if (navigator.mozGetUserMedia) {
			video.mozSrcObject = stream;
		} else {
			var vendorURL = window.URL || window.webkitURL;
			video.src = vendorURL.createObjectURL(stream);
		}
		localstream = stream;
		video.play();
	},
	function(err) {
		console.log("An error occured! " + err);
	}
	);

	video.addEventListener('canplay', function(ev){
		if (!streaming) {
			height = video.videoHeight / (video.videoWidth/width);

		// Firefox currently has a bug where the height can't be read from
		// the video, so we will make assumptions if this happens.

		if (isNaN(height)) {
			height = width / (4/3);
		}

		video.setAttribute('width', width);
		video.setAttribute('height', height);
		canvas.setAttribute('width', width);
		canvas.setAttribute('height', height);
		streaming = true;
	}
}, false);

	camera.style.display = 'block';
	startcontrols.style.display = 'block';
	photo.style.display = 'none';
	sendcontrols.style.display = 'none';
}

    // Capture a photo by fetching the current contents of the video
    // and drawing it into a canvas, then converting that to a PNG
    // format data URL. By drawing it on an offscreen canvas and then
    // drawing that to the screen, we can change its size and/or apply
    // other changes before drawing it.

    function takepicture() {
    	var context = canvas.getContext('2d');
    	if (width && height) {
    		camera.style.display = "none";
    		canvas.width = width;
    		canvas.height = height;
    		context.drawImage(video, 0, 0, width, height);
	    // See: https://stackoverflow.com/questions/28140147/turn-off-webcam-camera-after-using-getusermedia
	    localstream.getTracks()[0].stop();
	    var data = canvas.toDataURL('image/jpeg');
	    photo.setAttribute('src', data);
	    photo.style.display = "inline-block";

	    sendcontrols.style.display = "block";
	    startcontrols.style.display = "none";

	    // Fetch friends list from CHUMPd
	   	friendslist.innerHTML = "Loading friends list...";
	    client.invoke("retrieve", "crapchat.friendslist", function(error, res, more) {
	    	if (error || res.length == 0) {
	    		console.error(error);
	   			friendslist.innerHTML = "No friends to show.";
	    	} else {
	   			friendslist.innerHTML = "";
	    		friends = res.split(" ");
	    		console.log(friends)
	    		for (var i = 0; i < friends.length; i++) {
	    			var label = document.createElement("label");
	    			var description = document.createTextNode(friends[i])
	    			var checkbox = document.createElement("input");

	    			checkbox.type = "checkbox";
	    			checkbox.name = "friendbox";
	    			checkbox.value = friends[i];

	    			label.appendChild(checkbox);
	    			label.appendChild(description);
	    			label.style.display = "block";

	    			friendslist.appendChild(label);
	    		}
	    		sendcontrols.style.display = "block";
	    	}
	    });
	}
}

function preparesend() {
	sendcontrols.style.display = "none";
	var friendboxes = document.getElementsByName("friendbox");
	var recipientslist = [];
	for (var i = 0; i < friendboxes.length; i++) {
		if (friendboxes[i].checked) {
			recipientslist.push(friendboxes[i].value);
		}
	}

	var data = photo.getAttribute('src');
	client.invoke("send", "crapchat-photo", recipientslist, data, function(error, res, more) {
		if (error) {
			console.error(error);
		} else {
			alert("Sent!");
		}
	});

	resetCamera();
}



    // Set up our event listener to run the startup process
    // once loading is complete.
    window.addEventListener('load', startup, false);
})();
