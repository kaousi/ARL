from bson import ObjectId
from app.services import github_search
from app.services.githubSearch import GithubResult
from app.services.github_repo_monitor import monitor_github_repo
from app.services.dingtalk_webhook import send_github_event_notification
from app.modules import TaskStatus
from app import utils
from app.config import Config
from app.utils import push
from datetime import datetime, timedelta

logger = utils.get_logger()


class GithubTaskTask(object):
    def __init__(self, task_id, keyword):
        self.task_id = task_id
        self.keyword = keyword
        self.collection = "github_task"
        self.results = []

    def search_result(self):
        self.update_status("search")
        results = github_search(keyword=self.keyword)
        self.results.extend(results)

    def save_content(self):
        self.update_status("fetch content-{}".format(len(self.results)))
        for result in self.results:
            if not isinstance(result, GithubResult):
                continue

            if self.filter_result(result):
                continue

            item = self.result_to_dict(result)

            utils.conn_db("github_result").insert_one(item)

    def result_to_dict(self, result):
        item = result.to_dict()
        item["human_content"] = result.human_content(self.keyword)
        item["keyword"] = self.keyword
        item["github_task_id"] = self.task_id
        return item

    def filter_result(self, result: GithubResult):
        path_keyword_list = ["open-app-filter/", "/adbyby",
                             "/adblock", "luci-app-dnsfilter/",
                             "Spider/", "/spider", "_files/",
                             "alexa_10k.json", "/WeWorkProviderTest.php"]
        for path in path_keyword_list:
            if path in result.path:
                return True

        content_keyword_list = ["DOMAIN-SUFFIX", "HOST-SUFFIX", "name:[proto;sport;dport;host",
                                '  "websites": [',
                                "import android.app.Application;",
                                "import android.app.Activity;"]
        for keyword in content_keyword_list:
            if keyword in result.content:
                return True

        return False

    def update_status(self, value):
        query = {"_id": ObjectId(self.task_id)}
        update = {"$set": {"status": value}}
        utils.conn_db(self.collection).update_one(query, update)

    def set_start_time(self):
        query = {"_id": ObjectId(self.task_id)}
        update = {"$set": {"start_time": utils.curr_date()}}
        utils.conn_db(self.collection).update_one(query, update)

    def set_end_time(self):
        query = {"_id": ObjectId(self.task_id)}
        update = {"$set": {"end_time": utils.curr_date()}}
        utils.conn_db(self.collection).update_one(query, update)

    def statistic(self):
        query = {"_id": ObjectId(self.task_id)}
        table_list = ['github_result']
        result = {}
        for table in table_list:
            cnt = utils.conn_db(table).count_documents({"github_task_id": self.task_id})
            stat_key = table + "_cnt"
            result[stat_key] = cnt

        logger.info("insert task stat")
        update = {"$set": {"statistic": result}}
        utils.conn_db(self.collection).update_one(query, update)

    def run(self):
        self.set_start_time()

        self.search_result()
        self.save_content()

        self.update_status(TaskStatus.DONE)
        self.statistic()
        self.set_end_time()


class GithubTaskMonitor(GithubTaskTask):
    def __init__(self, task_id, keyword, scheduler_id):
        super().__init__(task_id, keyword)
        self.scheduler_id = scheduler_id
        self.hash_md5_list = []
        self.new_results = []  # 保存过滤后的结果

    def init_md5_list(self):
        query = {"github_scheduler_id": self.scheduler_id}
        results = list(utils.conn_db("github_hash").find(query, {"hash_md5": 1}))
        for result in results:
            if result["hash_md5"] not in self.hash_md5_list:
                self.hash_md5_list.append(result["hash_md5"])

    def save_mongo(self):
        cnt = 0
        self.update_status("fetch content")
        for result in self.results:
            if not isinstance(result, GithubResult):
                continue

            if result.hash_md5 in self.hash_md5_list:
                continue

            # 保存md5, 直接在过滤前，避免重复过滤
            self.hash_md5_list.append(result.hash_md5)
            hash_data = {"hash_md5": result.hash_md5, "github_scheduler_id": self.scheduler_id}
            utils.conn_db("github_hash").insert_one(hash_data)

            if self.filter_result(result):
                continue

            item = self.result_to_dict(result)
            item["github_scheduler_id"] = self.scheduler_id
            item["update_date"] = utils.curr_date_obj()
            cnt += 1
            self.new_results.append(result)
            utils.conn_db("github_monitor_result").insert_one(item)

        logger.info("github_monitor save {} {}".format(self.keyword, cnt))

    def build_repo_map(self):
        repo_map = dict()
        for result in self.new_results:
            repo_name = result.repo_full_name
            if repo_map.get(repo_name) is None:
                repo_map[repo_name] = [result]
            else:
                repo_map[repo_name].append(result)

        return repo_map

    def build_html_report(self):
        repo_map = self.build_repo_map()
        repo_cnt = 0
        html = "<br/><br/> <div> 搜索: {}  仓库数：{}  结果数： {} </div>".format(self.keyword,
                                                                        len(repo_map.keys()), len(self.new_results))
        for repo_name in repo_map:
            repo_cnt += 1
            # 为了较少长度，超过 5 个仓库就跳过
            if repo_cnt > 5:
                break

            start_div = '<br/><br/><br/><div>#{} <a href="https://github.com/{}"> {} </a> 结果数：{}</div><br/>\n'.format(
                repo_cnt, repo_name, repo_name, len(repo_map[repo_name]))
            table_start = '''<table style="border-collapse: collapse;">
            <thead>
                <tr>
                    <th style="border: 0.5pt solid; padding:14px;">编号</th>
                    <th style="border: 0.5pt solid; padding:14px;">文件名</th>
                    <th style="border: 0.5pt solid; padding:14px;">代码</th>
                    <th style="border: 0.5pt solid; padding:14px;">Commit 时间</th>
                </tr>
            </thead>
            <tbody>\n'''
            html += start_div
            html += table_start

            style = 'style="border: 0.5pt solid; font-size: 14px; padding:14px"'
            tr_cnt = 0
            for item in repo_map[repo_name]:
                tr_cnt += 1
                code_content = item.human_content(self.keyword).replace('>', "&#x3e;").replace('<', "&#x3c;")
                code_content = code_content[:2000]
                tr_tag = '<tr>' \
                         '<td {}> {} </td>' \
                         '<td {}> <div style="width: 300px"> <a href="{}"> {} </a> </div> </td>' \
                         '<td {}> <pre style="max-width: 600px; overflow: auto; max-height: 600px;">{}</pre></td>' \
                         '<td {}> {} </td>' \
                         '</tr>\n'.format(
                    style, tr_cnt, style, item.html_url, item.path,
                    style, code_content,
                    style, item.commit_date)

                html += tr_tag
                if tr_cnt > 10:
                    break

            table_end = '</tbody></table>'
            end_div = "</div>"

            html += table_end
            html += end_div

        return html

    def build_markdown_report(self):
        repo_map = self.build_repo_map()

        markdown = "[监控-Github-{}] \n 仓库数:{}  结果数:{} \n --- \n".format(self.keyword,
                                                                        len(repo_map.keys()), len(self.new_results))

        global_cnt = 0
        repo_cnt = 0
        for repo_name in repo_map:
            repo_cnt += 1
            # 为了较少长度，超过 5 个参考就跳过
            if repo_cnt > 5:
                break

            tr_cnt = 0
            for item in repo_map[repo_name]:
                tr_cnt += 1
                global_cnt += 1
                url_text = item.repo_full_name + " " + item.path
                markdown += "{}. [{}]({})  \n".format(global_cnt, url_text, item.html_url)
                if tr_cnt > 5:
                    break

        return markdown

    # 消息推送
    def push_msg(self):
        if not self.new_results:
            return

        logger.info("found new result {} {}".format(self.keyword, len(self.new_results)))

        self.push_dingding()
        self.push_email()

    def push_dingding(self):
        try:
            if Config.DINGDING_ACCESS_TOKEN and Config.DINGDING_SECRET:
                data = push.dingding_send(access_token=Config.DINGDING_ACCESS_TOKEN,
                                      secret=Config.DINGDING_SECRET, msgtype="markdown",
                                      msg=self.build_markdown_report())
                if data.get("errcode", -1) == 0:
                    logger.info("push dingding succ")
                return True

        except Exception as e:
            logger.warning(self.keyword, e)

    def push_email(self):
        try:
            if Config.EMAIL_HOST and Config.EMAIL_USERNAME and Config.EMAIL_PASSWORD:
                html_report = self.build_html_report()
                push.send_email(host=Config.EMAIL_HOST, port=Config.EMAIL_PORT, mail=Config.EMAIL_USERNAME,
                                password=Config.EMAIL_PASSWORD, to=Config.EMAIL_TO,
                                title="[Github--{}] 灯塔消息推送".format(self.keyword), html=html_report)
                logger.info("send email succ")
                return True
        except Exception as e:
            logger.warning(self.keyword, e)

    def run(self):
        self.set_start_time()

        # 初始化MD5
        self.init_md5_list()

        # 根据关键字搜索出结果
        self.search_result()

        # 保存到监控结果
        self.save_mongo()

        # 保存到任务结果
        self.results = self.new_results
        self.save_content()

        self.push_msg()

        # 保存统计结果
        self.statistic()
        self.update_status(TaskStatus.DONE)
        self.set_end_time()


# Github 普通任务
def github_task_task(task_id, keyword):
    task = GithubTaskTask(task_id=task_id, keyword=keyword)
    try:
        if not Config.GITHUB_TOKEN:
            logger.error("GITHUB_TOKEN is empty")
            task.update_status(TaskStatus.ERROR)
            task.set_end_time()
            return

        task.run()
    except Exception as e:
        logger.exception(e)

        task.update_status(TaskStatus.ERROR)
        task.set_end_time()


# Github 监控任务
def github_task_monitor(task_id, keyword, scheduler_id):
    task = GithubTaskMonitor(task_id=task_id,
                             keyword=keyword, scheduler_id=scheduler_id)
    try:
        task.run()
    except Exception as e:
        logger.exception(e)

        task.update_status(TaskStatus.ERROR)
        task.set_end_time()


class GithubRepoMonitorTask(object):
    """GitHub repository monitoring task"""
    
    def __init__(self, task_id, repo_owner, repo_name, scheduler_id):
        self.task_id = task_id
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.scheduler_id = scheduler_id
        self.collection = "github_repo_task"
        self.events = []
    
    def update_status(self, value):
        query = {"_id": ObjectId(self.task_id)}
        update = {"$set": {"status": value}}
        utils.conn_db(self.collection).update_one(query, update)
    
    def set_start_time(self):
        query = {"_id": ObjectId(self.task_id)}
        update = {"$set": {"start_time": utils.curr_date()}}
        utils.conn_db(self.collection).update_one(query, update)
    
    def set_end_time(self):
        query = {"_id": ObjectId(self.task_id)}
        update = {"$set": {"end_time": utils.curr_date()}}
        utils.conn_db(self.collection).update_one(query, update)
    
    def get_last_check_time(self):
        """Get the last check time from previous task run"""
        query = {
            "github_repo_scheduler_id": self.scheduler_id,
            "status": TaskStatus.DONE
        }
        last_task = utils.conn_db(self.collection).find_one(
            query, 
            sort=[("end_time", -1)]
        )
        if last_task and last_task.get("end_time"):
            # Check events from last task end time
            try:
                last_time = utils.parse_datetime(last_task["end_time"])
                return last_time
            except:
                pass
        
        # Default to 1 hour ago
        return datetime.now() - timedelta(hours=1)
    
    def fetch_events(self):
        """Fetch GitHub repository events"""
        self.update_status("fetching events")
        
        try:
            last_check_time = self.get_last_check_time()
            logger.info(f"Checking GitHub events for {self.repo_owner}/{self.repo_name} since {last_check_time}")
            
            self.events = monitor_github_repo(
                self.repo_owner, 
                self.repo_name, 
                since_time=last_check_time
            )
            
            logger.info(f"Found {len(self.events)} new events for {self.repo_owner}/{self.repo_name}")
        except Exception as e:
            logger.exception(f"Error fetching events: {e}")
    
    def save_events(self):
        """Save events to database"""
        self.update_status(f"saving {len(self.events)} events")
        
        for event in self.events:
            event_data = event.to_dict()
            event_data["github_repo_scheduler_id"] = self.scheduler_id
            event_data["github_repo_task_id"] = self.task_id
            event_data["saved_at"] = utils.curr_date_obj()
            
            # Check if event already exists
            existing = utils.conn_db("github_repo_event").find_one({
                "event_id": event.event_id,
                "github_repo_scheduler_id": self.scheduler_id
            })
            
            if not existing:
                utils.conn_db("github_repo_event").insert_one(event_data)
    
    def send_notification(self):
        """Send DingTalk notification for new events"""
        if not self.events:
            logger.info("No new events to notify")
            return
        
        try:
            logger.info(f"Sending DingTalk notification for {len(self.events)} events")
            
            # Use configured webhook URL and secret
            webhook_url = Config.DINGTALK_WEBHOOK_URL
            secret = Config.DINGDING_SECRET
            
            if not webhook_url:
                logger.warning("DingTalk webhook URL not configured, skipping notification")
                return
            
            response = send_github_event_notification(
                self.repo_owner,
                self.repo_name,
                self.events,
                webhook_url=webhook_url,
                secret=secret
            )
            
            if response.get("errcode", -1) == 0:
                logger.info("DingTalk notification sent successfully")
            else:
                logger.warning(f"DingTalk notification failed: {response}")
                
        except Exception as e:
            logger.exception(f"Error sending notification: {e}")
    
    def statistic(self):
        """Update task statistics"""
        query = {"_id": ObjectId(self.task_id)}
        result = {
            "event_count": len(self.events)
        }
        update = {"$set": {"statistic": result}}
        utils.conn_db(self.collection).update_one(query, update)
    
    def run(self):
        """Run the monitoring task"""
        self.set_start_time()
        
        try:
            # Fetch events from GitHub
            self.fetch_events()
            
            # Save events to database
            self.save_events()
            
            # Send DingTalk notification
            self.send_notification()
            
            # Update statistics
            self.statistic()
            
            self.update_status(TaskStatus.DONE)
            
        except Exception as e:
            logger.exception(f"Error in GitHub repo monitor task: {e}")
            self.update_status(TaskStatus.ERROR)
        
        finally:
            self.set_end_time()


# GitHub repository monitoring task
def github_repo_monitor_task(task_id, repo_owner, repo_name, scheduler_id):
    """Execute GitHub repository monitoring task"""
    task = GithubRepoMonitorTask(
        task_id=task_id,
        repo_owner=repo_owner,
        repo_name=repo_name,
        scheduler_id=scheduler_id
    )
    
    try:
        if not Config.GITHUB_TOKEN:
            logger.error("GITHUB_TOKEN is not configured")
            task.update_status(TaskStatus.ERROR)
            task.set_end_time()
            return
        
        task.run()
        
    except Exception as e:
        logger.exception(e)
        task.update_status(TaskStatus.ERROR)
        task.set_end_time()
