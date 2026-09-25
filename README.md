# NetBoxSelf Audit

NetBox plugin that audits changes made in NetBox itself: you choose which object types and fields are watched,
give each a severity and optionally your own log message, and get a report (web page, PDF, CSV, HTML, e-mail)
of who changed what.

Requires NetBox 4.7.

## Installation / upgrade

```bash
pip install --upgrade --force-reinstall git+https://github.com/ArK761/NetBoxSelf_Audit.git@1.0.0
```

Enable the plugin in `configuration.py`:

```python
PLUGINS = ["netbox_self_audit"]
```

Run the migration and restart NetBox and its background worker:

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
  `{removed}`, `{changes}`, `{action}`. An empty message uses the default text in the selected language.
- An overview shows all watched object types and fields.
- Options: language (English, Slovak, Czech, German), date/time format, minimum severity in the report.

### Audit (NetBoxSelf Audit → Audit)

- Period: today, yesterday, a chosen day, date range, last 7 days, all.
- Filter by object types and minimum severity.
- Table: time, severity, user, object (link to the object), the change and a link to the NetBox changelog entry.
- Lists (e.g. a multi-object custom field with 10 PCs, tags) and multi-line text show only the added (+) and
  removed (−) items / lines.
- Download as PDF, CSV (Excel) or HTML, or send by e-mail (recipients chosen in a dialog, optional PDF attachment,
  optionally password protected).

### NetBox version and plugins

Changes of the NetBox version and of the installed plugins (installed, removed, updated) are always recorded as
Critical. The check runs every minute in the NetBox background worker (`netbox-rq`); the first run only stores the
current state.

### E-mail (NetBoxSelf Audit → E-mail)

- Own SMTP settings like in LibreNMS (none / SSL / STARTTLS, Auto TLS, authentication, sender name and address,
  timeout). When the SMTP server is empty, NetBox's own `EMAIL` settings are used.
- Test e-mail (uses the saved settings, recipients chosen in a dialog).
- Automatic audit e-mail: daily (previous day), weekly (last 7 days, on a chosen weekday) or monthly
  (previous month, on the 1st) at a chosen time; optionally also when there were no changes.
- The audit is always in the e-mail body; PDF attachment optional, optionally password protected (128-bit;
  printing and copying allowed, editing blocked).
- Results of the automatic e-mail are written to the NetBox log (`netbox.plugins.netbox_self_audit`).

### Data and limits

- The changes come from the NetBox changelog, so the audit reaches back as far as NetBox keeps it
  (`CHANGELOG_RETENTION`, 90 days by default). Watched fields apply to the whole stored changelog, also to changes
  made before the field was watched.
- The SMTP password and the PDF password are stored in the NetBox database as plain text (not encrypted) and are
  not shown back in the form.
