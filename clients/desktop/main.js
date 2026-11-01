const path = require("path");
const { app, BrowserWindow, Tray, Menu, globalShortcut, session, nativeImage } = require("electron");

const NOVA_URL = process.env.NOVA_URL || "http://127.0.0.1:8010";
const ORIGIN = new URL(NOVA_URL).origin;
const ICON = path.join(__dirname, "..", "..", "app", "web", "static", "icons", "icon-192.png");
const ALLOWED_PERMISSIONS = ["media", "notifications"];

let win = null;
let tray = null;
let quitting = false;

function createWindow() {
  win = new BrowserWindow({
    width: 460,
    height: 760,
    minWidth: 360,
    backgroundColor: "#0f1419",
    title: "Nova",
    icon: ICON,
    autoHideMenuBar: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  win.loadURL(NOVA_URL);

  // Vera site ku poga koodaadhu, new window open aagakoodaadhu
  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  win.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith(ORIGIN)) event.preventDefault();
  });

  // X click pannina tray ku poidum (Quit tray menu la)
  win.on("close", (event) => {
    if (!quitting) {
      event.preventDefault();
      win.hide();
    }
  });
}

function showWindow() {
  if (!win) return;
  win.show();
  win.focus();
}

function toggleMic() {
  showWindow();
  win.webContents.executeJavaScript("window.nova && window.nova.toggleMic()").catch(() => {});
}

app.whenReady().then(() => {
  // Mic + notification mattum, Nova server origin ku mattum allow
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback, details) => {
    callback(ALLOWED_PERMISSIONS.includes(permission) && details.requestingUrl.startsWith(ORIGIN));
  });
  session.defaultSession.setPermissionCheckHandler((webContents, permission, requestingOrigin) => {
    return ALLOWED_PERMISSIONS.includes(permission) && requestingOrigin.startsWith(ORIGIN);
  });

  createWindow();

  tray = new Tray(nativeImage.createFromPath(ICON));
  tray.setToolTip("Nova");
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "Show Nova", click: showWindow },
      { label: "Talk (Ctrl+Shift+Space)", click: toggleMic },
      { type: "separator" },
      { label: "Quit", click: () => { quitting = true; app.quit(); } },
    ])
  );
  tray.on("click", showWindow);

  globalShortcut.register("Control+Shift+Space", toggleMic);
});

app.on("before-quit", () => { quitting = true; });
app.on("will-quit", () => globalShortcut.unregisterAll());