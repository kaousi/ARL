import time
from crontab import CronTab
from bson import ObjectId
from app.modules import CeleryAction, SchedulerStatus, TaskStatus
from app import celerytask, utils

logger = utils.get_logger()


def submit_github_repo_task(task_data, delay_flag=True):
    """
    Submit GitHub repository monitoring task
    
    Args:
        task_data: Task data containing repo_owner, repo_name, etc.
        delay_flag: Whether to delay task execution
    
    Returns:
        Task data with task_id and celery_id
    """
    collection = "github_repo_task"
    task_options = {
        "celery_action": CeleryAction.GITHUB_REPO_MONITOR,
        "data": task_data
    }
    
    repo_name = f"{task_data['repo_owner']}/{task_data['repo_name']}"
    task_data["celery_id"] = ""
    utils.conn_db(collection).insert_one(task_data)
    task_id = str(task_data.pop("_id"))
    task_data["task_id"] = task_id
    
    try:
        if delay_flag:
            celery_id = celerytask.arl_github.delay(options=task_options)
        else:
            celery_id = "fake_celery_id"
            celerytask.arl_github(options=task_options)
        
        logger.info(f"GitHub repo monitor task: {repo_name} task_id:{task_id} celery_id:{celery_id}")
        values = {"$set": {"celery_id": str(celery_id)}}
        task_data["celery_id"] = str(celery_id)
        utils.conn_db(collection).update_one({"_id": ObjectId(task_id)}, values)
        
    except Exception as e:
        utils.conn_db(collection).delete_one({"_id": ObjectId(task_id)})
        logger.error(f"GitHub repo task submission failed for {repo_name}: {e}")
        return str(e)
    
    return task_data


def github_repo_cron_run(item):
    """
    Execute a scheduled GitHub repository monitoring task
    
    Args:
        item: Scheduler item from github_repo_scheduler collection
    """
    task_data = {
        "name": f"GitHub仓库监控-{item['name']}",
        "repo_owner": item["repo_owner"],
        "repo_name": item["repo_name"],
        "start_time": "-",
        "end_time": "-",
        "github_repo_scheduler_id": str(item["_id"]),
        "status": TaskStatus.WAITING,
    }
    
    # Submit scheduled monitoring task
    submit_github_repo_task(task_data=task_data)
    
    # Update scheduler
    item["run_number"] = item["run_number"] + 1
    item["last_run_date"] = utils.curr_date()
    item["last_run_time"] = int(time.time())
    entry = CronTab(item["cron"])
    now_time = time.time() + 61
    next_sec = entry.next(now=now_time, default_utc=False)
    item["next_run_date"] = utils.time2date(now_time + next_sec - 60)
    
    query = {"_id": item["_id"]}
    utils.conn_db('github_repo_scheduler').find_one_and_replace(query, item)


def github_repo_scheduler():
    """
    GitHub repository monitoring task scheduler
    Called periodically to check and execute scheduled tasks
    """
    items = list(utils.conn_db('github_repo_scheduler').find())
    for item in items:
        try:
            if item["status"] != SchedulerStatus.RUNNING:
                continue
            
            entry = CronTab(item["cron"])
            next_sec = entry.next(default_utc=False)
            
            # Check if it's time to run (within next 60 seconds and hasn't run in last 3 minutes)
            if next_sec < 60 and abs(time.time() - item["last_run_time"]) > 60*3:
                repo_name = f"{item['repo_owner']}/{item['repo_name']}"
                logger.info(f"GitHub repo cron run: {repo_name} scheduler_id:{item['_id']}")
                github_repo_cron_run(item)
                
        except Exception as e:
            logger.exception(f"Error in GitHub repo scheduler: {e}")


def find_github_repo_scheduler(_id):
    """Find GitHub repository scheduler by ID"""
    query = {"_id": ObjectId(_id)}
    item = utils.conn_db('github_repo_scheduler').find_one(query)
    return item


def delete_github_repo_scheduler(_id):
    """
    Delete GitHub repository scheduler and all related data
    
    Args:
        _id: Scheduler ID (24-character hex string)
    """
    if len(_id) != 24:
        return
    
    query = {"_id": ObjectId(_id)}
    utils.conn_db('github_repo_scheduler').delete_one(query)
    
    result_query = {"github_repo_scheduler_id": _id}
    
    # Delete GitHub repository events
    utils.conn_db('github_repo_event').delete_many(result_query)
    
    # Delete GitHub repository tasks
    utils.conn_db('github_repo_task').delete_many(result_query)


def recover_github_repo_task(_id):
    """
    Recover (resume) a stopped GitHub repository scheduler
    
    Args:
        _id: Scheduler ID
    """
    if len(_id) != 24:
        return
    
    item = find_github_repo_scheduler(_id)
    if not item:
        return
    
    item["status"] = SchedulerStatus.RUNNING
    entry = CronTab(item["cron"])
    next_sec = entry.next(default_utc=False)
    item["next_run_date"] = utils.time2date(time.time() + next_sec)
    
    query = {"_id": ObjectId(_id)}
    utils.conn_db('github_repo_scheduler').find_one_and_replace(query, item)


def stop_github_repo_task(_id):
    """
    Stop a running GitHub repository scheduler
    
    Args:
        _id: Scheduler ID
    """
    if len(_id) != 24:
        return
    
    item = find_github_repo_scheduler(_id)
    if not item:
        return
    
    item["status"] = SchedulerStatus.STOP
    item["next_run_date"] = "-"
    
    query = {"_id": ObjectId(_id)}
    utils.conn_db('github_repo_scheduler').find_one_and_replace(query, item)
