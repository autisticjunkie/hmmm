# Telegram Referral Bot

A Telegram bot that tracks referrals and manages a referral program for your group.

## Features

- Generate unique invite links for users
- Track referrals when users join via invite links
- Maintain a leaderboard of top referrers
- Track when users leave and update referral counts
- Notify users when their referrals join or leave

## Setup

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up your bot token in main.py
4. Set your group ID in main.py

## Deployment to Render

1. Create a Render account at https://render.com
2. Create a new Web Service
3. Connect your GitHub repository
4. Configure the service:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python main.py`
   - Environment Variables: None required

## Commands

- `/start` - Get your referral link
- `/leaderboard` - View top referrers
- `/myreferrals` - Check your referral stats

## Making Updates

1. Clone the repository locally
2. Make your changes
3. Push to GitHub
4. Render will automatically redeploy

## Database

The bot uses SQLite for data storage. The database file is created automatically when the bot starts.
