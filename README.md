# Free Fire Likes Bot

This starter bot accepts Free Fire UID requests, sends each request to one admin for approval,
and enforces a 24-hour cooldown after the admin marks a request completed.

## Important
- This bot does **not** send Free Fire likes by itself. Connect only an official/authorized
  game API or an authorized provider before promising or automating likes.
- Do not ask users for their Free Fire password or login code.
- SQLite is suitable for a small test, but use persistent storage (or a managed database)
  on your hosting platform so data survives restarts/redeploys.

## Deploy on Render
Create a **Background Worker** (not Web Service) from this GitHub repository.
- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `python main.py`
- Environment variables:
  - `BOT_TOKEN`: token from @BotFather (keep secret)
  - `ADMIN_ID`: your numeric Telegram user ID

## Admin workflow
1. A user sends their numeric Free Fire UID.
2. The bot forwards the request to the admin with Approve/Reject buttons.
3. After approving, the admin performs the permitted like action manually/through an authorized service.
4. When finished, the admin sends `/complete REQUEST_ID` in the bot.
5. The user's 24-hour cooldown starts at completion.

Use `/status` to check the latest request.
