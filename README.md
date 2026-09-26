# NetBoxSelf Audit

NetBox plugin that audits changes made in NetBox itself: you choose which object types and fields are watched,
give each a severity and optionally your own log message, and get a report (web page, PDF, HTML, e-mail)
of who changed what.

Requires NetBox 4.7.

**At a glance**

- Watched fields per NetBox object type (incl. custom fields), severity and log message per field
- Audit by object (tree) or by time, PDF / HTML export, e-mail (in the body or as PDF), scheduled e-mail
- NetBox version and plugin changes recorded automatically
- **Internal self-check:** the background check reports every minute (heartbeat); when it has not run for 5 or
  10 minutes (Settings), the plugin pages show a warning and `/plugins/self-audit/health/` returns `ERROR`
  (HTTP 503) instead of `OK` – ready for LibreNMS or any other monitoring; the address can be switched off in
  Settings. A **Check now** button on the Audit page sends a test job to `netbox-rq` and waits for the answer.
  An interrupted background run is cleared automatically when `netbox-rq` starts.
- Shows how long each audit took to generate and send
- English, Slovak, Czech, German

## Installation / upgrade

1. Install the plugin into the NetBox virtual environment:

```bash
source /opt/netbox/venv/bin/activate
pip install --upgrade --force-reinstall git+https://github.com/ArK761/NetBoxSelf_Audit.git@1.0.0
```

2. **Required:** enable the plugin in `/opt/netbox/netbox/netbox/configuration.py` (add it to the existing list):

```python
PLUGINS = [
    # ... other plugins ...
    "netbox_self_audit",
]
```

3. **Recommended:** add the plugin to `/opt/netbox/local_requirements.txt`, so that NetBox's `upgrade.sh` installs it
   again after a NetBox upgrade (otherwise NetBox does not start after the upgrade, because the plugin is enabled in
   `configuration.py` but no longer installed):

```
netbox-self-audit @ git+https://github.com/ArK761/NetBoxSelf_Audit.git@1.0.0
```

The plugin is not on PyPI, so the line must contain the GitHub address, not only the name.

4. Run the migration and restart NetBox and its background worker:

```bash
cd /opt/netbox/netbox
./manage.py migrate netbox_self_audit
systemctl restart netbox netbox-rq
```

## Features

### Watched fields (NetBoxSelf Audit → Watched fields)

- Choose a NetBox object type (Device, Tenant, IP address, Prefix, IP range, VLAN, VLAN group, Virtual machine, …).
- The fields are listed in the same order and sections as in the NetBox edit form; custom fields follow in their
  NetBox order (group, weight).
- Tick the fields to watch, set a severity (Low / Medium / High / Critical) and optionally the log message.
  *Object created* and *Object deleted* can be watched too. Nothing is watched until you choose it.
- Log message placeholders: `{user}`, `{object}`, `{object_type}`, `{field}`, `{old}`, `{new}`, `{added}`,
  `{removed}`, `{changes}`, `{action}`. An empty message uses the default text in the selected language
  (the user is not repeated in the default text; it has its own column).
  Ready-made templates can be picked next to each message, placeholder buttons insert at the cursor and a preview
  shows the resulting text.
- An overview shows all watched object types as green buttons (click to edit) with their fields; **Delete** removes all watched fields of an object type. The editing screen has a Back button that asks whether to save unsaved changes.

### Settings (NetBoxSelf Audit → Settings)

- Language (English, Slovak, Czech, German) and date/time format.
- Minimum severity in the report.
- Default period on the Audit page (today, yesterday, last 7 days).
- Report header: text at the top of the report, PDF and e-mail and at the start of the e-mail subject.
- Record NetBox version and plugin changes (on by default) and the severity of each kind of change.

### Audit (NetBoxSelf Audit → Audit)

- Period: today, yesterday, a chosen day, date range, last 7 days, all.
- Filter by object types and minimum severity.
- Two views (default chosen in Settings, also used for the PDF and the automatic e-mail):
  - **By object** (tree): object type → object → its changes (oldest first), with the highest severity of each branch
    (in the PDF and e-mail each object is in its own frame and is never split across two PDF pages, unless it is longer than a page);
    expand / collapse all; deleted objects are marked.
  - **By time**: one table, newest first.
- Each change shows time, severity, user, the change and a link to the NetBox changelog entry.
- **Object created**: all filled fields of the new object are listed, watched or not. **Object deleted**: only the
  information that it was deleted. **Changes**: only watched fields.
- Lists (e.g. a multi-object custom field with 10 PCs, tags) and multi-line text show only the added (+) and
  removed (−) items / lines.
- Download as PDF or HTML, or send by e-mail (recipients chosen in a dialog; the audit goes either in the e-mail body
  or as a PDF attachment,
  optionally password protected).

### NetBox version and plugins

Changes of the NetBox version and of the installed plugins (installed, removed, updated) are recorded (can be
switched off in Settings). The severity of each kind is set in Settings; defaults: NetBox version High, plugin
installed Critical, plugin removed Critical, plugin updated Medium. The check runs every minute in the NetBox background worker (`netbox-rq`); the
first run only stores the current state.

### E-mail (NetBoxSelf Audit → E-mail)

- Own SMTP settings like in LibreNMS (none / SSL / STARTTLS, Auto TLS, authentication, sender name and address,
  timeout). When the SMTP server is empty, NetBox's own `EMAIL` settings are used.
- Test e-mail (uses the saved settings, recipients chosen in a dialog).
- Automatic audit e-mail: daily (previous day), weekly (last 7 days, on a chosen weekday) or monthly
  (previous month, on the 1st) at a chosen time; optionally also when there were no changes.
- The audit goes either in the e-mail body or as a PDF attachment (then the e-mail has only a short summary); the PDF
  can be password protected (128-bit;
  printing and copying allowed, editing blocked).
- Results of the automatic e-mail are written to the NetBox log (`netbox.plugins.netbox_self_audit`).
- The Audit page, the PDF and the "sent" message show how long the audit took to generate / send.

### Monitoring (heartbeat)

The background check (NetBox background worker `netbox-rq`) reports every minute. If it has not run for longer than
the set time (Settings: 5 or 10 minutes, default 10):

- all plugin pages show a red warning;
- `http://<netbox>/plugins/self-audit/health/` returns HTTP **503** with `ERROR` and the reason, otherwise HTTP
  **200** with `OK` and the time of the last run. The address needs no login and shows only this status.

Add it to LibreNMS as an HTTP service (Services → Add service → type `http`, parameters e.g.
`-u /plugins/self-audit/health/ -s OK`) or to any other monitoring. Monitoring can be switched off in Settings.
The address itself can be switched off in Settings (then it returns 404). The limit is 5 or 10 minutes: the check
runs every minute but not to the second, so a shorter limit would give false alarms.

**Check now:** the button on the Audit page sends a test job to `netbox-rq` and waits up to 15 seconds for the
answer – it shows at once whether the background worker is running.

If a background run is interrupted (e.g. `netbox-rq` restarted while it was running), it is cleared automatically
when `netbox-rq` starts, so the schedule does not stay blocked.

### Data and limits

- The changes come from the NetBox changelog, so the audit reaches back as far as NetBox keeps it
  (`CHANGELOG_RETENTION`, 90 days by default). Watched fields apply to the whole stored changelog, also to changes
  made before the field was watched.
- The SMTP password and the PDF password are stored in the NetBox database as plain text (not encrypted) and are
  not shown back in the form.
