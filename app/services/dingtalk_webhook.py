import time
import base64
import hmac
import urllib.parse
import hashlib
from app.utils import http_req, get_logger
from app.config import Config

logger = get_logger()


class DingTalkWebhook:
    """DingTalk webhook notification service"""
    
    def __init__(self, webhook_url=None, secret=None):
        """
        Initialize DingTalk webhook
        
        Args:
            webhook_url: DingTalk webhook URL (if None, use Config.DINGTALK_WEBHOOK_URL)
            secret: DingTalk webhook secret (if None, use Config.DINGTALK_SECRET)
        """
        self.webhook_url = webhook_url or Config.DINGTALK_WEBHOOK_URL
        self.secret = secret or Config.DINGDING_SECRET
        
        if not self.webhook_url:
            logger.warning("DingTalk webhook URL is not configured")
    
    def _generate_sign(self):
        """Generate DingTalk webhook signature"""
        timestamp = str(round(time.time() * 1000))
        secret_enc = self.secret.encode('utf-8')
        string_to_sign = f'{timestamp}\n{self.secret}'
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return timestamp, sign
    
    def send_text(self, content, at_mobiles=None, is_at_all=False):
        """
        Send text message to DingTalk
        
        Args:
            content: Text content
            at_mobiles: List of mobile numbers to @
            is_at_all: Whether to @ all members
        
        Returns:
            Response data from DingTalk
        """
        if not self.webhook_url:
            logger.error("DingTalk webhook URL is not configured")
            return {"errcode": -1, "errmsg": "Webhook URL not configured"}
        
        url = self.webhook_url
        
        # Add signature if secret is configured
        if self.secret:
            timestamp, sign = self._generate_sign()
            url = f"{url}&timestamp={timestamp}&sign={sign}"
        
        message = {
            "msgtype": "text",
            "text": {
                "content": content
            }
        }
        
        if at_mobiles or is_at_all:
            message["at"] = {
                "atMobiles": at_mobiles or [],
                "isAtAll": is_at_all
            }
        
        try:
            conn = http_req(url, method='post', json=message)
            response = conn.json()
            
            if response.get("errcode", -1) == 0:
                logger.info("DingTalk text message sent successfully")
            else:
                logger.warning(f"DingTalk send failed: {response}")
            
            return response
            
        except Exception as e:
            logger.exception(f"Error sending DingTalk message: {e}")
            return {"errcode": -1, "errmsg": str(e)}
    
    def send_markdown(self, title, content, at_mobiles=None, is_at_all=False):
        """
        Send markdown message to DingTalk
        
        Args:
            title: Message title
            content: Markdown content
            at_mobiles: List of mobile numbers to @
            is_at_all: Whether to @ all members
        
        Returns:
            Response data from DingTalk
        """
        if not self.webhook_url:
            logger.error("DingTalk webhook URL is not configured")
            return {"errcode": -1, "errmsg": "Webhook URL not configured"}
        
        url = self.webhook_url
        
        # Add signature if secret is configured
        if self.secret:
            timestamp, sign = self._generate_sign()
            url = f"{url}&timestamp={timestamp}&sign={sign}"
        
        message = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": content
            }
        }
        
        if at_mobiles or is_at_all:
            message["at"] = {
                "atMobiles": at_mobiles or [],
                "isAtAll": is_at_all
            }
        
        try:
            conn = http_req(url, method='post', json=message)
            response = conn.json()
            
            if response.get("errcode", -1) == 0:
                logger.info("DingTalk markdown message sent successfully")
            else:
                logger.warning(f"DingTalk send failed: {response}")
            
            return response
            
        except Exception as e:
            logger.exception(f"Error sending DingTalk message: {e}")
            return {"errcode": -1, "errmsg": str(e)}
    
    def send_link(self, title, text, message_url, pic_url=None):
        """
        Send link message to DingTalk
        
        Args:
            title: Message title
            text: Message text
            message_url: Link URL
            pic_url: Picture URL (optional)
        
        Returns:
            Response data from DingTalk
        """
        if not self.webhook_url:
            logger.error("DingTalk webhook URL is not configured")
            return {"errcode": -1, "errmsg": "Webhook URL not configured"}
        
        url = self.webhook_url
        
        # Add signature if secret is configured
        if self.secret:
            timestamp, sign = self._generate_sign()
            url = f"{url}&timestamp={timestamp}&sign={sign}"
        
        message = {
            "msgtype": "link",
            "link": {
                "title": title,
                "text": text,
                "messageUrl": message_url
            }
        }
        
        if pic_url:
            message["link"]["picUrl"] = pic_url
        
        try:
            conn = http_req(url, method='post', json=message)
            response = conn.json()
            
            if response.get("errcode", -1) == 0:
                logger.info("DingTalk link message sent successfully")
            else:
                logger.warning(f"DingTalk send failed: {response}")
            
            return response
            
        except Exception as e:
            logger.exception(f"Error sending DingTalk message: {e}")
            return {"errcode": -1, "errmsg": str(e)}


def send_github_event_notification(repo_owner, repo_name, events, webhook_url=None, secret=None):
    """
    Send GitHub event notification to DingTalk
    
    Args:
        repo_owner: GitHub repository owner
        repo_name: GitHub repository name
        events: List of GithubRepoEvent objects
        webhook_url: DingTalk webhook URL (optional)
        secret: DingTalk webhook secret (optional)
    
    Returns:
        Response from DingTalk
    """
    from app.services.github_repo_monitor import format_events_for_dingtalk
    
    dingtalk = DingTalkWebhook(webhook_url, secret)
    
    title = f"GitHub 监控 - {repo_owner}/{repo_name}"
    content = format_events_for_dingtalk(repo_owner, repo_name, events)
    
    return dingtalk.send_markdown(title, content)


def send_dingtalk_notification(title, content, msgtype="markdown", webhook_url=None, secret=None):
    """
    Send notification to DingTalk
    
    Args:
        title: Message title
        content: Message content
        msgtype: Message type ('text' or 'markdown')
        webhook_url: DingTalk webhook URL (optional)
        secret: DingTalk webhook secret (optional)
    
    Returns:
        Response from DingTalk
    """
    dingtalk = DingTalkWebhook(webhook_url, secret)
    
    if msgtype == "text":
        return dingtalk.send_text(content)
    else:
        return dingtalk.send_markdown(title, content)
