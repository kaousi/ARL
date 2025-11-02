from app.utils import http_req, get_logger, gen_md5
from app.config import Config
from app.utils.time import parse_datetime
import time
from datetime import datetime, timedelta

logger = get_logger()


class GithubRepoEvent:
    """Represents a GitHub repository event"""
    
    def __init__(self, event_data, event_type):
        self.event_data = event_data
        self.event_type = event_type
        self.repo_name = event_data.get('repo', {}).get('name', '')
        self.created_at = event_data.get('created_at', '')
        self._parse_event()
    
    def _parse_event(self):
        """Parse event data based on event type"""
        self.actor = self.event_data.get('actor', {}).get('login', 'Unknown')
        self.event_id = self.event_data.get('id', '')
        
        payload = self.event_data.get('payload', {})
        
        if self.event_type == 'PushEvent':
            self.commits = payload.get('commits', [])
            self.ref = payload.get('ref', '')
            self.size = payload.get('size', 0)
        elif self.event_type == 'IssuesEvent':
            self.action = payload.get('action', '')
            self.issue = payload.get('issue', {})
        elif self.event_type == 'PullRequestEvent':
            self.action = payload.get('action', '')
            self.pull_request = payload.get('pull_request', {})
        elif self.event_type == 'CreateEvent':
            self.ref_type = payload.get('ref_type', '')
            self.ref = payload.get('ref', '')
        elif self.event_type == 'DeleteEvent':
            self.ref_type = payload.get('ref_type', '')
            self.ref = payload.get('ref', '')
        elif self.event_type == 'ReleaseEvent':
            self.action = payload.get('action', '')
            self.release = payload.get('release', {})
    
    def to_dict(self):
        """Convert event to dictionary"""
        return {
            'event_id': self.event_id,
            'event_type': self.event_type,
            'repo_name': self.repo_name,
            'actor': self.actor,
            'created_at': self.created_at,
            'event_data': self.event_data
        }
    
    def get_summary(self):
        """Get a human-readable summary of the event"""
        if self.event_type == 'PushEvent':
            branch = self.ref.split('/')[-1] if self.ref else 'unknown'
            return f"{self.actor} pushed {self.size} commit(s) to {branch}"
        elif self.event_type == 'IssuesEvent':
            issue_title = self.issue.get('title', 'Unknown issue')
            return f"{self.actor} {self.action} issue: {issue_title}"
        elif self.event_type == 'PullRequestEvent':
            pr_title = self.pull_request.get('title', 'Unknown PR')
            return f"{self.actor} {self.action} pull request: {pr_title}"
        elif self.event_type == 'CreateEvent':
            return f"{self.actor} created {self.ref_type}: {self.ref}"
        elif self.event_type == 'DeleteEvent':
            return f"{self.actor} deleted {self.ref_type}: {self.ref}"
        elif self.event_type == 'ReleaseEvent':
            release_name = self.release.get('name', self.release.get('tag_name', 'Unknown'))
            return f"{self.actor} {self.action} release: {release_name}"
        else:
            return f"{self.actor} triggered {self.event_type}"


class GithubRepoMonitor:
    """Monitor GitHub repository for events"""
    
    def __init__(self, repo_owner, repo_name, monitored_events=None):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.full_repo_name = f"{repo_owner}/{repo_name}"
        
        # Default events to monitor
        if monitored_events is None:
            self.monitored_events = [
                'PushEvent', 
                'IssuesEvent', 
                'PullRequestEvent',
                'CreateEvent',
                'DeleteEvent',
                'ReleaseEvent'
            ]
        else:
            self.monitored_events = monitored_events
        
        self.events = []
    
    def fetch_events(self, since_time=None):
        """
        Fetch recent events from GitHub repository
        
        Args:
            since_time: Only fetch events after this time (datetime object)
        
        Returns:
            List of GithubRepoEvent objects
        """
        if not Config.GITHUB_TOKEN:
            logger.error("GITHUB_TOKEN is not configured")
            return []
        
        url = f"https://api.github.com/repos/{self.full_repo_name}/events"
        
        headers = {
            "Authorization": f"Bearer {Config.GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        try:
            # Add rate limiting
            time.sleep(1)
            
            conn = http_req(url, headers=headers)
            
            if conn.status_code != 200:
                logger.error(f"Failed to fetch events for {self.full_repo_name}: {conn.status_code}")
                return []
            
            data = conn.json()
            
            for event_data in data:
                event_type = event_data.get('type', '')
                
                # Filter by event type
                if event_type not in self.monitored_events:
                    continue
                
                # Filter by time if specified
                if since_time:
                    event_created_at = parse_datetime(event_data.get('created_at', ''))
                    if event_created_at and event_created_at <= since_time:
                        continue
                
                event = GithubRepoEvent(event_data, event_type)
                self.events.append(event)
            
            logger.info(f"Fetched {len(self.events)} events for {self.full_repo_name}")
            return self.events
            
        except Exception as e:
            logger.exception(f"Error fetching events for {self.full_repo_name}: {e}")
            return []
    
    def get_events_summary(self):
        """Get a summary of all events"""
        if not self.events:
            return "No new events"
        
        summary = []
        for event in self.events:
            summary.append(event.get_summary())
        
        return summary


def monitor_github_repo(repo_owner, repo_name, since_time=None, monitored_events=None):
    """
    Monitor a GitHub repository and return new events
    
    Args:
        repo_owner: GitHub repository owner
        repo_name: GitHub repository name
        since_time: Only fetch events after this time
        monitored_events: List of event types to monitor
    
    Returns:
        List of GithubRepoEvent objects
    """
    monitor = GithubRepoMonitor(repo_owner, repo_name, monitored_events)
    return monitor.fetch_events(since_time)


def format_events_for_dingtalk(repo_owner, repo_name, events):
    """
    Format GitHub events for DingTalk markdown notification
    
    Args:
        repo_owner: GitHub repository owner
        repo_name: GitHub repository name
        events: List of GithubRepoEvent objects
    
    Returns:
        Formatted markdown string
    """
    if not events:
        return f"### GitHub 仓库监控 - {repo_owner}/{repo_name}\n\n暂无新事件"
    
    markdown = f"### GitHub 仓库监控\n\n"
    markdown += f"**仓库**: [{repo_owner}/{repo_name}](https://github.com/{repo_owner}/{repo_name})\n\n"
    markdown += f"**事件数量**: {len(events)}\n\n"
    markdown += "---\n\n"
    
    for idx, event in enumerate(events[:10], 1):  # Limit to 10 events
        markdown += f"**{idx}. {event.event_type}**\n\n"
        markdown += f"- **操作者**: {event.actor}\n"
        markdown += f"- **时间**: {event.created_at}\n"
        markdown += f"- **详情**: {event.get_summary()}\n\n"
        
        # Add specific details based on event type
        if event.event_type == 'PushEvent' and hasattr(event, 'commits'):
            if event.commits:
                commit = event.commits[0]
                markdown += f"- **提交信息**: {commit.get('message', 'N/A')[:100]}\n"
        elif event.event_type == 'IssuesEvent' and hasattr(event, 'issue'):
            markdown += f"- **Issue链接**: {event.issue.get('html_url', 'N/A')}\n"
        elif event.event_type == 'PullRequestEvent' and hasattr(event, 'pull_request'):
            markdown += f"- **PR链接**: {event.pull_request.get('html_url', 'N/A')}\n"
        elif event.event_type == 'ReleaseEvent' and hasattr(event, 'release'):
            markdown += f"- **Release链接**: {event.release.get('html_url', 'N/A')}\n"
        
        markdown += "\n"
    
    if len(events) > 10:
        markdown += f"\n... 还有 {len(events) - 10} 个事件未显示\n"
    
    return markdown
