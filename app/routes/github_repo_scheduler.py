import time
from bson import ObjectId
from flask_restx import fields, Namespace
from app.utils import get_logger, auth
from app import utils
from app.utils.github_repo_task import (
    find_github_repo_scheduler, 
    delete_github_repo_scheduler,
    recover_github_repo_task,
    stop_github_repo_task
)
from . import base_query_fields, ARLResource, get_arl_parser
from app.modules import SchedulerStatus, ErrorMsg

ns = Namespace('github_repo_scheduler', description="GitHub 仓库监控调度")

logger = get_logger()

base_search_fields = {
    'name': fields.String(required=False, description="任务名"),
    'repo_owner': fields.String(description="仓库所有者"),
    'repo_name': fields.String(description="仓库名称"),
    'status': fields.String(description="状态")
}

base_search_fields.update(base_query_fields)


add_github_repo_scheduler_fields = ns.model('AddGithubRepoScheduler', {
    'name': fields.String(required=True, description="任务名"),
    'repo_owner': fields.String(required=True, description="GitHub 仓库所有者"),
    'repo_name': fields.String(required=True, description="GitHub 仓库名称"),
    'cron': fields.String(required=True, description="Cron 表达式"),
    'monitored_events': fields.List(fields.String, description="监控的事件类型列表", required=False)
})


@ns.route('/')
class ARLGithubRepoScheduler(ARLResource):
    parser = get_arl_parser(base_search_fields, location='args')

    @auth
    @ns.expect(parser)
    def get(self):
        """
        GitHub 仓库监控任务信息查询
        """
        args = self.parser.parse_args()
        data = self.build_data(args=args, collection='github_repo_scheduler')
        return data

    @auth
    @ns.expect(add_github_repo_scheduler_fields)
    def post(self):
        """
        添加 GitHub 仓库监控任务
        """
        args = self.parse_args(add_github_repo_scheduler_fields)
        name = args.pop('name')
        repo_owner = args.pop('repo_owner').strip()
        repo_name = args.pop('repo_name').strip()
        cron = args.pop('cron')
        monitored_events = args.pop('monitored_events', None)

        if not repo_owner or not repo_name:
            return utils.build_ret(ErrorMsg.Error, {"message": "仓库所有者和仓库名称不能为空"})

        # Validate cron expression
        check_flag, msg = utils.check_cron_interval(cron)
        if not check_flag:
            return msg

        previous, next_sec, _ = utils.check_cron(cron)

        scheduler_data = {
            "name": name,
            "repo_owner": repo_owner,
            "repo_name": repo_name,
            "cron": cron,
            "monitored_events": monitored_events or ['PushEvent', 'IssuesEvent', 'PullRequestEvent'],
            "run_number": 0,
            "last_run_date": "-",
            "last_run_time": 0,
            "next_run_date": utils.time2date(time.time() + next_sec),
            "status": SchedulerStatus.RUNNING
        }

        utils.conn_db('github_repo_scheduler').insert_one(scheduler_data)
        scheduler_data["_id"] = str(scheduler_data["_id"])

        return utils.build_ret(ErrorMsg.Success, data=scheduler_data)


delete_github_repo_scheduler_fields = ns.model('DeleteGithubRepoScheduler', {
    "_id": fields.List(fields.String(description="GitHub 仓库监控任务ID列表"))
})


@ns.route('/delete/')
class DeleteGithubRepoScheduler(ARLResource):

    @auth
    @ns.expect(delete_github_repo_scheduler_fields)
    def post(self):
        """
        删除 GitHub 仓库监控任务
        """
        args = self.parse_args(delete_github_repo_scheduler_fields)
        job_id_list = args.get("_id", [])

        ret_data = {"_id": job_id_list}

        for job_id in job_id_list:
            item = find_github_repo_scheduler(job_id)
            if not item:
                return utils.build_ret(ErrorMsg.JobNotFound, ret_data)

        for job_id in job_id_list:
            delete_github_repo_scheduler(job_id)

        return utils.build_ret(ErrorMsg.Success, ret_data)


update_github_repo_scheduler_fields = ns.model('UpdateGithubRepoScheduler', {
    "_id": fields.String(required=True, description="GitHub 仓库监控任务ID"),
    'name': fields.String(required=False, description="任务名"),
    'repo_owner': fields.String(required=False, description="仓库所有者"),
    'repo_name': fields.String(required=False, description="仓库名称"),
    "cron": fields.String(required=False, description="Cron 表达式"),
    'monitored_events': fields.List(fields.String, description="监控的事件类型列表", required=False)
})


@ns.route('/update/')
class UpdateGithubRepoScheduler(ARLResource):

    @auth
    @ns.expect(update_github_repo_scheduler_fields)
    def post(self):
        """
        修改 GitHub 仓库监控任务
        """
        args = self.parse_args(update_github_repo_scheduler_fields)
        job_id = args.get("_id")
        name = args.pop('name')
        repo_owner = args.pop('repo_owner')
        repo_name = args.pop('repo_name')
        cron = args.pop('cron')
        monitored_events = args.pop('monitored_events')

        item = find_github_repo_scheduler(job_id)
        if not item:
            return utils.build_ret(ErrorMsg.JobNotFound, {"_id": job_id})

        if name:
            item["name"] = name

        if repo_owner:
            item["repo_owner"] = repo_owner.strip()

        if repo_name:
            item["repo_name"] = repo_name.strip()
        
        if monitored_events:
            item["monitored_events"] = monitored_events

        if cron:
            check_flag, msg = utils.check_cron_interval(cron)
            if not check_flag:
                return msg

            previous, next_sec, _ = utils.check_cron(cron)
            item["next_run_date"] = utils.time2date(time.time() + next_sec)
            item["cron"] = cron

        query = {"_id": ObjectId(job_id)}
        utils.conn_db('github_repo_scheduler').find_one_and_replace(query, item)

        item["_id"] = str(item["_id"])

        return utils.build_ret(ErrorMsg.Success, data=item)


recover_github_repo_scheduler_fields = ns.model('RecoverGithubRepoScheduler', {
    "_id": fields.List(fields.String(required=True, description="GitHub 仓库监控任务ID"))
})


@ns.route('/recover/')
class RecoverGithubRepoScheduler(ARLResource):

    @auth
    @ns.expect(recover_github_repo_scheduler_fields)
    def post(self):
        """
        恢复 GitHub 仓库监控周期任务
        """
        args = self.parse_args(recover_github_repo_scheduler_fields)
        job_id_list = args.get("_id")

        for job_id in job_id_list:
            item = find_github_repo_scheduler(job_id)
            if not item:
                return utils.build_ret(ErrorMsg.JobNotFound, {"_id": job_id})

            status = item.get("status", SchedulerStatus.RUNNING)
            if status != SchedulerStatus.STOP:
                return utils.build_ret(ErrorMsg.SchedulerStatusNotStop, {"_id": job_id})

            recover_github_repo_task(_id=job_id)

        return utils.build_ret(ErrorMsg.Success, {"job_id_list": job_id_list})


stop_github_repo_scheduler_fields = ns.model('StopGithubRepoScheduler', {
    "_id": fields.List(fields.String(required=True, description="GitHub 仓库监控任务ID"))
})


@ns.route('/stop/')
class StopGithubRepoScheduler(ARLResource):

    @auth
    @ns.expect(stop_github_repo_scheduler_fields)
    def post(self):
        """
        停止 GitHub 仓库监控周期任务
        """
        args = self.parse_args(stop_github_repo_scheduler_fields)
        job_id_list = args.get("_id")

        for job_id in job_id_list:
            item = find_github_repo_scheduler(job_id)
            if not item:
                return utils.build_ret(ErrorMsg.JobNotFound, {"_id": job_id})

            status = item.get("status", SchedulerStatus.RUNNING)
            if status != SchedulerStatus.RUNNING:
                return utils.build_ret(ErrorMsg.SchedulerStatusNotRunning, {"_id": job_id})

            stop_github_repo_task(_id=job_id)

        return utils.build_ret(ErrorMsg.Success, {"job_id_list": job_id_list})
