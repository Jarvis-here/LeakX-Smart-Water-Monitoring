LeakX V14 — Left Navigation Admin Dashboard

This version keeps the V11 functionality and moves the admin tab navigation into a fixed left sidebar on desktop.

Pages:
  /             Login-first landing page
  /dashboard    Admin dashboard with left-side navigation
  /report-leak  Customer leak reporting page

Desktop dashboard navigation:
  Overview
  Live Monitoring
  Incidents
  Reports
  Controls

The sidebar collapses back to the existing horizontal navigation behavior on smaller screens for mobile usability.

Run:
  python -m pip install fastapi uvicorn python-multipart itsdangerous
  python -m uvicorn main:app --reload

UI font: Roboto (loaded from Google Fonts with system fallbacks).


UI update: V16 minimal light theme with aligned content, Roboto typography, soft status colors, and responsive layout. Existing database file is preserved.


Leak alert sound:
  The dashboard uses static/leak-alert.mp3 as the leak alarm.
  Click "Alarm Sound — Off" once to enable browser audio before demonstrating a leak.
  The uploaded alarm loops while a leak alert is active and stops when acknowledged or resolved.
