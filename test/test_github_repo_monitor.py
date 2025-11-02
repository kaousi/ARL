import unittest
from datetime import datetime, timedelta
from app.services.github_repo_monitor import (
    GithubRepoMonitor,
    monitor_github_repo,
    format_events_for_dingtalk
)
from app.services.dingtalk_webhook import DingTalkWebhook, send_github_event_notification
from app.config import Config


class TestGithubRepoMonitor(unittest.TestCase):
    """Test GitHub repository monitoring functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Use a public repository for testing
        self.repo_owner = "octocat"
        self.repo_name = "Hello-World"
    
    def test_github_repo_monitor_init(self):
        """Test GithubRepoMonitor initialization"""
        monitor = GithubRepoMonitor(self.repo_owner, self.repo_name)
        self.assertEqual(monitor.repo_owner, self.repo_owner)
        self.assertEqual(monitor.repo_name, self.repo_name)
        self.assertEqual(monitor.full_repo_name, f"{self.repo_owner}/{self.repo_name}")
        self.assertIsInstance(monitor.monitored_events, list)
        self.assertIn('PushEvent', monitor.monitored_events)
    
    def test_github_repo_monitor_with_custom_events(self):
        """Test GithubRepoMonitor with custom event types"""
        custom_events = ['PushEvent', 'IssuesEvent']
        monitor = GithubRepoMonitor(
            self.repo_owner, 
            self.repo_name, 
            monitored_events=custom_events
        )
        self.assertEqual(monitor.monitored_events, custom_events)
    
    def test_fetch_events(self):
        """Test fetching events from GitHub (requires valid token)"""
        if not Config.GITHUB_TOKEN:
            self.skipTest("GITHUB_TOKEN not configured")
        
        monitor = GithubRepoMonitor(self.repo_owner, self.repo_name)
        
        # Fetch events from last 24 hours
        since_time = datetime.now() - timedelta(days=1)
        events = monitor.fetch_events(since_time=since_time)
        
        # Should return a list (may be empty if no recent events)
        self.assertIsInstance(events, list)
    
    def test_monitor_github_repo_function(self):
        """Test the standalone monitor function"""
        if not Config.GITHUB_TOKEN:
            self.skipTest("GITHUB_TOKEN not configured")
        
        events = monitor_github_repo(
            self.repo_owner,
            self.repo_name,
            since_time=datetime.now() - timedelta(days=7)
        )
        
        self.assertIsInstance(events, list)
    
    def test_format_events_for_dingtalk(self):
        """Test DingTalk markdown formatting"""
        # Create mock events
        mock_events = []
        
        markdown = format_events_for_dingtalk(
            self.repo_owner,
            self.repo_name,
            mock_events
        )
        
        self.assertIsInstance(markdown, str)
        self.assertIn("GitHub 仓库监控", markdown)
        self.assertIn(f"{self.repo_owner}/{self.repo_name}", markdown)


class TestDingTalkWebhook(unittest.TestCase):
    """Test DingTalk webhook functionality"""
    
    def test_dingtalk_webhook_init(self):
        """Test DingTalkWebhook initialization"""
        webhook_url = "https://oapi.dingtalk.com/robot/send?access_token=test"
        secret = "test_secret"
        
        dingtalk = DingTalkWebhook(webhook_url, secret)
        self.assertEqual(dingtalk.webhook_url, webhook_url)
        self.assertEqual(dingtalk.secret, secret)
    
    def test_dingtalk_webhook_init_with_config(self):
        """Test DingTalkWebhook initialization with Config"""
        dingtalk = DingTalkWebhook()
        self.assertEqual(dingtalk.webhook_url, Config.DINGTALK_WEBHOOK_URL)
        self.assertEqual(dingtalk.secret, Config.DINGDING_SECRET)
    
    def test_generate_sign(self):
        """Test DingTalk signature generation"""
        webhook_url = "https://oapi.dingtalk.com/robot/send?access_token=test"
        secret = "test_secret"
        
        dingtalk = DingTalkWebhook(webhook_url, secret)
        timestamp, sign = dingtalk._generate_sign()
        
        self.assertIsInstance(timestamp, str)
        self.assertIsInstance(sign, str)
        self.assertTrue(len(timestamp) > 0)
        self.assertTrue(len(sign) > 0)


class TestIntegration(unittest.TestCase):
    """Integration tests (require valid configuration)"""
    
    def test_end_to_end_monitoring(self):
        """Test complete monitoring workflow"""
        if not Config.GITHUB_TOKEN:
            self.skipTest("GITHUB_TOKEN not configured")
        
        if not Config.DINGTALK_WEBHOOK_URL:
            self.skipTest("DINGTALK_WEBHOOK_URL not configured")
        
        # This test requires valid credentials
        # Fetch events
        events = monitor_github_repo(
            "octocat",
            "Hello-World",
            since_time=datetime.now() - timedelta(days=7)
        )
        
        # Format for DingTalk
        markdown = format_events_for_dingtalk("octocat", "Hello-World", events)
        
        self.assertIsInstance(markdown, str)
        self.assertTrue(len(markdown) > 0)
        
        # Note: Uncomment to actually send notification (will use real webhook)
        # response = send_github_event_notification("octocat", "Hello-World", events)
        # self.assertEqual(response.get("errcode", -1), 0)


if __name__ == '__main__':
    unittest.main()
