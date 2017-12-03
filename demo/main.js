const {app, BrowserWindow} = require('electron')
const path = require('path')
const url = require('url')

let win

function createWindow () {
    // Create the browser window.
    win = new BrowserWindow({width: 800, height: 600,
    webPreferences: {
        webSecurity: false
    }})

    // and load the index.html of the app.
    win.loadURL(url.format({
	pathname: path.join(__dirname, 'inbox.html'),
	protocol: 'file:',
	slashes: true
    }))

    // Open the DevTools.
    win.webContents.openDevTools()

    // Emitted when the window is closed.
    win.on('closed', () => {
	win = null
    })
}
app.on('ready', createWindow)

console.log("test");

