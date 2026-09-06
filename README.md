# Joongbu LMS monitor

Runs every 10 minutes on GitHub Actions and sends new or changed Canvas announcements and assignments to Discord and optionally Gmail. Repository code and `state.json` contain no LMS token, webhook, message body, title, course name, or email credential. `state.json` stores resource IDs and SHA-256 fingerprints only.

Required repository secrets: `CANVAS_TOKEN`, `DISCORD_WEBHOOK`. Optional Gmail secrets: `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`.

The first successful run creates a baseline without sending old items. Later runs notify on new items or changes to title, body, due date, lock date, or submission type. Delivery status remains only until all configured channels succeed. The workflow uses only GET requests to the Canvas API. LearningX external boards/resources are outside this cloud monitor.

GitHub may delay scheduled jobs during heavy load. The schedule is polling, not an instant webhook. The LMS token expires on 2027-01-01 and must then be replaced.
