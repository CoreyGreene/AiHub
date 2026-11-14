// The Settings page (the gear). Settings are kept on the server, for this
// machine only.

const use3060 = document.getElementById("use-3060");
const note = document.getElementById("settings-note");
const device = document.getElementById("settings-device");

export async function loadSettings() {
  try {
    const res = await fetch("api/settings");
    const data = await res.json();
    use3060.checked = data.use_3060_settings;
    use3060.disabled = false;
    device.textContent = data.device_name;
  } catch {
    note.textContent = "Couldn't load the settings. Is the server running?";
  }
}

use3060.addEventListener("change", async () => {
  use3060.disabled = true;
  try {
    const res = await fetch("api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ use_3060_settings: use3060.checked }),
    });
    if (!res.ok) throw new Error();
    note.textContent = "Saved. The next picture loads the model again with this setting (a little slower once).";
  } catch {
    use3060.checked = !use3060.checked;
    note.textContent = "Couldn't save. Is the server running?";
  } finally {
    use3060.disabled = false;
  }
});
