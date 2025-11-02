# GitHub Repository Monitoring with DingTalk Webhook

This feature enables monitoring of GitHub repositories for events (commits, issues, PRs, etc.) and sends notifications to DingTalk when events occur.

## Features

- Monitor GitHub repositories for various event types:
  - Push events (commits)
  - Issues (created, closed, etc.)
  - Pull requests
  - Branch/tag creation and deletion
  - Releases
- Send formatted notifications to DingTalk webhook
- Schedule monitoring tasks using cron expressions
- Track event history to avoid duplicate notifications

## Configuration

### 1. Configure GitHub Token

Edit `app/config.yaml` and add your GitHub Personal Access Token:

```yaml
GITHUB:
  TOKEN: "your_github_personal_access_token"
```

You can create a GitHub token at: https://github.com/settings/tokens

### 2. Configure DingTalk Webhook

Edit `app/config.yaml` and add your DingTalk webhook configuration:

```yaml
DINGDING:
  SECRET: "your_dingtalk_secret"
  ACCESS_TOKEN: "your_access_token"  # For legacy code leak monitoring
  # New webhook URL for GitHub repository monitoring
  WEBHOOK_URL: "https://oapi.dingtalk.com/robot/send?access_token=YOUR_ACCESS_TOKEN"
```

To create a DingTalk webhook:
1. Go to your DingTalk group settings
2. Add a custom robot
3. Enable security settings (signature verification) and copy the secret
4. Copy the webhook URL

Reference: https://open.dingtalk.com/document/robots/custom-robot-access

## Usage

### Via API

#### 1. Create a GitHub Repository Monitor

**POST** `/api/github_repo_scheduler/`

```json
{
  "name": "Monitor my-repo",
  "repo_owner": "username",
  "repo_name": "repository-name",
  "cron": "0 */1 * * *",
  "monitored_events": ["PushEvent", "IssuesEvent", "PullRequestEvent"]
}
```

Parameters:
- `name`: A friendly name for the monitoring task
- `repo_owner`: GitHub username or organization name
- `repo_name`: Repository name
- `cron`: Cron expression for scheduling (e.g., "0 */1 * * *" = every hour)
- `monitored_events` (optional): List of event types to monitor. Defaults to:
  - `PushEvent`: Commits pushed to repository
  - `IssuesEvent`: Issues created, closed, etc.
  - `PullRequestEvent`: Pull requests created, merged, etc.
  - `CreateEvent`: Branch/tag creation
  - `DeleteEvent`: Branch/tag deletion
  - `ReleaseEvent`: New releases

#### 2. List All Monitors

**GET** `/api/github_repo_scheduler/`

Query parameters:
- `page`: Page number (default: 1)
- `size`: Items per page (default: 10)
- `name`: Filter by name
- `repo_owner`: Filter by repository owner
- `status`: Filter by status (running/stop)

#### 3. Update a Monitor

**POST** `/api/github_repo_scheduler/update/`

```json
{
  "_id": "scheduler_id",
  "name": "Updated name",
  "cron": "0 */2 * * *"
}
```

#### 4. Stop a Monitor

**POST** `/api/github_repo_scheduler/stop/`

```json
{
  "_id": ["scheduler_id1", "scheduler_id2"]
}
```

#### 5. Resume a Monitor

**POST** `/api/github_repo_scheduler/recover/`

```json
{
  "_id": ["scheduler_id1", "scheduler_id2"]
}
```

#### 6. Delete a Monitor

**POST** `/api/github_repo_scheduler/delete/`

```json
{
  "_id": ["scheduler_id1", "scheduler_id2"]
}
```

## How It Works

1. **Scheduler**: The system checks scheduled monitors every minute
2. **Event Fetching**: When it's time to run, the system fetches recent events from GitHub API
3. **Deduplication**: Events are compared against previous runs to identify new events only
4. **Storage**: New events are stored in MongoDB (`github_repo_event` collection)
5. **Notification**: A formatted markdown notification is sent to DingTalk webhook

## DingTalk Notification Format

Notifications are sent in markdown format with the following information:
- Repository name with link
- Event count
- For each event (up to 10):
  - Event type
  - Actor (who triggered the event)
  - Timestamp
  - Event summary
  - Relevant links (issue URL, PR URL, release URL, etc.)

Example notification:
```
### GitHub 仓库监控

**仓库**: [username/repo-name](https://github.com/username/repo-name)
**事件数量**: 3

---

**1. PushEvent**
- **操作者**: developer
- **时间**: 2024-01-15T10:30:00Z
- **详情**: developer pushed 2 commit(s) to main
- **提交信息**: Fix bug in authentication

**2. IssuesEvent**
- **操作者**: user123
- **时间**: 2024-01-15T09:15:00Z
- **详情**: user123 opened issue: Add new feature
- **Issue链接**: https://github.com/username/repo/issues/42
```

## Database Collections

The feature uses the following MongoDB collections:

- `github_repo_scheduler`: Stores monitoring schedules
- `github_repo_task`: Stores task execution records
- `github_repo_event`: Stores GitHub events

## Troubleshooting

### No notifications received

1. Check that `GITHUB_TOKEN` is configured correctly
2. Verify `DINGTALK_WEBHOOK_URL` and `DINGDING_SECRET` are set
3. Check scheduler logs for errors
4. Ensure the repository owner and name are correct

### Rate limiting

GitHub API has rate limits:
- Authenticated requests: 5,000 requests per hour
- The system includes automatic rate limiting with sleep delays

### Scheduler not running

Make sure the scheduler process is running:
```bash
python3 -m app.scheduler
```

## Architecture

```
┌─────────────────┐
│   Scheduler     │
│  (cron-based)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  GitHub API     │
│  Fetch Events   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Filter &      │
│   Deduplicate   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Store Events in │
│    MongoDB      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Format &       │
│  Send DingTalk  │
└─────────────────┘
```

## Example Use Cases

1. **Monitor production repository**: Get notified of any commits to production branch
2. **Track PR reviews**: Be alerted when PRs are opened or merged
3. **Release notifications**: Get notified when new releases are published
4. **Issue tracking**: Monitor new issues being created
5. **Branch management**: Track branch creation and deletion

## Security Notes

- Keep your GitHub token secure
- Use DingTalk signature verification (SECRET)
- Limit GitHub token permissions to read-only access
- Consider using environment variables for sensitive configuration
