# Slack Integration Setup Guide

This guide walks you through setting up the Slack integration for the MCP Cooking Lab Notebook system.

## Overview

The Slack integration provides:
- **Slash Commands**: `/cook-feedback` and `/cook-schedule` for interactive feedback collection
- **Modal Forms**: Rich feedback collection with structured data (rating, doneness, salt level, notes)
- **Scheduled Notifications**: Automated feedback prompts after cooking sessions
- **Interactive Buttons**: Quick rating and detailed feedback options
- **Direct Messages**: Natural language feedback processing

## Prerequisites

1. Slack workspace with admin permissions
2. MCP Cooking Lab Notebook system running
3. Public URL accessible by Slack (for webhooks)

## Step 1: Create Slack App

1. **Go to Slack API Dashboard**
   - Visit https://api.slack.com/apps
   - Click "Create New App"
   - Choose "From an app manifest"

2. **Use the Provided Manifest**
   - Copy the contents of `slack_manifest.json` in the project root
   - Update the URLs to point to your deployment:
     - Replace `https://your-domain.com` with your actual domain
     - Example: `https://cooking-lab.example.com/slack/events`

3. **Configure App Settings**
   - App Name: "MCP Cooking Lab Notebook"
   - Description: "Collect feedback on cooking sessions and experiments"
   - Icon: Upload a cooking-related icon (optional)

## Step 2: Configure OAuth & Permissions

1. **OAuth Scopes**
   The manifest includes these required scopes:
   - `app_mentions:read` - Detect when the bot is mentioned
   - `channels:read` - Read channel information
   - `chat:write` - Send messages
   - `commands` - Handle slash commands
   - `im:history`, `im:read`, `im:write` - Direct message handling
   - `users:read`, `users:read.email` - User information
   - `files:read`, `files:write` - File handling (for future features)

2. **Install App to Workspace**
   - Click "Install App to Workspace"
   - Authorize the requested permissions
   - Copy the "Bot User OAuth Token" (starts with `xoxb-`)

## Step 3: Configure Environment Variables

Add these environment variables to your `.env` file:

```bash
# Slack Configuration
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_SIGNING_SECRET=your-signing-secret-here
SLACK_APP_TOKEN=xapp-your-app-token-here  # Optional, for Socket Mode
```

To find these values:
- **Bot Token**: OAuth & Permissions → Bot User OAuth Token
- **Signing Secret**: Basic Information → App Credentials → Signing Secret
- **App Token**: Basic Information → App-Level Tokens (create if needed)

## Step 4: Configure Webhook URLs

Update these URLs in your Slack app settings to point to your deployment:

1. **Slash Commands**
   - `/cook-feedback`: `https://your-domain.com/slack/commands/cook-feedback`
   - `/cook-schedule`: `https://your-domain.com/slack/commands/cook-schedule`

2. **Interactivity & Shortcuts**
   - Request URL: `https://your-domain.com/slack/interactive`

3. **Event Subscriptions**
   - Request URL: `https://your-domain.com/slack/events`
   - Subscribe to Bot Events:
     - `app_mention`
     - `message.im`

## Step 5: Test the Integration

1. **Health Check**
   ```bash
   curl https://your-domain.com/slack/health
   ```
   Should return: `{"status":"healthy","slack_configured":true}`

2. **Slash Command Test**
   - In Slack: `/cook-feedback 2024-12-15_test-entry`
   - Should open a feedback modal or show quick rating buttons

3. **App Mention Test**
   - In a channel: `@CookingLab feedback`
   - Bot should respond with feedback options

4. **Direct Message Test**
   - Send a DM to the bot: "The dinner was delicious!"
   - Bot should process and respond appropriately

## Step 6: Configure Family Members

To enable spouse/family feedback collection:

1. **Get User IDs**
   ```bash
   # Use Slack Web API to get user info
   curl -H "Authorization: Bearer xoxb-your-bot-token" \
        "https://slack.com/api/users.list"
   ```

2. **Update Configuration**
   Add family member user IDs to your environment:
   ```bash
   SLACK_FAMILY_USER_IDS=U1234567890,U0987654321
   SLACK_DEFAULT_NOTIFICATION_CHANNEL=C1234567890  # Optional: default channel
   ```

## Features Overview

### Slash Commands

#### `/cook-feedback <entry-id>`
Opens a modal for detailed feedback collection with:
- Overall rating (1-10 stars)
- Doneness level (perfect, under/overdone)
- Salt level (perfect, needs more, too salty)
- Free-form notes and comments

#### `/cook-schedule <entry-id> [delay-minutes]`
Schedules automated feedback collection:
- Default: 45 minutes after dinner time
- Sends notification with quick action buttons
- Customizable delay per session

### Interactive Components

#### Quick Rating Buttons
- ⭐ Rate 1-5 / ⭐⭐⭐⭐⭐ Rate 6-10
- 📝 Detailed Feedback (opens modal)
- Instant feedback submission

#### Feedback Modal
- Structured form with validation
- Real-time preview of submission
- Integration with MCP server for storage

### Automated Notifications

The system automatically:
1. Detects `dinner_time` from notebook entries
2. Schedules notifications 45 minutes later (configurable)
3. Sends personalized prompts to family members
4. Provides quick rating and detailed feedback options
5. Stores responses in the Git-backed notebook

### Natural Language Processing

Basic NLP for direct messages:
- "Good", "great", "delicious" → 8/10 rating
- "Bad", "terrible", "burnt" → 3/10 rating
- "OK", "fine", "average" → 6/10 rating
- General messages → Helpful response with guidance

## Troubleshooting

### Common Issues

1. **"Slack service not configured"**
   - Check environment variables are set correctly
   - Verify bot token starts with `xoxb-`
   - Restart the application after adding environment variables

2. **Webhook verification fails**
   - Ensure signing secret matches exactly
   - Check URL is publicly accessible
   - Verify SSL certificate is valid

3. **Modal doesn't open**
   - Check interactive components URL is correct
   - Verify app has required scopes
   - Test with a valid entry ID

4. **Notifications not sending**
   - Check user IDs are correct
   - Verify bot can DM users (they must have DM'd the bot first)
   - Check error logs for API failures

### Debug Endpoints

```bash
# Check Slack configuration
curl https://your-domain.com/slack/health

# Test notification channels
curl https://your-domain.com/notifier/channels

# Manually send feedback prompt
curl -X POST https://your-domain.com/slack/send-feedback-prompt \
     -H "Content-Type: application/json" \
     -d '{"user_id":"U1234567890","entry_id":"2024-12-15_test","title":"Test Entry"}'
```

### Logs

Monitor these log files for debugging:
- Application logs: `./logs/app.log`
- Slack API responses: Look for `slack_service` entries
- Webhook deliveries: Slack app dashboard → Event Subscriptions

## Security Considerations

1. **Signature Verification**: All Slack requests are verified using HMAC signatures
2. **Rate Limiting**: 100 requests per minute per IP by default
3. **Input Validation**: All entry IDs and user inputs are validated
4. **Token Security**: Store tokens as environment variables, never in code

## Production Deployment

For production deployment:

1. **SSL Certificate**: Required for Slack webhooks
2. **Load Balancing**: Ensure all instances can handle Slack webhooks
3. **Monitoring**: Set up alerts for webhook failures
4. **Backup**: Include Slack configuration in your backup strategy

## Advanced Configuration

### Custom Notification Templates

Modify notification messages in `app/services/slack_service.py`:

```python
def _create_feedback_prompt(self, entry_id: str, title: str):
    # Customize the message format and buttons
    pass
```

### Additional Slash Commands

Add new commands by:
1. Updating the Slack app manifest
2. Adding handlers in `SlackService._register_handlers()`
3. Creating endpoint routes in `app/routers/slack.py`

### Integration with Other Services

The Slack service integrates with:
- **MCP Server**: For reading/writing notebook entries
- **Feedback Service**: For processing and storing feedback
- **Scheduler Service**: For automated notification timing
- **Notifier Service**: For multi-channel support

## Support

For issues or questions:
1. Check the application logs
2. Review Slack app configuration
3. Test webhook URLs manually
4. Consult the main DEVELOPMENT.md documentation

The Slack integration is designed to be family-friendly and provide an intuitive way to collect cooking feedback without leaving the Slack environment.